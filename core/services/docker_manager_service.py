import logging
from datetime import timedelta
import docker
from django.utils import timezone
from django.conf import settings
from core.models import Team, Challenge, ActiveInstance
from core.constants import (
    INSTANCE_LIFESPAN_MINUTES,
    DOCKER_MEM_LIMIT,
    DOCKER_MEMSWAP_LIMIT,
    DOCKER_NANO_CPUS,
    DOCKER_RESTART_POLICY,
    DEFAULT_TRAEFIK_NETWORK,
)

logger = logging.getLogger(__name__)

# Initialize Docker client
# Connects via /var/run/docker.sock mounted in the container
try:
    client = docker.from_env()
except Exception as e:
    logger.error(f"Failed to initialize Docker client: {e}")
    client = None


class DockerManagerService:
    """
    Service responsible for orchestrating independent, isolated container challenges
    for teams using the Sibling Container trick via the host's Docker daemon.
    """

    # docker-compose generates network names based on the directory name by default.
    NETWORK_NAME = getattr(settings, "TRAEFIK_NETWORK_NAME", DEFAULT_TRAEFIK_NETWORK)

    @classmethod
    def spawn_instance(cls, team: Team, challenge: Challenge) -> ActiveInstance:
        """
        Dynamically spins up a Docker container for a specific team and challenge,
        and configures Traefik labels so traffic is routed to this new container immediately.
        """
        if client is None:
            raise RuntimeError("Docker client is not initialized.")

        # 1. Safety Check: Does the team already have an active instance for this challenge?
        existing_instance = ActiveInstance.objects.filter(
            team=team, challenge=challenge
        ).first()
        if existing_instance:
            logger.info(
                f"Team {team.name} already has an active instance for challenge {challenge.title}."
            )
            return existing_instance

        if not challenge.docker_image_tag:
            raise ValueError(
                f"Challenge '{challenge.title}' does not have a docker_image_tag set."
            )

        # 2. Compute routing identifiers
        subdomain = f"team{team.id}-chall{challenge.id}.{settings.CTF_HOST_IP}.nip.io"
        # We need a unique container name to avoid collisions on the Docker host daemon
        container_name = f"ctf_team{team.id}_chall{challenge.id}"

        # 2b. Ghost Container Remediation
        # Scenario: Celery cleaned the ActiveInstance DB record (step 1 passed) but the
        # docker stop/remove call failed silently, leaving a zombie container on the
        # daemon. A subsequent containers.run(name=container_name) would throw a 409
        # Conflict and fail with no automatic recovery. We pre-emptively check for and
        # purge any container that shares our deterministic name before spawning fresh.
        try:
            ghost = client.containers.get(container_name)
            logger.warning(
                f"Ghost container '{container_name}' found on daemon (status: {ghost.status}). "
                f"Purging before fresh spawn."
            )
            ghost.remove(force=True)
            logger.info(f"Ghost container '{container_name}' removed.")
        except docker.errors.NotFound:
            pass  # Clean state — no ghost present, proceed normally.
        except docker.errors.APIError as e:
            # Non-fatal: log and attempt spawn anyway; Docker will surface the real error.
            logger.error(f"Could not remove ghost container '{container_name}': {e}")

        # 3. Traefik Routing Labels
        # Traefik uses these to dynamically bind the subdomain to the container's exposed port
        labels = {
            "traefik.enable": "true",
            f"traefik.http.routers.{container_name}.rule": f"Host(`{subdomain}`)",
            f"traefik.http.routers.{container_name}.entrypoints": "web",
            f"traefik.http.services.{container_name}.loadbalancer.server.port": str(challenge.internal_port),
        }

        # 4. Build environment variables from ChallengeTemplate (CTF Builder Engine)
        env_vars = {}
        if challenge.template:
            # Start with template defaults
            for tvar in challenge.template.variables.all():
                if tvar.default_value:
                    env_vars[tvar.key_name] = tvar.default_value
            # Override with instructor's custom_parameters
            if challenge.custom_parameters:
                env_vars.update(challenge.custom_parameters)
            logger.info(
                f"Injecting {len(env_vars)} env variables from template '{challenge.template.name}'"
            )

        # 5. Spin up the container with security limits
        logger.info(
            f"Starting container {container_name} from image {challenge.docker_image_tag}..."
        )
        try:
            container = client.containers.run(
                image=challenge.docker_image_tag,
                name=container_name,
                detach=True,
                network=cls.NETWORK_NAME,
                labels=labels,
                environment=env_vars if env_vars else None,
                mem_limit=DOCKER_MEM_LIMIT,
                memswap_limit=DOCKER_MEMSWAP_LIMIT,
                nano_cpus=DOCKER_NANO_CPUS,
                restart_policy=DOCKER_RESTART_POLICY,
            )
        except docker.errors.APIError as e:
            logger.error(f"Docker API Error failed to start container {container_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to start container {container_name}: {e}")
            raise

        # 6. Calculate expiration and record in Database
        expires_at = timezone.now() + timedelta(minutes=INSTANCE_LIFESPAN_MINUTES)

        active_instance = ActiveInstance.objects.create(
            team=team,
            challenge=challenge,
            container_id=container.id,
            traefik_subdomain=subdomain,
            expires_at=expires_at,
        )

        logger.info(f"Successfully started container {container_name} at {subdomain}.")
        return active_instance

    @classmethod
    def kill_instance(cls, active_instance: ActiveInstance):
        """
        Stops and removes the container dynamically, and cleans up the ActiveInstance record.
        Intended to be called by Celery Beat or when a Team solves/forfeits the challenge.
        """
        if client is None:
            raise RuntimeError("Docker client is not initialized.")

        container_id = active_instance.container_id

        try:
            container = client.containers.get(container_id)
            logger.info(
                f"Stopping container {container_id} (Subdomain: {active_instance.traefik_subdomain})..."
            )
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            # Container was already deleted externally (e.g., manual cleanup)
            logger.warning(
                f"Container {container_id} not found on Docker daemon. Proceeding to clean DB record."
            )
        except docker.errors.APIError as e:
            logger.error(f"Docker API Error stopping container {container_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error stopping container {container_id}: {e}")
            raise

        # Remove the tracking record from the database
        active_instance.delete()
        logger.info(f"Cleaned up ActiveInstance record for container {container_id}.")

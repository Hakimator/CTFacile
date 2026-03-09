import logging
from datetime import timedelta
import docker
from django.utils import timezone
from django.conf import settings
from core.models import Team, Challenge, ActiveInstance
from core.constants import INSTANCE_LIFESPAN_MINUTES

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
    NETWORK_NAME = getattr(settings, "TRAEFIK_NETWORK_NAME", "ctfacile_traefik_public")

    @classmethod
    def start_challenge_instance(
        cls, team: Team, challenge: Challenge
    ) -> ActiveInstance:
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
        subdomain = f"team-{team.id}-chall-{challenge.id}.ctfacile.local"
        # We need a unique container name to avoid collisions on the Docker host daemon
        container_name = f"ctf_team{team.id}_chall{challenge.id}"

        # 3. Traefik Routing Labels
        # Traefik uses these to dynamically bind the subdomain to the container's exposed port 80
        labels = {
            "traefik.enable": "true",
            f"traefik.http.routers.{container_name}.rule": f"Host(`{subdomain}`)",
            f"traefik.http.routers.{container_name}.entrypoints": "web",
            f"traefik.http.services.{container_name}.loadbalancer.server.port": "80",
        }

        # 4. Spin up the container with security limits
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
                mem_limit="256m",
                memswap_limit="256m",
                nano_cpus=500000000,
                restart_policy={"Name": "no"},
            )
        except Exception as e:
            logger.error(f"Failed to start container {container_name}: {e}")
            raise

        # 5. Calculate expiration and record in Database
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
    def stop_challenge_instance(cls, active_instance: ActiveInstance):
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
        except Exception as e:
            logger.error(f"Error stopping container {container_id}: {e}")
            raise

        # Remove the tracking record from the database
        active_instance.delete()
        logger.info(f"Cleaned up ActiveInstance record for container {container_id}.")

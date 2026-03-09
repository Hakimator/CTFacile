import logging
from celery import shared_task
from django.utils import timezone
from core.models import ActiveInstance
from core.services.docker_manager_service import DockerManagerService

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_containers():
    """
    Periodic task designed to be run by Celery Beat every X minutes.
    Queries the database for ActiveInstances whose expires_at time has passed,
    and uses the DockerManagerService to forcefully tear them down.
    """
    logger.info("Initiating cleanup of expired containers...")

    # Find all containers that have outlived their lifespan
    expired_instances = ActiveInstance.objects.filter(expires_at__lte=timezone.now())
    total_found = expired_instances.count()

    if total_found == 0:
        logger.info("No expired containers found. Sweeper routine complete.")
        return 0

    logger.info(f"Found {total_found} expired containers. Beginning teardown protocol.")

    death_toll = 0
    for instance in expired_instances:
        try:
            # Tell DockerManager to kill and delete the record
            DockerManagerService.stop_challenge_instance(instance)
            death_toll += 1
        except Exception as e:
            # CRITICAL: We catch all exceptions here so a single rogue container
            # failing to shut down doesn't crash the entire sweeper routine,
            # leaving other containers running endlessly.
            logger.error(
                f"Failed to cleanly sweep container {instance.container_id} ({instance.traefik_subdomain}): {e}"
            )

    logger.info(
        f"Sweeper routine complete. Successfully tore down {death_toll}/{total_found} containers."
    )
    return death_toll

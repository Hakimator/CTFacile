import redis
from django.conf import settings
from core import constants

# Initialize Redis client (Singleton-like behavior per worker)
# In production, settings.REDIS_URL must be configured.
redis_client = redis.StrictRedis.from_url(
    getattr(settings, "REDIS_URL", "redis://localhost:6379/0"), decode_responses=True
)


class ScoringService:
    """
    Service responsible for calculating points and handling dynamic scoring math.
    Strictly uses Redis for counters to preserve PostgreSQL performance, following the 3NF constraint.
    """

    @classmethod
    def calculate_dynamic_points(cls, challenge_id: int, base_points: int) -> int:
        """
        Calculates the current point value of a challenge based on the number of solves.
        Reads the solve count entirely from Redis `challenge:{id}:solves`.
        """
        redis_key = f"challenge:{challenge_id}:solves"

        # Read the current solve count. If it doesn't exist, it defaults to 0 logically.
        solves_str = redis_client.get(redis_key)
        solves_count = int(solves_str) if solves_str else 0

        # Math: Base Points - (Solves * Degradation)
        # Capped at MINIMUM_DYNAMIC_POINTS
        computed_score = base_points - (
            solves_count * constants.DYNAMIC_DEGRADATION_STEP
        )

        return max(computed_score, constants.MINIMUM_DYNAMIC_POINTS)

    @classmethod
    def increment_solve_count(cls, challenge_id: int) -> int:
        """
        Increments the Redis solve counter for the given challenge.
        Called by the FlagValidationService AFTER a successful, first-time solve.
        Returns the new total count.
        """
        redis_key = f"challenge:{challenge_id}:solves"
        return redis_client.incr(redis_key)

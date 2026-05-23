import redis
from collections import defaultdict
from typing import Dict, List, Tuple
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
    def calculate_scores_for_session(cls, session_id: int) -> Dict[int, int]:
        """
        Efficiently computes the total score for every team in a session using a
        single bulk database query instead of one query per team (N+1 fix).

        Returns a dict of {team_id: total_score}, including teams with 0 points.
        Callers should fetch Team objects separately and merge.
        """
        # Avoid a circular import — import here rather than at module level.
        from core.models import Submission, Team

        # 1. One query: all correct submissions for the session, deduplicated per
        #    (team, challenge) pair. Because FlagValidationService prevents duplicate
        #    correct submissions, this is purely defensive but costs nothing.
        rows = (
            Submission.objects
            .filter(team__session_id=session_id, is_correct=True)
            .values("team_id", "challenge_id", "challenge__base_points")
            .distinct()
        )

        # 2. Accumulate scores in Python — Redis reads are fast (sub-millisecond),
        #    so iterating here is far cheaper than N SQL round-trips.
        scores: Dict[int, int] = defaultdict(int)
        for row in rows:
            pts = cls.calculate_dynamic_points(
                row["challenge_id"], row["challenge__base_points"]
            )
            scores[row["team_id"]] += pts

        # 3. Ensure every team in the session is represented (even those with 0 points).
        all_team_ids = Team.objects.filter(session_id=session_id).values_list("id", flat=True)
        for tid in all_team_ids:
            if tid not in scores:
                scores[tid] = 0

        return dict(scores)

    @classmethod
    def increment_solve_count(cls, challenge_id: int) -> int:
        """
        Increments the Redis solve counter for the given challenge.
        NOTE: This is now called automatically by TelemetryService.log_submission()
        via the flag_submitted signal. Manual calls are only needed in tests or
        administrative backfill scripts.
        Returns the new total count.
        """
        redis_key = f"challenge:{challenge_id}:solves"
        return redis_client.incr(redis_key)

import redis
from django.conf import settings

# Initialize Redis client using settings
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

class TelemetryService:
    """
    Handles rapid-fire Gamification and Telemetry updates strictly in Redis
    to protect PostgreSQL performance.

    Redis keys maintained:
      team:{id}:correct_solves       — total correct submissions by team
      team:{id}:failed_attempts      — total wrong submissions by team (read by ATTEMPT_COUNT achievements)
      team:{id}:first_blood          — number of first-blood solves earned by team (read by FIRST_BLOOD achievements)
      team:{id}:solve_streak         — current consecutive-correct streak (read by SOLVE_STREAK achievements)
      challenge:{id}:solves          — global solve counter used by ScoringService for dynamic degradation
      challenge:{id}:correct_solves  — alias kept for legacy compatibility
      challenge:{id}:failed_attempts — global failed-attempt counter per challenge
    """

    @classmethod
    def log_submission(cls, user_id: int, team_id: int, challenge_id: int, is_correct: bool):
        if is_correct:
            # --- Core counters ---
            cls._increment_metric(f"team:{team_id}:correct_solves")

            # Increment the global solve counter used by ScoringService for dynamic
            # point degradation.  Redis INCR is atomic, so the returned value tells
            # us exactly how many teams have solved this challenge so far.
            new_global_solve_count = redis_client.incr(f"challenge:{challenge_id}:solves")
            # Keep the legacy alias in sync
            redis_client.incr(f"challenge:{challenge_id}:correct_solves")

            # --- First Blood detection ---
            # The first team to solve a challenge (global solve count becomes 1)
            # earns a first-blood credit.  This is atomic and race-condition safe
            # because Redis INCR is a single-step operation.
            if new_global_solve_count == 1:
                redis_client.incr(f"team:{team_id}:first_blood")

            # --- Solve Streak ---
            # Increment the team's consecutive-correct-solve counter.
            redis_client.incr(f"team:{team_id}:solve_streak")

        else:
            # --- Failure counters ---
            cls._increment_metric(f"team:{team_id}:failed_attempts")
            cls._increment_metric(f"challenge:{challenge_id}:failed_attempts")

            # Reset the solve streak on any incorrect attempt.
            redis_client.set(f"team:{team_id}:solve_streak", 0)

    @staticmethod
    def _increment_metric(key: str):
        redis_client.incr(key)

    @classmethod
    def get_team_metric(cls, team_id: int, metric_name: str) -> int:
        """
        Reads a specific team metric from Redis.
        Supported metric_name values: correct_solves, failed_attempts,
        first_blood, solve_streak.
        """
        key = f"team:{team_id}:{metric_name.lower()}"
        val = redis_client.get(key)
        if val is None:
            return 0
        try:
            return int(val)
        except ValueError:
            return 0

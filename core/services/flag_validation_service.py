import hashlib
from typing import Dict, Any
from core.models import User, Team, Challenge, Submission
from core.constants import ScoringMode
from core.services.scoring_service import ScoringService, redis_client


# Note: In a real Django app, this would be an actual Signal or Celery task import.
# Using a mock dispatcher per the prompt's request for an Event-Driven architecture decoupling.
class MockEventDispatcher:
    @staticmethod
    def send(event_name: str, payload: dict):
        # E.g., triggers Celery tasks like process_achievement_badges.delay(**payload)
        pass


class FlagValidationService:
    """
    Core engine handling flag submissions, score state delegation, telemetry mapping,
    and event emissions. Strictly decouples achievements via Event Bus.
    """

    MAX_SUBMISSIONS_PER_MINUTE = 15

    @classmethod
    def process_submission(
        cls, user: User, team: Team, challenge: Challenge, submitted_flag: str
    ) -> Dict[str, Any]:
        """
        Validates a flag entry. Flow:
        1. Rate Limiting (Redis)
        2. Hash Comparison
        3. Database Log (PostgreSQL)
        4. Telemetry Updates (Redis)
        5. Score Calculation (if correct)
        6. Event Dispatch for Achievements (if correct)
        """
        response: Dict[str, Any] = {
            "success": False,
            "message": "",
            "points_awarded": 0,
        }

        # 1. Anti-Cheat & Rate Limiting (Redis)
        rate_limit_key = f"user:{user.id}:submissions_per_minute"
        current_requests = redis_client.incr(rate_limit_key)

        # Set expiry on first request of the minute bucket
        if current_requests == 1:
            redis_client.expire(rate_limit_key, 60)

        if current_requests > cls.MAX_SUBMISSIONS_PER_MINUTE:
            response["message"] = "Rate limit exceeded. Please wait."
            response["status_code"] = 429  # HTTP 429 mapping
            return response

        # 2. Duplicate Solve Check (Prevent Farming)
        if Submission.objects.filter(
            team=team, challenge=challenge, is_correct=True
        ).exists():
            response["message"] = "Your team has already captured this flag."
            return response

        # 3. Hash Comparison
        hasher = hashlib.sha256()
        hasher.update(submitted_flag.encode("utf-8"))
        submitted_hash = hasher.hexdigest()

        is_correct = submitted_hash == challenge.flag_hash

        # 4. Database Log: Create immutable PostgreSQL Submission record
        Submission.objects.create(
            user=user,
            team=team,
            challenge=challenge,
            submitted_payload=submitted_flag,
            is_correct=is_correct,
        )

        # Handle Incorrect Submission
        if not is_correct:
            # 5a. Update failed attempt telemetry
            failed_attempts_key = f"team:{team.id}:total_failed_attempts"
            redis_client.hincrby(failed_attempts_key, "count", 1)

            # Reset consecutive solves telemetry for the user
            consecutive_solves_key = f"user:{user.id}:consecutive_solves"
            redis_client.hset(consecutive_solves_key, "count", 0)

            response["message"] = "Incorrect flag."
            return response

        # 5b. Update correct solve telemetry
        consecutive_solves_key = f"user:{user.id}:consecutive_solves"
        redis_client.hincrby(consecutive_solves_key, "count", 1)

        # 6. Score Calculation & First Blood Check
        # Check session scoring mode to determine points awarded
        solve_index = ScoringService.increment_solve_count(challenge.id)

        if challenge.session.scoring_mode == ScoringMode.DYNAMIC:
            points = ScoringService.calculate_dynamic_points(
                challenge.id, challenge.base_points
            )
        else:
            # Static scoring just yields the current base points
            points = challenge.base_points

        # Record first blood strictly in Redis if this is the very first solve
        if solve_index == 1:
            first_blood_key = f"user:{user.id}:first_bloods"
            redis_client.hincrby(first_blood_key, "count", 1)

        response["success"] = True
        response["message"] = "Correct flag! Well done."
        response["points_awarded"] = points

        # 7. Event Dispatch for Achievements (Decoupled Logic)
        # The AchievementService will listen to this and check Redis for threshold matches.
        MockEventDispatcher.send(
            event_name="FlagSolvedEvent",
            payload={
                "user_id": user.id,
                "team_id": team.id,
                "challenge_id": challenge.id,
                "points_awarded": points,
            },
        )

        return response

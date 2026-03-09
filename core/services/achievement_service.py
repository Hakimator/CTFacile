import logging
from django.core.cache import cache
from core.models import User, Team, Challenge, Achievement, TeamAchievement
from core.constants import TriggerType
from core.services.scoring_service import redis_client

logger = logging.getLogger(__name__)


class AchievementService:
    """
    Decoupled Event Consumer for Gamification.
    Listens for FlagSolvedEvents and uses Redis telemetry to dynamically evaluate unlocked achievements.
    """

    @classmethod
    def evaluate_achievements(cls, user: User, team: Team, challenge: Challenge):
        """
        Iterates over all defined dynamic achievements and evaluates them
        against the team's and user's current high-speed Redis telemetry state.
        This is designed to be called asynchronously by an event dispatcher.
        """
        # Fetch all active achievement rules from Cache or Database
        achievements = cache.get("active_achievements")
        if achievements is None:
            achievements = list(Achievement.objects.all())
            cache.set("active_achievements", achievements, 3600)

        for achievement in achievements:
            # 1. Idempotency Check: Already unlocked?
            if TeamAchievement.objects.filter(
                team=team, achievement=achievement
            ).exists():
                continue

            threshold_met = False

            # 2. Dynamic Evaluation based on TriggerType mapping to the Redis state
            if achievement.trigger_type == TriggerType.FIRST_BLOOD:
                # User First Bloods
                first_bloods_key = f"user:{user.id}:first_bloods"
                count_str = redis_client.hget(first_bloods_key, "count")
                count = int(count_str) if count_str else 0
                if count >= achievement.threshold_value:
                    threshold_met = True

            elif achievement.trigger_type == TriggerType.ATTEMPT_COUNT:
                # Team Total Failed Attempts
                # e.g., unlocking 'Persistence' when fails >= 20
                failed_attempts_key = f"team:{team.id}:total_failed_attempts"
                count_str = redis_client.hget(failed_attempts_key, "count")
                count = int(count_str) if count_str else 0
                if count >= achievement.threshold_value:
                    threshold_met = True

            elif achievement.trigger_type == TriggerType.SOLVE_STREAK:
                # User Consecutive Solves streak
                consecutive_solves_key = f"user:{user.id}:consecutive_solves"
                count_str = redis_client.hget(consecutive_solves_key, "count")
                count = int(count_str) if count_str else 0
                if count >= achievement.threshold_value:
                    threshold_met = True

            # 3. Granting the Badge
            if threshold_met:
                TeamAchievement.objects.create(
                    team=team, achievement=achievement, unlocked_by_user=user
                )
                logger.info(
                    f"Achievement Unlocked! Team {team.name} unlocked '{achievement.title}' by User {user.username}."
                )

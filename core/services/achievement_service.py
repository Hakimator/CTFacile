import logging
from django.core.cache import cache
from core.models import User, Team, Achievement, TeamAchievement
from core.constants import TriggerType
from core.services.telemetry_service import TelemetryService

logger = logging.getLogger(__name__)

class AchievementService:
    """
    Decoupled Event Consumer for Gamification.
    Listens for FlagSolvedEvents and uses Redis telemetry to dynamically evaluate unlocked achievements.
    """

    @classmethod
    def evaluate_team_achievements(cls, team_id: int, user_id: int):
        # Fetch all active achievement rules from Cache or Database
        achievements = cache.get("active_achievements")
        if achievements is None:
            achievements = list(Achievement.objects.all())
            cache.set("active_achievements", achievements, 3600)

        unlocked_ids = set(TeamAchievement.objects.filter(team_id=team_id).values_list('achievement_id', flat=True))

        for achievement in achievements:
            if achievement.id in unlocked_ids:
                continue

            threshold_met = False

            # Dynamic Evaluation based on TriggerType mapping to the Redis state via TelemetryService
            if achievement.trigger_type == TriggerType.FIRST_BLOOD:
                # User First Bloods
                count = TelemetryService.get_team_metric(team_id, "first_blood") # Or map user first bloods appropriately if needed, but parameter is team_id per instruction.
                if count >= achievement.threshold_value:
                    threshold_met = True

            elif achievement.trigger_type == TriggerType.ATTEMPT_COUNT:
                # Team Total Failed Attempts
                count = TelemetryService.get_team_metric(team_id, "failed_attempts")
                if count >= achievement.threshold_value:
                    threshold_met = True

            elif achievement.trigger_type == TriggerType.SOLVE_STREAK:
                # Solve streak
                count = TelemetryService.get_team_metric(team_id, "solve_streak")
                if count >= achievement.threshold_value:
                    threshold_met = True

            # Granting the Badge
            if threshold_met:
                TeamAchievement.objects.create(
                    team_id=team_id, 
                    achievement_id=achievement.id, 
                    unlocked_by_user_id=user_id
                )
                logger.info(
                    f"Achievement Unlocked! Team {team_id} unlocked '{achievement.title}' by User {user_id}."
                )

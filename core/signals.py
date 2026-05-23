import django.dispatch
from django.dispatch import receiver
from core.services.telemetry_service import TelemetryService
from core.services.achievement_service import AchievementService

# 1. Define the custom signal: The Event Bus
flag_submitted = django.dispatch.Signal() # Providing args: user_id, team_id, challenge_id, is_correct

# 2. Wire the receiver
@receiver(flag_submitted)
def handle_flag_submitted(sender, **kwargs):
    """
    Decoupled listener that hears the 'flag_submitted' event.
    Updates the Redis telemetry maps for high-speed gamification indexing,
    then evaluates badges if applicable.
    """
    user_id = kwargs.get('user_id')
    team_id = kwargs.get('team_id')
    challenge_id = kwargs.get('challenge_id')
    is_correct = kwargs.get('is_correct')
    
    # Update high-speed metrics in Redis
    TelemetryService.log_submission(
        user_id=user_id,
        team_id=team_id,
        challenge_id=challenge_id,
        is_correct=is_correct
    )
    
    # Evaluate achievements dynamically
    if is_correct:
        AchievementService.evaluate_team_achievements(team_id=team_id, user_id=user_id)

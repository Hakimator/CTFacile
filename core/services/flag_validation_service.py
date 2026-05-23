import hashlib
import hmac
from core.models import User, Challenge, Submission, TeamMembership, SiteSettings
from core.signals import flag_submitted
from core.services.validators import get_validator

class FlagValidationService:
    """
    Core engine handling flag submissions.
    """

    @classmethod
    def validate_submission(cls, user: User, challenge: Challenge, submitted_flag: str) -> tuple[bool, str]:
        # Global Control Override
        settings = SiteSettings.load()
        if settings.is_ctf_paused:
            raise PermissionError("The CTF is currently paused by the Administrator.")

        # Protocol Active: Strict Adherence to Service Layer Architecture
        membership = TeamMembership.objects.filter(user=user).select_related('team__session').first()
        if not membership:
            raise ValueError("User must be in a team to submit flags.")

        team = membership.team

        # --- Multi-Tenancy Enforcement ---
        # A team belongs to a specific CTFSession. A challenge also belongs to a
        # specific CTFSession. These MUST match. Without this guard a student in
        # session A could submit a flag for a challenge that only exists in session B,
        # or exploit flag hashes across isolated tenant boundaries.
        if team.session_id != challenge.session_id:
            raise PermissionError(
                "This challenge does not belong to your current session."
            )

        # Replace hardcoded hash check with polymorphic Strategy Pattern
        validator = get_validator(challenge.challenge_type)
        is_correct = validator.verify(challenge, team, submitted_flag)

        if is_correct:
            # Duplicate Solve Check
            if Submission.objects.filter(team=team, challenge=challenge, is_correct=True).exists():
                return True, "Already solved"

            # ADHERENCE TO CONCEPTION.MD RULE 3 (Strict 3NF Normalization):
            # We DO NOT save total_score to the Team model. PostgreSQL must remain strictly 3NF.
            # Points are calculated dynamically via Redis or Django .annotate().

            # Database Log: Create immutable PostgreSQL Submission record
            Submission.objects.create(
                user=user,
                team=team,
                challenge=challenge,
                submitted_payload=submitted_flag,
                is_correct=True,
            )

            # Fire Gamification Event via Signals (Decoupled execution)
            flag_submitted.send(
                sender=cls,
                user_id=user.id,
                team_id=team.id,
                challenge_id=challenge.id,
                is_correct=True,
            )

            return True, "Flag captured!"
        else:
            # Immutable log for incorrect attempts
            Submission.objects.create(
                user=user,
                team=team,
                challenge=challenge,
                submitted_payload=submitted_flag,
                is_correct=False,
            )

            # Fire Gamification Event via Signals (Decoupled execution)
            flag_submitted.send(
                sender=cls,
                user_id=user.id,
                team_id=team.id,
                challenge_id=challenge.id,
                is_correct=False,
            )

            return False, "Incorrect flag."

from abc import ABC, abstractmethod
import hashlib
import hmac
from django.utils import timezone
from core.models import Challenge, Team, ActiveInstance

class BaseChallengeValidator(ABC):
    @abstractmethod
    def verify(self, challenge: Challenge, team: Team, submitted_flag: str) -> bool:
        pass
        
    def _verify_hash(self, challenge: Challenge, submitted_flag: str) -> bool:
        hasher = hashlib.sha256()
        hasher.update(submitted_flag.encode("utf-8"))
        submitted_hash = hasher.hexdigest()
        return hmac.compare_digest(submitted_hash, challenge.flag_hash)

class StaticChallengeValidator(BaseChallengeValidator):
    def verify(self, challenge: Challenge, team: Team, submitted_flag: str) -> bool:
        return self._verify_hash(challenge, submitted_flag)

class ContainerChallengeValidator(BaseChallengeValidator):
    def verify(self, challenge: Challenge, team: Team, submitted_flag: str) -> bool:
        # Check if team has an active, running instance of this challenge
        active_instance = ActiveInstance.objects.filter(
            team=team, 
            challenge=challenge, 
            expires_at__gt=timezone.now()
        ).first()
        
        if not active_instance:
            raise PermissionError("You must start the machine before submitting this flag. Ghost solves are forbidden.")
            
        return self._verify_hash(challenge, submitted_flag)

def get_validator(challenge_type: str) -> BaseChallengeValidator:
    if challenge_type == 'STATIC':
        return StaticChallengeValidator()
    elif challenge_type == 'CONTAINER':
        return ContainerChallengeValidator()
    else:
        raise ValueError(f"Unknown challenge type: {challenge_type}")

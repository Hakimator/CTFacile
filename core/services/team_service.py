import uuid
from django.db import transaction
from core.models import Team, TeamMembership, CTFSession, User

class TeamService:
    """
    Service layer handling all logic regarding CTF team creation and joining.
    Strictly decoupled from HTTP mechanics.
    """

    @classmethod
    def create_team(cls, user: User, session: CTFSession, team_name: str) -> Team:
        if not team_name or len(team_name.strip()) == 0:
            raise ValueError("Team name cannot be empty.")
            
        if TeamMembership.objects.filter(user=user, team__session=session).exists():
            raise ValueError("You are already in a team for this session.")
            
        if Team.objects.filter(name=team_name, session=session).exists():
            raise ValueError("A team with this name already exists in this session.")
            
        with transaction.atomic():
            team = Team.objects.create(name=team_name.strip(), session=session)
            TeamMembership.objects.create(user=user, team=team)
            
        return team

    @classmethod
    def join_team(cls, user: User, session: CTFSession, join_code: str) -> Team:
        if not join_code:
            raise ValueError("Join code cannot be empty.")
            
        if TeamMembership.objects.filter(user=user, team__session=session).exists():
            raise ValueError("You are already in a team for this session.")
            
        try:
            uuid_obj = uuid.UUID(join_code)
        except ValueError:
            raise ValueError("Invalid join code format. Must be a UUID.")
            
        team = Team.objects.filter(join_code=uuid_obj, session=session).first()
        if not team:
            raise ValueError("Invalid join code or team does not exist in this session.")
            
        TeamMembership.objects.create(user=user, team=team)
        return team

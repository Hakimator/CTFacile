from core.models import SOSTicket, Team, Challenge, User
from core.constants import TicketStatus
import logging

logger = logging.getLogger(__name__)

class SOSTicketService:
    """
    Service layer handling SOS Help Desk ticket creation.
    Validates limits before allowing users to ping administrators.
    """

    @classmethod
    def create_ticket(cls, user: User, team_id: int, challenge_id: int, issue_description: str) -> SOSTicket:
        if not issue_description or len(issue_description.strip()) == 0:
            raise ValueError("Issue description cannot be empty.")

        # Anti-Spam Check: Limit to 1 open/in_progress ticket per team per challenge
        active_tickets = SOSTicket.objects.filter(
            team_id=team_id,
            challenge_id=challenge_id,
            status__in=[TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value]
        )
        
        if active_tickets.exists():
            raise ValueError("Your team already has an active help request for this challenge. Please wait for a mentor.")

        # Create new SOS ticket
        ticket = SOSTicket.objects.create(
            team_id=team_id,
            challenge_id=challenge_id,
            issue_description=issue_description,
            status=TicketStatus.OPEN.value
        )
        
        # In a real deployed app with Discord integration, we'd fire off a Celery task here:
        # discord_services.send_sos_alert.delay(ticket.id)
        logger.info(f"SOS Ticket #{ticket.id} created by user {user.username} for Team #{team_id} on Challenge #{challenge_id}")
        
        return ticket

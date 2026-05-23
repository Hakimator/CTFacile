from core.models import WriteUp, Submission, Team

class WriteUpService:
    """
    Service layer handling Methodology Report submissions (Module E).
    Validates academic requirements before allowing artifact uploads.
    """

    @classmethod
    def submit_writeup(cls, team_id: int, challenge_id: int, content: str) -> WriteUp:
        # Security Check: Verify team has solved the challenge
        is_solved = Submission.objects.filter(
            team_id=team_id, 
            challenge_id=challenge_id, 
            is_correct=True
        ).exists()
        
        if not is_solved:
            raise PermissionError("You must capture the flag before submitting a write-up.")
            
        if not content or len(content.strip()) == 0:
            raise ValueError("Write-up content cannot be empty.")
            
        # Upsert Logic: Update if exists, else create
        writeup, created = WriteUp.objects.update_or_create(
            team_id=team_id,
            challenge_id=challenge_id,
            defaults={'content': content}
        )
        
        # update_or_create saves automatically, but we might want to ensure 'submitted_at' is updated
        # Django's auto_now_add only fires on creation. If we want to explicitly record the edit time, 
        # we would need to add auto_now=True to the model or update it here. Since the prompt implies
        # updating the timestamp, we can just save it.
        writeup.save()
            
        return writeup

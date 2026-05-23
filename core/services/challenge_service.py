from typing import Dict, List, Any
from core.models import Challenge, ChallengePrerequisite, Submission, Category

class ChallengeService:
    """
    Service layer handling gamified Skill Tree logic (Module B).
    Calculates unlock tree state for challenges.
    """

    @classmethod
    def get_team_skill_tree(cls, team_id: int) -> Dict[str, List[Dict[str, Any]]]:
        # 1. Fetch all active challenges
        all_categories = Category.objects.prefetch_related('challenges').all()
        
        # 2. Fetch all challenge_ids the team has successfully solved
        solved_challenge_ids = set(
            Submission.objects.filter(team_id=team_id, is_correct=True).values_list('challenge_id', flat=True)
        )
        
        # 3. Fetch all prerequisites to calculate unlock status
        # We group prerequisites by target_challenge_id for quick lookup
        prerequisites_qs = ChallengePrerequisite.objects.all()
        prereqs_map = {}
        for prereq in prerequisites_qs:
            target_id = prereq.target_challenge_id
            required_id = prereq.required_challenge_id
            if target_id not in prereqs_map:
                prereqs_map[target_id] = []
            prereqs_map[target_id].append(required_id)
            
        # 4. Determine state for each challenge and group by Category Name
        grouped_tree = {}
        
        for category in all_categories:
            challenges_list = []
            
            for challenge in category.challenges.all():
                state = "LOCKED"
                
                # Check if Solved
                if challenge.id in solved_challenge_ids:
                    state = "SOLVED"
                else:
                    # If not solved, check if Unlocked
                    if challenge.is_entry_node:
                        state = "UNLOCKED"
                    else:
                        # Check prerequisites list
                        required_prereqs = prereqs_map.get(challenge.id, [])
                        if not required_prereqs:
                            # Edge case: If it's not an entry node but has 0 prerequisites, default to LOCKED 
                            # (or UNLOCKED depending on design, but prompt implies LOCKED otherwise)
                            state = "LOCKED" 
                        else:
                            # It is UNLOCKED if the team has solved ALL required prerequisites
                            if all(req_id in solved_challenge_ids for req_id in required_prereqs):
                                state = "UNLOCKED"
                
                # Append annotated challenge dictionary
                challenges_list.append({
                    "id": challenge.id,
                    "title": challenge.title,
                    "base_points": challenge.base_points,
                    "description": challenge.description,
                    "state": state
                })
                
            grouped_tree[category.name] = challenges_list
            
        return grouped_tree

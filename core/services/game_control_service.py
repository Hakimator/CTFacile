from core.models import SiteSettings, Team, Submission, TeamAchievement, CTFSession
from core.services.scoring_service import ScoringService


class GameControlService:
    """
    Service layer for Global CTF Controls and Cyber-Map (Module E).
    """

    @classmethod
    def toggle_ctf_state(cls, admin_user) -> bool:
        if admin_user.role != 'ADMIN' and not admin_user.is_staff:
            raise PermissionError("Only Administrators can toggle the CTF state.")

        settings = SiteSettings.load()
        settings.is_ctf_paused = not settings.is_ctf_paused
        settings.save()
        return settings.is_ctf_paused

    @classmethod
    def get_live_map_data(cls) -> dict:
        """
        Builds the live-map payload for the classroom projector view.

        Uses calculate_scores_for_session() to avoid an N+1 loop over teams.
        Scopes to the currently active CTFSession; falls back to all sessions
        when none is active (e.g. between events).
        """
        active_session = CTFSession.objects.filter(is_active=True).first()

        if active_session:
            # Bulk-score every team in the active session — single DB query.
            session_scores = ScoringService.calculate_scores_for_session(active_session.id)
            teams_qs = Team.objects.filter(session_id=active_session.id)
        else:
            # No active session: show scores across all sessions (admin view).
            # Still avoids N+1 by scoring per-session and merging.
            session_scores = {}
            for session in CTFSession.objects.all():
                for tid, score in ScoringService.calculate_scores_for_session(session.id).items():
                    session_scores[tid] = session_scores.get(tid, 0) + score
            teams_qs = Team.objects.all()

        leaderboard = [
            {"team": t, "score": session_scores.get(t.id, 0)}
            for t in teams_qs
        ]
        leaderboard.sort(key=lambda x: x["score"], reverse=True)
        top_10 = leaderboard[:10]

        # Activity Feed: 10 most recent correct submissions and achievements.
        # select_related avoids additional per-row queries on team/challenge/achievement.
        recent_submissions = list(
            Submission.objects
            .filter(is_correct=True)
            .select_related('team', 'challenge')
            .order_by('-timestamp')[:10]
        )
        recent_achievements = list(
            TeamAchievement.objects
            .select_related('team', 'achievement')
            .order_by('-unlocked_at')[:10]
        )

        feed = []
        for sub in recent_submissions:
            feed.append({
                'type': 'submission',
                'team_name': sub.team.name,
                'title': sub.challenge.title,
                'timestamp': sub.timestamp,
            })
        for ach in recent_achievements:
            feed.append({
                'type': 'achievement',
                'team_name': ach.team.name,
                'title': ach.achievement.title,
                'timestamp': ach.unlocked_at,
            })

        feed.sort(key=lambda x: x['timestamp'], reverse=True)

        return {
            'leaderboard': top_10,
            'activity_feed': feed[:10],
        }

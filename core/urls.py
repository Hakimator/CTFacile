from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from core.views import (
    RegisterView,
    SecureTokenObtainPairView,
    JoinTeamView,
    SkillTreeView,
    StartChallengeView,
    SubmitFlagView,
    LeaderboardView,
    DashboardView,
    health_ping,
    challenge_detail,
    test_outcome,
)

urlpatterns = [
    # --- Authentication ---
    path("auth/register/", RegisterView.as_view(), name="auth_register"),
    path("auth/login/", SecureTokenObtainPairView.as_view(), name="auth_login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth_refresh"),
    # --- Teams ---
    path("teams/join/", JoinTeamView.as_view(), name="team_join"),
    # --- Data Fetching (Frontend Rendering) ---
    path("challenges/tree/", SkillTreeView.as_view(), name="skill_tree"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    # --- Actions ---
    path("challenges/start/", StartChallengeView.as_view(), name="challenge_start"),
    path("submissions/", SubmitFlagView.as_view(), name="flag_submission"),
    # --- Frontend Shell & Infra ---
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("health/ping/", health_ping, name="health_ping"),
    path(
        "challenges/view/<int:challenge_id>/", challenge_detail, name="challenge_detail"
    ),
    path(
        "test-outcome/<int:challenge_id>/<str:status>/", test_outcome, name="test_outcome"
    ),
]

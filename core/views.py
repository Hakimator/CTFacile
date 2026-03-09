import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.utils import timezone

from core.models import Challenge, Team, TeamMembership, Category, Submission
from core.serializers import (
    FlagSubmissionSerializer,
    StartChallengeSerializer,
    UserRegistrationSerializer,
    JoinTeamSerializer,
    CategoryTreeSerializer,
)
from core.services.flag_validation_service import FlagValidationService
from core.services.scoring_service import ScoringService
from core.services.docker_manager_service import DockerManagerService
from rest_framework_simplejwt.views import TokenObtainPairView

logger = logging.getLogger(__name__)


class SubmitFlagView(APIView):
    """
    API Endpoint for submitting CTF flags.
    Acts purely as the HTTP Transport layer. Delegates all business logic,
    rate limiting, caching, and database writes to FlagValidationService.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # 1. Deserialize and validate incoming JSON
        serializer = FlagSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        challenge_id = serializer.validated_data["challenge_id"]
        submitted_flag = serializer.validated_data["submitted_flag"]

        user = request.user

        # 2. Fetch the User's Active Team
        # Assuming the user belongs to at least one team for this session logic
        team = user.teams.first()
        if not team:
            return Response(
                {
                    "success": False,
                    "message": "You must be part of a team to submit flags.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # 3. Fetch the Challenge safely
        challenge = get_object_or_404(Challenge, id=challenge_id)

        # 4. Handoff to the Brain (Service Layer)
        try:
            result = FlagValidationService.process_submission(
                user=user, team=team, challenge=challenge, submitted_flag=submitted_flag
            )

            # Map Service layer rate-limiting response (429) if triggered
            if result.get("status_code") == 429:
                if "HX-Request" in request.headers:
                    return HttpResponse(
                        '<div class="p-3 bg-yellow-900 border border-yellow-700 text-yellow-200 rounded">⏳ Rate limited. Please wait.</div>',
                        status=429,
                    )
                return Response(result, status=status.HTTP_429_TOO_MANY_REQUESTS)

            if "HX-Request" in request.headers:
                if result.get("success"):
                    return HttpResponse(
                        '<div class="p-3 bg-green-900 border border-green-700 text-green-200 rounded">✅ Correct! Points added to your team.</div>'
                    )
                else:
                    return HttpResponse(
                        '<div class="p-3 bg-red-900 border border-red-700 text-red-200 rounded">❌ Incorrect flag. Try again.</div>'
                    )

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error processing flag submission for User {user.id}: {e}")
            return Response(
                {
                    "success": False,
                    "message": "An internal error occurred while validating the flag.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StartChallengeView(APIView):
    """
    API Endpoint for spinning up isolated Docker containers for specific challenges.
    Delegates daemon interactions and loadbalancer routing to the DockerManagerService.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = StartChallengeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        challenge_id = serializer.validated_data["challenge_id"]
        user = request.user
        team = user.teams.first()

        if not team:
            return Response(
                {
                    "success": False,
                    "message": "You must be part of a team to start a challenge.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        challenge = get_object_or_404(Challenge, id=challenge_id)

        if not challenge.docker_image_tag:
            return Response(
                {
                    "success": False,
                    "message": "This is a static challenge, no machine needed.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            active_instance = DockerManagerService.start_challenge_instance(
                team, challenge
            )

            if "HX-Request" in request.headers:
                return challenge_detail(request, challenge.id)

            return Response(
                {
                    "success": True,
                    "message": "Machine started.",
                    "subdomain": active_instance.traefik_subdomain,
                    "expires_at": active_instance.expires_at,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(
                f"Failed to start challenge '{challenge.title}' for team {team.name}: {e}"
            )

            if "HX-Request" in request.headers:
                return HttpResponse(
                    '<div class="p-3 bg-red-900 border border-red-700 text-red-200 rounded text-sm text-center">Service unavailable. Docker daemon failed to provision machine.</div>',
                    status=503,
                )

            return Response(
                {
                    "success": False,
                    "message": "Service unavailable. Docker daemon failed to provision machine.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class RegisterView(APIView):
    """
    API Endpoint for User Registration.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"success": True, "message": "User created successfully."},
            status=status.HTTP_201_CREATED,
        )


class SecureTokenObtainPairView(TokenObtainPairView):
    """
    Strict XSS-protected JWT Login endpoint.
    Moves the refresh token to an HttpOnly, Lax cookie so the frontend JS cannot access it.
    """

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            refresh = response.data.get("refresh")
            if refresh:
                response.set_cookie(
                    key="refresh_token", value=refresh, httponly=True, samesite="Lax"
                )
                del response.data["refresh"]
        return response


class JoinTeamView(APIView):
    """
    API Endpoint for joining a team via Join Code.
    Strictly prevents spying by checking if the user is already in a team for the session.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = JoinTeamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        join_code = serializer.validated_data["join_code"]
        team = get_object_or_404(Team, join_code=join_code)

        user = request.user

        # Security Rule: Spying Prevention
        if TeamMembership.objects.filter(
            user=user, team__session=team.session
        ).exists():
            return Response(
                {
                    "success": False,
                    "message": "You are already in a team for this CTF Session.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        TeamMembership.objects.create(user=user, team=team)
        return Response(
            {"success": True, "message": f"Successfully joined team {team.name}."},
            status=status.HTTP_200_OK,
        )


class SkillTreeView(APIView):
    """
    API Endpoint for rendering the visual CTF skill tree.
    Returns categorized challenges decorated with solve states and current dynamic values.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        categories = Category.objects.prefetch_related("challenges").all()
        serializer = CategoryTreeSerializer(
            categories, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class LeaderboardView(APIView):
    """
    API Endpoint for rendering the scoreboard ranking.
    Agressively cached for 60 seconds to prevent Redis/PostgreSQL flooding during peak CTF traffic.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        team = user.teams.first()

        if not team:
            return Response(
                {
                    "success": False,
                    "message": "You must be part of a team to view the leaderboard.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        session_id = team.session.id
        cache_key = f"leaderboard_{session_id}"
        cached_data = cache.get(cache_key)

        if cached_data is not None:
            return Response(cached_data, status=status.HTTP_200_OK)

        # Re-calculate leaderboard
        # Fetching all teams for the active session
        teams = Team.objects.filter(session_id=session_id)

        leaderboard = []
        for t in teams:
            total_score = 0
            # Get IDs of all challenges this team has successfully solved
            solved_challenge_ids = Submission.objects.filter(
                team=t, is_correct=True
            ).values_list("challenge__id", "challenge__base_points")

            # Map their solve count through the ScoringService to get current values
            for cid, base_pts in solved_challenge_ids:
                total_score += ScoringService.calculate_dynamic_points(cid, base_pts)

            leaderboard.append({"team_name": t.name, "score": total_score})

        # Sort descending by score
        leaderboard.sort(key=lambda x: x["score"], reverse=True)

        # Cache the computationally expensive ranking payload for 60s
        cache.set(cache_key, leaderboard, 60)

        return Response(leaderboard, status=status.HTTP_200_OK)


from django.views.generic import TemplateView
from django.http import JsonResponse
from django.shortcuts import render
from core.models import ActiveInstance


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Prefetch the categories and their related challenges to pass directly to HTML
        context["categories"] = Category.objects.prefetch_related("challenges").all()
        return context


def health_ping(request):
    """
    Simple 200 OK endpoint for the Alpine.js Cockroach heartbeat protocol.
    If the worker goes down or the load balancer drops, this will fail and
    trigger the UI's offline mode.
    """
    return JsonResponse({"status": "alive", "timestamp": str(timezone.now())})


def challenge_detail(request, challenge_id):
    """
    HTMX endpoint to render the contents of a specific Challenge Modal.
    Determines if the team already solved it and interacts with ActiveInstance
    to display connection details or a "Start Machine" button.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    challenge = get_object_or_404(Challenge, id=challenge_id)
    team = request.user.teams.first()

    if not team:
        return JsonResponse({"error": "You must be part of a team."}, status=403)

    # 1. State checking
    is_solved = Submission.objects.filter(
        team=team, challenge=challenge, is_correct=True
    ).exists()
    current_points = ScoringService.calculate_dynamic_points(
        challenge.id, challenge.base_points
    )

    # 2. Docker Sibling Logic
    active_instance = None
    if challenge.docker_image_tag:
        active_instance = ActiveInstance.objects.filter(
            team=team, challenge=challenge, expires_at__gt=timezone.now()
        ).first()

    context = {
        "challenge": challenge,
        "team": team,
        "is_solved": is_solved,
        "current_points": current_points,
        "active_instance": active_instance,
    }

    return render(request, "partials/challenge_detail.html", context)


def test_outcome(request, challenge_id, status):
    """
    Solid test mechanism endpoint.
    """
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)
        
    if request.method == "POST":
        challenge = get_object_or_404(Challenge, id=challenge_id)
        team = request.user.teams.first()

        if not team:
            return HttpResponse('<div class="p-3 bg-red-900 border border-red-700 text-red-200 rounded">❌ You must be part of a team.</div>', status=403)
            
        is_correct = (status == 'success')
        
        # Create immutable submission
        Submission.objects.create(
            user=request.user,
            team=team,
            challenge=challenge,
            submitted_payload=f"TEST_PAYLOAD_{'SUCCESS' if is_correct else 'FAILURE'}",
            is_correct=is_correct
        )
        
        if is_correct:
            return HttpResponse(f'<span class="text-success font-bold" style="color: #198754;">Validé ! (+{challenge.base_points} Points)</span>')
        else:
            return HttpResponse('<span class="text-danger font-bold" style="color: #dc3545;">Échec ! (Veuillez réessayer)</span>')
            
    return HttpResponse("Method Not Allowed", status=405)

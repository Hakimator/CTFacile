import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Challenge, Category, Submission, Team, ActiveInstance, CTFSession, TeamMembership, ChallengeTemplate, SiteSettings
from core.services.flag_validation_service import FlagValidationService
from core.services.scoring_service import ScoringService
from core.services.docker_manager_service import DockerManagerService
from core.services.team_service import TeamService
from core.services.challenge_service import ChallengeService
from core.services.writeup_service import WriteUpService
from core.services.sos_service import SOSTicketService
from core.services.game_control_service import GameControlService
from core.services.challenge_builder_service import ChallengeBuilderService

logger = logging.getLogger(__name__)

def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


def health_ping(request):
    return JsonResponse({"status": "alive"})


@login_required
def team_dashboard(request):
    active_session = CTFSession.objects.filter(is_active=True).first()
    if not active_session:
        return render(request, 'core/team_join_create.html', {"error": "No active CTF session right now."})

    membership = TeamMembership.objects.filter(user=request.user, team__session=active_session).first()
    if membership:
        team = membership.team
        session_scores = ScoringService.calculate_scores_for_session(active_session.id)
        total_score = session_scores.get(team.id, 0)
        return render(request, 'core/team_detail.html', {'team': team, 'total_score': total_score, 'session': active_session})
    else:
        return render(request, 'core/team_join_create.html', {'session': active_session})


@require_POST
@login_required
def create_team_action(request):
    active_session = CTFSession.objects.filter(is_active=True).first()
    if not active_session:
        return HttpResponse('<div class="text-red-500">Error: No active CTF session.</div>', status=400)
    team_name = request.POST.get('team_name', '')
    try:
        TeamService.create_team(request.user, active_session, team_name)
        response = HttpResponse()
        response['HX-Redirect'] = reverse('team_dashboard')
        return response
    except ValueError as e:
        return HttpResponse(f'<div class="p-4 bg-red-900 border border-red-500 text-red-200 rounded">Error: {str(e)}</div>', status=400)


@require_POST
@login_required
def join_team_action(request):
    active_session = CTFSession.objects.filter(is_active=True).first()
    if not active_session:
        return HttpResponse('<div class="text-red-500">Error: No active CTF session.</div>', status=400)
    join_code = request.POST.get('join_code', '')
    try:
        TeamService.join_team(request.user, active_session, join_code)
        response = HttpResponse()
        response['HX-Redirect'] = reverse('team_dashboard')
        return response
    except ValueError as e:
        return HttpResponse(f'<div class="p-4 bg-red-900 border border-red-500 text-red-200 rounded">Error: {str(e)}</div>', status=400)


@login_required
def dashboard(request):
    team_membership = getattr(request.user, 'teammembership', None)
    if team_membership:
        team = team_membership.team
    else:
        team = getattr(request.user, 'teams', None)
        team = team.first() if team else None

    if not team:
        return redirect('team_dashboard')

    tree_data = ChallengeService.get_team_skill_tree(team.id)
    context = {
        'tree_data': tree_data,
        'team': team
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def challenge_detail(request, challenge_id):
    challenge = get_object_or_404(Challenge, id=challenge_id)
    team_membership = getattr(request.user, 'teammembership', None)
    team = None
    if team_membership:
        team = team_membership.team
    else:
        team = getattr(request.user, 'teams', None)
        team = team.first() if team else None

    if not team:
        return HttpResponse('<div class="text-red-500">You must be part of a team.</div>', status=403)

    is_solved = Submission.objects.filter(team=team, challenge=challenge, is_correct=True).exists()
    current_points = ScoringService.calculate_dynamic_points(challenge.id, challenge.base_points)

    active_instance = None
    if challenge.docker_image_tag:
        active_instance = ActiveInstance.objects.filter(team=team, challenge=challenge, expires_at__gt=timezone.now()).first()

    context = {
        "challenge": challenge,
        "team": team,
        "is_solved": is_solved,
        "current_points": current_points,
        "active_instance": active_instance,
    }
    return render(request, "partials/challenge_detail.html", context)


@login_required
def leaderboard(request):
    team = request.user.teams.first()
    if not team:
        return HttpResponse("You must be part of a team.", status=403)

    session_id = team.session.id
    cache_key = f"leaderboard_ui_{session_id}"
    cached_board = cache.get(cache_key)

    if cached_board is None:
        session_scores = ScoringService.calculate_scores_for_session(session_id)
        teams_qs = Team.objects.filter(session_id=session_id)
        leaderboard_data = [
            {"team": t, "score": session_scores.get(t.id, 0)}
            for t in teams_qs
        ]
        leaderboard_data.sort(key=lambda x: x["score"], reverse=True)
        cached_board = leaderboard_data
        cache.set(cache_key, cached_board, 60)

    return render(request, 'core/leaderboard.html', {'leaderboard': cached_board})


# --- Action Endpoints (HTMX Partial Responders) ---

@require_POST
@login_required
def submit_flag(request, challenge_id):
    challenge = get_object_or_404(Challenge, id=challenge_id)
    flag_payload = request.POST.get('flag', '')

    try:
        success, message = FlagValidationService.validate_submission(request.user, challenge, flag_payload)
        if success:
            return HttpResponse(f'<div class="p-4 mb-4 text-green-200 bg-green-900 rounded border border-green-700">✅ {message}</div>')
        else:
            return HttpResponse(f'<div class="p-4 mb-4 text-red-200 bg-red-900 rounded border border-red-700">❌ {message}</div>')
    except PermissionError as e:
        return HttpResponse(f'<div class="p-4 mb-4 text-yellow-200 bg-yellow-900 rounded border border-yellow-700">🔒 {str(e)}</div>', status=403)
    except ValueError as e:
        return HttpResponse(f'<div class="p-4 mb-4 text-red-200 bg-red-900 rounded border border-red-700">❌ Error: {str(e)}</div>')


@require_POST
@login_required
def submit_writeup(request, challenge_id):
    team_membership = getattr(request.user, 'teammembership', None)
    if team_membership:
        team = team_membership.team
    else:
        team = getattr(request.user, 'teams', None)
        team = team.first() if team else None

    if not team:
        return HttpResponse('<div class="p-4 mb-4 text-red-200 bg-red-900 rounded border border-red-700">❌ Error: You must join a team.</div>')

    content = request.POST.get('writeup_content', '')
    try:
        WriteUpService.submit_writeup(team.id, challenge_id, content)
        return HttpResponse('<div class="p-4 mb-4 text-green-200 bg-green-900 rounded border border-green-700">📝 Write-up saved successfully!</div>')
    except PermissionError as e:
        return HttpResponse(f'<div class="p-4 mb-4 text-red-200 bg-red-900 rounded border border-red-700">❌ Error: {str(e)}</div>', status=403)
    except ValueError as e:
        return HttpResponse(f'<div class="p-4 mb-4 text-red-200 bg-red-900 rounded border border-red-700">❌ Error: {str(e)}</div>', status=400)


@require_POST
@login_required
def create_sos_ticket(request, challenge_id):
    team_membership = getattr(request.user, 'teammembership', None)
    if team_membership:
        team = team_membership.team
    else:
        team = getattr(request.user, 'teams', None)
        team = team.first() if team else None

    if not team:
        return HttpResponse('<div class="p-4 mb-4 text-red-200 bg-red-900 rounded border border-red-700">❌ Error: You must join a team.</div>')

    issue_description = request.POST.get('issue_description', '')
    try:
        SOSTicketService.create_ticket(request.user, team.id, challenge_id, issue_description)
        return HttpResponse('<div class="p-4 mb-4 text-yellow-200 bg-yellow-900/80 rounded border border-yellow-700">🚨 SOS Beacon activated! A mentor will be with you shortly.</div>')
    except Exception as e:
        return HttpResponse(f'<div class="p-4 mb-4 text-red-200 bg-red-900 rounded border border-red-700">❌ Error: {str(e)}</div>', status=400)


def live_cyber_map(request):
    from core.models import SiteSettings as SiteSettingsModel
    site = SiteSettingsModel.load()
    return render(request, 'core/live_map.html', {'is_paused': site.is_ctf_paused})


# --- CTF Builder Engine Views ---

@login_required
def builder_dashboard(request):
    templates = ChallengeTemplate.objects.all().select_related('category')
    return render(request, 'core/builder_dashboard.html', {'templates': templates})


@login_required
def get_template_form(request, template_id):
    template = get_object_or_404(ChallengeTemplate, pk=template_id)
    variables = template.variables.all()
    return render(request, 'partials/template_form.html', {
        'template': template,
        'variables': variables,
    })


@require_POST
@login_required
def submit_built_challenge(request):
    template_id = request.POST.get('template_id')
    category_id = request.POST.get('category_id')
    title = request.POST.get('title', '')
    base_points = int(request.POST.get('base_points', 100))
    # Instructor-supplied description override (falls back to template description in service)
    custom_description = request.POST.get('description', '').strip() or None
    # Internal port override (only relevant for CONTAINER challenges)
    _raw_port = request.POST.get('internal_port', '').strip()
    internal_port = int(_raw_port) if _raw_port.isdigit() else None

    # Extract custom_* fields into a dict
    custom_params = {
        key.replace('custom_', '', 1): value
        for key, value in request.POST.items()
        if key.startswith('custom_') and value
    }

    active_session = CTFSession.objects.filter(is_active=True).first()
    if not active_session:
        return HttpResponse(
            '<div class="p-4 text-red-200 bg-red-900 rounded border border-red-700">'
            '❌ No active CTF session found.</div>',
            status=400
        )

    try:
        challenge = ChallengeBuilderService.build_challenge(
            session_id=active_session.id,
            category_id=category_id,
            template_id=template_id,
            title=title,
            base_points=base_points,
            custom_params_dict=custom_params,
            custom_description=custom_description,
            internal_port=internal_port,
        )
        return HttpResponse(
            f'<div class="p-4 text-green-200 bg-green-900 rounded border border-green-700">'
            f'✅ Challenge <strong>{challenge.title}</strong> deployed successfully! '
            f'(ID: {challenge.id}, Type: {challenge.challenge_type})</div>'
        )
    except ValueError as e:
        return HttpResponse(
            f'<div class="p-4 text-red-200 bg-red-900 rounded border border-red-700">'
            f'❌ Validation Error: {str(e)}</div>',
            status=400
        )
    except Exception as e:
        logger.error(f"Builder Engine failure: {e}")
        return HttpResponse(
            f'<div class="p-4 text-red-200 bg-red-900 rounded border border-red-700">'
            f'❌ Build failed: {str(e)}</div>',
            status=500
        )


def live_cyber_map_data(request):
    data = GameControlService.get_live_map_data()
    return render(request, 'partials/live_map_data.html', data)


@require_POST
@login_required
def toggle_ctf_pause(request):
    try:
        is_paused = GameControlService.toggle_ctf_state(request.user)
        btn_text = "Resume CTF" if is_paused else "Pause CTF"
        btn_color = "bg-green-600 hover:bg-green-700" if is_paused else "bg-red-600 hover:bg-red-700"
        return HttpResponse(
            f'<button hx-post="{reverse("toggle_ctf_pause")}" hx-swap="outerHTML" '
            f'class="{btn_color} text-white px-4 py-2 rounded font-bold transition">{btn_text}</button>'
        )
    except PermissionError as e:
        return HttpResponse(f'<div class="text-red-500">❌ {str(e)}</div>', status=403)


from django.template import engines

@require_POST
@login_required
def spawn_challenge_instance(request, challenge_id):
    challenge = get_object_or_404(Challenge, id=challenge_id)
    team_membership = getattr(request.user, 'teammembership', None)

    team = None
    if team_membership:
        team = team_membership.team
    else:
        team = getattr(request.user, 'teams', None)
        team = team.first() if team else None

    if not team:
        return HttpResponse('<div class="text-red-500">Error: You must join a team.</div>')

    try:
        active_instance = DockerManagerService.spawn_instance(team, challenge)

        html_string = """
        <div class="mt-4 p-4 bg-green-900 border border-green-500 rounded text-center">
            <p class="text-green-300 mb-2">Machine is UP and routable.</p>
            <a href="http://{{ instance.traefik_subdomain }}" target="_blank" class="text-xl font-mono text-green-400 hover:text-green-200 underline">
                http://{{ instance.traefik_subdomain }}
            </a>
            <p class="text-sm text-gray-400 mt-2">Dies automatically in {{ instance.expires_at|timeuntil }}</p>
        </div>
        """
        django_engine = engines['django']
        template = django_engine.from_string(html_string)
        rendered_html = template.render({'instance': active_instance})
        return HttpResponse(rendered_html)

    except Exception as e:
        logger.error(f"Failed to start challenge instance: {e}")
        return HttpResponse(
            f'<div class="p-3 bg-red-900/50 border border-red-700 text-red-200 rounded">Spawn failed: {str(e)}</div>',
            status=503
        )

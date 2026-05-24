from django.urls import path
from django.contrib.auth import views as auth_views
from core import views

urlpatterns = [
    # Landing / Redirect
    path('', views.home, name='home'),
    path('health/ping/', views.health_ping, name='health_ping'),
    
    # Auth
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    
    # Dashboard & Skill Tree
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Challenge Modal Details (HTMX)
    path('challenge/<int:challenge_id>/', views.challenge_detail, name='challenge_detail'),
    
    # Leaderboard
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    
    # Teams
    path('team/', views.team_dashboard, name='team_dashboard'),
    path('team/create/', views.create_team_action, name='create_team_action'),
    path('team/join/', views.join_team_action, name='join_team_action'),
    
    # --- Backend Interceptor Actions ---
    # We keep the core mechanics available, simplified
    path('challenge/<int:challenge_id>/spawn/', views.spawn_challenge_instance, name='spawn_instance'),
    path('challenge/<int:challenge_id>/submit/', views.submit_flag, name='submit_flag'),
    path('challenge/<int:challenge_id>/writeup/', views.submit_writeup, name='submit_writeup'),
    path('challenge/<int:challenge_id>/sos/', views.create_sos_ticket, name='create_sos_ticket'),
    
    # --- Live Map & Admin Controls ---
    path('live/', views.live_cyber_map, name='live_cyber_map'),
    path('live/data/', views.live_cyber_map_data, name='live_cyber_map_data'),
    path('admin/toggle-pause/', views.toggle_ctf_pause, name='toggle_ctf_pause'),

    # --- CTF Builder Engine ---
    path('builder/', views.builder_dashboard, name='builder_dashboard'),
    path('builder/template/<int:template_id>/', views.get_template_form, name='get_template_form'),
    path('builder/submit/', views.submit_built_challenge, name='submit_built_challenge'),

    # --- Challenge Management (Builder) ---
    path('builder/challenges/', views.list_deployed_challenges, name='list_deployed_challenges'),
    path('builder/challenge/<int:challenge_id>/edit/', views.get_challenge_edit_form, name='get_challenge_edit_form'),
    path('builder/challenge/<int:challenge_id>/update/', views.update_challenge, name='update_challenge'),
    path('builder/challenge/<int:challenge_id>/delete/', views.delete_challenge, name='delete_challenge'),
]

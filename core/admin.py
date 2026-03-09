from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, CTFSession, Team, TeamMembership, 
    Category, Challenge, Submission, SiteSettings,
    ActiveInstance, Achievement, TeamAchievement
)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # This ensures your custom fields (role, theme) show up in the Admin
    fieldsets = UserAdmin.fieldsets + (
        ('CTF Profile', {'fields': ('role', 'ui_theme', 'preferred_language')}),
    )
    list_display = ('username', 'email', 'role', 'is_staff')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')

@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'base_points', 'is_entry_node')
    list_filter = ('category', 'session', 'is_tutorial')
    search_fields = ('title', 'description')

@admin.register(CTFSession)
class CTFSessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'scoring_mode', 'start_time')

# Register the infrastructure and auditing models
admin.site.register(Team)
admin.site.register(TeamMembership)
admin.site.register(Submission)
admin.site.register(ActiveInstance)
admin.site.register(Achievement)
admin.site.register(TeamAchievement)
admin.site.register(SiteSettings)
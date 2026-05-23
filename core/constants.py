from django.db import models
from django.utils.translation import gettext_lazy as _

# --- Database Field Limits ---
MAX_CHAR_LENGTH_SHORT = 50
MAX_CHAR_LENGTH_MEDIUM = 100
MAX_CHAR_LENGTH_LONG = 255
MAX_URL_LENGTH = 500
HASH_LENGTH_SHA256 = 64

# --- Gameplay & Infrastructure Defaults ---
DEFAULT_BASE_POINTS = 500
MINIMUM_DYNAMIC_POINTS = 100
DYNAMIC_DEGRADATION_STEP = 10
INSTANCE_LIFESPAN_MINUTES = 60  # 60 minutes for Docker containers
HEARTBEAT_INTERVAL_SECONDS = 15

# --- Docker Resource Constraints ---
DOCKER_MEM_LIMIT = "256m"
DOCKER_MEMSWAP_LIMIT = "256m"
DOCKER_NANO_CPUS = 500000000  # 0.5 CPU
DOCKER_RESTART_POLICY = {"Name": "no"}
DEFAULT_TRAEFIK_NETWORK = "ctfacile_traefik_public"

# --- Django Enums (TextChoices) ---


class ScoringMode(models.TextChoices):
    STATIC = "STATIC", _("Static Scoring")
    DYNAMIC = "DYNAMIC", _("Dynamic Scoring")


class LanguageLock(models.TextChoices):
    NONE = "NONE", _("No Lock (User Preference)")
    EN = "EN", _("English Locked")
    FR = "FR", _("French Locked")


class UserRole(models.TextChoices):
    ADMIN = "ADMIN", _("Administrator")
    PROF = "PROF", _("Professor")
    STUDENT = "STUDENT", _("Student")


class UITheme(models.TextChoices):
    LIGHT = "LIGHT", _("Light Mode")
    DARK = "DARK", _("Dark Mode")
    HACKER = "HACKER", _("Hacker Mode (Matrix)")


class TicketStatus(models.TextChoices):
    OPEN = "OPEN", _("Open")
    IN_PROGRESS = "IN_PROGRESS", _("In Progress")
    RESOLVED = "RESOLVED", _("Resolved")


class TriggerType(models.TextChoices):
    FIRST_BLOOD = "FIRST_BLOOD", _("First Blood")
    ATTEMPT_COUNT = "ATTEMPT_COUNT", _("Attempt Count")
    SOLVE_STREAK = "SOLVE_STREAK", _("Solve Streak")

import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from core import constants

# --- Module A: Identity, Sessions & Teams ---


class CTFSession(models.Model):
    name = models.CharField(max_length=constants.MAX_CHAR_LENGTH_MEDIUM)
    is_active = models.BooleanField(default=False)
    scoring_mode = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_SHORT,
        choices=constants.ScoringMode.choices,
        default=constants.ScoringMode.STATIC.value,
    )
    language_lock = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_SHORT,
        choices=constants.LanguageLock.choices,
        default=constants.LanguageLock.NONE.value,
    )
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    role = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_SHORT,
        choices=constants.UserRole.choices,
        default=constants.UserRole.STUDENT.value,
    )
    ui_theme = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_SHORT,
        choices=constants.UITheme.choices,
        default=constants.UITheme.LIGHT.value,
    )
    preferred_language = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_SHORT,
        choices=constants.LanguageLock.choices,
        default=constants.LanguageLock.NONE.value,
    )

    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name="groups",
        blank=True,
        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
        related_name="custom_user_groups",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name="user permissions",
        blank=True,
        help_text="Specific permissions for this user.",
        related_name="custom_user_permissions",
        related_query_name="user",
    )

    def __str__(self):
        return self.username


class Team(models.Model):
    session = models.ForeignKey(
        CTFSession, on_delete=models.CASCADE, related_name="teams"
    )
    name = models.CharField(max_length=constants.MAX_CHAR_LENGTH_MEDIUM)
    join_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    members = models.ManyToManyField(
        User, through="TeamMembership", related_name="teams"
    )

    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "team")


# --- Module B: The Gamified Skill Tree & Challenges ---


class Category(models.Model):
    name = models.CharField(max_length=constants.MAX_CHAR_LENGTH_MEDIUM)
    description = models.TextField()

    def __str__(self):
        return self.name


class ChallengeTemplate(models.Model):
    """Elementary Brick — a reusable template that instructors use to generate challenges."""
    name = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_MEDIUM,
        help_text="e.g. 'Basic SQL Injection', 'XSS Reflected'"
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="templates"
    )
    description = models.TextField(
        help_text="Explains the pedagogical goal and vulnerability covered by this brick."
    )
    base_docker_image = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_LONG,
        help_text="Docker image shipped with the brick (e.g. vulnerable-nginx-php)"
    )
    vulnerability_type = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_SHORT,
        help_text="Canonical tag: sqli, xss, lfi, rce, idor, etc."
    )

    def __str__(self):
        return f"[{self.vulnerability_type.upper()}] {self.name}"


class TemplateVariable(models.Model):
    """Defines a configurable parameter that an instructor can set when instantiating a template."""
    template = models.ForeignKey(
        ChallengeTemplate, on_delete=models.CASCADE, related_name="variables"
    )
    key_name = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_MEDIUM,
        help_text="Environment variable key injected into the container (e.g. FLAG_FORMAT, DB_PASSWORD)"
    )
    default_value = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_LONG, blank=True, default=""
    )
    is_required = models.BooleanField(default=False)

    class Meta:
        unique_together = ("template", "key_name")

    def __str__(self):
        return f"{self.template.name} :: {self.key_name}"


class Challenge(models.Model):
    session = models.ForeignKey(
        CTFSession, on_delete=models.CASCADE, related_name="challenges"
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="challenges"
    )
    title = models.CharField(max_length=constants.MAX_CHAR_LENGTH_MEDIUM)
    description = models.TextField()
    base_points = models.IntegerField(default=constants.DEFAULT_BASE_POINTS)
    flag_hash = models.CharField(max_length=constants.HASH_LENGTH_SHA256)
    is_tutorial = models.BooleanField(default=False)
    is_entry_node = models.BooleanField(default=False)
    docker_image_tag = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_LONG, null=True, blank=True
    )
    challenge_type = models.CharField(
        max_length=50,
        choices=[('STATIC', 'Static'), ('CONTAINER', 'Containerized')],
        default='STATIC'
    )
    internal_port = models.IntegerField(
        default=80,
        help_text="The internal port the container listens on (e.g., 80 for Nginx, 5000 for Flask)"
    )
    # --- CTF Builder fields ---
    template = models.ForeignKey(
        ChallengeTemplate,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="challenges",
        help_text="Optional: the Elementary Brick this challenge was generated from."
    )
    custom_parameters = models.JSONField(
        default=dict, blank=True,
        help_text='Instructor-configured values for template variables, e.g. {"FLAG": "FLAG{custom123}"}'
    )
    attachment = models.FileField(
        upload_to='challenges/attachments/',
        null=True, blank=True,
        help_text="Optional file attachment (e.g., forensics evidence, pcap, stego image)"
    )

    def __str__(self):
        return self.title


class ChallengePrerequisite(models.Model):
    target_challenge = models.ForeignKey(
        Challenge, on_delete=models.CASCADE, related_name="prerequisites"
    )
    required_challenge = models.ForeignKey(
        Challenge, on_delete=models.CASCADE, related_name="unlocks_challenges"
    )

    class Meta:
        unique_together = ("target_challenge", "required_challenge")


# --- Module C: Infrastructure & State ---


class ActiveInstance(models.Model):
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="active_instances"
    )
    challenge = models.ForeignKey(
        Challenge, on_delete=models.CASCADE, related_name="active_instances"
    )
    container_id = models.CharField(max_length=constants.MAX_CHAR_LENGTH_LONG)
    traefik_subdomain = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_LONG, unique=True
    )
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"{self.team.name} - {self.challenge.title}"


# --- Module D: Immutable Auditing & Education ---


class Submission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submissions")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="submissions")
    challenge = models.ForeignKey(
        Challenge, on_delete=models.CASCADE, related_name="submissions"
    )
    submitted_payload = models.TextField()
    is_correct = models.BooleanField(default=False, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"Submission by {self.user.username} for {self.challenge.title} - {'Correct' if self.is_correct else 'Incorrect'}"


class WriteUp(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="writeups")
    challenge = models.ForeignKey(
        Challenge, on_delete=models.CASCADE, related_name="writeups"
    )
    content = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"WriteUp by {self.team.name} for {self.challenge.title}"


class SOSTicket(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="sos_tickets")
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sos_tickets",
    )
    issue_description = models.TextField()
    status = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_SHORT,
        choices=constants.TicketStatus.choices,
        default=constants.TicketStatus.OPEN.value,
    )

    def __str__(self):
        return f"SOS Ticket from {self.team.name}"


class Achievement(models.Model):
    title = models.CharField(max_length=constants.MAX_CHAR_LENGTH_MEDIUM)
    description = models.TextField()
    trigger_type = models.CharField(
        max_length=constants.MAX_CHAR_LENGTH_SHORT,
        choices=constants.TriggerType.choices,
        default=constants.TriggerType.FIRST_BLOOD.value,
    )
    threshold_value = models.IntegerField()
    is_secret = models.BooleanField(default=False)
    icon_reference = models.CharField(max_length=constants.MAX_CHAR_LENGTH_LONG)

    def __str__(self):
        return self.title


class TeamAchievement(models.Model):
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="achievements"
    )
    achievement = models.ForeignKey(
        Achievement, on_delete=models.CASCADE, related_name="unlocked_by"
    )
    unlocked_at = models.DateTimeField(auto_now_add=True)
    unlocked_by_user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("team", "achievement")

    def __str__(self):
        return f"{self.team.name} unlocked {self.achievement.title}"


# --- Module E: Global Controls ---


class SiteSettings(models.Model):
    is_ctf_paused = models.BooleanField(default=False)
    global_announcement = models.TextField(blank=True)
    discord_webhook_url = models.URLField(
        max_length=constants.MAX_URL_LENGTH, blank=True
    )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Global Site Settings"

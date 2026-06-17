import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models


class Tournament(models.Model):
    class Format(models.TextChoices):
        LEAGUE = "league", "League"
        KNOCKOUT = "knockout", "Knockout"
        GROUP_AND_KNOCKOUT = "group_and_knockout", "Group + Knockout"
        UEFA_LEAGUE_PHASE = "uefa_league_phase", "UEFA League Phase"

    class Mode(models.TextChoices):
        SINGLE_LEG = "single_leg", "Single Leg"
        HOME_AWAY = "home_away", "Home & Away"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    format = models.CharField(max_length=20, choices=Format.choices, default=Format.LEAGUE)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.SINGLE_LEG)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="managed_tournaments"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tournaments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} [{self.get_format_display()}]"


class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=150)
    player_name = models.CharField(max_length=10,default='Player')
    founded_year = models.PositiveSmallIntegerField(null=True, blank=True)
    country = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "teams"
        ordering = ["name"]
        unique_together = [("tournament", "player_name")]

    def __str__(self):
        return f"{self.name} ({self.tournament.name})"


class AuditLog(models.Model):
    ACTION_LEVELS = [
        ('INFO', 'Information'),
        ('WARN', 'Modification'),
        ('CRIT', 'Destructive/Purge'),
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=50)  # e.g., "TOURNAMENT_DELETE", "TEAM_CREATE"
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=ACTION_LEVELS, default='INFO')
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} - {self.action_type}"


class Group(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(max_length=50)  # "Group A", "Group B" …
    teams = models.ManyToManyField(Team, related_name="groups", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "groups"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} — {self.tournament.name}"


class Fixture(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        PLAYED = "played", "Played"
        POSTPONED = "postponed", "Postponed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="fixtures")
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name="fixtures")
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="home_fixtures")
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="away_fixtures")

    round = models.PositiveSmallIntegerField(default=1)
    match_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)

    home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score = models.PositiveSmallIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fixtures"
        ordering = ["match_date", "round"]

    @property
    def is_played(self):
        return self.status == self.Status.PLAYED

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} — {self.match_date}"
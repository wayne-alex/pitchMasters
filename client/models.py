from django.db import models

from tournament.models import Tournament, Team, Fixture


# Create your models here.
class DeviceUserPreference(models.Model):
    device_uuid = models.UUIDField(unique=True, db_index=True)
    favorite_tournaments = models.ManyToManyField(Tournament, blank=True, related_name="favorited_by")
    favorite_fixtures = models.ManyToManyField(Fixture, blank=True, related_name='favored_by')
    favorite_teams = models.ManyToManyField(Team, blank=True, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "device_user_preferences"

    def __str__(self):
        return f"Preferences for {self.device_uuid}"
from django.db import models

# Create your models here.
from apps.alliance.models import Alliance


class Corporation(models.Model):
    alliance_id = models.BigIntegerField(null=True)
    ceo_id = models.BigIntegerField()
    creator_id = models.BigIntegerField()
    date_founded = models.DateTimeField(null=True)
    description = models.TextField(null=True)
    faction_id = models.BigIntegerField(null=True)
    home_station_id = models.BigIntegerField(null=True)
    member_count = models.IntegerField()
    name = models.CharField(max_length=100)
    shares = models.IntegerField(null=True)
    tax_rate = models.FloatField()
    ticker = models.CharField(max_length=6)
    url = models.URLField(default='')
    war_eligible = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class CorporationIcon(models.Model):
    corporation = models.OneToOneField(
        Corporation, on_delete=models.CASCADE, primary_key=True
    )
    px64x64 = models.URLField()
    px128x128 = models.URLField()


class CorporationAllianceHistory(models.Model):
    corporation_id = models.ForeignKey(Corporation, on_delete=models.CASCADE)
    alliance_id = models.ForeignKey(Alliance, on_delete=models.CASCADE, null=True)
    start_date = models.DateTimeField()
    record_id = models.IntegerField()
    is_deleted = models.BooleanField(default=False)

    class Meta:
        unique_together = ('corporation_id', 'alliance_id', 'record_id')

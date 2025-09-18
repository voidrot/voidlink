from django.db import models

# Create your models here.


class Alliance(models.Model):
    creator_corporation_id = models.BigIntegerField()
    creator_id = models.BigIntegerField()
    date_founded = models.DateTimeField()
    executor_corporation_id = models.BigIntegerField(null=True)
    faction_id = models.BigIntegerField(
        null=True,
        help_text='The faction the alliance is aligned with if enrolled in faction warfare.',
    )
    name = models.CharField(max_length=100)
    ticker = models.CharField(max_length=6)


class AllianceIcon(models.Model):
    alliance = models.OneToOneField(
        Alliance, on_delete=models.CASCADE, primary_key=True
    )
    px64x64 = models.URLField()
    px128x128 = models.URLField()

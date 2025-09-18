import logging

from celery import shared_task
from django.utils import timezone

from apps.shared.providers import esi
from apps.wars.models import War
from apps.wars.operations import _get_war_details
from apps.wars.operations import _get_war_killmails

logger = logging.getLogger(__name__)


@shared_task
def get_wars():
    logger.debug('Fetching wars from ESI')
    op = esi.client.Wars.GetWars()
    res = op.results()
    finished_wars = War.objects.filter(finished__lt=timezone.now()).values_list(
        'id', flat=True
    )
    for war_id in res:
        if war_id in finished_wars:
            logger.debug(f'War {war_id} has finished')
            continue
        logger.debug(f'Queueing war details fetch for war ID {war_id}')
        get_war_details.apply_async(kwargs={'war_id': war_id})  # pyright: ignore[reportCallIssue]
        # TODO: Add call to killmails tasks to collect all killmails for a war
    logger.debug(f'Fetched {len(res)} wars from ESI')


@shared_task(rate_limit='30/m')
def get_war_details(war_id: int):
    _get_war_details(war_id)


@shared_task(rate_limit='30/m')
def get_war_killmails(war_id: int):
    _get_war_killmails(war_id)

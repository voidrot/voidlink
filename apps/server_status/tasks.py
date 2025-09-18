import logging

from celery import shared_task

from apps.server_status.models import ServerStatus
from apps.shared.providers import esi

logger = logging.getLogger(__name__)


@shared_task()
def fetch_server_status():
    """Query the EVE Online server status endpoint."""

    logger.debug('Fetching server status from ESI')
    op = esi.client.Status.GetStatus()
    response = op.result()
    logger.debug('Server status response: %s', response)
    ServerStatus(
        player_count=response.players,
        server_version=response.server_version,
        start_time=response.start_time,
        vip_mode=response.vip if response.vip is not None else False,
    ).save()

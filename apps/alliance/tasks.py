import logging

from celery import shared_task

from apps.alliance.models import Alliance
from apps.alliance.operations import _get_alliance_icon
from apps.alliance.operations import _get_alliance_info
from apps.shared.providers import esi

logger = logging.getLogger(__name__)


# No rate limit for this task since it is controlled by celery beat
@shared_task
def get_alliance_list() -> None:
    """
    Fetch the list of all alliances from ESI and dispatch tasks to fetch info and corporations for each.
    """
    logger.info('Fetching alliance list')
    op = esi.client.Alliance.GetAlliances()
    res = op.results()
    logger.info('Fetched %d alliances', len(res))
    for alliance_id in res:
        get_alliance_info.delay(alliance_id)
        get_alliance_corporations.delay(alliance_id)


@shared_task(rate_limit='30/m')
def get_alliance_info(alliance_id: int) -> None:
    """
    Fetch and update info for a specific alliance by ID.
    
    Parameters:
        alliance_id (int): The ID of the alliance to fetch info for.
    """
    _get_alliance_info(alliance_id)


@shared_task(rate_limit='30/m')
def get_alliance_corporations(alliance_id: int) -> None:
    """
    Fetch and log the corporations for a specific alliance by ID.
    
    Parameters:
        alliance_id (int): The ID of the alliance to fetch corporations for.
    """
    logger.info('Fetching corporations for alliance ID: %d', alliance_id)
    op = esi.client.Alliance.GetAlliancesAllianceIdCorporations(alliance_id=alliance_id)
    res = op.result()
    logger.info('Fetched %d corporations for alliance ID: %d', len(res), alliance_id)


@shared_task
def get_alliance_icons() -> None:
    """
    Dispatch tasks to fetch icons for all alliances in the database.
    """
    alliances = Alliance.objects.all().values_list('id', flat=True)
    for alliance_id in alliances:
        get_alliance_icon.delay(kwargs={'alliance_id': alliance_id})


@shared_task(rate_limit='30/m')
def get_alliance_icon(alliance_id: int) -> None:
    """
    Fetch and update the icon for a specific alliance by ID.
    
    Parameters:
        alliance_id (int): The ID of the alliance to fetch the icon for.
    """
    _get_alliance_icon(alliance_id)

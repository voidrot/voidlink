import logging

from apps.alliance.models import Alliance
from apps.alliance.models import AllianceIcon
from apps.esi.decorators import wait_for_esi_errorlimit_reset
from apps.shared.providers import esi

logger = logging.getLogger(__name__)


@wait_for_esi_errorlimit_reset()
def _get_alliance_info(alliance_id: int):
    """
    Fetch alliance info from ESI and update or create the Alliance record.

    Parameters:
        alliance_id (int): The ID of the alliance to fetch info for.
    """
    logger.info('Fetching info for alliance ID: %d', alliance_id)
    op = esi.client.Alliance.GetAlliancesAllianceId(alliance_id=alliance_id)
    res = op.result()
    logger.info('Fetched info for alliance ID: %d', alliance_id)
    logger.debug('Alliance info: %s', res)
    Alliance.objects.update_or_create(
        id=alliance_id,
        defaults={
            'creator_corporation_id': res.creator_corporation_id,
            'creator_id': res.creator_id,
            'date_founded': res.date_founded,
            'executor_corporation_id': res.executor_corporation_id,
            'faction_id': res.faction_id,
            'name': res.name,
            'ticker': res.ticker,
        },
    )


@wait_for_esi_errorlimit_reset()
def _get_alliance_icon(alliance_id: int) -> None:
    """
    Fetch alliance icon data from ESI and update or create the AllianceIcon record.

    Parameters:
        alliance_id (int): The ID of the alliance to fetch icon data for.
    """
    logger.info('Fetching icons for alliance ID: %d', alliance_id)
    op = esi.client.Alliance.GetAlliancesAllianceIdIcons(alliance_id=alliance_id)
    res = op.results()
    AllianceIcon.objects.update_or_create(
        alliance_id=alliance_id,
        defaults={
            'px64x64': res.px64x64,
            'px128x128': res.px128x128,
        },
    )
    logger.info('Fetched icons for alliance ID: %d', alliance_id)

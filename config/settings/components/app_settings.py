from pathlib import Path

from config.env import BASE_DIR
from config.env import env

# SDE
SDE_WORKSPACE = Path(BASE_DIR / '.sde_workspace')
SDE_ARCHIVE_URL = (
    'https://eve-static-data-export.s3-eu-west-1.amazonaws.com/tranquility/sde.zip'
)
SDE_CHECKSUM_URL = (
    'https://eve-static-data-export.s3-eu-west-1.amazonaws.com/tranquility/checksum'
)
SDE_CHECKSUM_FILE = SDE_WORKSPACE / 'checksum'
SDE_HOBOLEAKS_BASE_URL = 'https://sde.hoboleaks.space/tq/'

ESI_SCOPES = {
    'publicData': 'Allows reading public data',
    'esi-calendar.respond_calendar_events.v1': 'Allows responding to calendar events',
    'esi-calendar.read_calendar_events.v1': 'Allows reading calendar events',
    'esi-location.read_location.v1': 'Allows reading location data',
    'esi-location.read_ship_type.v1': 'Allows reading ship type data',
    'esi-mail.organize_mail.v1': 'Allows organizing mail',
    'esi-mail.read_mail.v1': 'Allows reading mail',
    'esi-mail.send_mail.v1': 'Allows sending mail',
    'esi-skills.read_skills.v1': 'Allows reading skills',
    'esi-skills.read_skillqueue.v1': 'Allows reading skill queue',
    'esi-wallet.read_character_wallet.v1': 'Allows reading character wallet',
    'esi-wallet.read_corporation_wallet.v1': 'Allows reading corporation wallet',
    'esi-search.search_structures.v1': 'Allows searching structures',
    'esi-clones.read_clones.v1': 'Allows reading clones',
    'esi-characters.read_contacts.v1': 'Allows reading contacts',
    'esi-universe.read_structures.v1': 'Allows reading structures',
    'esi-killmails.read_killmails.v1': 'Allows reading killmails',
    'esi-corporations.read_corporation_membership.v1': 'Allows reading corporation membership',
    'esi-assets.read_assets.v1': 'Allows reading assets',
    'esi-planets.manage_planets.v1': 'Allows managing planets',
    'esi-fleets.read_fleet.v1': 'Allows reading fleet information',
    'esi-fleets.write_fleet.v1': 'Allows writing fleet information',
    'esi-ui.open_window.v1': 'Allows opening a UI window',
    'esi-ui.write_waypoint.v1': 'Allows writing a waypoint',
    'esi-characters.write_contacts.v1': 'Allows writing contacts',
    'esi-fittings.read_fittings.v1': 'Allows reading fittings',
    'esi-fittings.write_fittings.v1': 'Allows writing fittings',
    'esi-markets.structure_markets.v1': 'Allows accessing structure markets',
    'esi-corporations.read_structures.v1': 'Allows reading corporation structures',
    'esi-characters.read_loyalty.v1': 'Allows reading loyalty points',
    'esi-characters.read_chat_channels.v1': 'Allows reading chat channels',
    'esi-characters.read_medals.v1': 'Allows reading medals',
    'esi-characters.read_standings.v1': 'Allows reading standings',
    'esi-characters.read_agents_research.v1': 'Allows reading agents research',
    'esi-characters.read_implants.v1': 'Allows reading implants',
    'esi-industry.read_character_jobs.v1': 'Allows reading character jobs',
    'esi-markets.read_character_orders.v1': 'Allows reading character orders',
    'esi-characters.read_blueprints.v1': 'Allows reading blueprints',
    'esi-characters.read_corporation_roles.v1': 'Allows reading corporation roles',
    'esi-location.read_online.v1': 'Allows reading online status',
    'esi-contracts.read_character_contracts.v1': 'Allows reading character contracts',
    'esi-clones.read_implants.v1': 'Allows reading implants',
    'esi-characters.read_fatigue.v1': 'Allows reading fatigue',
    'esi-killmails.read_corporation_killmails.v1': 'Allows reading corporation killmails',
    'esi-corporations.track_members.v1': 'Allows tracking corporation members',
    'esi-wallet.read_corporation_wallets.v1': 'Allows reading corporation wallets',
    'esi-characters.read_notifications.v1': 'Allows reading notifications',
    'esi-corporations.read_divisions.v1': 'Allows reading corporation divisions',
    'esi-corporations.read_contacts.v1': 'Allows reading corporation contacts',
    'esi-assets.read_corporation_assets.v1': 'Allows reading corporation assets',
    'esi-corporations.read_titles.v1': 'Allows reading corporation titles',
    'esi-corporations.read_blueprints.v1': 'Allows reading corporation blueprints',
    'esi-contracts.read_corporation_contracts.v1': 'Allows reading corporation contracts',
    'esi-corporations.read_standings.v1': 'Allows reading corporation standings',
    'esi-corporations.read_starbases.v1': 'Allows reading corporation starbases',
    'esi-industry.read_corporation_jobs.v1': 'Allows reading corporation jobs',
    'esi-markets.read_corporation_orders.v1': 'Allows reading corporation orders',
    'esi-corporations.read_container_logs.v1': 'Allows reading corporation container logs',
    'esi-industry.read_character_mining.v1': 'Allows reading character mining',
    'esi-industry.read_corporation_mining.v1': 'Allows reading corporation mining',
    'esi-planets.read_customs_offices.v1': 'Allows reading customs offices',
    'esi-characters.read_customs_offices.v1': 'Allows reading customs offices',
    'esi-corporations.read_facilities.v1': 'Allows reading corporation facilities',
    'esi-corporations.read_medals.v1': 'Allows reading corporation medals',
    'esi-characters.read_titles.v1': 'Allows reading character titles',
    'esi-alliances.read_contacts.v1': 'Allows reading alliance contacts',
    'esi-characters.read_fw_stats.v1': 'Allows reading character FW stats',
    'esi-corporations.read_fw_stats.v1': 'Allows reading corporation FW stats',
    'esi-corporations.read_projects.v1': 'Allows reading corporation projects',
}

ESI_REDIS_URL = env('REDIS_ESI_CACHE_URL', default='redis://redis:6379/1')

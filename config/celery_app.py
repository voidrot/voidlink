import os

from celery import Celery
from celery.signals import setup_logging
from django.conf import settings
from kombu import Exchange
from kombu import Queue

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('voidlink')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')


# Configure multiple queues and exchanges
app.conf.task_queues = (
    Queue('default', Exchange('default'), routing_key='default'),
    Queue('users', Exchange('users'), routing_key='users'),
    Queue('esi', Exchange('esi'), routing_key='esi'),
    Queue(
        'esi_server_status',
        Exchange('esi_server_status'),
        routing_key='esi_server_status',
    ),
    Queue('esi_alliance', Exchange('esi_alliance'), routing_key='esi_alliance'),
    Queue('esi_asset', Exchange('esi_asset'), routing_key='esi_asset'),
    Queue('esi_character', Exchange('esi_character'), routing_key='esi_character'),
    Queue('esi_clones', Exchange('esi_clones'), routing_key='esi_clones'),
    Queue('esi_contacts', Exchange('esi_contacts'), routing_key='esi_contacts'),
    Queue('esi_contracts', Exchange('esi_contracts'), routing_key='esi_contracts'),
    Queue(
        'esi_corporation', Exchange('esi_corporation'), routing_key='esi_corporation'
    ),
    Queue(
        'esi_faction_warfare',
        Exchange('esi_faction_warfare'),
        routing_key='esi_faction_warfare',
    ),
    Queue('esi_fittings', Exchange('esi_fittings'), routing_key='esi_fittings'),
    Queue('esi_fleets', Exchange('esi_fleets'), routing_key='esi_fleets'),
    Queue('esi_incursions', Exchange('esi_incursions'), routing_key='esi_incursions'),
    Queue('esi_industry', Exchange('esi_industry'), routing_key='esi_industry'),
    Queue('esi_insurance', Exchange('esi_insurance'), routing_key='esi_insurance'),
    Queue('esi_killmails', Exchange('esi_killmails'), routing_key='esi_killmails'),
    Queue('esi_location', Exchange('esi_location'), routing_key='esi_location'),
    Queue('esi_loyalty', Exchange('esi_loyalty'), routing_key='esi_loyalty'),
    Queue('esi_mail', Exchange('esi_mail'), routing_key='esi_mail'),
    Queue('esi_market', Exchange('esi_market'), routing_key='esi_market'),
    Queue(
        'esi_planetary_interaction',
        Exchange('esi_planetary_interaction'),
        routing_key='esi_planetary_interaction',
    ),
    Queue('esi_skills', Exchange('esi_skills'), routing_key='esi_skills'),
    Queue(
        'esi_sovereignty', Exchange('esi_sovereignty'), routing_key='esi_sovereignty'
    ),
    Queue('esi_wallet', Exchange('esi_wallet'), routing_key='esi_wallet'),
    Queue('esi_wars', Exchange('esi_wars'), routing_key='esi_wars'),
)

app.conf.task_default_queue = 'default'
app.conf.task_default_exchange = 'default'
app.conf.task_default_exchange_type = 'direct'
app.conf.task_default_routing_key = 'default'

app.conf.task_routes = {
    'apps.esi.tasks.*': {'queue': 'esi', 'exchange': 'esi', 'routing_key': 'esi'},
    'apps.server_status.tasks.*': {
        'queue': 'esi_server_status',
        'exchange': 'esi_server_status',
        'routing_key': 'esi_server_status',
    },
    'apps.wars.tasks.*': {
        'queue': 'esi_wars',
        'exchange': 'esi_wars',
        'routing_key': 'esi_wars',
    },
    'apps.alliance.tasks.*': {
        'queue': 'esi_alliance',
        'exchange': 'esi_alliance',
        'routing_key': 'esi_alliance',
    },
    'apps.asset.tasks.*': {
        'queue': 'esi_asset',
        'exchange': 'esi_asset',
        'routing_key': 'esi_asset',
    },
    'apps.character.tasks.*': {
        'queue': 'esi_character',
        'exchange': 'esi_character',
        'routing_key': 'esi_character',
    },
    'apps.clones.tasks.*': {
        'queue': 'esi_clones',
        'exchange': 'esi_clones',
        'routing_key': 'esi_clones',
    },
    'apps.contacts.tasks.*': {
        'queue': 'esi_contacts',
        'exchange': 'esi_contacts',
        'routing_key': 'esi_contacts',
    },
    'apps.contracts.tasks.*': {
        'queue': 'esi_contracts',
        'exchange': 'esi_contracts',
        'routing_key': 'esi_contracts',
    },
    'apps.corporation.tasks.*': {
        'queue': 'esi_corporation',
        'exchange': 'esi_corporation',
        'routing_key': 'esi_corporation',
    },
    'apps.faction_warfare.tasks.*': {
        'queue': 'esi_faction_warfare',
        'exchange': 'esi_faction_warfare',
        'routing_key': 'esi_faction_warfare',
    },
    'apps.fittings.tasks.*': {
        'queue': 'esi_fittings',
        'exchange': 'esi_fittings',
        'routing_key': 'esi_fittings',
    },
    'apps.fleets.tasks.*': {
        'queue': 'esi_fleets',
        'exchange': 'esi_fleets',
        'routing_key': 'esi_fleets',
    },
    'apps.incursions.tasks.*': {
        'queue': 'esi_incursions',
        'exchange': 'esi_incursions',
        'routing_key': 'esi_incursions',
    },
    'apps.industry.tasks.*': {
        'queue': 'esi_industry',
        'exchange': 'esi_industry',
        'routing_key': 'esi_industry',
    },
    'apps.insurance.tasks.*': {
        'queue': 'esi_insurance',
        'exchange': 'esi_insurance',
        'routing_key': 'esi_insurance',
    },
    'apps.killmails.tasks.*': {
        'queue': 'esi_killmails',
        'exchange': 'esi_killmails',
        'routing_key': 'esi_killmails',
    },
    'apps.location.tasks.*': {
        'queue': 'esi_location',
        'exchange': 'esi_location',
        'routing_key': 'esi_location',
    },
    'apps.loyalty.tasks.*': {
        'queue': 'esi_loyalty',
        'exchange': 'esi_loyalty',
        'routing_key': 'esi_loyalty',
    },
    'apps.mail.tasks.*': {
        'queue': 'esi_mail',
        'exchange': 'esi_mail',
        'routing_key': 'esi_mail',
    },
    'apps.market.tasks.*': {
        'queue': 'esi_market',
        'exchange': 'esi_market',
        'routing_key': 'esi_market',
    },
    'apps.planetary_interaction.tasks.*': {
        'queue': 'esi_planetary_interaction',
        'exchange': 'esi_planetary_interaction',
        'routing_key': 'esi_planetary_interaction',
    },
    'apps.skills.tasks.*': {
        'queue': 'esi_skills',
        'exchange': 'esi_skills',
        'routing_key': 'esi_skills',
    },
    'apps.sovereignty.tasks.*': {
        'queue': 'esi_sovereignty',
        'exchange': 'esi_sovereignty',
        'routing_key': 'esi_sovereignty',
    },
    'apps.wallet.tasks.*': {
        'queue': 'esi_wallet',
        'exchange': 'esi_wallet',
        'routing_key': 'esi_wallet',
    },
    'apps.users.tasks.*': {
        'queue': 'users',
        'exchange': 'users',
        'routing_key': 'users',
    },
}


@setup_logging.connect
def config_loggers(*args, **kwargs):
    from logging.config import dictConfig  # noqa: PLC0415

    dictConfig(settings.LOGGING)


# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

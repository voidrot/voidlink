import ssl

from celery.schedules import crontab

from config.env import env
from config.settings.components.common import TIME_ZONE
from config.settings.components.common import USE_TZ

REDIS_URL = env('REDIS_CELERY_URL', default='redis://redis:6379/5')  # type: ignore  # noqa: PGH003
REDIS_SSL = REDIS_URL.startswith('rediss://')  # type: ignore  # noqa: PGH003

if USE_TZ:
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE = TIME_ZONE
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL = REDIS_URL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#redis-backend-use-ssl
CELERY_BROKER_USE_SSL = {'ssl_cert_reqs': ssl.CERT_NONE} if REDIS_SSL else None
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND = REDIS_URL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#redis-backend-use-ssl
CELERY_REDIS_BACKEND_USE_SSL = CELERY_BROKER_USE_SSL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-extended
CELERY_RESULT_EXTENDED = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-always-retry
# https://github.com/celery/celery/pull/6122
CELERY_RESULT_BACKEND_ALWAYS_RETRY = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-max-retries
CELERY_RESULT_BACKEND_MAX_RETRIES = 10
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT = ['json']
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER = 'json'
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER = 'json'
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-time-limit
# TODO: set to whatever value is adequate in your circumstances
CELERY_TASK_TIME_LIMIT = 5 * 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-soft-time-limit
# TODO: set to whatever value is adequate in your circumstances
CELERY_TASK_SOFT_TIME_LIMIT = 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#beat-scheduler
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#worker-send-task-events
CELERY_WORKER_SEND_TASK_EVENTS = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std-setting-task_send_sent_event
CELERY_TASK_SEND_SENT_EVENT = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#worker-hijack-root-logger
CELERY_WORKER_HIJACK_ROOT_LOGGER = False


CELERY_BEAT_SCHEDULE = {
    'esi_cleanup_callbackredirect': {
        'task': 'apps.esi.tasks.cleanup_callbackredirect',
        'schedule': crontab(hour='*/4'),
    },
    'esi_cleanup_token_subset': {  # 1/48th * 1hr = 48Hr/2Day Refresh Cycles.
        'task': 'apps.esi.tasks.cleanup_token_subset',
        'schedule': crontab(minute='0', hour='*/1'),
    },
    # Server Status Jobs
    'server_status_query': {
        'task': 'apps.server_status.tasks.fetch_server_status',
        'schedule': 30.0,  # every 30 seconds
    },
    # Wars Jobs
    'get_wars': {  # This will queue up jobs to get ware info and killmails for active wars
        'task': 'apps.wars.tasks.get_wars',
        'schedule': crontab(minute='0', hour='*/1'),  # every hour
    },
    # Alliance Jobs
    'get_alliance_list': {
        'task': 'apps.alliance.tasks.get_alliance_list',
        'schedule': crontab(minute='0', hour='*/1'),  # every hour
    },
    'get_alliance_icons': {
        'task': 'apps.alliance.tasks.get_alliance_icons',
        'schedule': crontab(minute='45', hour='11'),  # every day at 11:45 UTC
    },
}

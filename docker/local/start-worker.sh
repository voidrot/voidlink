#!/usr/bin/env bash

set -o errexit
set -o pipefail
set -o nounset

watchmedo auto-restart --directory=./apps --directory=./config --pattern=*.py --recursive -- celery -A config.celery_app worker -n "${CELERY_QUEUE:-default}" -l DEBUG -Q "${CELERY_QUEUE:-default}"
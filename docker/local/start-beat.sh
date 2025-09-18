#!/usr/bin/env bash

set -o errexit
set -o pipefail
set -o nounset


watchmedo auto-restart --directory=./apps --directory=./config --pattern=*.py --recursive -- celery -A config.celery_app beat -l INFO
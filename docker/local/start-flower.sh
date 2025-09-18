#!/bin/bash

set -o errexit
set -o nounset



until timeout 10 celery -A config.celery_app inspect ping; do
    >&2 echo "Celery workers not available"
done

echo 'Starting flower'


celery -A config.celery_app --broker=redis://redis:6379/5 flower --port=5555 --address='0.0.0.0'
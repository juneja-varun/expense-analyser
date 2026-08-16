#!/bin/sh
# Applies migrations, then hands off to the CMD (gunicorn).
#
# Running migrations here rather than in a separate step keeps `docker compose
# up` a genuine one-command install — the thing most self-hosters judge the
# project on within their first two minutes.

set -eu

echo "Waiting for the database..."
until python -c "
import sys, django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()
from django.db import connection
try:
    connection.ensure_connection()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    sleep 1
done
echo "Database is up."

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear >/dev/null

echo "Starting: $*"
exec "$@"

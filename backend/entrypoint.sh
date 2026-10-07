#!/bin/sh
set -eu

alembic upgrade head

exec fastapi run main.py --host 0.0.0.0 --port "${PORT:-8000}"

#!/bin/sh

set -eu

case "${DATABASE_URL:-}" in
    *://*@*) ;;
    *)
        echo "DATABASE_URL must include a PostgreSQL username and password." >&2
        exit 1
        ;;
esac

authority=${DATABASE_URL#*://}
userinfo=${authority%%@*}
case "$userinfo" in
    *:*) ;;
    *)
        echo "DATABASE_URL must include a PostgreSQL username and password." >&2
        exit 1
        ;;
esac

POSTGRES_USER=${userinfo%%:*}
POSTGRES_PASSWORD=${userinfo#*:}
if [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_PASSWORD" ]; then
    echo "DATABASE_URL must include a PostgreSQL username and password." >&2
    exit 1
fi

export POSTGRES_USER POSTGRES_PASSWORD
exec /usr/local/bin/docker-entrypoint.sh "$@"

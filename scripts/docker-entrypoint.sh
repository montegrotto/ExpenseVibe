#!/bin/sh
set -eu

# Körs som root så den kan rätta ägarskap på /data-volymen, som kan ha
# populerats av en äldre imagebyggnad (eller skapats externt) med annat
# ägarskap än nuvarande appuser uid/gid. Namngivna volymer synkas aldrig om
# mot imagens ägarskap vid ombyggnad, så det måste självläkas här istället
# för att förlita sig på chown i byggsteget.
mkdir -p /data/media /app/staticfiles
chown -R appuser:appuser /data /app/staticfiles

if [ -d /opt/staticfiles ]; then
    find /app/staticfiles -mindepth 1 -delete
    cp -a /opt/staticfiles/. /app/staticfiles/
    chown -R appuser:appuser /app/staticfiles
fi

if [ "${EXPENSEVIBE_RUN_MIGRATIONS:-1}" = "1" ]; then
    gosu appuser /opt/venv/bin/python /app/manage.py migrate --noinput
fi

exec gosu appuser "$@"

FROM python:3.13-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends build-essential nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
# Templates refererar bara en minifierad fil per vendor-paket (plus
# bootstrap-icons typsnittsfiler) - utan detta hashar och gzippar whitenoises
# CompressedManifestStaticFilesStorage varje oanvänd sourcemap/icke-minifierad
# variant i onödan.
RUN npm ci --omit=dev \
    && find node_modules/bootstrap/dist -type f ! -name 'bootstrap.min.css' ! -name 'bootstrap.bundle.min.js' -delete \
    && find node_modules/bootstrap-icons/font -type f ! -name 'bootstrap-icons.min.css' ! -name 'bootstrap-icons.woff' ! -name 'bootstrap-icons.woff2' -delete \
    && find node_modules/bootstrap/dist node_modules/bootstrap-icons/font -depth -type d -empty -delete \
    && sed -i '/sourceMappingURL/d' node_modules/bootstrap/dist/css/bootstrap.min.css node_modules/bootstrap/dist/js/bootstrap.bundle.min.js

COPY requirements.lock ./
RUN python -m venv /opt/venv \
    && . /opt/venv/bin/activate \
    && pip install --upgrade pip \
    && pip install --no-compile -r requirements.lock \
    && find /opt/venv -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && rm -rf /opt/venv/lib/python*/site-packages/pip /opt/venv/lib/python*/site-packages/pip-*.dist-info /opt/venv/bin/pip*

COPY manage.py ./
COPY expensevibe expensevibe
COPY accounts accounts
COPY core core
COPY attachments attachments
COPY expenses expenses
COPY mileage mileage
COPY absence absence
COPY export export
COPY api api
COPY templates templates
COPY static static

ENV PATH="/opt/venv/bin:$PATH" \
    EXPENSEVIBE_DATA_DIR=/data \
    EXPENSEVIBE_STATIC_ROOT=/app/staticfiles \
    DJANGO_DEBUG=0

# collectstatic bara läser/skriver statiska filer - körs innan riktig
# DJANGO_SECRET_KEY finns tillgänglig. settings.py vägrar starta utan nyckel
# när DEBUG är av, så en engångsnyckel sätts bara för just det här steget.
RUN mkdir -p /data/media /app/staticfiles \
    && DJANGO_SECRET_KEY=build-time-only-not-used-at-runtime python manage.py collectstatic --noinput


FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    EXPENSEVIBE_DATA_DIR=/data \
    EXPENSEVIBE_STATIC_ROOT=/app/staticfiles \
    DJANGO_SETTINGS_MODULE=expensevibe.settings

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/manage.py /app/manage.py
COPY --from=builder --chown=appuser:appuser /app/expensevibe /app/expensevibe
COPY --from=builder --chown=appuser:appuser /app/accounts /app/accounts
COPY --from=builder --chown=appuser:appuser /app/core /app/core
COPY --from=builder --chown=appuser:appuser /app/attachments /app/attachments
COPY --from=builder --chown=appuser:appuser /app/expenses /app/expenses
COPY --from=builder --chown=appuser:appuser /app/mileage /app/mileage
COPY --from=builder --chown=appuser:appuser /app/absence /app/absence
COPY --from=builder --chown=appuser:appuser /app/export /app/export
COPY --from=builder --chown=appuser:appuser /app/api /app/api
COPY --from=builder --chown=appuser:appuser /app/templates /app/templates
COPY --from=builder --chown=appuser:appuser /app/static /app/static
COPY --from=builder --chown=appuser:appuser /app/staticfiles /opt/staticfiles
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod 755 /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /data/media /app/staticfiles \
    && chown -R appuser:appuser /data /app/staticfiles

VOLUME ["/data"]

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["gunicorn", "expensevibe.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-"]

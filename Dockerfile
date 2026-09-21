FROM python:3.13-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
ENV PORT=8000 STATE_DIR=/data
# Writable by whichever user the platform runs the container as (some force a non-root uid), and
# set before VOLUME so a new named volume inherits it.
RUN mkdir -p /data && chmod 777 /data
VOLUME /data
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/healthz' % os.environ['PORT'])"
# One worker on purpose: the player keeps what it queued in memory. Threads handle concurrency.
# --no-control-socket: we never use gunicornc, and the socket needs a writable home directory
# (it failed with "Permission denied: '/.gunicorn'" when run as a user without one).
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT} -w 1 --threads 8 --no-control-socket app.wsgi:app"]

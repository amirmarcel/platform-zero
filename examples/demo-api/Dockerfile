FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8080
USER 65532:65532

# --workers 1: prometheus_client counters are per-process, so /metrics must
# be scraped from the one process that's actually serving traffic.
# --threads 8: a single sync worker would serialize requests, so injected
# /work latency (LATENCY_MS) would queue the whole process instead of just
# responding slowly — and could time out the liveness probe into a pod
# restart, muddying the incident story. Threads give concurrency within the
# one process so injected latency shows up as latency, nothing else.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "app:app"]

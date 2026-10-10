FROM --platform=linux/amd64 python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
RUN apt-get update && apt-get install -y --no-install-recommends bash git tmux procps asciinema curl ca-certificates sqlite3 && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/runtime:/app PIPELINE_DB=/app/work/pipeline.db OUTPUT_DIR=/app/work/outputs EFFECTS_DB=/app/work/effects.db CHAOS_DB=/app/work/chaos.db
WORKDIR /app
COPY pipeline /app/pipeline
COPY runtime /app/runtime
COPY tools /app/tools
COPY CONTRACT.md /app/CONTRACT.md
RUN mkdir -p /app/work /app/submission && chmod 777 /app/submission /app/work

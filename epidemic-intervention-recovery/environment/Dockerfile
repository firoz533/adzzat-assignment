FROM --platform=linux/amd64 python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
RUN apt-get update && apt-get install -y --no-install-recommends bash git tmux procps asciinema curl ca-certificates libgomp1 && rm -rf /var/lib/apt/lists/*
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg MPLCONFIGDIR=/tmp/matplotlib
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: -r /tmp/requirements.txt
WORKDIR /app
RUN mkdir -p /app/data /app/submission && chmod 777 /app/submission
COPY data/cases.csv /app/data/cases.csv
COPY data/meta.json /app/data/meta.json
COPY CONTRACT.md /app/CONTRACT.md

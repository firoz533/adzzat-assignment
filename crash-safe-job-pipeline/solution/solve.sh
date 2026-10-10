#!/bin/bash
set -euo pipefail
mkdir -p /app/submission
cp -R /app/pipeline /app/submission/pipeline
cp /solution/worker.py /app/submission/pipeline/worker.py

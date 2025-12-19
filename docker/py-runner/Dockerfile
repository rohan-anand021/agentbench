FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 runner

WORKDIR /workspace

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
PIP_NO_INPUT=1 \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1

USER runner

RUN pip install --user --no-cache-dir pytest

ENV PATH="/home/runner/.local/bin:$PATH"



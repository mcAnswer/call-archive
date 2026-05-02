FROM nvidia/cuda:12.8.2-runtime-ubuntu24.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY call_archive ./call_archive
COPY pyproject.toml .
COPY transcribe.py .

RUN pip install --no-cache-dir --break-system-packages -e .

ENV PYTHONPATH=/app
ENTRYPOINT ["call-archive"]
CMD ["--help"]

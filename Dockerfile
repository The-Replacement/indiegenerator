# indiegenerator — batch renderer for the radio stack.
#
# Pinned Python 3.15 to match pyproject.toml (>=3.15,<3.16). Wheels for
# numpy/scipy on cp315 may require a recent pip; if a wheel is unavailable
# the build needs compilers and BLAS headers (see build deps below).
FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Single-threaded BLAS/OpenMP: the renderer pins thread caps in code
    # before numpy import, but the env is the belt to the suspenders.
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1

WORKDIR /app

# Runtime: libsndfile (soundfile), ffmpeg (codec gates). Docker CLI for the
# optional liquidsoap restart path (mount /var/run/docker.sock to enable).
# Build: compilers/headers in case a pinned dependency has no cp315 wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      ffmpeg \
      libsndfile1 \
      docker.io \
    && apt-get install -y --no-install-recommends \
      build-essential \
      gfortran \
      libopenblas-dev \
      libsndfile1-dev \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE MUSIC-LICENSE /app/
COPY src/ /app/src/
COPY presets/ /app/presets/

RUN pip install --no-cache-dir /app \
    && apt-get purge -y --auto-remove \
      build-essential gfortran libopenblas-dev libsndfile1-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/radio-cycle.sh /usr/local/bin/radio-cycle
RUN chmod +x /usr/local/bin/radio-cycle

# The radio's music directory and the generator's working state are volumes.
VOLUME ["/music", "/var/lib/indiegen"]

ENTRYPOINT ["indiegen"]
CMD ["serve", "--music-dir", "/music", "--work-dir", "/var/lib/indiegen", "--presets-dir", "/app/presets"]

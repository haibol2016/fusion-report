FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Build dependencies are kept in this stage only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml setup.py MANIFEST.in README.md requirements.txt ./
# The HGNC snapshot (fusion_report/data/hgnc/hgnc_complete_set.txt.gz) is declared
# as package_data in setup.py so it is bundled into the wheel by `pip wheel .`
# and installed into site-packages/fusion_report/data/hgnc/ at runtime.
COPY fusion_report ./fusion_report
COPY bin ./bin

RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt \
    && pip wheel --no-cache-dir --wheel-dir /wheels .


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Optional HGNC resolver behaviour (see docs/download.md):
#   FUSION_REPORT_HGNC_STRICT=1          – fail if HGNC cannot be loaded from any source
#   FUSION_REPORT_HGNC_BUNDLED_PATH=...  – path to an alternative bundled HGNC gzip

WORKDIR /app

# sqlite3 is required by fusion-report runtime database operations.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-compile --no-index --find-links=/wheels fusion-report \
    && rm -rf /wheels

ENTRYPOINT ["fusion_report"]
CMD ["--help"]

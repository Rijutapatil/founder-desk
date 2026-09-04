# founder-desk as a service.
#
# The corpus is committed to the repository, so the image needs no network at
# run time to answer a question - it only reaches out when you deliberately
# re-run ingestion. That is what makes a single `docker run` a reasonable way to
# put this behind a UI.
#
#   docker build -t founder-desk .
#   docker run --rm -p 8123:8123 \
#     -e FOUNDER_DESK_CORS_ORIGINS=http://localhost:3000 founder-desk
#
# The default build installs the light path: no torch, no models. That means the
# *lexical* refusal gate, which is measurably worse at declining what it cannot
# answer (0.333 against 0.593 - see docs/evaluation.md). For the gate the
# numbers in the docs describe:
#
#   docker build --build-arg EXTRAS=serving,rerank -t founder-desk .
#
# That pulls ~2 GB and downloads two models on first request.
#
# NOTE: not yet built or run anywhere - no Docker daemon was available on the
# machine this was written on. Treat the first `docker build` as the test.

FROM python:3.12-slim AS base

ARG EXTRAS=serving

WORKDIR /app

# Dependency metadata first, so a code change does not invalidate the pip layer.
COPY pyproject.toml README.md ./
COPY agent ./agent
COPY ingest ./ingest
COPY eval ./eval
COPY serving ./serving
COPY sources ./sources

# The built corpus. Without it the service starts and reports itself unready,
# which is correct but useless - so it is part of the image rather than a mount.
COPY data/corpus ./data/corpus

RUN pip install --no-cache-dir ".[${EXTRAS}]"

# Non-root: the process only ever reads its own corpus.
RUN useradd --create-home --uid 10001 desk && chown -R desk /app
USER desk

EXPOSE 8123

# /ready, not /health: readiness means the corpus loaded and it can actually
# answer, and a load balancer routing on liveness alone would send traffic to a
# process that is running and useless.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8123/ready').status==200 else 1)"

CMD ["uvicorn", "serving.app:app", "--host", "0.0.0.0", "--port", "8123"]

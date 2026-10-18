# Public Langflow + local bbsctl wheel. No private registries.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/app \
    LANGFLOW_COMPONENTS_PATH=/app/components \
    LANGFLOW_HOST=0.0.0.0 \
    LANGFLOW_PORT=7860

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY wheels/bbsctl-*.whl /tmp/wheels/
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir /tmp/wheels/bbsctl-*.whl \
    && python -m pip install --no-cache-dir "langflow>=1.4,<2" \
    && rm -rf /tmp/wheels \
    && bbsctl --version

COPY components/ /app/components/
COPY flows/ /app/flows/
COPY fixtures/ /app/fixtures/

EXPOSE 7860

CMD ["langflow", "run", "--host", "0.0.0.0", "--port", "7860"]

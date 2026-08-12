FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml README.md LICENSE ./
COPY wall_harness ./wall_harness
COPY scripts/start-margin.sh ./scripts/start-margin.sh
RUN chmod 755 ./scripts/start-margin.sh && pip install --no-cache-dir .

EXPOSE 8765
CMD ["/app/scripts/start-margin.sh"]

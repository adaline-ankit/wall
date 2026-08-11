FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml README.md LICENSE ./
COPY wall_harness ./wall_harness
RUN pip install --no-cache-dir .

EXPOSE 8765
CMD ["wall", "serve", "/data/wall.yaml", "--host", "0.0.0.0", "--port", "8765", "--allow-network"]

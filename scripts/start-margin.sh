#!/bin/sh
set -eu

if [ -n "${WALL_DATA_DIR:-}" ]; then
  data_dir="$WALL_DATA_DIR"
elif [ -d /data ]; then
  # Preserve the existing docker-compose volume convention for local installs.
  data_dir=/data
else
  data_dir=/var/data
fi
app_dir="${MARGIN_APP_DIR:-/app}"
if [ ! -f "$app_dir/wall_harness/examples/frontier-ai.yaml" ]; then
  app_dir="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
fi
spec_path="${WALL_SPEC_PATH:-$data_dir/wall.yaml}"

mkdir -p "$data_dir"
if [ ! -f "$spec_path" ]; then
  cp "$app_dir/wall_harness/examples/frontier-ai.yaml" "$spec_path"
fi

exec wall serve "$spec_path" \
  --host 0.0.0.0 \
  --port "${PORT:-8765}" \
  --allow-network

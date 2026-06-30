#!/usr/bin/env bash
set -euo pipefail

args=()

if [[ -n "${STREAM:-}" ]]; then
  args+=("--stream" "$STREAM")
fi

if [[ -n "${SOCKET_URL:-}" ]]; then
  args+=("--socket-url" "$SOCKET_URL")
fi

if [[ -n "${AIRFRAMES_API_KEY:-}" ]]; then
  args+=("--api-key" "$AIRFRAMES_API_KEY")
fi

if [[ -n "${AIRFRAMES_TOKEN:-}" ]]; then
  args+=("--token" "$AIRFRAMES_TOKEN")
fi

if [[ -n "${STATION_ID:-}" ]]; then
  args+=("--station-id" "$STATION_ID")
fi

if [[ -n "${FILTERS:-}" ]]; then
  IFS=',' read -ra filters <<< "$FILTERS"
  for filter in "${filters[@]}"; do
    args+=("--filter" "$filter")
  done
fi

if [[ -n "${INLINE_WIDTH:-}" ]]; then
  args+=("--inline-width" "$INLINE_WIDTH")
fi

if [[ -n "${NODE_RED_URL:-}" ]]; then
  args+=("--node-red-url" "$NODE_RED_URL")
fi

if [[ "${NODE_RED_INSECURE_TLS:-}" =~ ^(1|true|yes)$ ]]; then
  args+=("--node-red-insecure-tls")
fi

if [[ -n "${NODE_RED_TIMEOUT:-}" ]]; then
  args+=("--node-red-timeout" "$NODE_RED_TIMEOUT")
fi

if [[ -n "${NODE_RED_QUEUE_SIZE:-}" ]]; then
  args+=("--node-red-queue-size" "$NODE_RED_QUEUE_SIZE")
fi

if [[ -n "${NODE_RED_RETRIES:-}" ]]; then
  args+=("--node-red-retries" "$NODE_RED_RETRIES")
fi

if [[ -n "${NODE_RED_RETRY_DELAY:-}" ]]; then
  args+=("--node-red-retry-delay" "$NODE_RED_RETRY_DELAY")
fi

if [[ -n "${NODE_RED_CA_FILE:-}" ]]; then
  args+=("--node-red-ca-file" "$NODE_RED_CA_FILE")
fi

if [[ -n "${INFLUX_URL:-}" ]]; then
  args+=("--influx-url" "$INFLUX_URL")
fi

if [[ -n "${INFLUX_TOKEN:-}" ]]; then
  args+=("--influx-token" "$INFLUX_TOKEN")
fi

if [[ -n "${INFLUX_ORG:-}" ]]; then
  args+=("--influx-org" "$INFLUX_ORG")
fi

if [[ -n "${INFLUX_BUCKET:-}" ]]; then
  args+=("--influx-bucket" "$INFLUX_BUCKET")
fi

if [[ -n "${INFLUX_TIMEOUT:-}" ]]; then
  args+=("--influx-timeout" "$INFLUX_TIMEOUT")
fi

if [[ -n "${INFLUX_QUEUE_SIZE:-}" ]]; then
  args+=("--influx-queue-size" "$INFLUX_QUEUE_SIZE")
fi

if [[ -n "${INFLUX_RETRIES:-}" ]]; then
  args+=("--influx-retries" "$INFLUX_RETRIES")
fi

if [[ -n "${INFLUX_RETRY_DELAY:-}" ]]; then
  args+=("--influx-retry-delay" "$INFLUX_RETRY_DELAY")
fi

if [[ "${NODE_RED_ONLY:-}" =~ ^(1|true|yes)$ ]]; then
  args+=("--node-red-only")
fi

if [[ "${INLINE_SUMMARY:-}" =~ ^(1|true|yes)$ ]]; then
  args+=("--inline-summary")
fi

if [[ "${SUMMARY:-}" =~ ^(1|true|yes)$ ]]; then
  args+=("--summary")
fi

# The image is intended to run without libacars by default.
if [[ "${LIBACARS:-}" =~ ^(1|true|yes)$ ]]; then
  args+=("--libacars")
fi

exec python3 main.py "${args[@]}" "$@"

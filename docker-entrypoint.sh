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
# Do not enable libacars unless the binary is available in the container.
if [[ "${LIBACARS:-}" =~ ^(1|true|yes)$ ]]; then
  args+=("--libacars")
fi

exec python main.py "${args[@]}" "$@"

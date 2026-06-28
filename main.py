#!/usr/bin/env python3.11
# type: ignore
"""
Command-line Socket.IO client for the airframes.io live stream.

Supported stream modes:
    sniff   sampled global message firehose via messages:sniff
    feed    authenticated per-account station feed via API key
    station live monitor for one station id
"""

import argparse
import asyncio
import json
import os
import signal

from src.helpers import parse_filters
from src.libacars import DEFAULT_DECODER
from src.nodeRedPipe import NodeRedPipe
from src.socket_client import build_client, register_handlers

DEFAULT_SOCKET_URL = "https://ws.airframes.io"  # PROD
DEFAULT_NODE_RED_URL = "https://localhost:1880/airframes"


def build_parser():
    parser = argparse.ArgumentParser(description="airframes.io Socket.IO client")
    parser.add_argument(
        "--stream",
        choices=("auto", "sniff", "feed", "station"),
        default="auto",
        help=(
            "Stream mode. auto uses station when --station-id is provided, "
            "feed when --api-key is provided, otherwise sniff. Default: auto."
        ),
    )
    parser.add_argument(
        "--socket-url",
        default=DEFAULT_SOCKET_URL,
        help=f"Socket.IO endpoint. Default: {DEFAULT_SOCKET_URL}",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("AIRFRAMES_API_KEY"),
        help="Airframes API key for the unsampled per-account feed. Can also be set with AIRFRAMES_API_KEY.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AIRFRAMES_TOKEN"),
        help="JWT for app/user session authentication. Can also be set with AIRFRAMES_TOKEN.",
    )
    parser.add_argument(
        "--station-id",
        type=int,
        help="Station id for station monitor mode.",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help=(
            "Add a filter in the format field=value. Repeat this argument for multiple filters. "
            "Values can be comma-separated. Example: --filter station.country_code=US,CA"
        ),
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a short JSON summary instead of the complete payload.",
    )
    parser.add_argument(
        "--inline-summary",
        "--inline_sumary",
        dest="inline_summary",
        action="store_true",
        help="Print each message as a single table-like log line.",
    )
    parser.add_argument(
        "--inline-width",
        type=int,
        help="Maximum width for --inline-summary. Defaults to the terminal width.",
    )
    parser.add_argument(
        "--node-red-url",
        nargs="?",
        const=DEFAULT_NODE_RED_URL,
        help=f"HTTP endpoint where each filtered JSON message will be POSTed. Default when used without a value: {DEFAULT_NODE_RED_URL}",
    )
    parser.add_argument(
        "--node-red-timeout",
        type=float,
        default=10.0,
        help="Timeout in seconds for POST requests to Node-RED. Default: 10.",
    )
    parser.add_argument(
        "--node-red-queue-size",
        type=int,
        default=1000,
        help="Maximum pending messages waiting to be sent to Node-RED. Default: 1000.",
    )
    parser.add_argument(
        "--node-red-retries",
        type=int,
        default=2,
        help="Retry attempts for each Node-RED POST after the first failure. Default: 2.",
    )
    parser.add_argument(
        "--node-red-retry-delay",
        type=float,
        default=1.0,
        help="Delay in seconds between Node-RED POST retries. Default: 1.",
    )
    parser.add_argument(
        "--node-red-only",
        action="store_true",
        help="Send matching events to Node-RED without printing each event locally.",
    )
    parser.add_argument(
        "--node-red-insecure-tls",
        action="store_true",
        help="Disable TLS certificate verification for the Node-RED POST endpoint.",
    )
    parser.add_argument(
        "--node-red-ca-file",
        help="Path to a CA certificate bundle used to verify the Node-RED HTTPS certificate.",
    )
    parser.add_argument(
        "--libacars",
        action="store_true",
        help="Decode supported ACARS application messages with libacars before output/forwarding.",
    )
    parser.add_argument(
        "--libacars-decoder",
        default=DEFAULT_DECODER,
        help=f"Path to decode_acars_apps. Default: {DEFAULT_DECODER}",
    )
    parser.add_argument(
        "--libacars-timeout",
        type=float,
        default=5.0,
        help="Timeout in seconds for each libacars decode. Default: 5.",
    )
    return parser


def resolve_stream_mode(args, parser):
    if args.stream == "auto":
        if args.station_id is not None:
            return "station"
        if args.api_key:
            return "feed"
        return "sniff"

    if args.stream == "feed" and not args.api_key:
        parser.error("--stream feed requires --api-key or AIRFRAMES_API_KEY")
    if args.stream == "station" and args.station_id is None:
        parser.error("--stream station requires --station-id")
    return args.stream


def build_auth_payload(args):
    auth = {}
    if args.api_key:
        auth["apiKey"] = args.api_key
    if args.token:
        auth["token"] = args.token
    return auth or None


def keyboard_interrupt_handler(signal_num, frame):
    print("Keyboard interrupt received. Exiting...")
    raise KeyboardInterrupt


signal.signal(signal.SIGINT, keyboard_interrupt_handler)


async def main():
    global FILTERS

    parser = build_parser()
    args = parser.parse_args()
    stream_mode = resolve_stream_mode(args, parser)

    node_red_pipe = None

    if args.node_red_url:
        node_red_pipe = NodeRedPipe(
            args.node_red_url,
            timeout=args.node_red_timeout,
            queue_size=args.node_red_queue_size,
            retries=args.node_red_retries,
            retry_delay=args.node_red_retry_delay,
            insecure_tls=args.node_red_insecure_tls,
            ca_file=args.node_red_ca_file,
        )
        await node_red_pipe.start()
        print(f"Node-RED pipe active: POST {args.node_red_url}")
        if args.node_red_insecure_tls:
            print("Node-RED TLS verification is disabled")

    filters = parse_filters(args.filter)
    sio = build_client()

    register_handlers(
        sio,
        stream_mode=stream_mode,
        filters=filters,
        station_id=args.station_id,
        summary_mode=args.summary,
        inline_summary_mode=args.inline_summary,
        inline_width=args.inline_width,
        node_red_pipe=node_red_pipe,
        node_red_only=args.node_red_only,
        libacars_enabled=args.libacars,
        libacars_decoder=args.libacars_decoder,
        libacars_timeout=args.libacars_timeout,
    )

    if filters:
        print(
            "active filters:",
            json.dumps({key: sorted(values) for key, values in filters.items()}),
        )

    auth = build_auth_payload(args)

    await sio.connect(
        args.socket_url,
        transports=["websocket"],
        socketio_path="socket.io",
        auth=auth,
        retry=True,
        wait_timeout=10,
    )
    try:
        await sio.wait()
    finally:
        await sio.disconnect()
        if node_red_pipe:
            await node_red_pipe.close()


if __name__ == "__main__":
    asyncio.run(main())

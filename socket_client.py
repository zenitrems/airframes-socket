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
import json
import os
import signal

import socketio

from src.helpers import (
    parse_filters,
    matches_filters,
    inline_summary,
    inline_summary_header,
    inline_summary_separator,
)
from src.nodeRedPipe import NodeRedPipe

DEFAULT_SOCKET_URL = "https://ws.airframes.io"
DEFAULT_NODE_RED_URL = "https://host:1880/airframes"
FILTERS = {}


def build_client():
    return socketio.Client(
        logger=False,
        engineio_logger=False,
        reconnection=True,
        reconnection_attempts=5,
        reconnection_delay=2,
    )


sio = build_client()


def summarize_message(data):
    if not isinstance(data, dict):
        return json.dumps({"event": "message", "payload": data}, ensure_ascii=False)

    station = data.get("station") or {}
    flight = data.get("flight") or {}
    airframe = data.get("airframe") or {}

    summary = {
        "id": data.get("id"),
        "timestamp": data.get("timestamp"),
        "station": (station.get("ident"), station.get("country_code")),
        "flight": {
            "flight": flight.get("flight"),
            "flight_icao": flight.get("flight_icao"),
            "flight_iata": flight.get("flight_iata"),
        },
        "airframe": {
            "icao": airframe.get("icao"),
            "tail": airframe.get("tail"),
            "model": airframe.get("manufacturer_model"),
            "owner": airframe.get("owner"),
        },
        "source_info": {
            "source": data.get("source"),
            "source_type": data.get("source_type"),
            "link_direction": data.get("link_direction"),
            "label": data.get("label"),
            "mode": data.get("mode"),
            "frequency": data.get("frequency"),
        },
        "message_data": {
            "message_number": data.get("message_number"),
            "text": data.get("text"),
            "block_end": data.get("block_end"),
        },
    }

    return json.dumps(summary, ensure_ascii=False, indent=2)


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


def register_handlers(
    stream_mode,
    station_id=None,
    summary_mode=False,
    inline_summary_mode=False,
    inline_width=None,
    node_red_pipe=None,
    node_red_only=False,
):
    printed_inline_header = False

    def process_message(data):
        nonlocal printed_inline_header

        if not matches_filters(data, FILTERS):
            return

        if node_red_pipe:
            node_red_pipe.send(data)

        if node_red_only:
            return

        if inline_summary_mode:
            if not printed_inline_header:
                print(inline_summary_header(inline_width))
                print(inline_summary_separator(inline_width))
                printed_inline_header = True
            print(inline_summary(data, inline_width))
        elif summary_mode:
            print(summarize_message(data))
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            print("-" * 40)

    @sio.event
    def connect():
        print(f"Connected. Stream mode: {stream_mode}")
        if stream_mode == "sniff":
            sio.emit("messages:sniff")
        elif stream_mode == "station":
            sio.emit("station:monitor:start", station_id)

    @sio.event
    def connect_error(data):
        print("Connection error:", data)

    @sio.event
    def connect_timeout():
        print("Connection timeout")

    @sio.event
    def reconnect():
        print("Reconnecting...")

    @sio.event
    def reconnect_attempt():
        print("Reconnection attempt...")

    @sio.event
    def reconnect_error():
        print("Reconnection error")

    @sio.event
    def reconnect_failed():
        print("Reconnection failed")

    @sio.event
    def disconnect():
        print("Disconnected from server")

    @sio.on("message")
    def global_message(data):
        process_message(data)

    @sio.on("messages:sniff:started")
    def messages_sniff_started(data):
        print("Global message sniff started:", json.dumps(data, ensure_ascii=False))

    @sio.on("feed:authenticated")
    def feed_authenticated(data):
        stations = data.get("stations") if isinstance(data, dict) else None
        station_count = len(stations or [])
        print(f"Feed authenticated. Stations: {station_count}")

    @sio.on("feed:message")
    def feed_message(data):
        process_message(data)

    @sio.on("station:monitor:started")
    def station_monitor_started(data):
        print("Station monitor started:", json.dumps(data, ensure_ascii=False))

    @sio.on("station:monitor:data")
    def station_monitor_data(data):
        if not isinstance(data, dict):
            return
        for message in data.get("newMessages") or []:
            process_message(message)

    @sio.on("station:monitor:stopped")
    def station_monitor_stopped(data):
        print("Station monitor stopped:", json.dumps(data, ensure_ascii=False))

    @sio.on("feed:error")
    def feed_error(data):
        print("Feed error:", data)

    @sio.on("chat:error")
    def chat_error(data):
        print("Chat error:", data)

    @sio.on("error")
    def socket_error(data):
        print("Socket error:", data)


def keyboard_interrupt_handler(signal, frame):
    print("Keyboard interrupt received. Exiting...")
    sio.disconnect()
    raise SystemExit(0)


signal.signal(signal.SIGINT, keyboard_interrupt_handler)


def main():
    global FILTERS

    parser = build_parser()
    args = parser.parse_args()
    stream_mode = resolve_stream_mode(args, parser)
    FILTERS = parse_filters(args.filter)
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
        node_red_pipe.start()
        print(f"Node-RED pipe active: POST {args.node_red_url}")
        if args.node_red_insecure_tls:
            print("Node-RED TLS verification is disabled")

    register_handlers(
        stream_mode=stream_mode,
        station_id=args.station_id,
        summary_mode=args.summary,
        inline_summary_mode=args.inline_summary,
        inline_width=args.inline_width,
        node_red_pipe=node_red_pipe,
        node_red_only=args.node_red_only,
    )

    if FILTERS:
        print(
            "active filters:",
            json.dumps({key: sorted(values) for key, values in FILTERS.items()}),
        )

    auth = build_auth_payload(args)
    sio.connect(
        args.socket_url,
        transports=["websocket"],
        socketio_path="socket.io",
        auth=auth,
        retry=True,
        wait_timeout=10,
    )

    sio.wait()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3.11
"""

A command-line WEBSOCKET client for airframes.io that connects to the live message stream, applies user-defined filters, and prints matching messages in a readable format. It also supports sending filtered messages to a Node-RED endpoint for further processing.
Usage examples:
    # Print all messages with a summary format
    python socket_client.py --summary

    # Print messages from US stations in an inline summary format
    python socket_client.py --filter station.country_code=US --inline-summary

    # Send messages for flights with ICAO code UAL123 to Node-RED without local printing
    python socket_client.py --filter flight.flight_icao=UAL123 --node-red-url https://host:1880/airframes --node-red-only

"""

import argparse
import json
import signal
import socketio
from src.helpers import (
    get_nested_value,
    parse_filters,
    matches_filters,
    inline_summary,
    inline_summary_header,
    inline_summary_separator,
)
from src.nodeRedPipe import NodeRedPipe


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
    flight = {
        "flight": get_nested_value(data, "flight.flight"),
        "flight_icao": get_nested_value(data, "flight.flight_icao"),
        "flight_iata": get_nested_value(data, "flight.flight_iata"),
    }
    airframe = {
        "icao": get_nested_value(data, "airframe.icao"),
        "tail": get_nested_value(data, "airframe.tail"),
        "model": get_nested_value(data, "airframe.manufacturer_model"),
        "owner": get_nested_value(data, "airframe.owner"),
    }

    message_data = {
        "message_number": data.get("message_number"),
        "data": data.get("data"),
        "text": data.get("text"),
        "departing_airport": data.get("departing_airport"),
        "destination_airport": data.get("destination_airport"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "altitude": data.get("altitude"),
        "ar_uuid": data.get("ar_uuid"),
        "ar_version": data.get("ar_version"),
        "block_end": data.get("block_end"),
    }
    source_info = {
        "source": data.get("source"),
        "link_direction": data.get("link_direction"),
        "from_hex": data.get("from_hex"),
        "to_hex": data.get("to_hex"),
        "error": data.get("error"),
        "mode": data.get("mode"),
        "label": data.get("label"),
        "block_id": data.get("block_id"),
        "ack": data.get("ack"),
    }

    summary = {
        "id": data.get("id"),
        "timestamp": data.get("timestamp"),
        "station": (station.get("ident"), station.get("country_code")),
        "flight": flight,
        "airframe": airframe,
        "source_info": source_info,
        "mesage_data": message_data,
    }

    return json.dumps(summary, ensure_ascii=False, indent=2)


def build_parser():
    parser = argparse.ArgumentParser(description="airframes.io WEBSOCKET client")
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help=(
            "Add a filter in the format field=value. You can specify multiple filters by repeating this argument. "
            "Values can be comma-separated for multiple matches. For example: --filter station.country_code=US,CA --filter flight.flight_icao=UAL123"
        ),
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Prints a short summary of the message instead of the complete JSON payload.",
    )
    parser.add_argument(
        "--inline-summary",
        "--inline_sumary",
        dest="inline_summary",
        action="store_true",
        help="Prints each message as a single table-like log line.",
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


def register_handlers(
    summary_mode=False,
    inline_summary_mode=False,
    inline_width=None,
    node_red_pipe=None,
    node_red_only=False,
):
    printed_inline_header = False

    @sio.event
    def connect():
        print("Listening")

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

    @sio.event
    def message(data):
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


def keyboard_interrupt_handler(signal, frame):
    print("Keyboard interrupt received. Exiting...")
    sio.disconnect()
    exit(0)


signal.signal(signal.SIGINT, keyboard_interrupt_handler)


def main():
    global FILTERS

    args = build_parser().parse_args()
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

    sio.connect(
        "https://ws.airframes.io",
        transports=["websocket"],
        socketio_path="socket.io",
        retry=True,
        wait_timeout=10,
    )

    sio.wait()


if __name__ == "__main__":
    main()

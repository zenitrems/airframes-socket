import argparse
import json
import queue
import shutil
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

import socketio


DEFAULT_INLINE_WIDTH = 120
DEFAULT_NODE_RED_URL = "https://orange.prefix64.org:1880/airframes"
INLINE_MIN_TEXT_WIDTH = 12
INLINE_COLUMN_SEPARATOR = " | "
INLINE_SUMMARY_BASE_COLUMNS = [
    ("time", 24, 19),
    ("station", 18, 12),
    ("cc", 2, 2),
    ("flight", 8, 6),
    ("icao", 6, 6),
    ("tail", 8, 6),
    ("mil", 3, 3),
]


def build_client():
    return socketio.Client(
        logger=False,
        engineio_logger=False,
        reconnection=True,
        reconnection_attempts=5,
        reconnection_delay=2,
    )


FILTERS = {}
sio = build_client()


class NodeRedPipe:
    def __init__(
        self,
        url,
        timeout=10.0,
        queue_size=1000,
        retries=2,
        retry_delay=1.0,
        insecure_tls=False,
        ca_file=None,
    ):
        self.url = url
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.ssl_context = self._build_ssl_context(insecure_tls, ca_file)
        self.queue = queue.Queue(maxsize=queue_size)
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.last_error_at = 0

    def _build_ssl_context(self, insecure_tls, ca_file):
        if insecure_tls:
            return ssl._create_unverified_context()
        if ca_file:
            return ssl.create_default_context(cafile=ca_file)
        return None

    def start(self):
        self.thread.start()

    def send(self, payload):
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            self._log_error("Node-RED queue is full; dropping message")

    def _worker(self):
        while True:
            payload = self.queue.get()
            try:
                self._post_with_retries(payload)
            except Exception as exc:
                self._log_error(f"Node-RED POST failed: {exc}")
            finally:
                self.queue.task_done()

    def _post_with_retries(self, payload):
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                self._post(payload)
                return
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.retry_delay)

        raise last_error

    def _post(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "airframes-socket-client",
            },
            method="POST",
        )

        with urllib.request.urlopen(
            request,
            timeout=self.timeout,
            context=self.ssl_context,
        ) as response:
            if response.status >= 400:
                raise urllib.error.HTTPError(
                    self.url,
                    response.status,
                    response.reason,
                    response.headers,
                    response,
                )

    def _log_error(self, message):
        now = time.monotonic()
        if now - self.last_error_at < 10:
            return
        self.last_error_at = now
        print(message, file=sys.stderr)


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


def format_table_value(value, width):
    if isinstance(value, bool):
        value = "true" if value else "false"
    if value is None:
        value = ""
    value = str(value).replace("\n", " ").replace("\r", " ")
    if len(value) > width:
        return value[: width - 3] + "..."
    return value.ljust(width)


def get_inline_width(max_width=None):
    if max_width:
        return max_width
    return shutil.get_terminal_size((DEFAULT_INLINE_WIDTH, 20)).columns


def inline_summary_columns(max_width=None):
    terminal_width = get_inline_width(max_width)
    columns = [
        {"name": name, "width": width, "min_width": min_width}
        for name, width, min_width in INLINE_SUMMARY_BASE_COLUMNS
    ]

    separator_width = len(INLINE_COLUMN_SEPARATOR) * len(columns)
    fixed_width = sum(column["width"] for column in columns)
    text_width = terminal_width - fixed_width - separator_width

    if text_width < INLINE_MIN_TEXT_WIDTH:
        missing_width = INLINE_MIN_TEXT_WIDTH - text_width
        for column in columns:
            available_width = column["width"] - column["min_width"]
            if available_width <= 0:
                continue

            shrink_by = min(available_width, missing_width)
            column["width"] -= shrink_by
            missing_width -= shrink_by

            if missing_width == 0:
                break

        fixed_width = sum(column["width"] for column in columns)
        text_width = max(
            INLINE_MIN_TEXT_WIDTH,
            terminal_width - fixed_width - separator_width,
        )

    return [
        (column["name"], column["width"]) for column in columns
    ] + [("text", text_width)]


def inline_summary_header(max_width=None):
    return INLINE_COLUMN_SEPARATOR.join(
        format_table_value(column, width)
        for column, width in inline_summary_columns(max_width)
    )


def inline_summary_separator(max_width=None):
    return "-+-".join("-" * width for _, width in inline_summary_columns(max_width))


def inline_summary(data, max_width=None):
    columns = inline_summary_columns(max_width)
    if not isinstance(data, dict):
        return format_table_value(
            json.dumps(data, ensure_ascii=False),
            get_inline_width(max_width),
        )

    military = get_nested_value(data, "airframe.military")
    if isinstance(military, bool):
        military = "Y" if military else "N"

    values = {
        "time": data.get("timestamp"),
        "station": get_nested_value(data, "station.ident"),
        "cc": get_nested_value(data, "station.country_code"),
        "flight": (
            get_nested_value(data, "flight.flight_iata")
            or get_nested_value(data, "flight.flight_icao")
            or get_nested_value(data, "flight.flight")
        ),
        "icao": get_nested_value(data, "airframe.icao"),
        "tail": get_nested_value(data, "airframe.tail") or data.get("tail"),
        "mil": military,
        "text": data.get("text"),
    }

    return INLINE_COLUMN_SEPARATOR.join(
        format_table_value(values[column], width) for column, width in columns
    )


def get_nested_value(data, path):
    current = data

    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)

    return current


def parse_filters(raw_filters):
    parsed_filters = {}

    for raw_filter in raw_filters or []:
        if "=" not in raw_filter:
            raise ValueError(
                f"Invalid filter '{raw_filter}'. Use the format field=value."
            )

        key, value = raw_filter.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise ValueError(f"Invalid filter '{raw_filter}'. The field is empty.")
        if not value:
            raise ValueError(f"Invalid filter '{raw_filter}'. The value is empty.")

        parsed_filters.setdefault(key, set()).update(
            item.strip() for item in value.split(",") if item.strip()
        )

    return parsed_filters


def normalize_filter_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value).strip().lower()


def matches_filters(data, filters):
    if not filters:
        return True

    if not isinstance(data, dict):
        return False

    for key, expected_values in filters.items():
        current_value = get_nested_value(data, key)
        if current_value is None:
            return False
        if normalize_filter_value(current_value) not in {
            normalize_filter_value(value) for value in expected_values
        }:
            return False

    return True


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

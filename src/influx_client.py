import asyncio
import contextlib
from datetime import datetime, timezone
from urllib.parse import urlencode
import sys
import time

import aiohttp

from src.helpers import get_nested_value

EVENT_MEASUREMENT = "airframes_event"
CATALOG_MEASUREMENT = "airframes_catalog"
CATALOG_TIMESTAMP_NS = 0


class InfluxClient:
    """Async InfluxDB writer for ACARS event history and aircraft catalog state."""

    def __init__(
        self,
        url,
        token,
        org,
        bucket,
        timeout=10.0,
        queue_size=1000,
        retries=2,
        retry_delay=1.0,
    ):
        self.url = url.rstrip("/")
        self.token = token
        self.org = org
        self.bucket = bucket
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.queue = asyncio.Queue(maxsize=queue_size)
        self.session = None
        self.worker_task = None
        self.last_error_at = 0
        self.closed = False
        self.catalog = {}

    async def start(self):
        if self.worker_task is not None:
            return
        self.session = aiohttp.ClientSession()
        self.worker_task = asyncio.create_task(self._worker())

    async def send(self, payload):
        if self.closed:
            self._log_error("InfluxDB client is closed; dropping message")
            return

        try:
            self.queue.put_nowait(payload)
        except asyncio.QueueFull:
            self._log_error("InfluxDB queue is full; dropping message")

    async def close(self):
        self.closed = True
        if self.worker_task is not None:
            await self.queue.join()
            self.worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.worker_task
        if self.session is not None:
            await self.session.close()

    async def _worker(self):
        while True:
            payload = await self.queue.get()
            try:
                lines = self.build_lines(payload)
                if lines:
                    await self._write_with_retries(lines)
            except Exception as exc:
                self._log_error(f"InfluxDB write failed: {exc}")
            finally:
                self.queue.task_done()

    def build_lines(self, payload):
        if not isinstance(payload, dict):
            return []

        lines = []
        event_line = build_event_line(payload)
        if event_line:
            lines.append(event_line)

        catalog_line = self.build_catalog_line(payload)
        if catalog_line:
            lines.append(catalog_line)

        return lines

    def build_catalog_line(self, payload):
        normalized = normalize_airframes_message(payload)

        icao = normalized["airframe_icao"]
        if not icao:
            return None

        event_time = normalized["timestamp"] or utc_now_iso()

        state = self.catalog.get(icao)

        if state is None:
            state = {
                "first_seen": event_time,
                "last_seen": event_time,
                "message_count": 0,
                "decoded_messages": 0,
                "text_messages": 0,
                "stations": set(),
                "tail": "",
                "flight": "",
                "country": "",
                "military": False,
                "first_frequency": 0.0,
                "last_frequency": 0.0,
                "last_station": "",
                "last_label": "",
                "last_mode": "",
            }

        state["message_count"] += 1
        state["last_seen"] = event_time

        if normalized["decoded_ok"]:
            state["decoded_messages"] += 1

        if normalized["text"]:
            state["text_messages"] += 1

        if normalized["tail"]:
            state["tail"] = normalized["tail"]

        if normalized["flight"]:
            state["flight"] = normalized["flight"]

        if normalized["country"]:
            state["country"] = normalized["country"]

        if normalized["station"]:
            state["last_station"] = normalized["station"]
            state["stations"].add(normalized["station"])

        if normalized["label"]:
            state["last_label"] = normalized["label"]

        if normalized["mode"]:
            state["last_mode"] = normalized["mode"]

        if normalized["frequency"] > 0:
            if state["first_frequency"] == 0:
                state["first_frequency"] = normalized["frequency"]

            state["last_frequency"] = normalized["frequency"]

        state["military"] = state["military"] or normalized["military"]

        self.catalog[icao] = state

        tags = {"airframe_icao": icao}

        fields = {
            "tail": state["tail"],
            "flight": state["flight"],
            "country": state["country"],
            "military": state["military"],
            "first_seen": state["first_seen"],
            "last_seen": state["last_seen"],
            "first_frequency": state["first_frequency"],
            "last_frequency": state["last_frequency"],
            "last_station": state["last_station"],
            "last_label": state["last_label"],
            "last_mode": state["last_mode"],
            "message_count": state["message_count"],
            "decoded_messages": state["decoded_messages"],
            "text_messages": state["text_messages"],
            "station_count": len(state["stations"]),
        }

        return line_protocol(
            CATALOG_MEASUREMENT,
            tags,
            fields,
            timestamp_ns=CATALOG_TIMESTAMP_NS,
        )

    async def _write_with_retries(self, lines):
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                await self._write(lines)
                return
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    await asyncio.sleep(self.retry_delay)

        raise last_error

    async def _write(self, lines):
        body = ("\n".join(lines) + "\n").encode("utf-8")
        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "text/plain; charset=utf-8",
            "User-Agent": "airframes-socket-client",
        }
        params = urlencode(
            {
                "org": self.org,
                "bucket": self.bucket,
                "precision": "ns",
            }
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with self.session.post(
            f"{self.url}/api/v2/write?{params}",
            data=body,
            headers=headers,
            timeout=timeout,
        ) as response:
            if response.status >= 400:
                content = await response.text()
                raise aiohttp.ClientResponseError(
                    history=(),
                    request_info=response.request_info,
                    status=response.status,
                    message=content,
                    headers=response.headers,
                )

    def _log_error(self, message):
        now = time.monotonic()
        if now - self.last_error_at < 10:
            return
        self.last_error_at = now
        print(message, file=sys.stderr)


def build_event_line(payload):
    normalized = normalize_airframes_message(payload)

    tags = {
        "station": normalized["station"] or "unknown",
        "country": normalized["country"] or "unknown",
        "source": normalized["source"] or "unknown",
        "source_type": normalized["source_type"] or "unknown",
        "label": normalized["label"] or "unknown",
        "mode": normalized["mode"] or "unknown",
        "military": bool_tag(normalized["military"]),
    }

    text = normalized["text"] or ""

    fields = {
        "airframe_icao": normalized["airframe_icao"] or "unknown",
        "tail": normalized["tail"] or "unknown",
        "flight": normalized["flight"] or "unknown",
        "frequency": normalized["frequency"],
        "decoded_ok": int(normalized["decoded_ok"]),
        "libacars_ok": int(normalized["libacars_ok"]),
        "api_cached": int(normalized["api_cached"]),
        "text_present": int(bool(text)),
        "text_length": len(text),
        "has_tail": int(bool(normalized["tail"])),
        "has_flight": int(bool(normalized["flight"])),
        "event_count": 1,
    }

    timestamp_ns = parse_timestamp_ns(normalized["timestamp"])

    return line_protocol(
        EVENT_MEASUREMENT,
        tags,
        fields,
        timestamp_ns=timestamp_ns,
    )


def normalize_airframes_message(payload):
    return {
        "timestamp": payload.get("timestamp") or payload.get("created_at"),
        "airframe_icao": clean_string(get_nested_value(payload, "airframe.icao")),
        "tail": clean_string(
            get_nested_value(payload, "airframe.tail") or payload.get("tail")
        ),
        "flight": clean_string(
            get_nested_value(payload, "flight.flight_iata")
            or get_nested_value(payload, "flight.flight_icao")
            or get_nested_value(payload, "flight.flight")
        ),
        "station": clean_string(get_nested_value(payload, "station.ident")),
        "country": clean_string(get_nested_value(payload, "station.country_code")),
        "source": clean_string(payload.get("source")),
        "source_type": clean_string(payload.get("source_type")),
        "label": clean_string(payload.get("label")),
        "mode": clean_string(payload.get("mode")),
        "military": bool_value(get_nested_value(payload, "airframe.military")),
        "frequency": float_value(payload.get("frequency"), default=0.0),
        "decoded_ok": bool_value(get_nested_value(payload, "acars_decoded.ok")),
        "libacars_ok": bool_value(get_nested_value(payload, "libacars.ok")),
        "api_cached": bool_value(payload.get("airframes_api")),
        "text": payload.get("text") if isinstance(payload.get("text"), str) else "",
    }


def line_protocol(measurement, tags, fields, timestamp_ns=None):
    tag_part = ",".join(
        f"{escape_key(key)}={escape_tag_value(value)}"
        for key, value in sorted(tags.items())
        if value is not None and value != ""
    )
    field_part = ",".join(
        f"{escape_key(key)}={format_field_value(value)}"
        for key, value in fields.items()
        if value is not None
    )

    if not field_part:
        return None

    line = escape_key(measurement)
    if tag_part:
        line = f"{line},{tag_part}"
    line = f"{line} {field_part}"
    if timestamp_ns is not None:
        line = f"{line} {timestamp_ns}"
    return line


def parse_timestamp_ns(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return int(dt.timestamp() * 1_000_000_000)


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_string(value):
    if value is None:
        return ""
    return str(value).strip()


def float_value(value, default=0.0):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def bool_tag(value):
    return "true" if bool(value) else "false"


def bool_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return value is not None


def escape_key(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(" ", "\\ ")
        .replace(",", "\\,")
        .replace("=", "\\=")
    )


def escape_tag_value(value):
    return escape_key(value)


def escape_string_field(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def format_field_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value}i"
    if isinstance(value, float):
        return repr(value)
    return f'"{escape_string_field(value)}"'

import asyncio
import contextlib
import csv
import io
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import aiohttp

from src.flight_init import parse_flight_init_message
from src.helpers import get_libacars_decoded_text, get_nested_value

EVENT_MEASUREMENT = "airframes_event"
CATALOG_MEASUREMENT = "airframes_catalog"
FLIGHT_MEASUREMENT = "airframes_flight"
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
        # Active flight entity per airframe_icao, opened by an H1 MDINI/INI
        # message and closed when the next one arrives for that aircraft.
        self.flights = {}
        # Last timestamp (ns) emitted per (icao, station), used to avoid
        # point collisions when two messages share the same second.
        self._last_event_ts = {}

    async def start(self):
        if self.worker_task is not None:
            return
        self.session = aiohttp.ClientSession()
        # Preload the catalog from InfluxDB so counters survive restarts.
        try:
            await self._load_catalog()
        except Exception as exc:
            self._log_error(f"InfluxDB catalog preload failed: {exc}")
        try:
            await self._load_flights()
        except Exception as exc:
            self._log_error(f"InfluxDB flight preload failed: {exc}")
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

        flight_lines, flight_uid = self._process_flight_state(payload)
        lines.extend(flight_lines)

        event_line = self.build_event_line(payload, flight_uid=flight_uid)
        if event_line:
            lines.append(event_line)

        catalog_line = self.build_catalog_line(payload)
        if catalog_line:
            lines.append(catalog_line)

        return lines

    def build_event_line(self, payload, flight_uid=None):
        normalized = normalize_airframes_message(payload)

        tags = {
            "airframe_icao": normalized["airframe_icao"] or "unknown",
            "station": normalized["station"] or "unknown",
            "country": normalized["country"] or "unknown",
            "source": normalized["source"] or "unknown",
            "source_type": normalized["source_type"] or "unknown",
            "label": normalized["label"] or "unknown",
            "mode": normalized["mode"] or "unknown",
            "military": bool_tag(normalized["military"]),
        }

        text = normalized["text"] or ""
        libacars_text = normalized["libacars_text"] or ""

        fields = {
            "tail": normalized["tail"] or "unknown",
            "flight": normalized["flight"] or "unknown",
            "libacars_ok": int(normalized["libacars_ok"]),
            "text_present": int(bool(text)),
            "text_length": len(text),
            # Full message body so it can be browsed from Grafana.
            # Newlines are stored escaped (see escape_string_field).
            "text": text,
            # Pretty-printed libacars decode (JSON), for a dedicated
            # Grafana panel. Empty when there's nothing to decode.
            "libacars_text": libacars_text,
            "event_count": 1,
            # id of the active flight entity (opened by an H1 MDINI/INI
            # message) this event belongs to, if any.
            "flight_uid": flight_uid or "",
        }

        timestamp_ns = parse_timestamp_ns(normalized["timestamp"])
        if timestamp_ns is None:
            # Fall back to arrival time so deduplication still applies.
            timestamp_ns = time.time_ns()

        key = (tags["airframe_icao"], tags["station"])
        timestamp_ns = self._dedupe_ts(key, timestamp_ns)

        return line_protocol(
            EVENT_MEASUREMENT,
            tags,
            fields,
            timestamp_ns=timestamp_ns,
        )

    def _dedupe_ts(self, key, ts_ns):
        """Ensure strictly increasing timestamps per key.

        InfluxDB overwrites points that share measurement + tags + timestamp.
        ACARS timestamps often have second precision, so two messages from
        the same aircraft/station in the same second would silently replace
        each other. Bumping by 1 ns keeps every event.
        """
        last = self._last_event_ts.get(key, 0)
        if ts_ns <= last:
            ts_ns = last + 1
        self._last_event_ts[key] = ts_ns
        return ts_ns

    def build_catalog_line(self, payload):
        """The aircraft catalog is a stateful representation of the aircraft
        seen in the events, and is updated with each event."""
        normalized = normalize_airframes_message(payload)

        icao = normalized["airframe_icao"]
        if not icao:
            return None

        event_time = normalized["timestamp"] or utc_now_iso()

        state = self.catalog.get(icao)

        if state is None:
            state = self._new_catalog_state(event_time)

        state["message_count"] += 1
        state["last_seen"] = event_time

        if normalized["libacars_ok"]:
            state["decoded_messages"] += 1

        if normalized["text"]:
            state["text_messages"] += 1

        if normalized["libacars_text"]:
            state["last_decoded_text"] = normalized["libacars_text"]

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
            "last_station": state["last_station"],
            "last_label": state["last_label"],
            "last_mode": state["last_mode"],
            "last_decoded_text": state["last_decoded_text"],
            "message_count": state["message_count"],
            "decoded_messages": state["decoded_messages"],
            "text_messages": state["text_messages"],
            # The full station set cannot be recovered after a restart, only
            # its size; never let the published count go backwards.
            "station_count": max(
                state["station_count_floor"], len(state["stations"])
            ),
        }

        return line_protocol(
            CATALOG_MEASUREMENT,
            tags,
            fields,
            timestamp_ns=CATALOG_TIMESTAMP_NS,
        )

    @staticmethod
    def _new_catalog_state(event_time):
        return {
            "first_seen": event_time,
            "last_seen": event_time,
            "message_count": 0,
            "decoded_messages": 0,
            "text_messages": 0,
            "stations": set(),
            "station_count_floor": 0,
            "tail": "",
            "flight": "",
            "country": "",
            "military": False,
            "last_station": "",
            "last_label": "",
            "last_mode": "",
            "last_decoded_text": "",
        }

    def _process_flight_state(self, payload):
        """Track flight entities opened by H1 MDINI/INI messages.

        An MDINI/INI message for an aircraft closes whatever flight entity
        was previously active for it and opens a new one. Every other
        message for that aircraft is folded into the currently active
        entity (message_count, last_seen) without changing its identity.

        Returns (lines, flight_uid) where lines are line-protocol points for
        the airframes_flight measurement (closed and/or updated entity) and
        flight_uid is the id of the entity this payload belongs to, if any.
        """
        normalized = normalize_airframes_message(payload)
        icao = normalized["airframe_icao"]
        if not icao:
            return [], None

        event_time = normalized["timestamp"] or utc_now_iso()
        init = parse_flight_init_message(payload)
        state = self.flights.get(icao)
        lines = []

        if init:
            if state is not None and state["status"] == "active":
                state["status"] = "closed"
                state["closed_at"] = event_time
                lines.append(self._flight_line(icao, state))

            state = self._new_flight_state(icao, init, event_time)
            self.flights[icao] = state
        elif state is None:
            return [], None
        else:
            state["last_seen"] = event_time

        state["message_count"] += 1
        lines.append(self._flight_line(icao, state))

        return lines, state["flight_uid"]

    @staticmethod
    def _new_flight_state(icao, init, event_time):
        return {
            "flight_uid": f"{icao}-{init['flight_init_id']}-{event_time}",
            "callsign": init["callsign"],
            "departure": init["departure"],
            "arrival": init["arrival"],
            "dataref": init["dataref"],
            "opened_at": event_time,
            "last_seen": event_time,
            "closed_at": "",
            "status": "active",
            "message_count": 0,
        }

    @staticmethod
    def _flight_line(icao, state):
        tags = {"airframe_icao": icao, "flight_uid": state["flight_uid"]}
        fields = {
            "callsign": state["callsign"] or "unknown",
            "departure": state["departure"] or "unknown",
            "arrival": state["arrival"] or "unknown",
            "dataref": state["dataref"] or "unknown",
            "opened_at": state["opened_at"],
            "last_seen": state["last_seen"],
            "closed_at": state["closed_at"],
            "status": state["status"],
            "message_count": state["message_count"],
        }

        return line_protocol(
            FLIGHT_MEASUREMENT,
            tags,
            fields,
            timestamp_ns=CATALOG_TIMESTAMP_NS,
        )

    async def _load_flights(self):
        """Preload active flight entities from InfluxDB so a restart doesn't
        lose track of the flight currently in progress for each aircraft."""
        flux = (
            f'from(bucket: "{self.bucket}")'
            " |> range(start: 0)"
            f' |> filter(fn: (r) => r._measurement == "{FLIGHT_MEASUREMENT}")'
            ' |> pivot(rowKey: ["airframe_icao", "flight_uid"],'
            ' columnKey: ["_field"], valueColumn: "_value")'
        )
        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/vnd.flux",
            "Accept": "application/csv",
        }
        params = urlencode({"org": self.org})
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with self.session.post(
            f"{self.url}/api/v2/query?{params}",
            data=flux.encode("utf-8"),
            headers=headers,
            timeout=timeout,
        ) as response:
            if response.status >= 400:
                content = await response.text()
                raise RuntimeError(
                    f"flight query returned {response.status}: {content[:200]}"
                )
            body = await response.text()

        loaded = 0
        header = None
        for row in csv.reader(io.StringIO(body)):
            if not row or row[0].startswith("#"):
                continue
            if "airframe_icao" in row and "flight_uid" in row:
                header = {name: index for index, name in enumerate(row)}
                continue
            if header is None:
                continue

            def col(name, default=""):
                index = header.get(name)
                if index is None or index >= len(row):
                    return default
                return row[index]

            icao = col("airframe_icao")
            flight_uid = col("flight_uid")
            if not icao or not flight_uid or col("status") != "active":
                continue

            self.flights[icao] = {
                "flight_uid": flight_uid,
                "callsign": col("callsign"),
                "departure": col("departure"),
                "arrival": col("arrival"),
                "dataref": col("dataref"),
                "opened_at": col("opened_at"),
                "last_seen": col("last_seen"),
                "closed_at": col("closed_at"),
                "status": "active",
                "message_count": to_int(col("message_count")),
            }
            loaded += 1

        if loaded:
            print(
                f"InfluxDB flight preload: {loaded} active flights",
                file=sys.stderr,
            )

    async def _load_catalog(self):
        """Preload catalog state from InfluxDB so counters (message_count,
        first_seen, ...) survive process restarts instead of resetting to
        zero and overwriting the stored point."""
        flux = (
            f'from(bucket: "{self.bucket}")'
            " |> range(start: 0)"
            f' |> filter(fn: (r) => r._measurement == "{CATALOG_MEASUREMENT}")'
            ' |> pivot(rowKey: ["airframe_icao"], columnKey: ["_field"],'
            ' valueColumn: "_value")'
        )
        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/vnd.flux",
            "Accept": "application/csv",
        }
        params = urlencode({"org": self.org})
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with self.session.post(
            f"{self.url}/api/v2/query?{params}",
            data=flux.encode("utf-8"),
            headers=headers,
            timeout=timeout,
        ) as response:
            if response.status >= 400:
                content = await response.text()
                raise RuntimeError(
                    f"catalog query returned {response.status}: {content[:200]}"
                )
            body = await response.text()

        loaded = 0
        header = None
        for row in csv.reader(io.StringIO(body)):
            if not row or row[0].startswith("#"):
                continue
            if "airframe_icao" in row:
                header = {name: index for index, name in enumerate(row)}
                continue
            if header is None:
                continue

            def col(name, default=""):
                index = header.get(name)
                if index is None or index >= len(row):
                    return default
                return row[index]

            icao = col("airframe_icao")
            if not icao:
                continue

            state = self._new_catalog_state(col("first_seen") or utc_now_iso())
            state["first_seen"] = col("first_seen") or state["first_seen"]
            state["last_seen"] = col("last_seen") or state["last_seen"]
            state["message_count"] = to_int(col("message_count"))
            state["decoded_messages"] = to_int(col("decoded_messages"))
            state["text_messages"] = to_int(col("text_messages"))
            state["station_count_floor"] = to_int(col("station_count"))
            state["tail"] = col("tail")
            state["flight"] = col("flight")
            state["country"] = col("country")
            state["military"] = to_bool(col("military"))
            state["last_station"] = col("last_station")
            state["last_label"] = col("last_label")
            state["last_mode"] = col("last_mode")
            state["last_decoded_text"] = col("last_decoded_text")
            if state["last_station"]:
                state["stations"].add(state["last_station"])

            self.catalog[icao] = state
            loaded += 1

        if loaded:
            print(
                f"InfluxDB catalog preloaded: {loaded} aircraft",
                file=sys.stderr,
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
        "libacars_ok": bool_value(get_nested_value(payload, "libacars.ok")),
        "text": payload.get("text") if isinstance(payload.get("text"), str) else "",
        "libacars_text": get_libacars_decoded_text(payload),
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


def to_int(value, default=0):
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


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
    # Line protocol does not allow raw newlines inside field values: a
    # newline terminates the point. ACARS text frequently contains \r\n,
    # so store them as the literal two-character sequences "\n" / "\r".
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def format_field_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value}i"
    if isinstance(value, float):
        return repr(value)
    return f'"{escape_string_field(value)}"'
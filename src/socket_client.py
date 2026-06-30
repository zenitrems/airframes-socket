import json

import socketio

from src.helpers import (
    matches_filters,
    inline_summary,
    inline_summary_header,
    inline_summary_separator,
)
from src.libacars import DEFAULT_DECODER, LibacarsDecodeError, enrich_airframes_message


def build_client():
    return socketio.AsyncClient(
        logger=False,
        engineio_logger=False,
        reconnection=True,
        reconnection_attempts=5,
        reconnection_delay=2,
    )


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


def register_handlers(
    sio,
    stream_mode,
    filters,
    station_id=None,
    summary_mode=False,
    inline_summary_mode=False,
    inline_width=None,
    node_red_pipe=None,
    node_red_only=False,
    influx_client=None,
    libacars_enabled=False,
    libacars_decoder=DEFAULT_DECODER,
    libacars_timeout=5,
):
    printed_inline_header = False

    async def process_message(data):
        nonlocal printed_inline_header

        if not matches_filters(data, filters):
            return

        if libacars_enabled:
            try:
                data = await enrich_airframes_message(
                    data,
                    decoder=libacars_decoder,
                    timeout=libacars_timeout,
                )
            except (LibacarsDecodeError, OSError, ValueError) as exc:
                if isinstance(data, dict):
                    data = {
                        **data,
                        "libacars": {
                            "ok": False,
                            "error": str(exc),
                        },
                    }

        if node_red_pipe:
            await node_red_pipe.send(data)

        if influx_client:
            await influx_client.send(data)

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
    async def connect():
        print(f"Connected. Stream mode: {stream_mode}")
        if stream_mode == "sniff":
            await sio.emit("messages:sniff")
        elif stream_mode == "station":
            await sio.emit("station:monitor:start", station_id)

    @sio.event
    async def connect_error(data):
        print("Connection error:", data)

    @sio.event
    async def connect_timeout():
        print("Connection timeout")

    @sio.event
    async def reconnect():
        print("Reconnecting...")

    @sio.event
    async def reconnect_attempt():
        print("Reconnection attempt...")

    @sio.event
    async def reconnect_error():
        print("Reconnection error")

    @sio.event
    async def reconnect_failed():
        print("Reconnection failed")

    @sio.event
    async def disconnect():
        print("Disconnected from server")

    @sio.on("message")
    async def global_message(data):
        await process_message(data)

    @sio.on("messages:sniff:started")
    async def messages_sniff_started(data):
        print("Global message sniff started:", json.dumps(data, ensure_ascii=False))

    @sio.on("feed:authenticated")
    async def feed_authenticated(data):
        stations = data.get("stations") if isinstance(data, dict) else None
        station_count = len(stations or [])
        print(f"Feed authenticated. Stations: {station_count}")

    @sio.on("feed:message")
    async def feed_message(data):
        await process_message(data)

    @sio.on("station:monitor:started")
    async def station_monitor_started(data):
        print("Station monitor started:", json.dumps(data, ensure_ascii=False))

    @sio.on("station:monitor:data")
    async def station_monitor_data(data):
        if not isinstance(data, dict):
            return
        for message in data.get("newMessages") or []:
            await process_message(message)

    @sio.on("station:monitor:stopped")
    async def station_monitor_stopped(data):
        print("Station monitor stopped:", json.dumps(data, ensure_ascii=False))

    @sio.on("feed:error")
    async def feed_error(data):
        print("Feed error:", data)

    @sio.on("chat:error")
    async def chat_error(data):
        print("Chat error:", data)

    @sio.on("error")
    async def socket_error(data):
        print("Socket error:", data)

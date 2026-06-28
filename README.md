# airframes-socket

A simple Socket.IO client for consuming the `airframes.io` live stream, filtering messages, and optionally forwarding them to Node-RED or another application.

## Basic usage

```bash
python main.py --options
```

list all options:

```bash
python main.py --help
```

Use the authenticated feed with your API key:

```bash
AIRFRAMES_API_KEY=your_api_key python main.py --stream feed
```

or

```bash
python main.py --stream feed --api-key your_api_key
```

Monitor one station:

```bash
python main.py --stream station --station-id 123 --inline-summary
```

Filter by a payload field:

```bash
python main.py --filter station.country_code=US
python main.py --filter airframe.icao=AE1453
python main.py --filter airframe.military=true
#See data-example.json for a list of possible fields.
```

enable libacars decoding (`libacars` must be installed):

```bash
python main.py --libacars
```

Send events to Node-RED:

```bash
python main.py --node-red-url https://host:1880/airframes
```

Send only to Node-RED without local printing:

```bash
python main.py --node-red-url https://host:1880/airframes --node-red-only
```

Docker build and run:

```bash
docker build -t airframes-socket .
docker run --rm \
  -e STREAM=sniff \
  -e AIRFRAMES_API_KEY="$AIRFRAMES_API_KEY" \
  -e NODE_RED_URL="https://host:1880/airframes" \
  airframes-socket
```

Build the container with libacars support:

```bash
docker build --build-arg INSTALL_LIBACARS=true -t airframes-socket .
docker run --rm -e LIBACARS=true airframes-socket
```

## Stream modes

- `sniff`: sampled global stream using `messages:sniff` and `message` events.
- `feed`: authenticated, unsampled messages from stations using `feed:message`.
- `station`: live monitor for one station id using `station:monitor:data`.
- `auto` (default): uses `station` when `--station-id` is provided, `feed` when an API key is present, otherwise `sniff`.

## Node-RED or other HTTP endpoints

A Node-RED flow can receive events through an HTTP endpoint such as:

```text
POST /airframes
```

From there, messages can be stored, shown in dashboards, decoded, counted, or used for further processing.

## Notes

- Filters use the `field=value` format.
- You can repeat multiple `--filter` arguments.
- `--inline-summary` is useful for compact terminal logs.
- Set `AIRFRAMES_API_KEY` or pass `--api-key` for the authenticated feed.
- `--libacars` uses `/usr/local/bin/decode_acars_apps` by default. In Docker, build with `--build-arg INSTALL_LIBACARS=true` and run with `LIBACARS=true`.
- If you use HTTPS with untrusted certificates in Node-RED, you may need `--node-red-insecure-tls`.

# airframes-socket

A simple Socket.IO client for consuming the `airframes.io` live stream, filtering messages, and optionally forwarding them to Node-RED or another application.

## Basic usage

Show help:

```bash
python socket_client.py --help
```

Listen to the sampled global firehose:

```bash
python socket_client.py --stream sniff --inline-summary
```

Use the authenticated per-account feed for your own stations:

```bash
AIRFRAMES_API_KEY=your_api_key python socket_client.py --stream feed
```

Monitor one station:

```bash
python socket_client.py --stream station --station-id 123 --inline-summary
```

Filter by a payload field:

```bash
python socket_client.py --filter station.country_code=US
python socket_client.py --filter airframe.icao=AE1453
python socket_client.py --filter airframe.military=true
```


Decode supported ACARS applications with libacars before printing or forwarding:

```bash
python socket_client.py --libacars --inline-summary
```

Send libacars-enriched events to Node-RED:

```bash
python socket_client.py --libacars --node-red-url https://host:1880/airframes --node-red-only
```

Send events to Node-RED:

```bash
python socket_client.py --node-red-url https://host:1880/airframes
```

Send only to Node-RED without local printing:

```bash
python socket_client.py --node-red-url https://host:1880/airframes --node-red-only
```

## Stream modes

- `sniff`: sampled global stream using `messages:sniff` and `message` events.
- `feed`: authenticated, unsampled messages from your own stations using `feed:message`.
- `station`: live monitor for one station id using `station:monitor:data`.
- `auto`: uses `station` when `--station-id` is provided, `feed` when an API key is present, otherwise `sniff`.

## Node-RED

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
- `--libacars` uses `/usr/local/bin/decode_acars_apps` by default.
- If you use HTTPS with untrusted certificates in Node-RED, you may need `--node-red-insecure-tls`.

# airframes-socket

A simple client for consuming the `airframes.io` stream, filtering messages, and optionally forwarding them to Node-RED or another application.

## Basic usage

Help:

```bash
python socket_client.py --help
```


Filter by a payload field:

```bash
python socket_client.py --filter station.country_code=US
python socket_client.py --filter airframe.icao=AE1453
python socket_client.py --filter airframe.military=true
```

Send events to Node-RED:

```bash
python socket_client.py --node-red-url https://host:1880/airframes
```

Send only to Node-RED without local printing:

```bash
python socket_client.py --node-red-url https://host:1880/airframes --node-red-only
```

## Node-RED

The Node-RED flow can receive events through an HTTP endpoint such as:

```text
POST /airframes
```

From there, messages can be stored, shown in dashboards, and used for statistics or further processing.

## Notes

- Filters use the `field=value` format.
- You can repeat multiple `--filter` arguments.
- `--inline-summary` is useful for compact terminal logs.
- If you use HTTPS with untrusted certificates in Node-RED, you may need `--node-red-insecure-tls`.

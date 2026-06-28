import asyncio
import json
import os


DEFAULT_DECODER = "/usr/local/bin/decode_acars_apps"


class LibacarsDecodeError(RuntimeError):
    pass


def infer_direction(message):
    direction = str(message.get("link_direction") or "").strip().lower()
    if direction in {"u", "uplink", "ground-to-air", "ground_to_air"}:
        return "u"
    if direction in {"d", "downlink", "air-to-ground", "air_to_ground"}:
        return "d"
    return "d"


def parse_decoder_output(output):
    output = output.strip()
    if not output:
        return None

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        pass

    for line in reversed([line.strip() for line in output.splitlines() if line.strip()]):
        if not line.startswith(("{", "[")):
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue

    return output


async def decode_acars_message(direction, label, text, decoder=DEFAULT_DECODER, timeout=5):
    label = str(label or "").strip().upper()
    text = str(text or "")
    direction = str(direction or "d").strip().lower()

    if direction not in {"u", "d"}:
        raise ValueError("direction must be 'u' or 'd'")
    if not label:
        raise ValueError("label is required")
    if not text:
        raise ValueError("text is required")

    env = os.environ.copy()
    env["LA_JSON"] = "1"

    try:
        process = await asyncio.create_subprocess_exec(
            decoder,
            direction,
            label,
            text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise LibacarsDecodeError(f"decoder timed out after {timeout}s") from exc

    stdout_text = stdout.decode("utf-8", errors="replace")
    stderr_text = stderr.decode("utf-8", errors="replace")

    if process.returncode != 0:
        raise LibacarsDecodeError(stderr_text.strip() or f"decoder exited with {process.returncode}")

    return parse_decoder_output(stdout_text)


async def decode_airframes_message(message, decoder=DEFAULT_DECODER, timeout=5):
    if not isinstance(message, dict):
        return None

    label = str(message.get("label") or "").strip().upper()
    text = message.get("text")

    # Allow any libacars-supported label here so the wrapper can decode
    # FANS-1/A ADS-C, FANS-1/A CPDLC, MIAM, Media Advisory, OHMA, and similar
    if not label or not text:
        return None

    direction = infer_direction(message)
    decoded = await decode_acars_message(
        direction=direction,
        label=label,
        text=text,
        decoder=decoder,
        timeout=timeout,
    )

    return {
        "ok": True,
        "label": label,
        "direction": direction,
        "decoded": decoded,
    }


async def enrich_airframes_message(message, decoder=DEFAULT_DECODER, timeout=5):
    decoded = await decode_airframes_message(message, decoder=decoder, timeout=timeout)
    if decoded is None:
        return message

    enriched = dict(message)
    enriched["libacars"] = decoded
    return enriched

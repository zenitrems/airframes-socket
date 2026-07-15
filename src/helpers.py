import shutil
import json

INLINE_COLUMN_SEPARATOR = " | "
INLINE_MIN_TEXT_WIDTH = 11
DEFAULT_INLINE_WIDTH = 120
INLINE_SUMMARY_BASE_COLUMNS = [
    ("time", 24, 15),
    ("type", 8, 3),
    ("station", 19, 12),
    ("cc", 2, 2),
    ("icao", 6, 6),
    ("tail", 8, 8),
    ("e", 1, 1),
    ("m", 1, 1),
    ("l", 2, 2),
    ("b", 1, 1),
    ("a", 1, 1),
]


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

    return [(column["name"], column["width"]) for column in columns] + [
        ("text", text_width)
    ]


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

    libacars_ok = get_nested_value(data, "libacars.ok")
    text_content = ""

    if libacars_ok:
        # Extract meaningful decoded information
        label = get_nested_value(data, "libacars.label")
        decoded = get_nested_value(data, "libacars.decoded")

        if decoded:
            if isinstance(decoded, dict):
                # Extract key fields from decoded message
                text_parts = []

                # Common decoded fields to display
                display_fields = [
                    "message_type",
                    "report_type",
                    "aircraft_id",
                    "position",
                    "altitude",
                    "flight_id",
                    "status",
                ]

                for field in display_fields:
                    if field in decoded:
                        value = decoded[field]
                        if value:
                            text_parts.append(f"{field}={value}")

                if text_parts:
                    text_content = f"[{label}] " + " ".join(text_parts)
                else:
                    # Show decoded summary
                    text_content = (
                        f"[{label}] Decoded: "
                        + json.dumps(decoded, ensure_ascii=False)[:80]
                    )
            else:
                # If decoded is not a dict, show as string
                text_content = f"[{label}] {str(decoded)[:80]}"
    else:
        # Show raw message text if no libacars decoding
        text = data.get("text")
        if text:
            text_content = text[:80]

    values = {
        "time": data.get("timestamp"),
        "type": get_nested_value(data, "station.source_type"),
        "station": get_nested_value(data, "station.ident"),
        "cc": get_nested_value(data, "station.country_code"),
        "icao": get_nested_value(data, "airframe.icao"),
        "tail": get_nested_value(data, "airframe.tail") or data.get("tail"),
        "e": data.get("error"),
        "m": data.get("mode"),
        "l": data.get("label"),
        "b": data.get("block_id"),
        "a": data.get("ack"),
        "text": text_content if text_content else data.get("text", ""),
    }

    return INLINE_COLUMN_SEPARATOR.join(
        format_table_value(values[column], width) for column, width in columns
    )


def get_libacars_summary(message):
    if not isinstance(message, dict):
        return None

    libacars = message.get("libacars")
    if not libacars or not isinstance(libacars, dict):
        return None

    if not libacars.get("ok"):
        error = libacars.get("error")
        if error:
            return f"Error: {error}"
        return None

    label = libacars.get("label", "")
    decoded = libacars.get("decoded")

    if not decoded:
        return None

    if isinstance(decoded, dict):
        # Try to extract meaningful fields
        summary_parts = []

        # CPDLC position reports
        if label in {"SA", "AA", "B6", "BA", "A6", "MA"}:
            for key in ["position", "flight_id", "altitude", "flight_level"]:
                if key in decoded and decoded[key]:
                    summary_parts.append(f"{key}={decoded[key]}")

        # ADS-C reports
        elif label in {"S1", "S6"}:
            for key in ["latitude", "longitude", "altitude", "ground_speed"]:
                if key in decoded and decoded[key]:
                    summary_parts.append(f"{key}={decoded[key]}")

        # Generic key extraction
        if not summary_parts:
            for key in list(decoded.keys())[:3]:  # Show first 3 keys
                value = decoded[key]
                if value:
                    summary_parts.append(f"{key}={str(value)[:20]}")

        return (
            f"[{label}] " + " ".join(summary_parts)
            if summary_parts
            else f"[{label}] decoded"
        )

    return f"[{label}] {str(decoded)[:50]}"


def get_libacars_decoded_text(message):
    """Full pretty-printed JSON of the libacars decode, for display in Grafana."""
    if not isinstance(message, dict):
        return ""

    libacars = message.get("libacars")
    if not isinstance(libacars, dict):
        return ""

    if not libacars.get("ok"):
        error = libacars.get("error")
        return f"Error: {error}" if error else ""

    decoded = libacars.get("decoded")
    if decoded is None:
        return ""

    if isinstance(decoded, str):
        return decoded

    return json.dumps(decoded, ensure_ascii=False, indent=2, sort_keys=True)

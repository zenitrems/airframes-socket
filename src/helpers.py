import shutil
import json

INLINE_COLUMN_SEPARATOR = " | "
INLINE_MIN_TEXT_WIDTH = 12
DEFAULT_INLINE_WIDTH = 120
INLINE_SUMMARY_BASE_COLUMNS = [
    ("time", 24, 19),
    ("station", 18, 12),
    ("cc", 2, 2),
    ("flight", 8, 6),
    ("icao", 6, 6),
    ("tail", 8, 6),
    ("mil", 3, 3),
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

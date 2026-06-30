import os


def load_dotenv(path=".env"):
    """Load KEY=VALUE pairs from a local .env file without overriding the shell."""
    try:
        with open(path, encoding="utf-8") as env_file:
            lines = env_file.readlines()
    except FileNotFoundError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        if line.startswith("export "):
            line = line[7:].lstrip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = strip_env_value(value.strip())

        if key and key not in os.environ:
            os.environ[key] = value


def strip_env_value(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def env_value(name, default=None):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def env_bool(name, default=False):
    value = env_value(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name, default=None):
    value = env_value(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_float(name, default=None):
    value = env_value(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def env_list(name, default=None):
    value = env_value(name)
    if value is None:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]

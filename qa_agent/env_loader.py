"""Lightweight .env loader that populates os.environ without external dependencies."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(env_path: str | Path | None = None) -> dict[str, str]:
    """Load key-value pairs from a .env file into os.environ if not already set.

    Supports comments (#), quoted values, and inline exports.
    Does not overwrite pre-existing environment variables.
    """
    if env_path is None:
        # Check current directory and parents up to 2 levels
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parent.parent / ".env",
            Path(__file__).resolve().parent.parent.parent / ".env",
        ]
        target: Path | None = None
        for c in candidates:
            if c.exists() and c.is_file():
                target = c
                break
        if target is None:
            return {}
        env_file = target
    else:
        env_file = Path(env_path)
        if not env_file.exists() or not env_file.is_file():
            return {}

    loaded: dict[str, str] = {}
    try:
        content = env_file.read_text(encoding="utf-8")
    except Exception:
        return {}

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()

        # Strip matching quotes if wrapped
        if len(val) >= 2 and (
            (val.startswith('"') and val.endswith('"'))
            or (val.startswith("'") and val.endswith("'"))
        ):
            val = val[1:-1]

        # Ignore placeholder values
        if not val or val.startswith("<PASTE_") or val.endswith("_HERE>"):
            continue

        loaded[key] = val
        if key not in os.environ:
            os.environ[key] = val

    return loaded


# Automatically load default .env on module import
load_dotenv()

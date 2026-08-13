"""Launch the WishForge FastAPI service as a local desktop sidecar.

The Tauri host owns the process lifetime and passes an application-data
directory plus an ephemeral loopback port. Environment setup happens before
importing ``app.main`` because that import creates cached settings/storage.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WishForge local FastAPI sidecar")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None)
    return parser.parse_args()


def _load_config(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> None:
    args = _parse_args()
    data_dir = args.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    config = _load_config(args.config)

    # A packaged desktop sidecar must not accidentally read a repository
    # `.env` file.  All non-secret settings arrive through the host/config
    # bridge and credentials arrive only as process environment variables.
    os.environ["WISHFORGE_DESKTOP_SIDECAR"] = "1"
    os.environ["WISHFORGE_STORAGE_PATH"] = str(data_dir / "wishforge.db")
    os.environ["WISHFORGE_CORS_ORIGINS"] = (
        "http://127.0.0.1:1420,http://localhost:1420,"
        "tauri://localhost,http://tauri.localhost"
    )
    os.environ["WISHFORGE_APP_DATA_DIR"] = str(data_dir)
    config_env = {
        "explanation_provider": "WISHFORGE_EXPLANATION_PROVIDER",
        "explanation_model": "WISHFORGE_EXPLANATION_MODEL",
        "explanation_base_url": "WISHFORGE_EXPLANATION_BASE_URL",
        "demo_mode": "WISHFORGE_DEMO_MODE",
    }
    for config_key, env_key in config_env.items():
        value = config.get(config_key)
        if value is not None:
            os.environ[env_key] = str(value).lower() if isinstance(value, bool) else str(value)

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()

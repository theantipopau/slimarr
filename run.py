"""
Entry point — starts Slimarr with system tray (Windows) or headless (other OS).
"""
from __future__ import annotations

import os
import sys
import traceback

# Ensure we're running from the project root
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

try:
    # Load config before anything else
    from backend.config import ensure_secrets, load_config

    config_path = os.path.join(ROOT, "config.yaml")
    config = load_config(config_path)
    ensure_secrets(config, config_path)
except Exception as e:
    print(f"\n[FATAL] Failed to load configuration: {e}", file=sys.stderr)
    traceback.print_exc()
    input("\nPress Enter to exit...")
    sys.exit(1)

# Create data directories BEFORE database.py is imported (engine is built at import time)
try:
    import os as _os
    for _d in ["data", "data/logs", "data/MediaCover", config.files.recycling_bin]:
        if _d:
            _os.makedirs(_os.path.join(ROOT, _d), exist_ok=True)
except Exception as e:
    print(f"\n[FATAL] Failed to create data directories: {e}", file=sys.stderr)
    traceback.print_exc()
    input("\nPress Enter to exit...")
    sys.exit(1)


def run_headless() -> None:
    try:
        import uvicorn
        from backend.config import get_config
        cfg = get_config()
        uvicorn.run(
            "backend.main:socket_app",
            host=cfg.server.host,
            port=cfg.server.port,
            log_level=cfg.server.log_level.lower(),
        )
    except Exception as e:
        print(f"\n[FATAL] Server failed to start: {e}", file=sys.stderr)
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    headless = "--headless" in sys.argv or sys.platform != "win32"

    if headless:
        run_headless()
    else:
        try:
            from tray import run_tray
            run_tray()
        except ImportError as e:
            print(f"Tray not available ({e}), running headless")
            run_headless()

"""
System tray application - pystray icon with menu.
Works in both dev mode (run directly) and as a PyInstaller bundle.
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser

from PIL import Image


def _resource_dir() -> str:
    """Directory containing bundled resources (images/, frontend/dist/)."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """
    User data directory (config.yaml, data/slimarr.db, logs/).
    - Bundled: %AppData%\\Slimarr
    - Dev:     same folder as tray.py
    """
    if getattr(sys, 'frozen', False):
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        return os.path.join(appdata, 'Slimarr')
    return os.path.dirname(os.path.abspath(__file__))


def _ensure_data_dir() -> str:
    """Create data dir and seed a default config.yaml if missing."""
    data = _data_dir()
    os.makedirs(data, exist_ok=True)
    os.makedirs(os.path.join(data, 'data'), exist_ok=True)
    os.makedirs(os.path.join(data, 'data', 'logs'), exist_ok=True)
    os.makedirs(os.path.join(data, 'data', 'MediaCover'), exist_ok=True)

    cfg_path = os.path.join(data, 'config.yaml')
    if not os.path.exists(cfg_path):
        # Seed from bundled template if available
        template = os.path.join(_resource_dir(), 'config.yaml.example')
        if os.path.exists(template):
            shutil.copy(template, cfg_path)
        else:
            # Write minimal defaults
            with open(cfg_path, 'w') as f:
                f.write('# Slimarr configuration\n# Edit these settings via the web UI at http://localhost:9494\nserver:\n  port: 9494\n')
    return cfg_path


def _startup_log_path() -> str:
    return os.path.join(_data_dir(), 'data', 'logs', 'startup.log')


def _log_startup(message: str) -> None:
    try:
        os.makedirs(os.path.dirname(_startup_log_path()), exist_ok=True)
        with open(_startup_log_path(), 'a', encoding='utf-8') as handle:
            handle.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {message}\n')
    except Exception:
        pass


def _get_icon_path() -> str:
    return os.path.join(_resource_dir(), 'images', 'icon.PNG')


def _open_browser(icon=None, item=None) -> None:
    from backend.config import get_config, load_config

    cfg_path = os.path.join(_data_dir(), 'config.yaml')
    if os.path.exists(cfg_path):
        port = load_config(_ensure_data_dir()).server.port
    else:
        port = get_config().server.port
    webbrowser.open(f'http://localhost:{port}')


_server_thread: threading.Thread | None = None
_server_running = False


def _start_server() -> None:
    global _server_running
    import uvicorn
    from backend.config import ensure_secrets, get_config, set_config_path

    try:
        cfg_path = _ensure_data_dir()
        data_dir = _data_dir()
        db_path = os.path.join(data_dir, 'data', 'slimarr.db')
        os.environ['SLIMARR_DB'] = db_path

        # Tell config module where to find config.yaml (important for bundled app).
        set_config_path(cfg_path)
        config = get_config()
        ensure_secrets(config, cfg_path)

        # Keep relative config paths under AppData for installed builds.
        os.chdir(data_dir)
        _log_startup(f'Starting Slimarr from resources={_resource_dir()} data={data_dir} db={db_path}')
    except Exception:
        _log_startup('Startup preparation failed:\n' + traceback.format_exc())
        raise

    _server_running = True
    try:
        uvicorn.run(
            'backend.main:socket_app',
            host=config.server.host,
            port=config.server.port,
            log_level=config.server.log_level.lower(),
        )
    except Exception:
        _log_startup('Server crashed:\n' + traceback.format_exc())
        raise
    finally:
        _server_running = False


def _toggle_server(icon=None, item=None) -> None:
    global _server_thread
    if _server_running:
        # Can't easily stop uvicorn in thread; restart process as workaround.
        os.execv(sys.executable, [sys.executable] + sys.argv)
    else:
        _server_thread = threading.Thread(target=_start_server, daemon=True)
        _server_thread.start()


def _exit_app(icon=None, item=None) -> None:
    icon.stop()
    os._exit(0)


def run_tray() -> None:
    import pystray
    from pystray import MenuItem as Item

    icon_path = _get_icon_path()
    try:
        image = Image.open(icon_path)
    except Exception:
        # Fallback: create a simple green square
        image = Image.new("RGB", (64, 64), color="#4CAF50")

    menu = pystray.Menu(
        Item("Open Slimarr", _open_browser, default=True),
        pystray.Menu.SEPARATOR,
        Item("Start / Restart Service", _toggle_server),
        pystray.Menu.SEPARATOR,
        Item("Exit", _exit_app),
    )

    icon = pystray.Icon("Slimarr", image, "Slimarr", menu)

    # Start the server in the background when the tray starts
    global _server_thread
    _server_thread = threading.Thread(target=_start_server, daemon=True)
    _server_thread.start()

    # Open browser after a brief delay unless a launcher script handles it.
    if os.environ.get("SLIMARR_NO_AUTO_BROWSER", "").lower() in {"1", "true", "yes"}:
        icon.run()
        return

    # Open browser after a brief delay
    def _delayed_open():
        from backend.config import load_config

        port = load_config(_ensure_data_dir()).server.port
        health_url = f'http://127.0.0.1:{port}/api/v1/system/health'
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(health_url, timeout=1):
                    break
            except Exception:
                time.sleep(0.5)
        _open_browser()

    threading.Thread(target=_delayed_open, daemon=True).start()

    icon.run()

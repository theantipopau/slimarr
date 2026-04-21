"""
System tray application — pystray icon with menu.
Works in both dev mode (run directly) and as a PyInstaller bundle.
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import webbrowser

from PIL import Image


def _resource_dir() -> str:
    """Directory containing bundled resources (images/, frontend/dist/)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """
    User data directory (config.yaml, data/slimarr.db, logs/).
    - Bundled: %AppData%\Slimarr
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


def _get_icon_path() -> str:
    return os.path.join(_resource_dir(), 'images', 'icon.PNG')


def _open_browser(icon=None, item=None) -> None:
    from backend.config import get_config
    config = get_config()
    port = config.server.port
    webbrowser.open(f'http://localhost:{port}')


_server_thread: threading.Thread | None = None
_server_running = False


def _start_server() -> None:
    global _server_running
    import uvicorn
    from backend.config import get_config, load_config, set_config_path

    cfg_path = _ensure_data_dir()
    # Tell config module where to find config.yaml (important for bundled app)
    set_config_path(cfg_path)
    # Also change CWD to data dir so relative db path in SQLAlchemy resolves correctly
    os.chdir(_data_dir())
    config = get_config()

    _server_running = True
    uvicorn.run(
        'backend.main:socket_app',
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level.lower(),
    )
    _server_running = False


def _toggle_server(icon=None, item=None) -> None:
    global _server_thread
    if _server_running:
        # Can't easily stop uvicorn in thread — restart process as workaround
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

    # Open browser after a brief delay
    def _delayed_open():
        import time
        time.sleep(2)
        _open_browser()

    threading.Thread(target=_delayed_open, daemon=True).start()

    icon.run()

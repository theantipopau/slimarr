"""
System tray application — pystray icon with menu.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser

from PIL import Image


def _get_icon_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "images", "icon.PNG")


def _open_browser(icon=None, item=None) -> None:
    from backend.config import get_config
    config = get_config()
    port = config.server.port
    webbrowser.open(f"http://localhost:{port}")


_server_thread: threading.Thread | None = None
_server_running = False


def _start_server() -> None:
    global _server_running
    import uvicorn
    from backend.config import get_config, load_config

    # Ensure config is loaded
    load_config(os.path.join(os.path.dirname(__file__), "config.yaml"))
    config = get_config()

    _server_running = True
    uvicorn.run(
        "backend.main:socket_app",
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

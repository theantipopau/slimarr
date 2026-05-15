"""
Cross-platform filesystem and OS utilities for Slimarr.

Provides path normalisation, container detection, OS detection,
and disk-space helpers that work identically on Windows, Linux, and macOS.
"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Optional


# ── OS / container detection ─────────────────────────────────────────────────

def is_windows() -> bool:
    return sys.platform == "win32"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_docker() -> bool:
    """Return True when running inside a Docker container."""
    # Check /.dockerenv (created by Docker runtime)
    if os.path.exists("/.dockerenv"):
        return True
    # Check /proc/1/cgroup for docker/containerd/kubepods references
    try:
        with open("/proc/1/cgroup", "r") as f:
            content = f.read()
            if any(k in content for k in ("docker", "containerd", "kubepods")):
                return True
    except OSError:
        pass
    # Check SLIMARR_DOCKER env var (explicit override)
    return os.environ.get("SLIMARR_DOCKER", "").lower() in ("1", "true", "yes")


def container_id() -> Optional[str]:
    """Return the Docker container short-ID if running in Docker, else None."""
    if not is_docker():
        return None
    try:
        with open("/proc/self/cgroup", "r") as f:
            for line in f:
                parts = line.strip().split("/")
                for part in reversed(parts):
                    if len(part) == 64 and all(c in "0123456789abcdef" for c in part):
                        return part[:12]
    except OSError:
        pass
    return os.environ.get("HOSTNAME", None)


def os_info() -> dict[str, str]:
    """Return a concise dict of OS / runtime facts used in startup logging."""
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "in_docker": str(is_docker()),
        "container_id": container_id() or "",
    }


# ── Path normalisation ────────────────────────────────────────────────────────

def normalize_path(path: str) -> str:
    """Expand user/env vars and resolve to an absolute POSIX-style string.

    On Windows the result still uses the native separator so that OS calls
    work correctly, but leading/trailing whitespace and double-separators are
    cleaned up.  The returned string is always absolute.
    """
    if not path:
        return path
    expanded = os.path.expandvars(os.path.expanduser(path.strip()))
    return os.path.normpath(expanded)


def to_posix(path: str) -> str:
    """Convert a path string to forward-slash notation (useful for logging)."""
    return Path(path).as_posix()


def safe_makedirs(path: str, mode: int = 0o755) -> None:
    """Create *path* and all parents, respecting the container umask.

    Does nothing if the directory already exists.  Raises on genuine errors.
    """
    os.makedirs(path, mode=mode, exist_ok=True)


# ── Disk space ────────────────────────────────────────────────────────────────

def disk_free_bytes(path: str) -> Optional[int]:
    """Return free bytes for the filesystem containing *path*, or None on error."""
    try:
        existing = _find_existing_ancestor(path)
        if not existing:
            return None
        if is_windows():
            return _win_disk_free(existing)
        stat = os.statvfs(existing)
        return stat.f_bavail * stat.f_frsize
    except Exception:
        return None


def disk_total_bytes(path: str) -> Optional[int]:
    """Return total bytes for the filesystem containing *path*, or None on error."""
    try:
        existing = _find_existing_ancestor(path)
        if not existing:
            return None
        if is_windows():
            return _win_disk_total(existing)
        stat = os.statvfs(existing)
        return stat.f_blocks * stat.f_frsize
    except Exception:
        return None


def _find_existing_ancestor(path: str) -> Optional[str]:
    """Walk up *path* until an existing filesystem entry is found."""
    current = os.path.abspath(path)
    while True:
        if os.path.exists(current):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _win_disk_free(path: str) -> Optional[int]:
    try:
        import ctypes
        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(path), None, None, ctypes.pointer(free_bytes)
        )
        return free_bytes.value
    except Exception:
        return None


def _win_disk_total(path: str) -> Optional[int]:
    try:
        import ctypes
        total_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(path), None, ctypes.pointer(total_bytes), None
        )
        return total_bytes.value
    except Exception:
        return None


# ── Write-permission check ────────────────────────────────────────────────────

def is_writable(path: str) -> bool:
    """Return True if *path* (or its nearest existing ancestor) is writable."""
    target = _find_existing_ancestor(path)
    if not target:
        return False
    return os.access(target, os.W_OK)

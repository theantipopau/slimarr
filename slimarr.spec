# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Slimarr
# Build with: pyinstaller slimarr.spec
#
# Prerequisites:
#   pip install pyinstaller
#   (run with venv active)

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ── Collect packages that PyInstaller can't auto-detect ──────────────────────
datas_extra = []
binaries_extra = []
hiddenimports_extra = []

for pkg in ['uvicorn', 'fastapi', 'starlette', 'sqlalchemy', 'aiosqlite',
            'socketio', 'engineio', 'passlib', 'jose', 'pystray', 'loguru',
            'apscheduler', 'httpx', 'anyio', 'h11']:
    d, b, h = collect_all(pkg)
    datas_extra += d
    binaries_extra += b
    hiddenimports_extra += h

hidden = hiddenimports_extra + [
    # uvicorn internals
    'uvicorn.logging',
    'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.loops.asyncio',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl', 'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto', 'uvicorn.protocols.websockets.websockets_impl',
    'uvicorn.lifespan', 'uvicorn.lifespan.on',
    # SQLAlchemy / aiosqlite
    'sqlalchemy.dialects.sqlite',
    'sqlalchemy.ext.asyncio',
    'aiosqlite',
    # Auth
    'passlib.handlers.bcrypt',
    'passlib.handlers.sha2_crypt',
    'jose.backends',
    # SocketIO async
    'engineio.async_drivers.asgi',
    'socketio.async_namespace',
    'socketio.async_server',
    # pystray Windows backend
    'pystray._win32',
    # PIL
    'PIL._tkinter_finder',
    # misc
    'multipart',
    'yaml',
]

a = Analysis(
    ['tray.py'],
    pathex=['.'],
    binaries=binaries_extra,
    datas=datas_extra + [
        ('frontend/dist',    'frontend/dist'),
        ('images',           'images'),
        ('config.yaml.example', '.'),
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'pandas', 'numpy',
              'IPython', 'jupyter', 'notebook', 'pytest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Slimarr',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,         # No console window — tray app
    windowed=True,
    icon='images/icon.ico',  # Built by build-installer.ps1
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Slimarr',
)

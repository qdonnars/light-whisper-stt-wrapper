# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Whisper STT.

whisper-cpp DLLs and model are NOT bundled; they live in a whisper-cpp/
folder next to the exe (too large + user may swap model).
"""

a = Analysis(
    ["whisper_stt.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "pystray._win32",
    ],
    # Pillow imports numpy if it is there, and PyInstaller then ships it: 30 MB
    # the app never uses. Whatever else sits in the build environment stays out.
    excludes=["numpy", "charset_normalizer"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="whisper_stt",
    icon="whisper_stt.ico",
    console=False,
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="whisper_stt",
)

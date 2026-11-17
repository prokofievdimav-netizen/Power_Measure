# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для DM858_PY.py
Драйвер мультиметра RIGOL DM858 через PyVISA + pyvisa-py (без системной VISA).
"""

from PyInstaller.utils.hooks import collect_all, copy_metadata

# ------------------------------------------------------------------
# hiddenimports
# ------------------------------------------------------------------
hiddenimports = [
    # PyVISA
    "pyvisa",
    "pyvisa.resources",
    "pyvisa.highlevel",
    "pyvisa.util",
    "pyvisa.ctwrapper",

    # pyvisa-py (чистый Python-бэкенд VISA)
    "pyvisa_py",
    "pyvisa_py.highlevel",
    "pyvisa_py.tcpip",
    "pyvisa_py.usb",
    "pyvisa_py.serial",
    "pyvisa_py.protocols",
    "pyvisa_py.protocols.usbtmc",
    "pyvisa_py.protocols.vxi11",
    "pyvisa_py.protocols.hislip",
    "pyvisa_py.protocols.serial",

    # pyusb (нужен для USB-TMC)
    "usb",
    "usb.core",
    "usb.util",
    "usb.backend",
    "usb.backend.libusb1",
    "usb.backend.libusb0",
    "usb.backend.openusb",
]

# ------------------------------------------------------------------
# datas: метаданные пакетов, чтобы работали __version__ / get_debug_info()
# ------------------------------------------------------------------
datas = []
for _pkg in ("pyvisa", "pyvisa-py", "pyusb"):
    try:
        datas += copy_metadata(_pkg)
    except Exception as e:
        print(f"[spec] copy_metadata({_pkg}) пропущен: {e}")

# ------------------------------------------------------------------
# binaries: libusb-1.0.dll — нужен pyusb на Windows
# ------------------------------------------------------------------
binaries = []
import os

_libusb_candidates = [
    r"C:\Windows\System32\libusb-1.0.dll",
    r"C:\Windows\SysWOW64\libusb-1.0.dll",
    r"C:\Program Files\libusb-1.0\libusb-1.0.dll",
]
for _p in _libusb_candidates:
    if os.path.exists(_p):
        binaries.append((_p, "."))
        print(f"[spec] libusb добавлен: {_p}")
        break
else:
    print("[spec] libusb-1.0.dll не найден — USB-TMC может не заработать. "
          "Положите libusb-1.0.dll рядом с exe вручную.")

# ------------------------------------------------------------------
# Analysis
# ------------------------------------------------------------------
a = Analysis(
    ['DM858_PY.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Системная VISA нам не нужна — работаем через pyvisa-py.
        # Явно исключаем возможные конфликты.
        "mysql",
        "mysql.connector",
        "cryptography",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DM858_PY',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        # UPX ломает некоторые DLL — исключаем
        "libusb-1.0.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
    ],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
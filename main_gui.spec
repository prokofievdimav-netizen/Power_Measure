# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для main_gui.py
GUI-приложение контроля печатных плат кварцевого резонатора-термостата.

Сборка:
    pyinstaller --clean main_gui.spec

Ключевые моменты:
  * Драйвер MySQL — PyMySQL (чистый Python, без бинарных DLL).
    Это убирает silent-crash при mysql.connector.connect() в --onefile,
    вызванный отсутствием/битым _rust.pyd и libcrypto/libssl из cryptography.
  * VISA — только pyvisa-py ('@py'), без системной visa32.dll/visa64.dll.
    Это убирает 'access violation reading 0x...' в viFindRsrc на чужих ПК.
    Для USB-TMC приложен libusb-1.0.dll.
  * dearpygui и reportlab тянут за собой данные/бинарники — collect_all.
  * Папка fonts/ (используется в fonts/Font.py) должна попасть в архив.
  * pymodbus / serial / pyvisa / pyvisa_py / usb / screeninfo грузятся
    динамически — добавлены в hiddenimports.
  * UPX отключён для чувствительных DLL (dearpygui, libusb, vcruntime).
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

# ---------------------------------------------------------------- данные/модули
datas = []
binaries = []
hiddenimports = []

# Пакеты с бинарниками/ресурсами/подмодулями — собираем целиком.
# mysql.connector и cryptography сюда НЕ входят: используется PyMySQL.
for _pkg in (
    "dearpygui",
    "reportlab",
    "screeninfo",
):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as e:
        print(f"[spec] collect_all({_pkg}) пропущен: {e}")

# ---------------------------------------------------------------- метаданные
# Нужны, чтобы работали __version__ и pyvisa.util.get_debug_info().
for _pkg in ("pyvisa", "pyvisa-py", "pyusb", "pymysql"):
    try:
        datas += copy_metadata(_pkg)
    except Exception as e:
        print(f"[spec] copy_metadata({_pkg}) пропущен: {e}")

# ---------------------------------------------------------------- драйвер MySQL
hiddenimports += [
    "pymysql",
    "pymysql.cursors",
    "pymysql.connections",
    "pymysql.converters",
    "pymysql.constants",
    "pymysql.constants.CLIENT",
    "pymysql.constants.CR",
    "pymysql.constants.ER",
    "pymysql.constants.FIELD_TYPE",
    "pymysql.constants.FLAG",
    "pymysql.protocol",
    "pymysql.charset",
    "pymysql.err",
    "pymysql.util",
]

# ---------------------------------------------------------------- оборудование
hiddenimports += [
    # Modbus-контроллер реле
    "pymodbus",
    "pymodbus.client",
    "pymodbus.client.sync",
    "pymodbus.client.ModbusSerialClient",
    "pymodbus.transaction",
    "pymodbus.framer",
    "pymodbus.factory",
    "serial",
    "serial.tools",
    "serial.tools.list_ports",

    # PyVISA — только backend pyvisa-py ('@py')
    "pyvisa",
    "pyvisa.resources",
    "pyvisa.highlevel",
    "pyvisa.util",
    "pyvisa.ctwrapper",          # на всякий случай (если кто-то дёрнет)
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

# ---------------------------------------------------------------- libusb-1.0.dll
# pyusb общается с USB-TMC через libusb. Кладём DLL рядом с exe.
_libusb_candidates = [
    r"C:\Windows\System32\libusb-1.0.dll",
    r"C:\Windows\SysWOW64\libusb-1.0.dll",
    r"C:\Program Files\libusb-1.0\libusb-1.0.dll",
    # рядом со скриптом:
    os.path.join(os.getcwd(), "libusb-1.0.dll"),
]
for _p in _libusb_candidates:
    if os.path.exists(_p):
        binaries.append((_p, "."))
        print(f"[spec] libusb добавлен: {_p}")
        break
else:
    print("[spec] libusb-1.0.dll не найден — USB-TMC может не заработать. "
          "Положите libusb-1.0.dll рядом с exe вручную.")

# ---------------------------------------------------------------- подмодули app
try:
    hiddenimports += collect_submodules("measurement_engine")
except Exception as e:
    print(f"[spec] collect_submodules(measurement_engine) пропущен: {e}")

# ---------------------------------------------------------------- ресурсы GUI
# Папка шрифтов, которую читает fonts/Font.py (FONT_NAME = 'MonoCondensed')
datas += [
    ("fonts", "fonts"),
]

# Если рядом с main_gui.py лежат .otf/.ttf в корне — раскомментируйте:
# datas += [("MonoCondensed.otf", ".")]
# datas += [("MonoCondensed.ttf", ".")]

# ---------------------------------------------------------------- анализ
a = Analysis(
    ['main_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Уменьшаем размер: ненужные тяжёлые библиотеки.
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "matplotlib",
        "IPython",
        "pytest",
        "notebook",
        "jupyter",
        # Явно исключаем mysql-connector и cryptography — они больше не нужны.
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
    name='main_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        # UPX иногда ломает эти DLL — исключаем.
        "dearpygui",
        "libusb-1.0.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
    ],
    runtime_tmpdir=None,
    console=True,                  # для отладки; потом можно False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
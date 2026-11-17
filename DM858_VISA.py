# -*- coding: utf-8 -*-
import os
import sys
import glob
import time

import pyvisa as visa


# ----------------------------------------------------------------------
# Диагностика VISA
# ----------------------------------------------------------------------
# Известные «родные» VISA-библиотеки на Windows и типовые пути к ним.
# Используется только в диагностике — сам драйвер работает через
# явно указанную пользователем DLL.
KNOWN_VISA_DLLS = {
    "NI-VISA": [
        r"C:\Windows\System32\visa64.dll",
        r"C:\Windows\System32\visa32.dll",
        r"C:\Program Files\IVI Foundation\VISA\Win64\Bin\visa64.dll",
        r"C:\Program Files (x86)\IVI Foundation\VISA\WinNT\Bin\visa32.dll",
    ],
    "Keysight VISA": [
        r"C:\Program Files\Keysight\IO Libraries Suite\bin\visa64.dll",
        r"C:\Program Files (x86)\Keysight\IO Libraries Suite\bin\visa32.dll",
        r"C:\Program Files\Agilent\IO Libraries Suite\bin\visa64.dll",
    ],
    "R&S VISA": [
        r"C:\Program Files\Rohde-Schwarz\RsVisa\RsVisa64.dll",
        r"C:\Program Files (x86)\Rohde-Schwarz\RsVisa\RsVisa32.dll",
    ],
    "RIGOL VISA": [
        r"C:\Program Files (x86)\RIGOL\Ultra Sigma\VISA\RIGOLVisa64.dll",
    ],
}


def find_installed_visas() -> dict:
    """
    Сканирует систему на наличие известных VISA-библиотек.
    Возвращает {имя: [пути, которые реально существуют]}.
    """
    found = {}
    for name, paths in KNOWN_VISA_DLLS.items():
        existing = [p for p in paths if os.path.exists(p)]
        if existing:
            found[name] = existing
    return found


def print_visa_info(rm=None):
    """
    Печатает сведения о VISA-окружении:
      * версия PyVISA;
      * какая библиотека реально загружена текущим ResourceManager;
      * какие VISA-библиотеки вообще установлены в системе.

    :param rm: уже созданный ResourceManager (если есть).
               Если None — создаётся временный для диагностики.
    """
    sep = "=" * 64
    print(sep)
    print("VISA diagnostics")
    print(sep)

    # --- PyVISA ---
    print(f"PyVISA version:         {visa.__version__}")
    print(f"Python:                 {sys.version.split()[0]} "
          f"({sys.executable})")
    print(f"Platform:               {sys.platform}")
    print()

    # --- Что реально загружено ---
    tmp_rm = None
    try:
        if rm is None:
            tmp_rm = visa.ResourceManager()
            rm = tmp_rm
        visalib = getattr(rm, "visalib", None)
        print(f"Loaded VISA library:    {visalib}")
        lib_path = None
        for attr in ("library_path", "_library_path", "path"):
            if visalib is not None and hasattr(visalib, attr):
                lib_path = getattr(visalib, attr)
                break
        if lib_path:
            print(f"Loaded library path:    {lib_path}")
            if os.path.exists(str(lib_path)):
                st = os.stat(lib_path)
                import datetime
                print(f"  mtime:                "
                      f"{datetime.datetime.fromtimestamp(st.st_mtime)}")
                print(f"  size:                 {st.st_size} bytes")
    except Exception as e:
        print(f"  ! не удалось получить visalib: {e}")
    finally:
        if tmp_rm is not None:
            try:
                tmp_rm.close()
            except Exception:
                pass

    print()

    # --- Что установлено в системе ---
    print("Установленные VISA (по известным путям):")
    found = find_installed_visas()
    if not found:
        print("  ничего не найдено среди известных путей")
    else:
        for name, paths in found.items():
            print(f"  * {name}:")
            for p in paths:
                print(f"      - {p}")

    print()
    print("Полная отладочная информация PyVISA:")
    try:
        from pyvisa.util import get_debug_info
        info = get_debug_info()
        for line in info.splitlines():
            print(f"  {line}")
    except Exception as e:
        print(f"  ! get_debug_info() недоступен: {e}")

    print(sep)


# ----------------------------------------------------------------------
# Драйвер
# ----------------------------------------------------------------------
class DM858:
    # Путь к VISA-библиотеке по умолчанию (NI-VISA на Windows).
    # Можно переопределить через конструктор.
    DEFAULT_VISA_DLL = r'C:\Windows\System32\visa64.dll'

    def __init__(self, resource_address=None,
                 visa_dll: str = DEFAULT_VISA_DLL,
                 check_visa: bool = True):
        """
        Инициализация мультиметра.

        :param resource_address: VISA-адрес прибора. Если None или пустая
            строка — выполняется автопоиск DM858 среди доступных
            VISA-ресурсов.
        :param visa_dll: путь к используемой VISA-DLL.
        :param check_visa: печатать ли диагностику VISA при инициализации.
        """
        self.visa_dll = visa_dll
        self.rm = visa.ResourceManager(visa_dll)

        if check_visa:
            print_visa_info(self.rm)

        if not resource_address:
            resource_address = self.find_device()
            if resource_address is None:
                raise RuntimeError(
                    "Не удалось найти мультиметр DM858 среди доступных "
                    "VISA-ресурсов."
                )
            print(f"Автоматически найден DM858: {resource_address}")

        self.instr = self.rm.open_resource(resource_address)
        self.instr.timeout = 5000           # Таймаут 5 секунд
        self.instr.write("*RST")            # Сброс прибора
        time.sleep(1)

        # Получаем идентификационную информацию при инициализации
        self.manufacturer = None
        self.model = None
        self.serial_number = None
        self.firmware_version = None
        self._get_identification()

    # ------------------------------------------------------------------
    # Поиск
    # ------------------------------------------------------------------
    def find_device(self):
        """
        Автоматический поиск прибора DM858.
        Возвращает строку с адресом ресурса или None, если прибор не найден.
        """
        resources = list(self.rm.list_resources())
        print(f"Доступные VISA-ресурсы: {resources}")

        # Сначала USB (там наш DM858), потом всё остальное —
        # чтобы не ждать таймауты на TCPIP-адресах, если USB уже найден.
        ordered = ([r for r in resources if r.upper().startswith('USB')] +
                   [r for r in resources if not r.upper().startswith('USB')])

        for res in ordered:
            instr = None
            try:
                instr = self.rm.open_resource(res)

                if res.upper().startswith('USB'):
                    # DM858 «просыпается» не мгновенно — даём больше времени
                    instr.timeout = 5000
                    try:
                        instr.read_termination = '\n'
                        instr.write_termination = '\n'
                    except Exception:
                        pass
                    time.sleep(0.5)
                else:
                    instr.timeout = 1500

                # До 3 попыток: первый *IDN? по USB-CDC часто пустой
                idn = None
                last_err = None
                for _ in range(3):
                    try:
                        idn = instr.query("*IDN?").strip()
                        if idn:
                            break
                    except Exception as e:
                        last_err = e
                        time.sleep(0.3)

                if not idn:
                    raise RuntimeError(
                        f"пустой ответ на *IDN? ({last_err})"
                    )

                print(f"  {res} -> {idn}")
                if "DM858" in idn.upper():
                    return res

            except Exception as e:
                # ВАЖНО: не молчим — иначе причину не увидеть
                print(f"  {res}: {type(e).__name__}: {e}")
                continue
            finally:
                if instr is not None:
                    try:
                        instr.close()
                    except Exception:
                        pass

        return None

    # ------------------------------------------------------------------
    # Идентификация
    # ------------------------------------------------------------------
    def _get_identification(self):
        """Получить и разобрать идентификационную информацию прибора."""
        idn_string = self.instr.query("*IDN?")
        parts = idn_string.strip().split(',')
        print('IDN', idn_string)
        if len(parts) >= 4:
            self.manufacturer = parts[0]
            self.model = parts[1]
            self.serial_number = parts[2]
            self.firmware_version = parts[3]
        else:
            raise ValueError("Неверный формат идентификационной строки")

    # ------------------------------------------------------------------
    # Режимы измерения
    # ------------------------------------------------------------------
    def configure_dc_voltage(self, range_val=10, resolution=0.001):
        """Конфигурация измерения DC напряжения."""
        self.instr.write(f"CONF:VOLT:DC {range_val},{resolution}")

    def configure_resistance_2w_old(self):
        """Конфигурация измерения сопротивления (2-проводное)."""
        self.instr.write("CONF:RES")

    def configure_resistance_2w(self, range_val=None):
        """
        Конфигурация измерения сопротивления (2-проводное).
        range_val — предел в Омах. Если None, используется режим
        по умолчанию/авто.
        """
        if range_val is None:
            self.instr.write("CONF:RES")
        else:
            self.instr.write(f"CONF:RES {range_val}")

    def configure_diode(self):
        """Конфигурация измерения диода."""
        self.instr.write("CONF:DIOD")

    def configure_capacitance(self):
        """Конфигурация измерения ёмкости."""
        self.instr.write("CONF:CAP")

    def set_measurement_mode(self, mode: str, range_val=None):
        """
        Универсальный метод переключения режима измерения.
        Допустимые значения: 'DCV', 'RES', 'DIOD', 'CAP'.
        Для 'RES' можно передать range_val в Омах.
        """
        mode = mode.upper()
        if mode == 'DCV':
            self.configure_dc_voltage()
        elif mode == 'RES':
            self.configure_resistance_2w(range_val)
        elif mode == 'DIOD':
            self.configure_diode()
        elif mode == 'CAP':
            self.configure_capacitance()
        else:
            raise ValueError(f"Неизвестный режим измерения: {mode}")

    def set_measurement_mode_old(self, mode: str):
        """
        Универсальный метод переключения режима измерения (legacy).
        Допустимые значения: 'DCV', 'RES', 'DIOD', 'CAP'.
        """
        mode = mode.upper()
        if mode == 'DCV':
            self.configure_dc_voltage()
        elif mode == 'RES':
            self.configure_resistance_2w()
        elif mode == 'DIOD':
            self.configure_diode()
        elif mode == 'CAP':
            self.configure_capacitance()
        else:
            raise ValueError(f"Неизвестный режим измерения: {mode}")

    # ------------------------------------------------------------------
    # Измерение
    # ------------------------------------------------------------------
    def measure(self):
        """Выполнить измерение и вернуть результат."""
        return float(self.instr.query("READ?"))

    def close(self):
        """Закрыть соединение с прибором."""
        try:
            if getattr(self, "instr", None) is not None:
                self.instr.close()
        finally:
            try:
                if getattr(self, "rm", None) is not None:
                    self.rm.close()
            except Exception:
                pass


# ----------------------------------------------------------------------
# Пример использования
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # --- 1. Полная диагностика VISA ДО создания драйвера ---
    # Здесь ResourceManager создаётся временно только для диагностики.
    print_visa_info()

    # --- 2. Создание драйвера ---
    # check_visa=True  → DM858 ещё раз напечатает, какая библиотека
    # реально используется (уже в составе рабочего ResourceManager).
    # Если нужно подавить диагностику — передайте check_visa=False.
    multimeter = DM858(check_visa=True)

    try:
        # Вывод идентификационной информации
        print(f"Производитель:    {multimeter.manufacturer}")
        print(f"Модель:           {multimeter.model}")
        print(f"Серийный номер:   {multimeter.serial_number}")
        print(f"Версия прошивки:  {multimeter.firmware_version}")
        print("-" * 40)

        # Настройка измерения DC напряжения
        multimeter.configure_dc_voltage(range_val=10, resolution=0.0001)

        # Выполнение и вывод 10 измерений
        for i in range(10):
            measurement = multimeter.measure()
            print(f"Измерение {i + 1}: {measurement:.6f} V")
            time.sleep(0.5)

    finally:
        multimeter.close()
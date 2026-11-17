# -*- coding: utf-8 -*-
"""
Драйвер мультиметра DM858 (RIGOL) через PyVISA с бэкендом pyvisa-py.

Используется ЧИСТО Python-реализация VISA — 'pyvisa-py'.
Внешняя библиотека NI-VISA / Keysight VISA / R&S VISA НЕ требуется.

Зависимости:
    pip install pyvisa pyvisa-py pyusb

Примечание:
  * Для USB-подключения DM858 (USB-TMC) нужен пакет `pyusb`.
  * На Windows для доступа к USB-устройству через libusb может
    потребоваться установить драйвер WinUSB/libusb через Zadig
    (если прибор не виден через pyvisa-py, но виден в диспетчере устройств).
  * Если прибор работает как USB-CDC (виртуальный COM-порт), вместо
    USB-TMC используйте ресурс 'ASRL<COMx>::INSTR'.
"""

import time
import pyvisa as visa


# Бэкенд pyvisa-py. Пустая строка '' = автоопределение (NI-VISA и т.п.).
# '@py' — принудительно чистый Python-бэкенд pyvisa-py.
VISA_BACKEND = '@py'


class DM858:
    #: Список известных шаблонов адресов USB-TMC для DM858 (на случай,
    #: если list_resources() не вернёт ничего — пробуем напрямую).
    #: RIGOL DM858 имеет VID 0x1AB1 (RIGOL Technologies).
    _USB_IDN_CANDIDATES = [
        # USB0::<VID>::<PID>::<serial>::INSTR — точный адрес подставляется
        # автоматически при переборе, см. _scan_usb_tmc()
    ]

    def __init__(self, resource_address: str = None,
                 backend: str = VISA_BACKEND):
        """
        :param resource_address: VISA-адрес прибора. Если None или пустая
            строка — выполняется автопоиск DM858.
        :param backend: бэкенд PyVISA ('@py' — pyvisa-py, '' — авто).
        """
        self.backend = backend

        try:
            self.rm = visa.ResourceManager(backend)
        except Exception as e:
            raise RuntimeError(
                f"Не удалось создать ResourceManager pyvisa-py "
                f"(backend={backend!r}): {e}. "
                f"Проверьте установку: pip install pyvisa pyvisa-py pyusb"
            ) from e

        if not resource_address:
            resource_address = self.find_device()
            if resource_address is None:
                raise RuntimeError(
                    "Не удалось найти мультиметр DM858 среди доступных "
                    "VISA-ресурсов (pyvisa-py)."
                )
            print(f"Автоматически найден DM858: {resource_address}")

        self.resource_address = resource_address
        self.instr = self.rm.open_resource(resource_address)
        self.instr.timeout = 5000          # 5 сек
        # Для USB-TMC обычно нужен '\n' как терминатор
        try:
            self.instr.read_termination = '\n'
            self.instr.write_termination = '\n'
        except Exception:
            pass

        self.instr.write("*RST")
        time.sleep(1)

        # Идентификация
        self.manufacturer = None
        self.model = None
        self.serial_number = None
        self.firmware_version = None
        self._get_identification()

    # ------------------------------------------------------------------
    # Поиск прибора
    # ------------------------------------------------------------------
    @classmethod
    def _scan_usb_tmc(cls, rm: visa.ResourceManager) -> list:
        """
        Возвращает список VISA-адресов USB-TMC-устройств, найденных
        через pyvisa-py. Если list_resources() не сработал — возвращает [].
        """
        try:
            resources = list(rm.list_resources())
        except Exception as e:
            print(f"  list_resources() error: {type(e).__name__}: {e}")
            resources = []
        print(f"Доступные VISA-ресурсы: {resources}")
        return resources

    @classmethod
    def _probe(cls, rm: visa.ResourceManager, res: str,
               timeout_ms: int = 5000) -> str:
        """
        Открывает ресурс, спрашивает *IDN?, возвращает ответ (str)
        или бросает исключение.
        """
        instr = rm.open_resource(res)
        try:
            instr.timeout = timeout_ms
            try:
                instr.read_termination = '\n'
                instr.write_termination = '\n'
            except Exception:
                pass
            # USB-TMC «просыпается» не мгновенно — до 3 попыток
            last_err = None
            for _ in range(3):
                try:
                    idn = instr.query("*IDN?").strip()
                    if idn:
                        return idn
                except Exception as e:
                    last_err = e
                    time.sleep(0.3)
            raise RuntimeError(f"пустой ответ на *IDN? ({last_err})")
        finally:
            try:
                instr.close()
            except Exception:
                pass

    @classmethod
    def find_device(cls, backend: str = VISA_BACKEND) -> str:
        """
        Автопоиск DM858 через pyvisa-py.
        Возвращает VISA-адрес ресурса или None.
        """
        rm = visa.ResourceManager(backend)
        resources = cls._scan_usb_tmc(rm)

        # USB-ресурсы идут первыми, чтобы не ждать таймауты на TCPIP/ASRL.
        ordered = ([r for r in resources if r.upper().startswith('USB')] +
                   [r for r in resources if not r.upper().startswith('USB')])

        for res in ordered:
            try:
                idn = cls._probe(rm, res)
                print(f"  {res} -> {idn}")
                if "DM858" in idn.upper():
                    return res
            except Exception as e:
                # Не молчим — иначе причину не увидеть
                print(f"  {res}: {type(e).__name__}: {e}")
                continue

        return None

    # ------------------------------------------------------------------
    # Идентификация
    # ------------------------------------------------------------------
    def _get_identification(self):
        """Получить и разобрать идентификационную информацию прибора."""
        idn_string = self.instr.query("*IDN?").strip()
        parts = idn_string.split(',')
        print("IDN:", idn_string)
        if len(parts) >= 4:
            self.manufacturer = parts[0]
            self.model = parts[1]
            self.serial_number = parts[2]
            self.firmware_version = parts[3]
        else:
            raise ValueError(
                f"Неверный формат идентификационной строки: {idn_string!r}"
            )

    # ------------------------------------------------------------------
    # Режимы измерения
    # ------------------------------------------------------------------
    def configure_dc_voltage(self, range_val=10, resolution=0.001):
        """Конфигурация измерения DC напряжения."""
        self.instr.write(f"CONF:VOLT:DC {range_val},{resolution}")

    def configure_resistance_2w(self, range_val=None):
        """
        Конфигурация измерения сопротивления (2-проводное).
        range_val — предел в Омах. Если None — режим по умолчанию/авто.
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

    # ------------------------------------------------------------------
    # Измерение
    # ------------------------------------------------------------------
    def measure(self) -> float:
        """Выполнить измерение и вернуть результат (float)."""
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
    multimeter = DM858()

    try:
        print(f"Производитель:    {multimeter.manufacturer}")
        print(f"Модель:           {multimeter.model}")
        print(f"Серийный номер:   {multimeter.serial_number}")
        print(f"Версия прошивки:  {multimeter.firmware_version}")
        print("-" * 40)

        multimeter.configure_dc_voltage(range_val=10, resolution=0.0001)
        for i in range(10):
            measurement = multimeter.measure()
            print(f"Измерение {i + 1}: {measurement:.6f} V")
            time.sleep(0.5)
    finally:
        multimeter.close()
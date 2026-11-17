from pymodbus import ModbusException
from pymodbus.client import ModbusSerialClient
from serial.tools import list_ports
import time
from typing import List, Optional

N_RELAYS = 16
BAUDRATE = 9600
DELAY_AFTER_OPERATION = 0.005  # 5 ms
RELAY_CMD_ON = 0x0100
RELAY_CMD_OFF = 0x0200


def list_serial_ports() -> List[str]:
    """Список доступных COM-портов на ПК."""
    return [p.device for p in list_ports.comports()]


def find_relay_port(slave_id: int = 1,
                    timeout: float = 0.5,
                    verbose: bool = True) -> Optional[str]:
    """
    Автопоиск COM-порта контроллера реле.

    Перебираем все доступные последовательные порты, пытаемся открыть
    и выполнить пробное чтение holding-регистров (адрес 0x01, N_RELAYS штук).
    Если ответ получен без ошибок — порт найден.

    :param slave_id: Modbus slave-id контроллера.
    :param timeout:  таймаут отклика на пробный запрос (сек).
    :param verbose:  печатать отладочную информацию.
    :return: имя порта ('COM3', '/dev/ttyUSB0', …) или None.
    """
    ports = list_serial_ports()
    if verbose:
        print(f"Доступные COM-порты: {ports}")
    if not ports:
        print("COM-порты не обнаружены.")
        return None

    for port in ports:
        client = None
        try:
            client = ModbusSerialClient(
                port=port,
                baudrate=BAUDRATE,
                stopbits=1,
                bytesize=8,
                parity='N',
                timeout=timeout,
            )
            if not client.connect():
                if verbose:
                    print(f"  {port}: не удалось открыть")
                continue

            try:
                response = client.read_holding_registers(
                    address=0x01, count=N_RELAYS, slave=slave_id
                )
                if not response.isError():
                    if verbose:
                        print(f"  {port}: OK — контроллер реле найден")
                    return port
                else:
                    if verbose:
                        print(f"  {port}: ошибка ответа Modbus")
            except Exception as e:
                if verbose:
                    print(f"  {port}: нет ответа ({e.__class__.__name__})")
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    print("Контроллер реле не найден ни на одном COM-порту.")
    return None


class RelayController:
    def __init__(self, port: Optional[str] = None, slave_id: int = 1):
        """
        :param port:     имя COM-порта. Если None — выполняется автопоиск.
        :param slave_id: Modbus slave-id (по умолчанию 1).
        """
        if not port:
            print("Автопоиск COM-порта контроллера реле...")
            port = find_relay_port(slave_id=slave_id)
            if port is None:
                raise RuntimeError(
                    "Не удалось автоматически найти COM-порт контроллера реле."
                )
            print(f"Автоматически выбран порт: {port}")

        self.port = port
        self.client = ModbusSerialClient(
            port=port,
            baudrate=BAUDRATE,
            stopbits=1,
            bytesize=8,
            parity='N',
            timeout=1,
        )
        self.slave_id = slave_id

    def connect(self) -> bool:
        return self.client.connect()

    def disconnect(self):
        self.client.close()

    def set_relays(self, states: List[bool]) -> None:
        """Установка всех реле в заданные состояния."""
        for operation in [False, True]:
            for i, state in enumerate(states):
                if state == operation:
                    self._set_single_relay(i, operation)
                    time.sleep(DELAY_AFTER_OPERATION)

    def _set_single_relay(self, relay_number: int, state: bool) -> None:
        """Установка одного реле."""
        address = relay_number + 1  # Адресация начинается с 1
        value = RELAY_CMD_ON if state else RELAY_CMD_OFF
        response = self.client.write_register(
            address=address,
            value=value,
            slave=self.slave_id,
        )
        if response.isError():
            raise ModbusException(response)

    def get_relays(self) -> List[bool]:
        """Чтение состояния всех реле."""
        response = self.client.read_holding_registers(
            address=0x01,
            count=N_RELAYS,
            slave=self.slave_id,
        )
        if response.isError():
            raise ModbusException(response)
        return [reg == 1 for reg in response.registers]

    @staticmethod
    def state_str_to_bool(state_str: str) -> List[bool]:
        if len(state_str) != N_RELAYS or any(c not in '01' for c in state_str):
            raise ValueError("Invalid state string format")
        return [c == '1' for c in state_str]

    @staticmethod
    def state_bool_to_str(states: List[bool]) -> str:
        return ''.join('1' if s else '0' for s in states)


# Пример использования
if __name__ == "__main__":
    # Порт можно не указывать — сработает автопоиск
    controller = RelayController(slave_id=1)

    if not controller.connect():
        print(f"Connection failed on {controller.port}")
        exit(1)

    try:
        states = controller.state_str_to_bool("0000000000000000")
        controller.set_relays(states)
        current_state = controller.get_relays()
        print("Current state:", controller.state_bool_to_str(current_state))
    except Exception as e:
        print(f"Error: {e}")
    finally:
        controller.disconnect()
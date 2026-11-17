#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from relay_controller import RelayController
from DM858 import DM858
import time

# ------------------------------------------------------------------
# Карта соответствия позиции переключателя и индексов реле.
# ------------------------------------------------------------------
POSITION_MAP = {
    1:  (0, 9),   # XT9 -> DB-9 pin1, XT10 -> DB-9 pin5
    2:  (0, 7),   # XT9 -> pin1,      XT10 -> pin3
    3:  (3, 6),   # XT9 -> pin6,      XT10 -> pin2
    4:  (4, 10),  # XT9 -> pin7,      XT10 -> pin8
    5:  (1, 9),   # XT9 -> pin3,      XT10 -> pin5
    6:  (0, 9),   # XT9 -> pin1,      XT10 -> pin5
    7:  (5, 11),  # XT9 -> pin8,      XT10 -> pin9 (Корпус)
    8:  (2, 6),   # XT9 -> pin5,      XT10 -> pin2
    9:  (5, 8),   # XT9 -> pin8,      XT10 -> pin4
    10: (4, 7),   # XT9 -> pin7,      XT10 -> pin3
    11: (3, 11),  # XT9 -> pin6,      XT10 -> pin9 (Корпус)
    12: (3, 6), # XT9 -> pin2,      XT10 -> pin6 (доп. реле)
}

# ------------------------------------------------------------------
# Последовательность режимов измерения для каждой позиции.
# Позиция 3 — сначала ёмкость, затем напряжение в режиме диода.
# ------------------------------------------------------------------
POSITION_MEASURE_SEQUENCE = {
    1:  ['DIOD'],
    2:  ['DIOD'],
    3:  ['DIOD'],
    4:  ['RES'],
    5:  ['RES'],
    6:  ['RES'],
    7:  ['RES'],
    8:  ['RES'],
    9:  ['RES'],
    10: ['RES'],
    11: ['RES'],
    12: ['CAP'],
}

# ------------------------------------------------------------------
# Пределы измерения сопротивления по позициям, в Омах.
# ------------------------------------------------------------------
POSITION_RESISTANCE_RANGE = {
    4: 100_000,        # 100 кОм — ожидаемое 10–100 кОм
    6: 100_000,        # 100 кОм — ожидаемое 10–100 кОм
    5: 100_000_000,    # 100 МОм — ожидаемое > 40 МОм
    7: 200,            # 200 Ом — ожидаемое около 7 Ом
    8: 10_000_000,     # 10 МОм
    9: 10_000_000,     # 10 МОм
    10: 10_000_000,    # 10 МОм
    11: 10_000_000,    # 10 МОм
}

# ------------------------------------------------------------------
# Пауза для стабилизации после переключения режима (сек).
# Для ёмкости — 5 сек, для остальных — 2 сек.
# ------------------------------------------------------------------
SETTLE_TIME = {
    'CAP': 5.0,
    'DIOD': 2.0,
    'RES': 2.0,
    'DCV': 2.0,
}
DEFAULT_SETTLE_TIME = 2.0

N_RELAYS = 16


def set_position(controller: RelayController, pos: int) -> list:
    """Установить реле в состояние, соответствующее позиции переключателя."""
    if pos not in POSITION_MAP:
        raise ValueError(f"Позиция должна быть от 1 до 12, получено: {pos}")
    states = [False] * N_RELAYS
    idx_xt9, idx_xt10 = POSITION_MAP[pos]
    states[idx_xt9] = True
    states[idx_xt10] = True
    controller.set_relays(states)
    return states


def turn_off_all(controller: RelayController) -> list:
    """Выключить все реле."""
    states = [False] * N_RELAYS
    controller.set_relays(states)
    return states


def measure_position(multimeter: DM858, pos: int) -> None:
    """Выполнить всю последовательность измерений для позиции."""
    modes = POSITION_MEASURE_SEQUENCE[pos]
    for mode in modes:
        # Для режима сопротивления определяем предел по позиции
        range_val = None
        if mode == 'RES':
            range_val = POSITION_RESISTANCE_RANGE.get(pos)

        multimeter.set_measurement_mode(mode, range_val=range_val)

        if range_val is not None:
            print(f"Режим мультиметра переключён на {mode}, предел {range_val} Ом")
        else:
            print(f"Режим мультиметра переключён на {mode}")

        # Пауза для стабилизации (для ёмкости — 5 сек)
        settle = SETTLE_TIME.get(mode, DEFAULT_SETTLE_TIME)
        print(f"Пауза {settle} сек для стабилизации...")
        time.sleep(settle)

        # Измерение
        result = multimeter.measure()
        print(f"Результат измерения ({mode}): {result}")

def main():
    # ===== Настройки =====
    RELAY_PORT = None
    SLAVE_ID = 1

    # ===== Инициализация =====
    relay = RelayController(port=RELAY_PORT, slave_id=SLAVE_ID)
    if not relay.connect():
        print(f"Не удалось открыть порт {RELAY_PORT}")
        return

    # Автоматический поиск DM858 среди VISA-ресурсов
    multimeter = DM858()
    print(f"Мультиметр: {multimeter.model}, S/N: {multimeter.serial_number}")

    print("\nДоступные команды:")
    print("  1..12  — установить позицию и выполнить измерение")
    print("  0, off — выключить все реле")
    print("  q      — выход\n")

    try:
        while True:
            user_input = input("Команда: ").strip().lower()
            if user_input == 'q':
                break

            # Режим выключения всех реле
            if user_input in ('0', 'off', 'выкл'):
                try:
                    states = turn_off_all(relay)
                    state_str = relay.state_bool_to_str(states)
                    print(f"Все реле выключены. Состояние: {state_str}")
                except Exception as e:
                    print(f"Ошибка при выключении реле: {e}")
                continue

            # Установка позиции и измерение
            try:
                pos = int(user_input)
            except ValueError:
                print("Ошибка: введите число от 1 до 12, '0'/'off' или 'q'.")
                continue

            if not (1 <= pos <= 12):
                print("Ошибка: позиция должна быть от 1 до 12.")
                continue

            try:
                # 1. Установка реле
                states = set_position(relay, pos)
                state_str = relay.state_bool_to_str(states)
                print(f"Установлена позиция {pos}. Состояние реле: {state_str}")

                # 2. Выполнение последовательности измерений
                try:
                    measure_position(multimeter, pos)
                finally:
                    # 3. После завершения измерения позиции выключаем все реле
                    try:
                        states = turn_off_all(relay)
                        state_str = relay.state_bool_to_str(states)
                        print(f"Все реле выключены. Состояние: {state_str}")
                    except Exception as e:
                        print(f"Ошибка выключения реле: {e}")

            except Exception as e:
                print(f"Ошибка: {e}")

    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
    finally:
        # Страховка: выключаем реле перед отключением
        try:
            turn_off_all(relay)
            print("Все реле выключены перед отключением.")
        except Exception as e:
            print(f"Ошибка выключения реле перед отключением: {e}")

        relay.disconnect()
        multimeter.close()
        print("Соединение закрыто.")

def main_1():
    # ===== Настройки =====
    RELAY_PORT = None
    SLAVE_ID = 1

    # ===== Инициализация =====
    relay = RelayController(port=RELAY_PORT, slave_id=SLAVE_ID)
    if not relay.connect():
        print(f"Не удалось открыть порт {RELAY_PORT}")
        return

    # Автоматический поиск DM858 среди VISA-ресурсов
    multimeter = DM858()
    print(f"Мультиметр: {multimeter.model}, S/N: {multimeter.serial_number}")

    print("\nДоступные команды:")
    print("  1..12  — установить позицию и выполнить измерение")
    print("  0, off — выключить все реле")
    print("  q      — выход\n")

    try:
        while True:
            user_input = input("Команда: ").strip().lower()
            if user_input == 'q':
                break

            # Режим выключения всех реле
            if user_input in ('0', 'off', 'выкл'):
                try:
                    states = turn_off_all(relay)
                    state_str = relay.state_bool_to_str(states)
                    print(f"Все реле выключены. Состояние: {state_str}")
                except Exception as e:
                    print(f"Ошибка при выключении реле: {e}")
                continue

            # Установка позиции и измерение
            try:
                pos = int(user_input)
            except ValueError:
                print("Ошибка: введите число от 1 до 12, '0'/'off' или 'q'.")
                continue

            if not (1 <= pos <= 12):
                print("Ошибка: позиция должна быть от 1 до 12.")
                continue

            try:
                # 1. Установка реле
                states = set_position(relay, pos)
                state_str = relay.state_bool_to_str(states)
                print(f"Установлена позиция {pos}. Состояние реле: {state_str}")

                # 2. Выполнение последовательности измерений
                measure_position(multimeter, pos)

            except Exception as e:
                print(f"Ошибка: {e}")

    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
    finally:
        relay.disconnect()
        multimeter.close()
        print("Соединение закрыто.")


if __name__ == "__main__":
    main()
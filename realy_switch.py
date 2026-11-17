#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from relay_controller import RelayController

# ------------------------------------------------------------------
# Карта соответствия позиции переключателя и индексов реле.
# Индексы соответствуют порядковому номеру реле в драйвере (0..15).
# Каждая позиция задаёт два реле: одно для XT9 (+), одно для XT10 (-).
# ------------------------------------------------------------------
POSITION_MAP = {
    1:  (0, 9),   # XT9 -> DB-9 pin1, XT10 -> DB-9 pin5
    2:  (0, 7),   # XT9 -> pin1,      XT10 -> pin3
    3:  (3, 6),   # XT9 -> pin6,      XT10 -> pin2
    4:  (4, 10),  # XT9 -> pin7,      XT10 -> pin8
    5:  (1, 9),   # XT9 -> pin3,      XT10 -> pin5
    6:  (0, 9),   # XT9 -> pin1,      XT10 -> pin5 (совпадает с поз.1)
    7:  (5, 11),  # XT9 -> pin8,      XT10 -> pin9 (Корпус)
    8:  (2, 6),   # XT9 -> pin5,      XT10 -> pin2
    9:  (5, 8),   # XT9 -> pin8,      XT10 -> pin4
    10: (4, 7),   # XT9 -> pin7,      XT10 -> pin3
    11: (3, 11),  # XT9 -> pin6,      XT10 -> pin9 (Корпус)
    12: (12, 13), # XT9 -> pin2,      XT10 -> pin6 (доп. реле)
    
}

N_RELAYS = 16


def set_position(controller: RelayController, pos: int) -> list:
    """
    Устанавливает реле в состояние, соответствующее позиции переключателя.
    Возвращает список состояний всех реле (bool).
    """
    if pos not in POSITION_MAP:
        raise ValueError(f"Позиция должна быть от 1 до 11, получено: {pos}")

    states = [False] * N_RELAYS
    idx_xt9, idx_xt10 = POSITION_MAP[pos]
    states[idx_xt9] = True
    states[idx_xt10] = True

    controller.set_relays(states)
    return states


def turn_off_all(controller: RelayController) -> list:
    """Выключает все реле."""
    states = [False] * N_RELAYS
    controller.set_relays(states)
    return states


def main():
    PORT = 'COM5'
    SLAVE_ID = 1

    controller = RelayController(port=PORT, slave_id=SLAVE_ID)

    if not controller.connect():
        print(f"Не удалось открыть порт {PORT}")
        return

    print("Соединение установлено.")
    print("Доступные команды:")
    print("  1..12 — установить позицию переключателя")
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
                    states = turn_off_all(controller)
                    state_str = controller.state_bool_to_str(states)
                    print(f"Все реле выключены. Состояние: {state_str}")
                except Exception as e:
                    print(f"Ошибка при выключении реле: {e}")
                continue

            # Режим установки позиции
            try:
                pos = int(user_input)
            except ValueError:
                print("Ошибка: введите число от 1 до 11, '0'/'off' или 'q'.")
                continue

            if not (1 <= pos <= 12):
                print("Ошибка: позиция должна быть от 1 до 11.")
                continue

            try:
                states = set_position(controller, pos)
                state_str = controller.state_bool_to_str(states)
                print(f"Установлена позиция {pos}. Состояние реле: {state_str}")
            except Exception as e:
                print(f"Ошибка при установке реле: {e}")

    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
    finally:
        controller.disconnect()
        print("Соединение закрыто.")


if __name__ == "__main__":
    main()
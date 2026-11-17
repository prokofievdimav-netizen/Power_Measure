#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Движок измерений для контроля печатных плат кварцевого резонатора-термостата.
"""

import logging
import time
from typing import Optional, Dict

from relay_controller import RelayController
from DM858 import DM858
import relay_switch_m as rsm

# ==================== Логгер ====================
log = logging.getLogger("app")

# ==================== Настройки ====================
RELAY_PORT = None
SLAVE_ID = 1

# Стандартные пределы измерения сопротивления DM858 (в Омах).
# Используются для «ступенчатого» автопредела при перегрузке / нуле.
RES_RANGES = (
    100,
    1_000,
    10_000,
    100_000,
    1_000_000,
    10_000_000,
    100_000_000,
    1_000_000_000,
)

# Порог «перегрузки» DM858 (прибор отдаёт ~9.9e+37).
OVERLOAD_THRESHOLD = 1e37

# Пауза после смены предела сопротивления (сек).
RES_RANGE_SETTLE = 2.0


def _next_res_range(rng: int) -> Optional[int]:
    """Следующий (больший) предел из RES_RANGES или None."""
    for r in RES_RANGES:
        if r > rng:
            return r
    return None


def _prev_res_range(rng: int) -> Optional[int]:
    """Предыдущий (меньший) предел из RES_RANGES или None."""
    for r in reversed(RES_RANGES):
        if r < rng:
            return r
    return None


class MeasurementEngine:
    def __init__(self, port: str = RELAY_PORT, slave_id: int = SLAVE_ID):
        self.port = port
        self.slave_id = slave_id
        self.relay: Optional[RelayController] = None
        self.multimeter: Optional[DM858] = None

    def connect(self):
        log.info("Подключение оборудования: порт реле=%s, slave_id=%s",
                 self.port, self.slave_id)

        t0 = time.perf_counter()
        self.relay = RelayController(port=self.port, slave_id=self.slave_id)
        if not self.relay.connect():
            log.error("Не удалось открыть порт реле %s", self.port)
            raise RuntimeError(f"Не удалось открыть порт {self.port}")
        log.info("Реле подключены (%s, %.1f ms)",
                 self.port, (time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        try:
            self.multimeter = DM858()
            log.info("Мультиметр подключён: %s, S/N %s (%.1f ms)",
                     self.multimeter.model, self.multimeter.serial_number,
                     (time.perf_counter() - t0) * 1000)
        except Exception as e:
            log.error("Ошибка подключения мультиметра: %s", e)
            raise

    def disconnect(self):
        log.info("Отключение оборудования")
        try:
            if self.relay:
                self.relay.disconnect()
                log.info("Реле отключены")
        except Exception as e:
            log.warning("Ошибка отключения реле: %s", e)
        try:
            if self.multimeter:
                self.multimeter.close()
                log.info("Мультиметр отключён")
        except Exception as e:
            log.warning("Ошибка отключения мультиметра: %s", e)
        self.relay = None
        self.multimeter = None

    @property
    def connected(self) -> bool:
        return self.multimeter is not None

    # ------------------------------------------------------------------
    # Измерение сопротивления с автоподбором предела
    # ------------------------------------------------------------------
    def _measure_resistance(self, start_range: Optional[int]) -> float:
        """Измерение RES с автоподбором предела.

        Логика:
          * стартуем с start_range (или None → авто у прибора);
          * если прибор вернул перегрузку (~1e37) — предел ↑ на ступень,
            пауза RES_RANGE_SETTLE, повтор;
          * если прибор вернул 0 — предел ↓ на ступень,
            пауза RES_RANGE_SETTLE, повтор;
          * выходим, когда получено нормальное число, либо когда
            следующей ступени нет.
        """
        rng = start_range

        # Начальная конфигурация
        self.multimeter.set_measurement_mode('RES', range_val=rng)
        settle = rsm.SETTLE_TIME.get('RES', RES_RANGE_SETTLE)
        time.sleep(settle)
        v = self.multimeter.measure()
        log.info("RES: старт rng=%s → %.6g", rng, v)

        # --- подъём при перегрузке ---
        while abs(v) >= OVERLOAD_THRESHOLD:
            nxt = _next_res_range(rng) if rng is not None else RES_RANGES[0]
            if nxt is None:
                log.warning("RES: перегрузка и выше ступени нет (rng=%s)", rng)
                break
            log.info("RES: перегрузка → предел %s → %s", rng, nxt)
            rng = nxt
            self.multimeter.set_measurement_mode('RES', range_val=rng)
            time.sleep(RES_RANGE_SETTLE)
            v = self.multimeter.measure()
            log.info("RES: rng=%s → %.6g", rng, v)

        # --- спуск при нуле ---
        while v == 0.0:
            prv = _prev_res_range(rng) if rng is not None else None
            if prv is None:
                log.info("RES: получено 0 и ниже ступени нет (rng=%s)", rng)
                break
            log.info("RES: получено 0 → предел %s → %s", rng, prv)
            rng = prv
            self.multimeter.set_measurement_mode('RES', range_val=rng)
            time.sleep(RES_RANGE_SETTLE)
            v = self.multimeter.measure()
            log.info("RES: rng=%s → %.6g", rng, v)

        return v

    # ------------------------------------------------------------------
    # Полный цикл измерения
    # ------------------------------------------------------------------
    def measure_all(self, progress_cb=None,
                    resistance_ranges: Optional[Dict[int, int]] = None) -> Dict[int, str]:
        """Полное измерение по всем 12 позициям. Возвращает {pos: 'значение'}.

        :param resistance_ranges: {позиция: стартовый предел в Омах},
            вычисляется из спецификаций (норм) в GUI. Если None —
            используется устаревший POSITION_RESISTANCE_RANGE.
        """
        if not self.connected:
            raise RuntimeError("Оборудование не подключено")

        log.info("Начало полного измерения (12 позиций)")
        t_all = time.perf_counter()
        results: Dict[int, str] = {}

        for pos in range(1, 13):
            log.info("Позиция %d: установка реле", pos)
            states = [False] * rsm.N_RELAYS
            idx_xt9, idx_xt10 = rsm.POSITION_MAP[pos]
            states[idx_xt9] = True
            states[idx_xt10] = True
            self.relay.set_relays(states)
            log.debug("Состояние реле: %s",
                      self.relay.state_bool_to_str(states))

            modes = rsm.POSITION_MEASURE_SEQUENCE[pos]
            pos_values = []
            for mode in modes:
                if mode == 'RES':
                    start_rng = None
                    if resistance_ranges is not None:
                        start_rng = resistance_ranges.get(pos)
                    else:
                        start_rng = rsm.POSITION_RESISTANCE_RANGE.get(pos)

                    log.info("Позиция %d: режим RES, старт. предел %s Ом",
                             pos, start_rng)
                    t0 = time.perf_counter()
                    v = self._measure_resistance(start_rng)
                    log.info("Позиция %d: RES = %.6g (%.1f ms)",
                             pos, v, (time.perf_counter() - t0) * 1000)
                    pos_values.append(v)
                    continue

                # --- не-RES режимы: поведение как раньше ---
                log.info("Позиция %d: режим %s", pos, mode)
                self.multimeter.set_measurement_mode(mode, range_val=None)
                settle = rsm.SETTLE_TIME.get(mode, 2.0)
                log.debug("Пауза %.1f с", settle)
                time.sleep(settle)
                t0 = time.perf_counter()
                v = self.multimeter.measure()
                log.info("Позиция %d: измерено %.6g за %.1f ms",
                         pos, v, (time.perf_counter() - t0) * 1000)
                pos_values.append(v)

            if len(pos_values) == 1:
                results[pos] = f"{pos_values[0]:.6g}"
            else:
                results[pos] = "/".join(f"{v:.6g}" for v in pos_values)

            log.info("Позиция %d завершена: %s", pos, results[pos])
            if progress_cb:
                progress_cb(pos, results[pos])

        try:
            rsm.turn_off_all(self.relay)
            log.info("Все реле выключены")
        except Exception as e:
            log.warning("Ошибка выключения реле: %s", e)

        log.info("Полное измерение завершено за %.2f с",
                 time.perf_counter() - t_all)
        return results
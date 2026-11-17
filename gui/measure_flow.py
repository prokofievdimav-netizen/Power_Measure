#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Поток измерения и обработка очереди сообщений."""

import logging
import queue
import threading
from typing import Optional

import dearpygui.dearpygui as dpg

log = logging.getLogger("app")


class MeasureMixin:
    def on_measure(self, sender, app_data, user_data):
        idx = user_data
        if self.measuring:
            self.set_status("Измерение уже выполняется", (255, 150, 100))
            return
        if not self.engine.connected:
            log.warning("Попытка измерения без подключения")
            self.set_status("Оборудование не подключено. Нажмите «Подключить»",
                            (255, 100, 100))
            return

        if idx in self.measured_indices:
            self.measured_indices.discard(idx)
        self.rows[idx]['values'] = {}
        self.rows[idx]['status'] = ''
        self._reset_row_display(idx)
        self._reset_row_color(idx)

        total = len(self.rows)
        measured = len(self.measured_indices)
        n_good = sum(1 for i in self.measured_indices
                     if self.rows[i]['status'] == "Годен")
        n_bad = sum(1 for i in self.measured_indices
                     if self.rows[i]['status'] == "Брак")
        self.set_status(
            f"Измерено: {measured}/{total}   |   "
            f"Годен: {n_good}   |   Брак: {n_bad}",
            (200, 200, 100)
        )

        n = self.rows[idx]['N']
        log.info("Запуск измерения для %s (индекс %d)", n, idx)
        self.measuring = True
        self._color_row_green(idx)

        self.set_status(f"Измерение {n} ...", (200, 200, 100))
        threading.Thread(target=self._measure_thread, args=(idx,),
                         daemon=True).start()

    def _measure_thread(self, idx: int):
        try:
            ranges = self._compute_resistance_ranges()
            results = self.engine.measure_all(
                progress_cb=lambda pos, val:
                    self.msg_queue.put(('progress', idx, pos, val)),
                resistance_ranges=ranges,
            )
            self.msg_queue.put(('done', idx, results))
        except Exception as e:
            log.exception("Исключение в потоке измерения")
            self.msg_queue.put(('error', idx, str(e)))

    def process_messages(self):
        """Обрабатывает очередь сообщений от потока измерений."""
        while True:
            try:
                msg = self.msg_queue.get_nowait()
            except queue.Empty:
                break

            if msg[0] == 'progress':
                _, idx, pos, val = msg
                self.rows[idx]['values'][pos] = val
                tag = f"cell_{idx}_{pos}"
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, self._format_value_for_pos(pos, val))

            elif msg[0] == 'done':
                _, idx, results = msg
                log.info("Измерение для %s завершено: %s",
                         self.rows[idx]['N'], results)
                self.rows[idx]['values'] = results
                self._render_row_values(idx)
                status = self._evaluate_status(results)
                self.rows[idx]['status'] = status
                log.info("Статус для %s: %s", self.rows[idx]['N'], status)
                tag = f"status_{idx}"
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, status)
                self._reset_row_color(idx)
                if status == "Брак":
                    self._color_row_red(idx)
                    self._color_failed_cells_yellow(idx)
                self.measured_indices.add(idx)
                self._finish_measure()

            elif msg[0] == 'error':
                _, idx, err = msg
                log.error("Ошибка измерения для %s: %s",
                          self.rows[idx]['N'], err)
                self._reset_row_color(idx)
                self.set_status(f"Ошибка измерения: {err}", (255, 100, 100))
                self._finish_measure()

    def _finish_measure(self):
        self.measuring = False
        total = len(self.rows)
        measured = len(self.measured_indices)
        n_good = sum(1 for i in self.measured_indices
                     if self.rows[i]['status'] == "Годен")
        n_bad = sum(1 for i in self.measured_indices
                    if self.rows[i]['status'] == "Брак")
        log.info("Итог: измерено %d/%d, Годен=%d, Брак=%d",
                 measured, total, n_good, n_bad)
        self.set_status(
            f"Измерено: {measured}/{total}   |   Годен: {n_good}   |   Брак: {n_bad}",
            (200, 200, 100)
        )

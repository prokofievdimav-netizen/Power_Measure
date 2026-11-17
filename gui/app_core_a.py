# -*- coding: utf-8 -*-
"""Часть AppCore: AppCoreAMixin."""
from typing import Optional, List, Dict, Any
import logging
import queue

import dearpygui.dearpygui as dpg

import db_helper as db
import run_picker
from gui.constants import (
    FONT_NAME, NUM_RE, BARCODE_RE, MSK_RE,
    generate_range, OPEN_CIRCUIT_THRESHOLD, NORM_ABSENT, OVERLOAD_THRESHOLD,
)
from measurement_engine import MeasurementEngine

log = logging.getLogger("app")


class AppCoreAMixin:
    def __init__(self):
        self.engine = MeasurementEngine()
        self.rows: List[Dict[str, Any]] = []
        self.specs: List[Dict] = []
        self.nom_id: Optional[int] = None
        self.msk_real: Optional[str] = None
        self.msg_queue: queue.Queue = queue.Queue()
        self.measuring = False
        self.measured_indices: set = set()

        self.win_tag = "main_window"
        self.table_tag = "results_table"
        self.table_container = "table_container"
        self.status_tag = "status_text"
        self.input_tag = "input_id"
        self.info_tag = "info_text"
        self._pdf_font_name: Optional[str] = None
        self.column_names: Dict[int, str] = {}

        # Сопротивление выше этого значения считаем «обрывом» и в таблице
        # показываем как «Обрыв» вместо сырого числа.
        self.open_circuit_threshold = OPEN_CIRCUIT_THRESHOLD

        # Текущий выбранный замер (run_id) и флаг legacy-режима
        self.current_run_id: Optional[int] = None
        self.current_run_legacy: bool = False

        self._nk_list: List[Dict[str, Any]] = []

    def build(self):
        with dpg.window(tag=self.win_tag, label="RT - Montage Control",
                        width=-1, height=-1, no_title_bar=False,
                        no_move=False, no_resize=False):
            with dpg.group(horizontal=True):
                dpg.add_text("Штрих-код / МСК:")
                dpg.add_input_text(tag=self.input_tag, width=280,
                                   on_enter=True, callback=self.on_find)
                dpg.add_button(label="  Найти  ", callback=self.on_find,
                               width=100)
                dpg.add_button(label="  Подключить  ",
                               callback=self.on_connect, width=120)
                dpg.add_button(label="  Сохранить  ",
                               callback=self.on_save, width=110)
                dpg.add_button(label="  PDF  ",
                               callback=self.on_export_pdf, width=80)
                dpg.add_button(label="  Спецификации  ",
                               callback=self.on_open_spec_editor, width=140)

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("", tag=self.info_tag)
                dpg.add_spacer(width=20)
                dpg.add_text("НК:")
                dpg.add_combo(tag="spec_selector", items=[], width=220,
                              callback=self._on_spec_selector_changed)

            dpg.add_separator()
            dpg.add_child_window(tag=self.table_container, height=-40)
            dpg.add_text("Готово", tag=self.status_tag)

        self._load_nk_list()

    def set_status(self, text: str, color=(200, 200, 200)):
        if dpg.does_item_exist(self.status_tag):
            dpg.set_value(self.status_tag, text)
            dpg.configure_item(self.status_tag, color=color)

    def _nk_full_label(self, item: Dict[str, Any]) -> str:
        name = (item.get("name") or "").strip()
        msk = (item.get("msk") or "").strip()
        nom = item.get("nom_id")
        parts = []
        if name:
            parts.append(name)
        if msk:
            parts.append(f"МСК {msk}")
        if nom is not None:
            parts.append(f"#{nom}")
        return " | ".join(parts) if parts else str(nom or "?")

    def _load_nk_list(self):
        try:
            self._nk_list = db.get_nk_list() or []
        except Exception:
            log.exception("load nk list")
            self._nk_list = []
        labels = [self._nk_full_label(it) for it in self._nk_list]
        if dpg.does_item_exist("spec_selector"):
            dpg.configure_item("spec_selector", items=labels)
            if labels:
                dpg.set_value("spec_selector", labels[0])

    def _select_nk_by_nom_id(self, nom_id: Optional[int]):
        if nom_id is None or not self._nk_list:
            return
        for it in self._nk_list:
            if it.get("nom_id") == nom_id:
                label = self._nk_full_label(it)
                if dpg.does_item_exist("spec_selector"):
                    dpg.set_value("spec_selector", label)
                return

    def _on_spec_selector_changed(self, sender, app_data):
        label = app_data
        for it in self._nk_list:
            if self._nk_full_label(it) == label:
                self._apply_spec_choice(it)
                return

    def _apply_spec_choice(self, item: Dict[str, Any]):
        nom = item.get("nom_id")
        if nom is None:
            return
        self.nom_id = nom
        self.msk_real = item.get("msk") or self.msk_real
        self._update_info_text()
        try:
            self.specs = db.get_specs_by_nom_id(nom) or []
            self.column_names = db.get_column_names(nom) or {}
        except Exception:
            log.exception("apply spec")
            self.specs = []
            self.column_names = {}
        self._rebuild_table()

    def _current_spec_name(self) -> str:
        if dpg.does_item_exist("spec_selector"):
            return dpg.get_value("spec_selector") or ""
        return ""

    def _update_info_text(self):
        parts = []
        if self.msk_real:
            parts.append(f"МСК: {self.msk_real}")
        if self.nom_id is not None:
            parts.append(f"NOM_ID: {self.nom_id}")
        if self.current_run_id is not None:
            parts.append(f"run_id: {self.current_run_id}")
        elif self.current_run_legacy:
            parts.append("run: legacy")
        text = "  |  ".join(parts) if parts else ""
        if dpg.does_item_exist(self.info_tag):
            dpg.set_value(self.info_tag, text)

    def on_connect(self):
        if self.engine.connected:
            try:
                self.engine.disconnect()
            except Exception:
                log.exception("disconnect")
            self.set_status("Отключено", (200, 200, 100))
            return
        try:
            ok = self.engine.connect()
            if ok:
                self.set_status("Оборудование подключено", (100, 220, 120))
            else:
                self.set_status("Не удалось подключить оборудование",
                                (255, 100, 100))
        except Exception as e:
            log.exception("connect")
            self.set_status(f"Ошибка подключения: {e}", (255, 100, 100))

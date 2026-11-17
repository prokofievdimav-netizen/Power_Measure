# -*- coding: utf-8 -*-
"""Редактор спецификаций монтажа.

Полный UI-редактор вынесен сюда. Минимальная рабочая версия:
кнопка «Спецификации» открывает модальное окно со списком параметров
для текущего NOM_ID (чтение из БД). CRUD-форма может быть расширена
по образцу исходного main_gui.
"""

import logging
from typing import Optional, List, Dict, Any

import dearpygui.dearpygui as dpg

import db_helper as db
from gui.constants import UNITS_CHOICES

log = logging.getLogger("app")


class SpecEditorMixin:
    def _build_spec_editor(self):
        with dpg.window(
                tag="spec_editor_window",
                label="Редактор спецификаций",
                modal=True,
                show=False,
                width=900, height=500,
                pos=(120, 80),
                no_collapse=True,
        ):
            dpg.add_text("NOM_ID: -", tag="se_nom_info", color=(180, 200, 255))
            dpg.add_separator()
            dpg.add_child_window(tag="se_table_container", height=-40)
            with dpg.group(horizontal=True):
                dpg.add_button(label="  Обновить  ", callback=self._on_se_refresh)
                dpg.add_button(label="  Закрыть  ", callback=self._on_se_close)
            dpg.add_text("", tag="se_status")

    def on_open_spec_editor(self):
        if not dpg.does_item_exist("spec_editor_window"):
            self._build_spec_editor()
        nom = self.nom_id
        if dpg.does_item_exist("se_nom_info"):
            dpg.set_value("se_nom_info", f"NOM_ID: {nom if nom is not None else '-'}")
        self._se_reload_specs()
        dpg.configure_item("spec_editor_window", show=True)

    def _on_se_close(self):
        if dpg.does_item_exist("spec_editor_window"):
            dpg.configure_item("spec_editor_window", show=False)

    def _on_se_refresh(self):
        self._se_reload_specs()

    def _se_reload_specs(self):
        if dpg.does_item_exist("se_specs_table"):
            dpg.delete_item("se_specs_table")
        if not dpg.does_item_exist("se_table_container"):
            return
        if self.nom_id is None:
            if dpg.does_item_exist("se_status"):
                dpg.set_value("se_status", "Сначала выберите МСК / спецификацию")
            return
        try:
            rows = db.get_specs_by_nom_id(self.nom_id)
        except Exception as e:
            log.exception("se reload")
            if dpg.does_item_exist("se_status"):
                dpg.set_value("se_status", f"Ошибка: {e}")
            return

        with dpg.table(parent="se_table_container", tag="se_specs_table",
                       header_row=True, borders_innerH=True, borders_outerH=True,
                       borders_innerV=True, borders_outerV=True, scrollY=True):
            for h in ("ID", "switch_id", "Par_Name", "min", "max", "value", "Bool", "units"):
                dpg.add_table_column(label=h)
            for r in rows:
                with dpg.table_row():
                    dpg.add_text(str(r.get('ID') or ''))
                    dpg.add_text(str(r.get('switch_id') or ''))
                    dpg.add_text(str(r.get('Par_Name') or ''))
                    dpg.add_text(str(r.get('Par_min') if r.get('Par_min') is not None else ''))
                    dpg.add_text(str(r.get('Par_max') if r.get('Par_max') is not None else ''))
                    dpg.add_text(str(r.get('Par_value') if r.get('Par_value') is not None else ''))
                    dpg.add_text(str(r.get('Par_Bool') if r.get('Par_Bool') is not None else ''))
                    dpg.add_text(str(r.get('units') or ''))

        if dpg.does_item_exist("se_status"):
            dpg.set_value("se_status", f"Загружено спецификаций: {len(rows)}")

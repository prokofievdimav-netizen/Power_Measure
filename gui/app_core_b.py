# -*- coding: utf-8 -*-
"""Часть AppCore: AppCoreBMixin — on_find, on_save, resolve numbers."""
from typing import Optional, List, Dict, Any
import logging

import dearpygui.dearpygui as dpg

import db_helper as db
import run_picker
from gui.constants import NUM_RE, BARCODE_RE, MSK_RE, generate_range

log = logging.getLogger("app")


class AppCoreBMixin:
    def on_find(self):
        if self.measuring:
            self.set_status("Идёт измерение. Дождитесь окончания.",
                            (255, 150, 100))
            return

        s = dpg.get_value(self.input_tag).strip()
        log.info("Запрос: %r", s)
        if not s:
            self.set_status("Введите штрих-код или МСК", (255, 150, 100))
            return

        try:
            numbers = self._resolve_numbers(s)
        except Exception as e:
            log.exception("Ошибка разбора запроса")
            self.set_status(f"Ошибка: {e}", (255, 100, 100))
            return

        if not numbers:
            log.warning("Номера не найдены для %r", s)
            self.set_status("Номера не найдены", (255, 150, 100))
            return

        self._load_nk_list()

        if self.nom_id is not None:
            if not self._select_nk_by_nom_id(self.nom_id):
                if dpg.does_item_exist("spec_selector"):
                    dpg.set_value("spec_selector", "")
        else:
            if self._nk_list:
                first = self._nk_list[0]
                if dpg.does_item_exist("spec_selector"):
                    dpg.set_value("spec_selector",
                                  self._nk_full_label(first))
                nid = first.get("номенклатура")
                if nid is None:
                    nid = first.get("nom_id")
                self.nom_id = nid

        try:
            self.specs = (db.get_specs(self.nom_id)
                          if self.nom_id is not None else [])
        except Exception as e:
            self.specs = []
            log.exception("Ошибка загрузки спецификаций")
            self.set_status(f"Ошибка загрузки спецификаций: {e}",
                            (255, 100, 100))

        try:
            self.column_names = (db.get_column_names(self.nom_id)
                                 if self.nom_id is not None else {})
        except Exception:
            self.column_names = {}
            log.exception("Ошибка загрузки названий колонок")

        self.rows = [{'N': n, 'values': {}, 'status': ''} for n in numbers]
        self.measured_indices = set()
        self.current_run_id = None
        self.current_run_legacy = False
        self._rebuild_table()

        loaded = run_picker.offer_and_load(self)

        log.info("Сформирован список: %d номеров, NOM_ID=%s, specs=%d, "
                 "loaded=%d",
                 len(numbers), self.nom_id, len(self.specs), loaded)

        self._update_info_text()

        if loaded:
            self.set_status(
                f"Загружено {loaded} сохранённых записей из БД",
                (100, 200, 255)
            )
        else:
            self.set_status(f"Загружено {len(numbers)} номеров",
                            (100, 200, 255))

    def on_save(self):
        log.info("Сохранение: измерено %d строк", len(self.measured_indices))
        if not self.measured_indices:
            self.set_status("Нет измеренных номеров для сохранения",
                            (255, 150, 100))
            return
        rows_to_save = [self.rows[i] for i in sorted(self.measured_indices)]
        try:
            result = db.save_measurements(
                self.msk_real or '', self.nom_id, rows_to_save, note=''
            )
            run_picker.handle_save_result(self, result)
        except Exception as e:
            log.exception("Ошибка сохранения")
            self.set_status(f"Ошибка сохранения: {e}", (255, 100, 100))

    def _resolve_numbers(self, s: str) -> List[str]:
        if BARCODE_RE.match(s):
            msk_real = db.find_msk_real(s)
            if not msk_real:
                raise ValueError(f"Штрих-код {s} не найден в msk_rk")
            self.msk_real = msk_real
            rng = db.find_marker(msk_real)
            if not rng:
                if NUM_RE.match(msk_real.upper()):
                    self._load_nom_id()
                    return [msk_real.upper()]
                raise ValueError(f"Не найден маркер для МСК_Реал={msk_real}")
            self._load_nom_id()
            return generate_range(*rng)

        if MSK_RE.match(s):
            self.msk_real = s
            rng = db.find_marker(s)
            if not rng:
                raise ValueError(f"МСК {s} не найден в marker")
            self._load_nom_id()
            return generate_range(*rng)

        raise ValueError(
            "Неверный формат. Штрих-код — 5+ цифр; МСК — xx-xxxx."
        )

    def _load_nom_id(self):
        self.nom_id = None
        if not self.msk_real:
            return
        kod = db.get_kod_nom(self.msk_real)
        if kod:
            self.nom_id = db.get_nom_id(kod)

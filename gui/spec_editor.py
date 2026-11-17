# -*- coding: utf-8 -*-
"""Редактор спецификаций монтажа (просмотр + CRUD)."""

import logging
from typing import Optional, List, Dict, Any

import dearpygui.dearpygui as dpg

import db_helper as db
from gui.constants import UNITS_CHOICES

log = logging.getLogger("app")


class SpecEditorMixin:
    def _build_spec_editor(self):
        """Создание модального окна редактора спецификаций."""
        with dpg.window(
                tag="spec_editor_window",
                label="Редактор спецификаций",
                modal=True,
                show=False,
                width=1340, height=820,
                pos=(80, 40),
                no_collapse=True,
        ):
            with dpg.group(horizontal=True):
                dpg.add_text("Тип РК:")
                dpg.add_combo([], tag="se_rk_combo", width=340,
                              callback=self._on_se_rk_changed)
                dpg.add_spacer(width=15)
                dpg.add_text("Номинальная частота:")
                dpg.add_combo([], tag="se_freq_combo", width=420,
                              callback=self._on_se_freq_changed)
                dpg.add_spacer(width=15)
                dpg.add_text("NOM_ID: -", tag="se_nom_info",
                             color=(180, 200, 255))

            dpg.add_separator()
            dpg.add_child_window(tag="se_table_container", height=440)
            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_text("switch_id:")
                dpg.add_input_text(tag="se_sw", width=70)
                dpg.add_spacer(width=10)
                dpg.add_text("Параметр:")
                dpg.add_combo([" "], tag="se_par_name", width=320,
                              callback=self._on_se_param_changed)
                dpg.add_button(label="  ⟳  ",
                               callback=self._on_se_reload_params)
                dpg.add_spacer(width=10)
                dpg.add_text("Par_ID:")
                dpg.add_input_text(tag="se_par_id", width=90,
                                   readonly=True)
                dpg.add_spacer(width=10)
                dpg.add_text("Округление:")
                dpg.add_input_text(tag="se_round", width=70)

            with dpg.group(horizontal=True):
                dpg.add_text("units:")
                dpg.add_combo(UNITS_CHOICES, tag="se_units", width=110,
                              default_value="")
                dpg.add_spacer(width=20)
                dpg.add_text("MIN:")
                dpg.add_input_text(tag="se_min", width=130)
                dpg.add_spacer(width=10)
                dpg.add_text("MAX:")
                dpg.add_input_text(tag="se_max", width=130)

            with dpg.group(horizontal=True):
                dpg.add_text("Spc_Name:")
                dpg.add_input_text(tag="se_spc_name", width=320,
                                   readonly=True)
                dpg.add_spacer(width=20)
                dpg.add_checkbox(label="Цифровое значение (Par_value=1)",
                                 tag="se_pvalue")
                dpg.add_spacer(width=20)
                dpg.add_checkbox(label="Bool (замкнуто)",
                                 tag="se_pbool")

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="  Новая  ",
                               callback=self._on_se_new)
                dpg.add_button(label="  Сохранить  ",
                               callback=self._on_se_save)
                dpg.add_button(label="  Удалить  ",
                               callback=self._on_se_delete)
                dpg.add_spacer(width=20)
                dpg.add_button(label="  Обновить  ",
                               callback=self._on_se_refresh)
                dpg.add_spacer(width=20)
                dpg.add_button(label="  Закрыть  ",
                               callback=self._on_se_close)
                dpg.add_spacer(width=20)
                dpg.add_text("", tag="se_status",
                             color=(255, 220, 100))

    def _on_se_reload_params(self):
        try:
            self._se_params_list = db.get_parameters()
        except Exception as e:
            log.exception("Ошибка перезагрузки параметров")
            self._se_set_status(f"Ошибка параметров: {e}", (255, 100, 100))
            return
        self._se_apply_params_to_combo()
        self._se_set_status(f"Параметров: {len(self._se_params_list)}",
                            (100, 200, 255))

    def on_open_spec_editor(self):
        if not dpg.does_item_exist("spec_editor_window"):
            self._build_spec_editor()
        if not hasattr(self, "_se_selected_spec"):
            self._se_selected_spec = None
        if not hasattr(self, "_se_params_list"):
            self._se_params_list = []
        if not hasattr(self, "_se_rk_list"):
            self._se_rk_list = []
        if not hasattr(self, "_se_nk_list"):
            self._se_nk_list = []

        try:
            self._se_rk_list = db.get_resonator_types()
        except Exception as e:
            log.exception("Ошибка загрузки типов РК")
            self.set_status(f"Ошибка загрузки типов РК: {e}",
                            (255, 100, 100))
            return

        try:
            self._se_params_list = db.get_parameters()
        except Exception:
            log.exception("Ошибка загрузки параметров")
            self._se_params_list = []

        self._se_apply_params_to_combo()

        rk_labels = [self._se_rk_label(r) for r in self._se_rk_list]
        dpg.configure_item("se_rk_combo",
                           items=rk_labels if rk_labels else [""])

        if rk_labels:
            dpg.set_value("se_rk_combo", rk_labels[0])
            self._se_load_nomeklatura(0)
        else:
            dpg.set_value("se_rk_combo", "")
            self._se_nk_list = []
            dpg.configure_item("se_freq_combo", items=[""])
            dpg.set_value("se_freq_combo", "")
            self._se_set_nom_id(None)

        self._se_selected_spec = None
        self._se_clear_form()
        self._se_set_status("", (200, 200, 200))
        dpg.configure_item("spec_editor_window", show=True)

    def _se_apply_params_to_combo(self):
        names = [(p.get('Par_Name') or '').strip()
                 for p in self._se_params_list]
        names = [n for n in names if n]
        if not names:
            names = [' ']
        if dpg.does_item_exist("se_par_name"):
            dpg.configure_item("se_par_name", items=names)

    def _on_se_close(self):
        if dpg.does_item_exist("spec_editor_window"):
            dpg.configure_item("spec_editor_window", show=False)

    def _se_set_status(self, text: str, color=(255, 220, 100)):
        if dpg.does_item_exist("se_status"):
            dpg.set_value("se_status", text)
            dpg.configure_item("se_status", color=color)

    @staticmethod
    def _se_rk_label(r: Dict) -> str:
        name = (r.get('name') or r.get('наименование') or '').strip()
        rid = r.get('id') or r.get('ID') or r.get('РКНомер') or ''
        return f"{name} ({rid})" if name else str(rid)

    @staticmethod
    def _se_nk_label(n: Dict) -> str:
        freq = n.get('частота') or n.get('freq') or ''
        name = (n.get('наименование') or n.get('name') or '').strip()
        nom = n.get('номенклатура') or n.get('nom_id') or ''
        parts = [str(x) for x in (freq, name, nom) if x not in (None, '')]
        return ' | '.join(parts) if parts else str(nom)

    def _se_clear_form(self):
        for tag, val in (
            ("se_sw", ""), ("se_par_name", " "), ("se_par_id", ""),
            ("se_round", ""), ("se_units", ""), ("se_min", ""),
            ("se_max", ""), ("se_spc_name", ""),
        ):
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, val)
        if dpg.does_item_exist("se_pvalue"):
            dpg.set_value("se_pvalue", False)
        if dpg.does_item_exist("se_pbool"):
            dpg.set_value("se_pbool", False)

    @staticmethod
    def _fmt_num_edit(v) -> str:
        if v is None:
            return ""
        try:
            f = float(v)
            return str(int(f)) if f == int(f) else str(f)
        except (TypeError, ValueError):
            return str(v)

    @staticmethod
    def _fmt_tiny_edit(v) -> str:
        if v is None:
            return ""
        return str(int(v))

    def _se_get_int(self, tag: str) -> Optional[int]:
        if not dpg.does_item_exist(tag):
            return None
        s = str(dpg.get_value(tag) or '').strip()
        if not s:
            return None
        try:
            return int(float(s))
        except ValueError:
            raise ValueError(f"Поле {tag}: ожидается целое число")

    def _se_get_float(self, tag: str) -> Optional[float]:
        if not dpg.does_item_exist(tag):
            return None
        s = str(dpg.get_value(tag) or '').strip().replace(',', '.')
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"Поле {tag}: ожидается число")

    def _se_get_str(self, tag: str) -> Optional[str]:
        if not dpg.does_item_exist(tag):
            return None
        s = str(dpg.get_value(tag) or '').strip()
        return s if s else None

    @staticmethod
    def _se_bool_to_tiny(v) -> int:
        return 1 if v else 0

    def _on_se_rk_changed(self, sender, app_data):
        labels = [self._se_rk_label(r) for r in self._se_rk_list]
        try:
            idx = labels.index(app_data)
        except ValueError:
            idx = 0
        self._se_load_nomeklatura(idx)

    def _se_load_nomeklatura(self, rk_index: int):
        self._se_nk_list = []
        if not self._se_rk_list or rk_index < 0 or rk_index >= len(self._se_rk_list):
            dpg.configure_item("se_freq_combo", items=[""])
            dpg.set_value("se_freq_combo", "")
            self._se_set_nom_id(None)
            return
        rk = self._se_rk_list[rk_index]
        rk_id = rk.get('id') or rk.get('ID') or rk.get('РКНомер')
        try:
            self._se_nk_list = db.get_nomeklatura_by_rk(int(rk_id)) if rk_id is not None else []
        except Exception:
            log.exception("load nomeklatura")
            self._se_nk_list = []
        labels = [self._se_nk_label(n) for n in self._se_nk_list]
        dpg.configure_item("se_freq_combo",
                           items=labels if labels else [""])
        if labels:
            dpg.set_value("se_freq_combo", labels[0])
            self._on_se_freq_changed(None, labels[0])
        else:
            dpg.set_value("se_freq_combo", "")
            self._se_set_nom_id(None)

    def _on_se_freq_changed(self, sender, app_data):
        labels = [self._se_nk_label(n) for n in self._se_nk_list]
        try:
            idx = labels.index(app_data)
        except ValueError:
            self._se_set_nom_id(None)
            return
        n = self._se_nk_list[idx]
        nom = n.get('номенклатура') if n.get('номенклатура') is not None else n.get('nom_id')
        self._se_set_nom_id(nom)

    def _on_se_param_changed(self, sender, app_data):
        name = (app_data or '').strip()
        for p in self._se_params_list:
            if (p.get('Par_Name') or '').strip() == name:
                pid = p.get('Par_ID') or p.get('ID') or p.get('id')
                if dpg.does_item_exist("se_par_id"):
                    dpg.set_value("se_par_id", str(pid if pid is not None else ''))
                return

    def _se_set_nom_id(self, nom_id: Optional[int]):
        self._se_editor_nom_id = nom_id
        if dpg.does_item_exist("se_nom_info"):
            dpg.set_value("se_nom_info",
                          f"NOM_ID: {nom_id if nom_id is not None else '-'}")
        if dpg.does_item_exist("se_spc_name") and nom_id is not None:
            # подпись из выбранной номенклатуры
            label = dpg.get_value("se_freq_combo") if dpg.does_item_exist("se_freq_combo") else ''
            dpg.set_value("se_spc_name", label or '')
        self._se_reload_specs()

    def _se_reload_specs(self):
        nom = getattr(self, '_se_editor_nom_id', None)
        rows = []
        if nom is not None:
            try:
                rows = db.get_specs_by_nom_id(nom) or []
            except Exception as e:
                log.exception("se reload")
                self._se_set_status(f"Ошибка: {e}", (255, 100, 100))
                rows = []
        self._se_specs_rows = rows
        self._se_rebuild_table()
        self._se_set_status(f"Загружено: {len(rows)}", (180, 200, 255))

    def _se_rebuild_table(self):
        if dpg.does_item_exist("se_table"):
            dpg.delete_item("se_table")
        if not dpg.does_item_exist("se_table_container"):
            return
        rows = getattr(self, '_se_specs_rows', []) or []
        with dpg.table(
                parent="se_table_container", tag="se_table",
                header_row=True, row_background=True,
                borders_innerH=True, borders_outerH=True,
                borders_innerV=True, borders_outerV=True,
                scrollY=True, height=-1,
        ):
            for h in ("ID", "sw", "Par_Name", "min", "max",
                      "value", "Bool", "units", "round"):
                dpg.add_table_column(label=h)
            for r in rows:
                with dpg.table_row():
                    rid = r.get('ID')
                    # клик по строке — загрузка в форму
                    btn = dpg.add_button(
                        label=str(rid or ''),
                        callback=self._on_se_row_select,
                        user_data=r,
                        width=60,
                    )
                    dpg.add_text(str(r.get('switch_id') if r.get('switch_id') is not None else ''))
                    dpg.add_text(str(r.get('Par_Name') or ''))
                    dpg.add_text(self._fmt_num_edit(r.get('Par_min')))
                    dpg.add_text(self._fmt_num_edit(r.get('Par_max')))
                    dpg.add_text(self._fmt_tiny_edit(r.get('Par_value')))
                    dpg.add_text(self._fmt_tiny_edit(r.get('Par_Bool')))
                    dpg.add_text(str(r.get('units') or ''))
                    dpg.add_text(self._fmt_num_edit(
                        r.get('round_Value', r.get('round_value'))))

    def _on_se_row_select(self, sender, app_data, user_data):
        r = user_data or {}
        self._se_selected_spec = r
        if dpg.does_item_exist("se_sw"):
            dpg.set_value("se_sw", str(r.get('switch_id') if r.get('switch_id') is not None else ''))
        pname = (r.get('Par_Name') or '').strip() or ' '
        if dpg.does_item_exist("se_par_name"):
            dpg.set_value("se_par_name", pname)
        if dpg.does_item_exist("se_par_id"):
            dpg.set_value("se_par_id", str(r.get('Par_ID') if r.get('Par_ID') is not None else ''))
        if dpg.does_item_exist("se_round"):
            dpg.set_value("se_round", self._fmt_num_edit(
                r.get('round_Value', r.get('round_value'))))
        if dpg.does_item_exist("se_units"):
            dpg.set_value("se_units", r.get('units') or '')
        if dpg.does_item_exist("se_min"):
            dpg.set_value("se_min", self._fmt_num_edit(r.get('Par_min')))
        if dpg.does_item_exist("se_max"):
            dpg.set_value("se_max", self._fmt_num_edit(r.get('Par_max')))
        if dpg.does_item_exist("se_pvalue"):
            dpg.set_value("se_pvalue", bool(r.get('Par_value')))
        if dpg.does_item_exist("se_pbool"):
            dpg.set_value("se_pbool", bool(r.get('Par_Bool')))
        if dpg.does_item_exist("se_spc_name"):
            dpg.set_value("se_spc_name", r.get('Spc_Name') or '')
        self._se_set_status(f"Выбрана запись ID={r.get('ID')}", (180, 220, 255))

    def _on_se_new(self):
        try:
            self._se_params_list = db.get_parameters()
        except Exception:
            pass
        self._se_apply_params_to_combo()
        self._se_selected_spec = None
        self._se_clear_form()
        self._se_set_status("Новая запись — заполните поля и нажмите Сохранить",
                            (100, 220, 255))

    def _on_se_refresh(self):
        self._se_reload_specs()

    def _collect_spec_form(self) -> Dict[str, Any]:
        nom = getattr(self, '_se_editor_nom_id', None)
        if nom is None:
            raise ValueError("Не выбран NOM_ID (тип РК / частота)")
        sw = self._se_get_int("se_sw")
        if sw is None:
            raise ValueError("Укажите switch_id")
        pname = self._se_get_str("se_par_name")
        if not pname or pname == ' ':
            raise ValueError("Укажите имя параметра")
        par_id = self._se_get_int("se_par_id")
        units = self._se_get_str("se_units") or ''
        pmin = self._se_get_float("se_min")
        pmax = self._se_get_float("se_max")
        rnd = self._se_get_int("se_round")
        pvalue = self._se_bool_to_tiny(
            dpg.get_value("se_pvalue") if dpg.does_item_exist("se_pvalue") else False)
        pbool = self._se_bool_to_tiny(
            dpg.get_value("se_pbool") if dpg.does_item_exist("se_pbool") else False)
        spc = self._se_get_str("se_spc_name") or ''
        return {
            'NOM_ID': nom,
            'Spc_Name': spc,
            'Par_ID': par_id,
            'Par_Name': pname,
            'Par_min': pmin,
            'Par_max': pmax,
            'Par_value': pvalue,
            'Par_Bool': pbool,
            'units': units,
            'switch_id': sw,
            'round_Value': rnd,
        }

    def _on_se_save(self):
        try:
            spec = self._collect_spec_form()
        except ValueError as e:
            self._se_set_status(f"Ошибка ввода: {e}", (255, 100, 100))
            return
        try:
            sel = self._se_selected_spec
            if sel and sel.get('ID') is not None:
                db.update_spec(sel['ID'], spec)
                self._se_set_status(f"Запись ID={sel['ID']} обновлена",
                                    (100, 255, 100))
            else:
                new_id = db.insert_spec(spec)
                self._se_set_status(f"Добавлена запись ID={new_id}",
                                    (100, 255, 100))
            self._se_reload_specs()
            # обновить specs в основном окне, если NOM_ID совпадает
            if getattr(self, 'nom_id', None) == getattr(self, '_se_editor_nom_id', None):
                try:
                    self.specs = db.get_specs(self.nom_id) or []
                    self.column_names = db.get_column_names(self.nom_id) or {}
                except Exception:
                    pass
        except Exception as e:
            log.exception("se save")
            self._se_set_status(f"Ошибка сохранения: {e}", (255, 100, 100))

    def _on_se_delete(self):
        sel = getattr(self, '_se_selected_spec', None)
        if not sel or sel.get('ID') is None:
            self._se_set_status("Сначала выберите запись в таблице (кнопка ID)",
                                (255, 180, 100))
            return
        try:
            db.delete_spec(sel['ID'])
            self._se_set_status(f"Удалена запись ID={sel['ID']}", (255, 180, 100))
            self._se_selected_spec = None
            self._se_clear_form()
            self._se_reload_specs()
        except Exception as e:
            log.exception("se delete")
            self._se_set_status(f"Ошибка удаления: {e}", (255, 100, 100))

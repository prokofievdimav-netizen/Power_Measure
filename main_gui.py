#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI-приложение контроля печатных плат кварцевого резонатора-термостата.
Стиль — строгий классический, тёмная тема.
"""

import logging
import re
import queue
import threading
from typing import Optional, List, Dict, Any

import dearpygui.dearpygui as dpg
from screeninfo import get_monitors

from fonts.Font import setup_fonts

from measurement_engine import MeasurementEngine
import db_helper as db
import relay_switch_m as rsm
import os


# ==================== Логгер приложения ====================
log = logging.getLogger("app")


def _setup_console_logging():
    if log.handlers:
        return
    log.setLevel(logging.DEBUG)
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter(
        "[%(asctime)s] [APP] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    ))
    log.addHandler(h)
    log.propagate = False


_setup_console_logging()


# ==================== Настройки ====================
# Имя файла шрифта (без .otf) в папке ./fonts
FONT_NAME = 'MonoCondensed'

# Регулярные выражения
NUM_RE = re.compile(r'^([A-Z]{2})(\d{4})$')
BARCODE_RE = re.compile(r'^\d{5,}$')
MSK_RE = re.compile(r'^\d{2,3}-\d{1,4}$')

# ==================== Списки для редактора спецификаций ====================
# Единицы (англ.): напряжение / сопротивление / ёмкость с приставками.
_UNITS_CHOICES = [
    '',
    'V', 'mV', 'uV',
    'Ohm', 'kOhm', 'MOhm', 'GOhm',
    'F', 'mF', 'uF', 'nF', 'pF',
]


def generate_range(begin: str, end: str) -> List[str]:
    m1 = NUM_RE.match(begin.strip().upper())
    m2 = NUM_RE.match(end.strip().upper())
    if not m1 or not m2:
        raise ValueError(f"Неверный формат номера: {begin} / {end}")
    p1, n1 = m1.group(1), int(m1.group(2))
    p2, n2 = m2.group(1), int(m2.group(2))
    if p1 != p2:
        raise ValueError(f"Разные префиксы: {p1} vs {p2}")
    if n1 > n2:
        n1, n2 = n2, n1
    return [f"{p1}{i:04d}" for i in range(n1, n2 + 1)]

# ==================== SI-приставки ====================
# Множитель перевода «единица с приставкой → базовая единица»
_SI_PREFIXES = {
    'T': 1e12, 'Т': 1e12,
    'G': 1e9,  'Г': 1e9,
    'M': 1e6,  'М': 1e6,
    'k': 1e3,  'K': 1e3, 'к': 1e3, 'К': 1e3,
    '': 1.0,
    'm': 1e-3, 'м': 1e-3,
    'u': 1e-6, 'µ': 1e-6, 'μ': 1e-6, 'мк': 1e-6,
    'n': 1e-9, 'н': 1e-9,
    'p': 1e-12, 'п': 1e-12,
}

# Псевдонимы базовых единиц → каноническое имя
_BASE_UNITS = {
    'Ohm': 'Ohm', 'Om': 'Ohm', 'Ом': 'Ohm', 'ом': 'Ohm',
    'F': 'F',     'Ф': 'F',   'ф': 'F',
    'V': 'V',     'В': 'V',   'в': 'V',
    'A': 'A',     'А': 'A',   'а': 'A',
    'W': 'W',     'Вт': 'W',  'вт': 'W',
    'Hz': 'Hz',   'Гц': 'Hz', 'гц': 'Hz',
    'H': 'H',     'Гн': 'H',  'гн': 'H',
    'S': 'S',     'См': 'S',  'см': 'S',
}

# Порог «обрыв»: сопротивление выше 100 МОм не показываем числом
_OPEN_CIRCUIT_THRESHOLD = 100e6   # Ом
# Маркер «норма не задана» в Par_min / Par_max
_NORM_ABSENT = -1000000


def parse_units(units: str):
    """Разбирает строку units ('kOm', 'uF', 'V', 'MOhm').

    Возвращает (base, prefix, multiplier):
      * base       — каноническая базовая единица ('Ohm', 'F', …);
      * prefix     — префикс ('k', 'u', '', …);
      * multiplier — множитель для перевода значения в базовую единицу.
    """
    if not units:
        return ('', '', 1.0)
    u = units.strip()
    # Ищем самый длинный совпадающий суффикс-единицу
    for alias in sorted(_BASE_UNITS.keys(), key=len, reverse=True):
        if u.endswith(alias):
            prefix = u[:-len(alias)]
            if prefix in _SI_PREFIXES:
                return (_BASE_UNITS[alias], prefix, _SI_PREFIXES[prefix])
    return (u, '', 1.0)


# ==================== GUI ====================
class App:
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

        # --- Пороги и маркеры ---
        # Сопротивление выше этого значения считаем «обрывом» и в таблице
        # показываем не число, а строку «> Par_max units».
        self._OPEN_CIRCUIT_THRESHOLD = 100e6  # Ом
        # Значение -1000000 в Par_min / Par_max означает «норма не задана».
        self._NORM_ABSENT = -1000000

        self._OPEN_CIRCUIT_THRESHOLD = 100e6  # 100 МОм
        self._NORM_ABSENT = -1000000
        self._OVERLOAD_THRESHOLD = 1e37  # порог «перегрузки» DM858 (9.9e+37)
        # --- Состояние редактора спецификаций ---
        self._se_rk_list: List[Dict] = []
        self._se_nk_list: List[Dict] = []
        self._se_specs: List[Dict] = []
        self._se_nom_id: Optional[int] = None
        self._se_selected_spec: Optional[Dict] = None
        self._se_params_list: List[Dict] = []
        self._se_current_spc_name: str = ''

        self.measured_indices: set = set()
        # Теги item_handler_registry, созданных для кликабельных номеров.
        # Их нужно удалять вручную при пересборке таблицы — они не являются
        # дочерними элементами таблицы и не удаляются вместе с ней.
        self._row_registry_tags: List[str] = []
        # Полный список номенклатур РК для ручного выбора спецификации.
        self.nk_all: List[Dict] = []

    # ---------- Тема ----------
    def _apply_theme(self):
        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (28, 28, 30))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (22, 22, 24))
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, (35, 35, 38))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (70, 70, 75))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (45, 45, 50))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (60, 60, 65))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (75, 75, 80))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (35, 35, 38))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (50, 50, 55))
                dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, (35, 35, 38))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (22, 22, 24))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (60, 60, 65))
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (200, 200, 200))
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (120, 120, 130))
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (150, 150, 160))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (55, 55, 60))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (75, 75, 85))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (95, 95, 105))
                dpg.add_theme_color(dpg.mvThemeCol_Header, (55, 55, 60))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (75, 75, 85))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (95, 95, 105))
                dpg.add_theme_color(dpg.mvThemeCol_Separator, (70, 70, 75))
                dpg.add_theme_color(dpg.mvThemeCol_ResizeGrip, (80, 80, 90))
                dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, (50, 50, 55))
                dpg.add_theme_color(dpg.mvThemeCol_TableBorderStrong, (90, 90, 95))
                dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, (60, 60, 65))
                dpg.add_theme_color(dpg.mvThemeCol_TableRowBg, (28, 28, 30))
                dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, (34, 34, 37))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (215, 215, 220))
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (120, 120, 125))

                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 2)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 2)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 2)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 2)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 2)
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 6, 4)
        dpg.bind_theme(theme)

    # ---------- Построение ----------
    # ---------- Построение ----------
    def build(self):
        """Создать окно приложения (без create_context и viewport)."""
        with dpg.window(tag=self.win_tag, label="RT control ver 1.0",
                        width=1460, height=860, pos=(20, 20),
                        no_close=True):
            # ---------- Верхняя панель кнопок ----------
            with dpg.group(horizontal=True):
                dpg.add_text("Штрих-код / МСК:")
                dpg.add_input_text(tag=self.input_tag, width=260,
                                   on_enter=True, callback=self.on_find)
                dpg.add_button(label="  Найти  ", callback=self.on_find)
                dpg.add_spacer(width=20)
                dpg.add_button(label="  Сохранить  ", callback=self.on_save)
                dpg.add_spacer(width=20)
                dpg.add_button(label="  Экспорт PDF  ",
                               callback=self.on_export_pdf)
                dpg.add_button(label="  Подключить  ",
                               callback=self.on_connect)
                dpg.add_button(label="  Спецификации  ",
                               callback=self.on_open_spec_editor)

            dpg.add_spacer(height=4)

            # ---------- Выбор спецификации (список номенклатур РК) ----------
            with dpg.group(horizontal=True):
                dpg.add_text("Спецификация:")
                dpg.add_combo(
                    [], tag="spec_selector", width=900,
                    callback=self._on_spec_selector_changed,
                )

            dpg.add_spacer(height=4)

            # ---------- Информационная строка и статус ----------
            dpg.add_text("", tag=self.info_tag, color=(180, 200, 255))
            dpg.add_text("", tag=self.status_tag, color=(255, 220, 100))
            dpg.add_separator()

            # ---------- Контейнер таблицы результатов ----------
            dpg.add_child_window(tag=self.table_container, height=-1,
                                 horizontal_scrollbar=True)

            # ---------- Модальное окно редактора спецификаций ----------
            self._build_spec_editor()

    def build__(self):
        """Создать окно приложения (без create_context и viewport)."""
        with dpg.window(tag=self.win_tag, label="RT control ver 1.0",
                        width=1460, height=860, pos=(20, 20),
                        no_close=True):
            with dpg.group(horizontal=True):
                dpg.add_text("Штрих-код / МСК:")
                dpg.add_input_text(tag=self.input_tag, width=260,
                                   on_enter=True, callback=self.on_find)
                dpg.add_button(label="  Найти  ", callback=self.on_find)
                dpg.add_spacer(width=20)
                dpg.add_button(label="  Сохранить  ", callback=self.on_save)
                dpg.add_spacer(width=20)
                dpg.add_spacer(width=20)
                dpg.add_button(label="  Экспорт PDF  ", callback=self.on_export_pdf)
                dpg.add_button(label="  Подключить  ", callback=self.on_connect)
                dpg.add_button(label="  Спецификации  ",
                               callback=self.on_open_spec_editor)
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_text("Спецификация:")
                dpg.add_combo(
                    [], tag="spec_selector", width=700,
                    callback=self._on_spec_selector_changed,
                )

            dpg.add_spacer(height=4)
            dpg.add_text("", tag=self.info_tag, color=(180, 200, 255))
            dpg.add_text("", tag=self.status_tag, color=(255, 220, 100))

            dpg.add_spacer(height=4)
            dpg.add_text("", tag=self.info_tag, color=(180, 200, 255))
            dpg.add_text("", tag=self.status_tag, color=(255, 220, 100))
            dpg.add_separator()

            dpg.add_child_window(tag=self.table_container, height=-1,
                                 horizontal_scrollbar=True)
            self._build_spec_editor()

    def set_status(self, text: str, color=(255, 220, 100)):
        if dpg.does_item_exist(self.status_tag):
            dpg.set_value(self.status_tag, text)
            dpg.configure_item(self.status_tag, color=color)

    # ==================================================================
    #  ВЫБОР СПЕЦИФИКАЦИИ (главный экран)
    # ==================================================================

    @staticmethod
    def _nk_full_label(n: Dict) -> str:
        """Читаемая метка номенклатуры для combo спецификаций."""
        freq = n.get('частота')
        if isinstance(freq, (int, float)):
            f_str = f"{freq:g}"
        else:
            f_str = str(freq if freq is not None else '?')
        nm = (n.get('наименование') or '').strip()
        nid = n.get('номенклатура')
        return f"{f_str} Гц  |  {nm}  [ID {nid}]"

    def _load_nk_list(self):
        """Загрузить полный список спецификаций в combo."""
        try:
            self.nk_all = db.get_all_nomeklatura()
        except Exception as e:
            log.exception("Ошибка загрузки списка номенклатур")
            self.nk_all = []
            self.set_status(f"Ошибка загрузки списка спецификаций: {e}",
                            (255, 100, 100))

        labels = [self._nk_full_label(n) for n in self.nk_all] or [""]
        if dpg.does_item_exist("spec_selector"):
            dpg.configure_item("spec_selector", items=labels)

    def _select_nk_by_nom_id(self, nom_id) -> bool:
        """Установить значение combo, соответствующее nom_id.

        Возвращает True, если соответствующая запись найдена.
        """
        for n in self.nk_all:
            if n.get('номенклатура') == nom_id:
                dpg.set_value("spec_selector", self._nk_full_label(n))
                return True
        return False

    def _on_spec_selector_changed(self, sender, app_data):
        """Пользователь вручную выбрал спецификацию из списка."""
        if not app_data:
            return
        for n in self.nk_all:
            if self._nk_full_label(n) == app_data:
                new_nom_id = n.get('номенклатура')
                if new_nom_id == self.nom_id:
                    return
                log.info("Ручной выбор спецификации: NOM_ID=%s", new_nom_id)
                self._apply_spec_choice(new_nom_id)
                return

    def _apply_spec_choice(self, new_nom_id):
        """Сменить активную спецификацию и пересчитать всё отображение."""
        self.nom_id = new_nom_id

        try:
            self.specs = (db.get_specs(self.nom_id)
                          if self.nom_id is not None else [])
        except Exception:
            log.exception("Ошибка загрузки спецификаций")
            self.specs = []

        try:
            self.column_names = (db.get_column_names(self.nom_id)
                                 if self.nom_id is not None else {})
        except Exception:
            log.exception("Ошибка загрузки названий колонок")
            self.column_names = {}

        # Обновляем заголовки колонок (пересобираем таблицу)
        self._rebuild_table()

        # Перерисовываем значения и пересчитываем статусы по новым нормам
        for i, row in enumerate(self.rows):
            self._reset_row_color(i)
            if not row.get('values'):
                continue
            self._render_row_values(i)
            status = self._evaluate_status(row['values'])
            row['status'] = status
            tag = f"status_{i}"
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, status)
            if status == "Брак":
                self._color_row_red(i)
                self._color_failed_cells_yellow(i)

        self._update_info_text()
        self.set_status(
            f"Выбрана спецификация: {self._current_spec_name() or '-'}",
            (100, 200, 255)
        )

    def _current_spec_name(self) -> str:
        for n in self.nk_all:
            if n.get('номенклатура') == self.nom_id:
                return (n.get('наименование') or '').strip()
        return ''

    def _update_info_text(self):
        """Обновить строку информации под шапкой (без NOM_ID)."""
        if not dpg.does_item_exist(self.info_tag):
            return
        spec_name = self._current_spec_name() or '-'
        dpg.set_value(
            self.info_tag,
            f"МСК_Реал: {self.msk_real or '-'}   |   "
            f"Номеров: {len(self.rows)}   |   "
            f"Спецификация: {spec_name}   |   "
            f"Параметров: {len(self.specs)}   |   "
            f"Измерено: {len(self.measured_indices)}"
        )

    # ---------- Кнопки ----------
    def on_connect(self):
        if self.engine.connected:
            log.info("Оборудование уже подключено")
            self.set_status("Оборудование уже подключено", (200, 200, 100))
            return
        try:
            self.set_status("Подключение к оборудованию...", (200, 200, 100))
            log.info("Пользователь инициировал подключение")
            self.engine.connect()
            self.set_status("Оборудование подключено", (100, 255, 100))
        except Exception as e:
            log.exception("Ошибка подключения")
            self.set_status(f"Ошибка подключения: {e}", (255, 100, 100))

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

        # ---- Шаг 2: подтянуть список доступных спецификаций ----
        self._load_nk_list()

        # Попытаться подсветить спецификацию, привязанную к МСК.
        if self.nom_id is not None:
            if not self._select_nk_by_nom_id(self.nom_id):
                # NOM_ID из МСК отсутствует в списке номенклатур —
                # оставляем combo пустым, но продолжаем с этим NOM_ID.
                if dpg.does_item_exist("spec_selector"):
                    dpg.set_value("spec_selector", "")
        else:
            # Не удалось определить NOM_ID — если есть что-то в списке,
            # берём первый элемент, чтобы пользователь сразу что-то видел.
            if self.nk_all:
                first = self.nk_all[0]
                if dpg.does_item_exist("spec_selector"):
                    dpg.set_value("spec_selector",
                                  self._nk_full_label(first))
                self.nom_id = first.get('номенклатура')

        # ---- Шаг 3: загрузить спецификации под выбранный NOM_ID ----
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

        # ---- Шаг 4: перестроить таблицу и подтянуть сохранённые данные ----
        self.rows = [{'N': n, 'values': {}, 'status': ''} for n in numbers]
        self.measured_indices = set()
        self._rebuild_table()

        loaded = self._try_load_saved()

        log.info("Сформирован список: %d номеров, NOM_ID=%s, specs=%d, "
                 "loaded=%d",
                 len(numbers), self.nom_id, len(self.specs), loaded)

        # Итоговая строка информации — БЕЗ NOM_ID, с именем спецификации.
        self._update_info_text()

        if loaded:
            self.set_status(
                f"Загружено {loaded} сохранённых записей из БД",
                (100, 200, 255)
            )
        else:
            self.set_status(f"Загружено {len(numbers)} номеров",
                            (100, 200, 255))

    def on_find_old(self):
        if self.measuring:
            self.set_status("Идёт измерение. Дождитесь окончания.", (255, 150, 100))
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

        try:
            self.specs = db.get_specs(self.nom_id) if self.nom_id is not None else []
        except Exception as e:
            self.specs = []
            log.exception("Ошибка загрузки спецификаций")
            self.set_status(f"Ошибка загрузки спецификаций: {e}", (255, 100, 100))

        try:
            self.column_names = (db.get_column_names(self.nom_id)
                                 if self.nom_id is not None else {})
        except Exception:
            self.column_names = {}
            log.exception("Ошибка загрузки названий колонок")

        self.rows = [{'N': n, 'values': {}, 'status': ''} for n in numbers]
        self.measured_indices = set()
        self._rebuild_table()

        # Попытка подтянуть уже сохранённые результаты из xsr_rt_montag
        loaded = self._try_load_saved()

        log.info("Сформирован список: %d номеров, NOM_ID=%s, specs=%d",
                 len(numbers), self.nom_id, len(self.specs))

        dpg.set_value(
            self.info_tag,
            f"МСК_Реал: {self.msk_real or '-'}   |   "
            f"Номеров: {len(numbers)}   |   NOM_ID: {self.nom_id}   |   "
            f"Спецификаций: {len(self.specs)}   |   "
            f"Загружено из БД: {loaded}"
        )
        if loaded:
            self.set_status(
                f"Загружено {loaded} сохранённых записей из БД",
                (100, 200, 255)
            )
        else:
            self.set_status(f"Загружено {len(numbers)} номеров",
                            (100, 200, 255))
        self.set_status(f"Загружено {len(numbers)} номеров", (100, 200, 255))

    def _try_load_saved(self) -> int:
        """Подтянуть сохранённые измерения из БД и отобразить их.

        Возвращает количество успешно сопоставленных строк (0, если
        для текущего МСК ничего не сохранено).
        """
        if not self.msk_real:
            return 0

        try:
            saved = db.load_measurements(self.msk_real, self.nom_id)
        except Exception as e:
            log.exception("Ошибка загрузки сохранённых измерений")
            self.set_status(f"Ошибка загрузки сохранённых данных: {e}",
                            (255, 100, 100))
            return 0

        if not saved:
            log.info("Сохранённых измерений для МСК_Реал=%s нет",
                     self.msk_real)
            return 0

        # Индекс по номеру резонатора: {'AB0001': {...}, ...}
        by_n = {r['N']: r for r in saved if r.get('N')}

        loaded = 0
        for i, row in enumerate(self.rows):
            s = by_n.get(row['N'])
            if not s or not s.get('values'):
                continue

            row['values'] = dict(s['values'])
            status = self._evaluate_status(row['values'])
            row['status'] = status

            self._render_row_values(i)

            tag = f"status_{i}"
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, status)

            if status == "Брак":
                self._color_row_red(i)
                self._color_failed_cells_yellow(i)

            self.measured_indices.add(i)
            loaded += 1

        log.info("Сопоставлено сохранённых строк: %d из %d",
                 loaded, len(saved))
        return loaded


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

        # --- Сброс результатов предыдущего цикла для этой строки ---
        if idx in self.measured_indices:
            self.measured_indices.discard(idx)
        self.rows[idx]['values'] = {}
        self.rows[idx]['status'] = ''
        self._reset_row_display(idx)
        self._reset_row_color(idx)

        # Обновляем строку общего статуса (кол-во измеренных/годных/брака)
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
        # --- /Сброс ---

        n = self.rows[idx]['N']
        log.info("Запуск измерения для %s (индекс %d)", n, idx)
        self.measuring = True
        # Кнопок «Пуск» больше нет — просто подсвечиваем строку зелёным
        self._color_row_green(idx)

        self.set_status(f"Измерение {n} ...", (200, 200, 100))
        threading.Thread(target=self._measure_thread, args=(idx,),
                         daemon=True).start()

    def _collect_bad_cells_for_row(self, row_idx: int) -> set:
        """Возвращает множество позиций (1..12) строки row_idx,
        где норма не выполнена. Логика совпадает с
        _color_failed_cells_yellow, но без обращения к DearPyGui."""
        if not self.specs:
            return set()

        row = self.rows[row_idx]
        values = row.get('values') or {}
        cap_col = self._cap_display_col()
        cap_positions = self._cap_modes_positions()

        all_cap_parts: List[float] = []
        for cp in cap_positions:
            raw = values.get(cp)
            if not raw:
                continue
            for mode, part in self._split_by_mode(cp, raw):
                if mode == 'CAP':
                    try:
                        all_cap_parts.append(float(part))
                    except ValueError:
                        pass

        specs_by_switch: Dict[int, List[Dict]] = {}
        for s in self.specs:
            sw = s.get('switch_id')
            if sw is None:
                continue
            specs_by_switch.setdefault(sw, []).append(s)

        bad_positions: set = set()
        for pos in range(1, 13):
            specs = specs_by_switch.get(pos, [])
            if not specs:
                continue
            parts = self._get_checked_parts_for_pos(
                pos, values, cap_col, cap_positions, all_cap_parts
            )
            if not parts:
                continue
            for v in parts:
                for spec in specs:
                    if not self._check_spec(v, spec):
                        bad_positions.add(pos)
                        break
                else:
                    continue
                break

        return bad_positions

    def on_save(self):
        log.info("Сохранение: измерено %d строк", len(self.measured_indices))
        if not self.measured_indices:
            self.set_status("Нет измеренных номеров для сохранения",
                            (255, 150, 100))
            return
        rows_to_save = [self.rows[i] for i in sorted(self.measured_indices)]
        try:
            n = db.save_measurements(self.msk_real or '', self.nom_id, rows_to_save)
            self.set_status(f"Сохранено {n} записей в xsr_rt_montag",
                            (100, 255, 100))
        except Exception as e:
            log.exception("Ошибка сохранения")
            self.set_status(f"Ошибка сохранения: {e}", (255, 100, 100))

    # ==================================================================
    #  РЕДАКТОР СПЕЦИФИКАЦИЙ
    # ==================================================================

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
            # ---------- Выбор РК / частоты / NOM_ID ----------
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

            # ---------- Таблица спецификаций ----------
            dpg.add_child_window(tag="se_table_container", height=440)

            dpg.add_separator()

            # ---------- Форма редактирования ----------
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
                dpg.add_combo(_UNITS_CHOICES, tag="se_units", width=110,
                              default_value="")
                dpg.add_spacer(width=20)
                dpg.add_text("MIN:")
                dpg.add_input_text(tag="se_min", width=130)
                dpg.add_spacer(width=10)
                dpg.add_text("Max:")
                dpg.add_input_text(tag="se_max", width=130)

            with dpg.group(horizontal=True):
                dpg.add_text("Spc_Name:")
                dpg.add_input_text(tag="se_spc_name", width=320,
                                   readonly=True)
                dpg.add_spacer(width=20)
                dpg.add_checkbox(label="Цифровое значение (да/нет)",
                                 tag="se_pvalue")
                dpg.add_spacer(width=20)
                dpg.add_checkbox(label="Звуковой сигнал (да/нет)",
                                 tag="se_pbool")

            dpg.add_separator()

            # ---------- Кнопки ----------
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

    # ---------- Открытие / закрытие ----------

    def _on_se_reload_params(self):
        """Принудительно перечитать параметры из БД и обновить combo."""
        try:
            self._se_params_list = db.get_parameters()
        except Exception as e:
            log.exception("Ошибка перезагрузки параметров")
            self._se_set_status(f"Ошибка загрузки параметров: {e}",
                                (255, 100, 100))
            return
        self._se_apply_params_to_combo()
        n = len(self._se_params_list)
        if n == 0:
            self._se_set_status(
                "Список параметров пуст: проверьте таблицу "
                "spc_xsr_rt_parameters",
                (255, 150, 100)
            )
        else:
            self._se_set_status(f"Загружено параметров: {n}",
                                (100, 255, 100))

    def on_open_spec_editor(self):
        """Открыть модальное окно редактора."""
        # Типы РК
        try:
            self._se_rk_list = db.get_resonator_types()
        except Exception as e:
            log.exception("Ошибка загрузки типов РК")
            self.set_status(f"Ошибка загрузки типов РК: {e}",
                            (255, 100, 100))
            return

        # Параметры
        try:
            self._se_params_list = db.get_parameters()
        except Exception as e:
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
        """Заполнить combo Par_Name значениями из self._se_params_list.

        Всегда даёт непустой items (минимум [' ']) — иначе в части сборок
        DearPyGui пустой список не «подхватывается» после configure_item.
        """
        names = [(p.get('Par_Name') or '').strip()
                 for p in self._se_params_list]
        names = [n for n in names if n]
        if not names:
            names = [' ']   # чтобы комбо осталось кликабельным и не пустым
        dpg.configure_item("se_par_name", items=names)
        log.info("Par_Name combo: %d элементов", len(names))


    def _on_se_close(self):
        dpg.configure_item("spec_editor_window", show=False)

    # ---------- Вспомогательные ----------

    def _se_set_status(self, text: str, color=(255, 220, 100)):
        if dpg.does_item_exist("se_status"):
            dpg.set_value("se_status", text)
            dpg.configure_item("se_status", color=color)

    @staticmethod
    def _se_rk_label(r: Dict) -> str:
        return (r.get('Name') or '').strip()

    @staticmethod
    def _se_nk_label(n: Dict) -> str:
        freq = n.get('частота')
        if isinstance(freq, (int, float)):
            f_str = f"{freq:g}"
        else:
            f_str = str(freq if freq is not None else '?')
        nm = (n.get('наименование') or '').strip()
        return f"{f_str} Гц  |  {nm}"

    def _se_clear_form(self):
        for tag, val in [
            ("se_sw", ""), ("se_round", ""),
            ("se_min", ""), ("se_max", ""),
        ]:
            dpg.set_value(tag, val)
        dpg.set_value("se_par_name", "")
        dpg.set_value("se_par_id", "")
        dpg.set_value("se_units", "")
        dpg.set_value("se_pvalue", False)
        dpg.set_value("se_pbool", False)
        dpg.set_value("se_spc_name", self._se_current_spc_name or "")

    @staticmethod
    def _fmt_num_edit(x) -> str:
        if x is None:
            return ""
        if isinstance(x, float):
            return f"{x:g}"
        return str(x)

    @staticmethod
    def _fmt_tiny_edit(x) -> str:
        if x is None:
            return ""
        if x in (0, '0'):
            return "0"
        if x in (1, '1'):
            return "1"
        return str(x)

    def _se_get_int(self, tag: str) -> Optional[int]:
        v = dpg.get_value(tag)
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        try:
            return int(str(v).strip())
        except ValueError:
            raise ValueError(f"«{tag}»: не целое число ({v!r})")

    def _se_get_float(self, tag: str) -> Optional[float]:
        v = dpg.get_value(tag)
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        try:
            return float(str(v).replace(',', '.').strip())
        except ValueError:
            raise ValueError(f"«{tag}»: не число ({v!r})")

    def _se_get_str(self, tag: str) -> Optional[str]:
        v = dpg.get_value(tag)
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return str(v).strip()

    @staticmethod
    def _se_bool_to_tiny(v) -> int:
        return 1 if v else 0

    # ---------- Реакции комбобоксов ----------

    def _on_se_rk_changed(self, sender, app_data):
        idx = -1
        for i, r in enumerate(self._se_rk_list):
            if self._se_rk_label(r) == app_data:
                idx = i
                break
        if idx < 0:
            return
        self._se_load_nomeklatura(idx)

    def _se_load_nomeklatura(self, rk_index: int):
        rk = self._se_rk_list[rk_index]
        try:
            self._se_nk_list = db.get_nomeklatura_by_rk(rk['ID'])
        except Exception as e:
            log.exception("Ошибка загрузки номенклатур")
            self._se_set_status(f"Ошибка загрузки номенклатур: {e}",
                                (255, 100, 100))
            self._se_nk_list = []

        labels = [self._se_nk_label(n) for n in self._se_nk_list]
        dpg.configure_item("se_freq_combo", items=labels if labels else [""])

        if labels:
            dpg.set_value("se_freq_combo", labels[0])
            self._se_set_nom_id(self._se_nk_list[0].get('номенклатура'))
        else:
            dpg.set_value("se_freq_combo", "")
            self._se_set_nom_id(None)

    def _on_se_freq_changed(self, sender, app_data):
        idx = -1
        for i, n in enumerate(self._se_nk_list):
            if self._se_nk_label(n) == app_data:
                idx = i
                break
        if idx < 0:
            self._se_set_nom_id(None)
            return
        self._se_set_nom_id(self._se_nk_list[idx].get('номенклатура'))

    def _on_se_param_changed(self, sender, app_data):
        """При выборе имени параметра — автоматически подставить Par_ID."""
        for p in self._se_params_list:
            if (p.get('Par_Name') or '') == (app_data or ''):
                pid = p.get('Par_ID')
                dpg.set_value("se_par_id", "" if pid is None else str(pid))
                return
        dpg.set_value("se_par_id", "")

    def _se_set_nom_id(self, nom_id: Optional[int]):
        self._se_nom_id = nom_id

        # Spc_Name = наименование из nomeklatura_rk для выбранного NOM_ID
        name = ''
        if nom_id is not None:
            for n in self._se_nk_list:
                if n.get('номенклатура') == nom_id:
                    name = (n.get('наименование') or '').strip()
                    break
        self._se_current_spc_name = name

        if dpg.does_item_exist("se_nom_info"):
            dpg.set_value(
                "se_nom_info",
                f"NOM_ID: {nom_id if nom_id is not None else '-'}"
            )
        if dpg.does_item_exist("se_spc_name"):
            dpg.set_value("se_spc_name", name)

        self._se_reload_specs()

    # ---------- Таблица спецификаций ----------

    def _se_reload_specs(self):
        if self._se_nom_id is None:
            self._se_specs = []
        else:
            try:
                self._se_specs = db.get_specs_by_nom_id(self._se_nom_id)
            except Exception as e:
                log.exception("Ошибка загрузки спецификаций")
                self._se_set_status(f"Ошибка загрузки: {e}",
                                    (255, 100, 100))
                self._se_specs = []
        self._se_selected_spec = None
        self._se_rebuild_table()

    def _se_rebuild_table(self):
        if dpg.does_item_exist("se_table"):
            dpg.delete_item("se_table")

        with dpg.table(
                parent="se_table_container", tag="se_table",
                header_row=True, row_background=True,
                borders_innerH=True, borders_outerH=True,
                borders_innerV=True, borders_outerV=True,
                scrollY=True, height=-1, freeze_rows=1,
                policy=dpg.mvTable_SizingStretchProp,
        ):
            dpg.add_table_column(label="ID", init_width_or_weight=0.4)
            dpg.add_table_column(label="sw", init_width_or_weight=0.4)
            dpg.add_table_column(label="Параметр", init_width_or_weight=1.6)
            dpg.add_table_column(label="units", init_width_or_weight=0.6)
            dpg.add_table_column(label="MIN", init_width_or_weight=0.7)
            dpg.add_table_column(label="Max", init_width_or_weight=0.7)
            dpg.add_table_column(label="Цифр.", init_width_or_weight=0.5)
            dpg.add_table_column(label="Звук", init_width_or_weight=0.5)
            dpg.add_table_column(label="Окр.", init_width_or_weight=0.5)
            dpg.add_table_column(label="Par_ID", init_width_or_weight=0.5)
            dpg.add_table_column(label="Spc_Name", init_width_or_weight=1.3)

            for spec in self._se_specs:
                sid = spec.get('ID')
                with dpg.table_row():
                    dpg.add_button(
                        label=str(sid) if sid is not None else "-",
                        width=-1,
                        callback=self._on_se_row_select,
                        user_data=spec,
                    )
                    dpg.add_text(str(spec.get('switch_id') or ''))
                    dpg.add_text(str(spec.get('Par_Name') or ''))
                    dpg.add_text(str(spec.get('units') or ''))
                    dpg.add_text(self._fmt_num_edit(spec.get('Par_min')))
                    dpg.add_text(self._fmt_num_edit(spec.get('Par_max')))
                    dpg.add_text(self._fmt_tiny_edit(spec.get('Par_value')))
                    dpg.add_text(self._fmt_tiny_edit(spec.get('Par_Bool')))
                    dpg.add_text(self._fmt_num_edit(spec.get('round_Value')))
                    dpg.add_text(self._fmt_num_edit(spec.get('Par_ID')))
                    dpg.add_text(str(spec.get('Spc_Name') or ''))



    def _on_se_row_select(self, sender, app_data, user_data):
        """Загрузить выбранную запись в форму редактирования."""
        spec = user_data or {}
        self._se_selected_spec = spec

        # --- switch_id ---
        dpg.set_value("se_sw", self._fmt_num_edit(spec.get('switch_id')))

        # --- Par_Name: всегда актуальный список из spc_xsr_rt_parameters ---
        names = [(p.get('Par_Name') or '').strip()
                 for p in self._se_params_list]
        names = [n for n in names if n]

        par_name = (spec.get('Par_Name') or '').strip()
        # если в БД сохранено имя, которого нет в справочнике — добавим его,
        # чтобы combo корректно отобразило значение
        if par_name and par_name not in names:
            names = [par_name] + names
        if not names:
            names = ['']
        dpg.configure_item("se_par_name", items=names)
        dpg.set_value("se_par_name", par_name)

        # --- Par_ID: явная строка, без _fmt_num_edit ---
        par_id = spec.get('Par_ID')
        dpg.set_value("se_par_id", '' if par_id is None else str(par_id))

        # --- units: базовый список + возможное «нестандартное» значение ---
        units_val = spec.get('units') or ''
        items = list(_UNITS_CHOICES)
        if units_val and units_val not in items:
            items = [units_val] + items
        dpg.configure_item("se_units", items=items)
        dpg.set_value("se_units", units_val)

        # --- числовые поля ---
        dpg.set_value("se_round",
                      self._fmt_num_edit(spec.get('round_Value')))
        dpg.set_value("se_min", self._fmt_num_edit(spec.get('Par_min')))
        dpg.set_value("se_max", self._fmt_num_edit(spec.get('Par_max')))

        # --- чекбоксы ---
        dpg.set_value("se_pvalue", spec.get('Par_value') in (1, '1', True))
        dpg.set_value("se_pbool",  spec.get('Par_Bool')  in (1, '1', True))

        # --- Spc_Name — всегда из выбранной номенклатуры ---
        dpg.set_value("se_spc_name", self._se_current_spc_name or "")

        self._se_set_status(f"Выбрана запись ID={spec.get('ID')}",
                            (200, 200, 100))

    # ---------- Действия ----------

    def _on_se_new(self):
        """Начать ввод новой строки спецификации.

        Перед показом формы обновляем список параметров — это гарантирует,
        что в выпадающем списке всегда актуальный перечень
        spc_xsr_rt_parameters.
        """
        # На всякий случай — перечитаем параметры из БД
        try:
            self._se_params_list = db.get_parameters()
        except Exception:
            log.exception("Ошибка перезагрузки параметров")
        self._se_apply_params_to_combo()

        self._se_selected_spec = None
        self._se_clear_form()
        self._se_set_status("Новая запись — выберите параметр из списка",
                            (200, 200, 100))

    def _on_se_refresh(self):
        self._se_reload_specs()
        self._se_set_status("Таблица обновлена", (200, 200, 100))

    def _collect_spec_form(self) -> Dict:
        if self._se_nom_id is None:
            raise ValueError("Не выбран NOM_ID (РК / частота)")
        return {
            'NOM_ID': self._se_nom_id,
            'switch_id': self._se_get_int("se_sw"),
            'Par_Name': self._se_get_str("se_par_name"),
            'Par_ID': self._se_get_int("se_par_id"),
            'units': self._se_get_str("se_units"),
            'round_Value': self._se_get_int("se_round"),
            'Par_min': self._se_get_float("se_min"),
            'Par_max': self._se_get_float("se_max"),
            'Par_value': self._se_bool_to_tiny(dpg.get_value("se_pvalue")),
            'Par_Bool': self._se_bool_to_tiny(dpg.get_value("se_pbool")),
            'Spc_Name': self._se_current_spc_name or None,
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
        except Exception as e:
            log.exception("Ошибка сохранения спецификации")
            self._se_set_status(f"Ошибка сохранения: {e}",
                                (255, 100, 100))

    def _on_se_delete(self):
        sel = self._se_selected_spec
        if not sel or sel.get('ID') is None:
            self._se_set_status("Сначала выберите запись в таблице",
                                (255, 150, 100))
            return
        try:
            db.delete_spec(sel['ID'])
            self._se_set_status(f"Запись ID={sel['ID']} удалена",
                                (100, 255, 100))
            self._se_selected_spec = None
            self._se_clear_form()
            self._se_reload_specs()
        except Exception as e:
            log.exception("Ошибка удаления спецификации")
            self._se_set_status(f"Ошибка удаления: {e}",
                                (255, 100, 100))

    def _get_column_name(self, pos: int) -> str:
        """Название параметра для switch_id == pos.

        Основной источник — dict, загруженный из БД
        (db.get_column_names → Par_Name). Fallback — self.specs.
        """
        name = (self.column_names.get(pos) or '').strip()
        if name:
            return name
        # Резерв: вдруг column_names не загрузили, а specs есть
        for s in self.specs:
            if s.get('switch_id') == pos:
                n = (s.get('Par_Name') or '').strip()
                if n:
                    return n
        return ''

    def _get_column_title(self, pos: int,
                          max_len: Optional[int] = None) -> str:
        name = self._get_column_name(pos)
        if not name:
            return str(pos)
        if max_len is not None and len(name) > max_len:
            name = name[:max_len - 3].rstrip() + '...'
        return f"{pos}. {name}"

    # ---------- Экспорт PDF ----------
    def _register_pdf_font(self) -> str:
        """Регистрирует TTF-шрифт с кириллицей для reportlab (один раз)."""
        if self._pdf_font_name is not None:
            return self._pdf_font_name

        import os
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        candidates = [
            'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/DejaVuSans.ttf',
            'C:/Windows/Fonts/segoeui.ttf',
            'C:/Windows/Fonts/tahoma.ttf',
            'C:/Windows/Fonts/calibri.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont('ProtocolFont', path))
                    log.info("PDF-шрифт зарегистрирован: %s", path)
                    self._pdf_font_name = 'ProtocolFont'
                    return 'ProtocolFont'
                except Exception as e:
                    log.warning("Не удалось зарегистрировать шрифт %s: %s",
                                path, e)
        log.warning("Не найден TTF-шрифт с кириллицей — используется Helvetica")
        self._pdf_font_name = 'Helvetica'
        return 'Helvetica'

    def _open_file(self, path: str):
        """Открывает файл системным просмотрщиком."""
        import os, sys, subprocess
        try:
            if sys.platform.startswith('win'):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            log.warning("Не удалось открыть файл %s: %s", path, e)

    def _export_protocol_pdf(self) -> str:
        """Формирует PDF-протокол и возвращает путь к файлу."""
        import os
        import datetime
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                        Paragraph, Spacer)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import mm

        font_name = self._register_pdf_font()

        # --- Директория /Протоколы рядом со скриптом ---
        base_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir = os.path.join(base_dir, 'Протоколы')
        os.makedirs(out_dir, exist_ok=True)

        # --- Имя файла: мск_дата_время.pdf ---
        now = datetime.datetime.now()
        msk = (self.msk_real or 'MSK').strip() or 'MSK'
        safe_msk = ''.join(c if (c.isalnum() or c in '-_.') else '_'
                           for c in msk)
        ts = now.strftime('%Y-%m-%d_%H-%M-%S')
        base_name = f"{safe_msk}_{ts}"
        filepath = os.path.join(out_dir, f"{base_name}.pdf")
        counter = 1
        while os.path.exists(filepath):
            filepath = os.path.join(out_dir, f"{base_name}_{counter}.pdf")
            counter += 1

        # --- Документ ---
        doc = SimpleDocTemplate(
            filepath,
            pagesize=landscape(A4),
            leftMargin=10 * mm, rightMargin=10 * mm,
            topMargin=10 * mm, bottomMargin=10 * mm,
            title="Протокол проверки монтажа элементов",
            author="КР · Контроль плат",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ProtocolTitle', parent=styles['Title'],
            fontName=font_name, fontSize=16, leading=20, spaceAfter=4,
        )
        info_style = ParagraphStyle(
            'ProtocolInfo', parent=styles['Normal'],
            fontName=font_name, fontSize=10, leading=14,
        )
        cell_style = ParagraphStyle(
            'ProtocolCell', parent=styles['Normal'],
            fontName=font_name, fontSize=8, leading=10,
        )
        cell_style_bad = ParagraphStyle(
            'ProtocolCellBad', parent=cell_style,
            textColor=colors.HexColor('#8B0000'),
        )
        head_style = ParagraphStyle(
            'ProtocolHead', parent=cell_style,
            fontName=font_name, fontSize=6, leading=7, alignment=1,
        )

        story = []
        story.append(Paragraph("Протокол проверки монтажа элементов",
                               title_style))

        n_total = len(self.rows)
        n_meas = len(self.measured_indices)
        n_good = sum(1 for i in self.measured_indices
                     if self.rows[i].get('status') == 'Годен')
        n_bad = sum(1 for i in self.measured_indices
                    if self.rows[i].get('status') == 'Брак')

        info = (
            f"МСК: {self.msk_real or '-'} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Спецификация: {self._current_spec_name() or '-'}"
            f" &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Дата/время: {now.strftime('%d.%m.%Y %H:%M:%S')}<br/>"
            f"Всего номеров: {n_total} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Измерено: {n_meas} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Годные: {n_good} &nbsp;&nbsp;|&nbsp;&nbsp; Брак: {n_bad}"
        )
        story.append(Paragraph(info, info_style))
        story.append(Spacer(1, 4 * mm))

        # --- Таблица ---
        headers = (["№", "Номер"]
                   + [self._get_column_title(i) for i in range(1, 13)]
                   + ["Статус"])
        table_data = [[Paragraph(h, head_style) for h in headers]]

        bad_rows: List[int] = []                    # индексы строк «Брак»
        bad_cells_by_row: Dict[int, set] = {}       # индекс → колонки ячеек

        for i, row in enumerate(self.rows):
            is_bad = (row.get('status') or '') == 'Брак'

            cells = [str(i + 1), str(row.get('N', ''))]
            values = row.get('values', {})
            for pos in range(1, 13):
                raw = values.get(pos)
                if raw is None:
                    cells.append('-')
                    continue
                try:
                    cells.append(self._format_value_for_pos(pos, raw))
                except Exception:
                    log.exception("Ошибка форматирования pos=%d raw=%r",
                                  pos, raw)
                    cells.append(str(raw))
            status = row.get('status') or '-'
            cells.append(status)

            row_style = cell_style_bad if is_bad else cell_style
            table_data.append([Paragraph(str(c), row_style) for c in cells])

            if is_bad:
                r_idx = len(table_data) - 1
                bad_rows.append(r_idx)

                # Конкретные «проваленные» ячейки: колонки 2..13
                # (0=№, 1=Номер, 2..13=позиции 1..12, 14=Статус)
                bad_pos = self._collect_bad_cells_for_row(i)
                if bad_pos:
                    bad_cells_by_row[r_idx] = {pos + 1 for pos in bad_pos}

        avail = 297 * mm - 20 * mm  # A4 landscape - поля
        col_widths = ([10 * mm, 24 * mm]
                      + [(avail - 10 * mm - 24 * mm - 22 * mm) / 12] * 12
                      + [22 * mm])

        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # --- Цвета (единая палитра) ---
        c_head_bg   = colors.HexColor('#D9D9D9')
        c_grid      = colors.HexColor('#808080')
        c_bad_bg    = colors.HexColor('#FDE0E0')   # светлый розовый фон строки
        c_bad_text  = colors.HexColor('#8B0000')   # тёмно-красный текст
        c_badcell_bg = colors.HexColor('#F5A0A0')  # насыщенная ячейка
        c_badcell_text = colors.HexColor('#5A0000')  # почти чёрный бордо

        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), c_head_bg),
            ('GRID', (0, 0), (-1, -1), 0.5, c_grid),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ]

        # 1) Подсветка всей строки брака — светло-красный фон + тёмный текст
        for r in bad_rows:
            style_cmds.append(('BACKGROUND', (0, r), (-1, r), c_bad_bg))
            style_cmds.append(('TEXTCOLOR',  (0, r), (-1, r), c_bad_text))

        # 2) Подсветка конкретных «проваленных» ячеек — поверх фона строки
        for r, cols in bad_cells_by_row.items():
            for c in cols:
                style_cmds.append(
                    ('BACKGROUND', (c, r), (c, r), c_badcell_bg))
                style_cmds.append(
                    ('TEXTCOLOR',  (c, r), (c, r), c_badcell_text))

        table.setStyle(TableStyle(style_cmds))
        story.append(table)

        doc.build(story)
        log.info("Протокол сохранён: %s", filepath)
        return filepath

    def _export_protocol_pdf_3(self) -> str:
        """Формирует PDF-протокол и возвращает путь к файлу."""
        import os
        import datetime
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                        Paragraph, Spacer)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import mm

        font_name = self._register_pdf_font()

        # --- Директория /Протоколы рядом со скриптом ---
        base_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir = os.path.join(base_dir, 'Протоколы')
        os.makedirs(out_dir, exist_ok=True)

        # --- Имя файла: мск_дата_время.pdf ---
        now = datetime.datetime.now()
        msk = (self.msk_real or 'MSK').strip() or 'MSK'
        safe_msk = ''.join(c if (c.isalnum() or c in '-_.') else '_'
                           for c in msk)
        ts = now.strftime('%Y-%m-%d_%H-%M-%S')
        base_name = f"{safe_msk}_{ts}"
        filepath = os.path.join(out_dir, f"{base_name}.pdf")
        counter = 1
        while os.path.exists(filepath):
            filepath = os.path.join(out_dir, f"{base_name}_{counter}.pdf")
            counter += 1

        # --- Документ ---
        doc = SimpleDocTemplate(
            filepath,
            pagesize=landscape(A4),
            leftMargin=10 * mm, rightMargin=10 * mm,
            topMargin=10 * mm, bottomMargin=10 * mm,
            title="Протокол проверки монтажа элементов",
            author="КР · Контроль плат",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ProtocolTitle', parent=styles['Title'],
            fontName=font_name, fontSize=16, leading=20, spaceAfter=4,
        )
        info_style = ParagraphStyle(
            'ProtocolInfo', parent=styles['Normal'],
            fontName=font_name, fontSize=10, leading=14,
        )
        cell_style = ParagraphStyle(
            'ProtocolCell', parent=styles['Normal'],
            fontName=font_name, fontSize=8, leading=10,
        )
        head_style = ParagraphStyle(
            'ProtocolHead', parent=cell_style,
            fontName=font_name, fontSize=6, leading=7, alignment=1,
        )

        story = []
        story.append(Paragraph("Протокол проверки монтажа элементов",
                               title_style))

        n_total = len(self.rows)
        n_meas = len(self.measured_indices)
        n_good = sum(1 for i in self.measured_indices
                     if self.rows[i].get('status') == 'Годен')
        n_bad = sum(1 for i in self.measured_indices
                    if self.rows[i].get('status') == 'Брак')

        info = (
            f"МСК: {self.msk_real or '-'} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"NOM_ID: {self.nom_id if self.nom_id is not None else '-'}"
            f" &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Дата/время: {now.strftime('%d.%m.%Y %H:%M:%S')}<br/>"
            f"Всего номеров: {n_total} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Измерено: {n_meas} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Годен: {n_good} &nbsp;&nbsp;|&nbsp;&nbsp; Брак: {n_bad}"
        )
        story.append(Paragraph(info, info_style))
        story.append(Spacer(1, 4 * mm))

        # --- Таблица ---
        headers = (["№", "Номер"]
                   + [self._get_column_title(i) for i in range(1, 13)]
                   + ["Статус"])
        table_data = [[Paragraph(h, head_style) for h in headers]]
        bad_rows = []

        for i, row in enumerate(self.rows):
            cells = [str(i + 1), str(row.get('N', ''))]
            values = row.get('values', {})
            for pos in range(1, 13):
                raw = values.get(pos)
                if raw is None:
                    cells.append('-')
                    continue
                try:
                    cells.append(self._format_value_for_pos(pos, raw))
                except Exception:
                    log.exception("Ошибка форматирования pos=%d raw=%r",
                                  pos, raw)
                    cells.append(str(raw))
            status = row.get('status') or '-'
            cells.append(status)
            table_data.append([Paragraph(str(c), cell_style) for c in cells])
            if status == 'Брак':
                bad_rows.append(len(table_data) - 1)

        avail = 297 * mm - 20 * mm  # A4 landscape - поля
        col_widths = ([10 * mm, 24 * mm]
                      + [(avail - 10 * mm - 24 * mm - 22 * mm) / 12] * 12
                      + [22 * mm])

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D9D9D9')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#808080')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ]
        for r in bad_rows:
            style_cmds.append(('TEXTCOLOR', (0, r), (-1, r), colors.red))
        table.setStyle(TableStyle(style_cmds))
        story.append(table)

        doc.build(story)
        log.info("Протокол сохранён: %s", filepath)
        return filepath

    def on_export_pdf(self):
        if not self.rows:
            self.set_status("Нет данных для экспорта", (255, 150, 100))
            return
        if not self.measured_indices:
            self.set_status("Нет измеренных номеров для экспорта",
                            (255, 150, 100))
            return
        try:
            self.set_status("Формирование протокола...", (200, 200, 100))
            path = self._export_protocol_pdf()
            self.set_status(f"Протокол сохранён: {os.path.basename(path)}",
                            (100, 255, 100))
            self._open_file(path)
        except Exception as e:
            log.exception("Ошибка экспорта протокола")
            self.set_status(f"Ошибка экспорта: {e}", (255, 100, 100))

    # ---------- Логика ----------
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

        raise ValueError("Неверный формат. Штрих-код — 5+ цифр; МСК — xx-xxxx.")

    def _load_nom_id(self):
        self.nom_id = None
        if not self.msk_real:
            return
        print('MSK_REAL', self.msk_real)
        kod = db.get_kod_nom(self.msk_real)
        if kod:
            self.nom_id = db.get_nom_id(kod)

    # ---------- Таблица ----------

    def _rebuild_table(self):
        # Сначала удаляем все ранее созданные реестры нажатий —
        # иначе тег reg_N уже существует и add_item_handler_registry
        # падает с "Alias already exists".
        for tag in self._row_registry_tags:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._row_registry_tags = []

        if dpg.does_item_exist(self.table_tag):
            dpg.delete_item(self.table_tag)

        # Колонки «Измерение» больше нет — кнопка «Пуск» убрана.
        headers = (["№", "Номер резонатора"]
                   + [self._get_column_title(i, max_len=24)
                      for i in range(1, 13)]
                   + ["Статус"])

        with dpg.table(parent=self.table_container, tag=self.table_tag,
                       header_row=True,
                       borders_innerH=True, borders_outerH=True,
                       borders_innerV=True, borders_outerV=True,
                       row_background=True, scrollY=True, height=-1,
                       freeze_rows=1, freeze_columns=2):
            for h_idx, h in enumerate(headers):
                if h_idx == 0:
                    w = 50
                elif h_idx == 1:
                    w = 140
                elif h_idx >= len(headers) - 1:
                    w = 110
                else:
                    w = 170
                dpg.add_table_column(label=h, init_width_or_weight=w)

            for i, row in enumerate(self.rows):
                with dpg.table_row(tag=f"row_{i}"):
                    dpg.add_text(str(i + 1), tag=f"num_{i}")

                    # Номер резонатора — кликабельный текст.
                    dpg.add_text(row['N'], tag=f"n_{i}")

                    reg_tag = f"reg_{i}"
                    with dpg.item_handler_registry(tag=reg_tag) as reg:
                        dpg.add_item_clicked_handler(
                            callback=self.on_measure, user_data=i)
                    dpg.bind_item_handler_registry(f"n_{i}", reg)
                    self._row_registry_tags.append(reg_tag)

                    for pos in range(1, 13):
                        dpg.add_text("-", tag=f"cell_{i}_{pos}")
                    dpg.add_text("", tag=f"status_{i}")

    def _rebuild_table_old1(self):
        if dpg.does_item_exist(self.table_tag):
            dpg.delete_item(self.table_tag)

        # Колонка «Измерение» (кнопка) больше не нужна
        headers = (["№", "Номер резонатора"]
                   + [str(i) for i in range(1, 13)]
                   + ["Статус"])

        with dpg.table(parent=self.table_container, tag=self.table_tag,
                       header_row=True,
                       borders_innerH=True, borders_outerH=True,
                       borders_innerV=True, borders_outerV=True,
                       row_background=True, scrollY=True, height=-1,
                       freeze_rows=1, freeze_columns=2):
            for h_idx, h in enumerate(headers):
                if h_idx == 0:
                    w = 50
                elif h_idx == 1:
                    w = 140
                elif h_idx >= len(headers) - 1:
                    w = 110
                else:
                    w = 170
                dpg.add_table_column(label=h, init_width_or_weight=w)

            for i, row in enumerate(self.rows):
                with dpg.table_row(tag=f"row_{i}"):
                    dpg.add_text(str(i + 1), tag=f"num_{i}")

                    # Номер резонатора — кликабельный текст.
                    # Клик по нему запускает измерение строки.
                    dpg.add_text(row['N'], tag=f"n_{i}")
                    with dpg.item_handler_registry(tag=f"reg_{i}") as reg:
                        dpg.add_item_clicked_handler(
                            callback=self.on_measure, user_data=i)
                    dpg.bind_item_handler_registry(f"n_{i}", reg)

                    for pos in range(1, 13):
                        dpg.add_text("-", tag=f"cell_{i}_{pos}")
                    dpg.add_text("", tag=f"status_{i}")


    def _rebuild_table_1(self):
        if dpg.does_item_exist(self.table_tag):
            dpg.delete_item(self.table_tag)

        headers = (["№", "Номер резонатора"]
                   + [str(i) for i in range(1, 13)]
                   + ["Статус", "Измерение"])

        with dpg.table(parent=self.table_container, tag=self.table_tag,
                       header_row=True,
                       borders_innerH=True, borders_outerH=True,
                       borders_innerV=True, borders_outerV=True,
                       row_background=True, scrollY=True, height=-1,
                       freeze_rows=1, freeze_columns=2):
            for h_idx, h in enumerate(headers):
                if h_idx == 0:
                    w = 50
                elif h_idx == 1:
                    w = 140
                elif h_idx >= len(headers) - 2:
                    w = 110
                else:
                    w = 170
                dpg.add_table_column(label=h, init_width_or_weight=w)

            for i, row in enumerate(self.rows):
                with dpg.table_row(tag=f"row_{i}"):
                    dpg.add_text(str(i + 1), tag=f"num_{i}")
                    dpg.add_text(row['N'], tag=f"n_{i}")
                    for pos in range(1, 13):
                        dpg.add_text("-", tag=f"cell_{i}_{pos}")
                    dpg.add_text("", tag=f"status_{i}")
                    dpg.add_button(label="Пуск", tag=f"btn_{i}",
                                   callback=self.on_measure, user_data=i)



    # ---------- Поток измерения ----------
    def _measure_thread_old(self, idx: int):
        try:
            results = self.engine.measure_all(
                progress_cb=lambda pos, val:
                    self.msg_queue.put(('progress', idx, pos, val))
            )
            self.msg_queue.put(('done', idx, results))
        except Exception as e:
            log.exception("Исключение в потоке измерения")
            self.msg_queue.put(('error', idx, str(e)))

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


    # ---------- Обработка сообщений ----------
    def process_messages(self):
        """Обрабатывает очередь сообщений от потока измерений."""
        while True:
            try:
                msg = self.msg_queue.get_nowait()
            except queue.Empty:
                break

            if msg[0] == 'progress':
                _, idx, pos, val = msg
                # В модель пишем «сырое» значение (базовые единицы) — его
                # потом сохраняем в БД. В ячейку — уже форматированный текст.
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

                # Снимаем зелёную подсветку измерения

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

    # ---------- Ёмкостные позиции ----------
    def _cap_modes_positions(self) -> List[int]:
        """Позиции, где в последовательности измерений присутствует CAP."""
        out: List[int] = []
        for pos in range(1, 13):
            modes = rsm.POSITION_MEASURE_SEQUENCE.get(pos, [])
            if any(str(m).upper() == 'CAP' for m in modes):
                out.append(pos)
        return out

    def _cap_display_col(self) -> Optional[int]:
        """switch_id спецификации, у которой units — фарады.

        Это и есть колонка, где показываются все ёмкости (через '/').
        """
        for s in self.specs:
            base, _, _ = parse_units(s.get('units') or '')
            if base == 'F':
                return s.get('switch_id')
        return None

    def _split_by_mode(self, pos: int, raw: str):
        """Разбирает строку raw на список (mode, value_str).

        Если длина parts не совпадает с длиной sequence — возвращаем
        mode=None для «лишних» значений (не отфильтруются).
        """
        parts = [p.strip() for p in (raw or '').split('/') if p.strip()]
        seq = rsm.POSITION_MEASURE_SEQUENCE.get(pos, [])
        result = []
        for i, p in enumerate(parts):
            m = str(seq[i]).upper() if i < len(seq) else None
            result.append((m, p))
        return result

    def _format_cap_values(self, vals: List[str]) -> str:
        """Форматирует список ёмкостных значений (в фарадах) для колонки-агрегатора."""
        specs = [s for s in self.specs
                 if s.get('switch_id') == self._cap_display_col()]
        if not specs:
            return "/".join(vals)
        spec = specs[0]
        units = (spec.get('units') or '').strip()
        _, _, mult = parse_units(units)
        rv = spec.get('round_Value', spec.get('round_value'))
        try:
            nd = int(rv) if rv is not None else None
        except (TypeError, ValueError):
            nd = None

        out: List[str] = []
        for v_str in vals:
            try:
                v_base = float(v_str)
            except ValueError:
                out.append(v_str)
                continue
            display = v_base / mult if mult else v_base
            formatted = f"{display:.{nd}f}" if nd is not None else f"{display:.6g}"
            if units:
                formatted = f"{formatted} {units}"
            out.append(formatted)
        return "/".join(out)



    def _finish_measure_1(self):
        self.measuring = False
        for i in range(len(self.rows)):
            t = f"btn_{i}"
            if dpg.does_item_exist(t):
                dpg.configure_item(t, enabled=True)

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

    def _finish_measure(self):
        self.measuring = False
        # Кнопок «Пуск» больше нет — блокировать/разблокировать нечего.

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

    def _color_row_red(self, idx: int):
        red = (255, 80, 80)
        tags = [f"num_{idx}", f"n_{idx}", f"status_{idx}"]
        tags += [f"cell_{idx}_{p}" for p in range(1, 13)]
        for t in tags:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, color=red)

    def _color_row_green(self, idx: int):
        """Подсветить строку зелёным во время измерения."""
        green = (100, 255, 100)
        tags = [f"num_{idx}", f"n_{idx}", f"status_{idx}"]
        tags += [f"cell_{idx}_{p}" for p in range(1, 13)]
        for t in tags:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, color=green)

    def _get_checked_parts_for_pos(self, pos, values, cap_col,
                                   cap_positions, all_cap_parts) -> List[float]:
        """Значения (в базовых единицах), которые проверяются для колонки pos.

        Логика совпадает с _evaluate_status:
          * pos == cap_col        → все CAP-значения со всех позиций;
          * pos в cap_positions   → только «неёмкостные» значения этой позиции;
          * прочие                → значения позиции, разделённые '/'.
        """
        if pos == cap_col:
            return list(all_cap_parts)

        out: List[float] = []
        if pos in cap_positions:
            raw = values.get(pos)
            for mode, part in self._split_by_mode(pos, raw or ''):
                if mode == 'CAP':
                    continue
                try:
                    out.append(float(part))
                except ValueError:
                    pass
            return out

        raw = values.get(pos)
        if raw is None:
            return out
        for p in str(raw).split('/'):
            p = p.strip()
            if not p:
                continue
            try:
                out.append(float(p))
            except ValueError:
                pass
        return out

    def _color_failed_cells_yellow(self, idx: int):
        """Красит жёлтым только те ячейки строки, где норма не выполнена."""
        if not self.specs:
            return

        values = self.rows[idx].get('values') or {}
        cap_col = self._cap_display_col()
        cap_positions = self._cap_modes_positions()

        # Все CAP-значения со всех позиций (для колонки-агрегатора)
        all_cap_parts: List[float] = []
        for cp in cap_positions:
            raw = values.get(cp)
            if not raw:
                continue
            for mode, part in self._split_by_mode(cp, raw):
                if mode == 'CAP':
                    try:
                        all_cap_parts.append(float(part))
                    except ValueError:
                        pass

        specs_by_switch: Dict[int, List[Dict]] = {}
        for s in self.specs:
            sw = s.get('switch_id')
            if sw is None:
                continue
            specs_by_switch.setdefault(sw, []).append(s)

        yellow = (255, 220, 100)

        for pos in range(1, 13):
            specs = specs_by_switch.get(pos, [])
            if not specs:
                continue

            parts = self._get_checked_parts_for_pos(
                pos, values, cap_col, cap_positions, all_cap_parts
            )
            if not parts:
                continue

            failed = False
            for v in parts:
                for spec in specs:
                    if not self._check_spec(v, spec):
                        failed = True
                        break
                if failed:
                    break

            if failed:
                tag = f"cell_{idx}_{pos}"
                if dpg.does_item_exist(tag):
                    dpg.configure_item(tag, color=yellow)

    def _reset_row_color(self, idx: int):
        """Возвращает цвет текста всех элементов строки к стандартному."""
        default = (215, 215, 220)   # совпадает с mvThemeCol_Text в теме
        tags = [f"num_{idx}", f"n_{idx}", f"status_{idx}"]
        tags += [f"cell_{idx}_{p}" for p in range(1, 13)]
        for t in tags:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, color=default)

    def _reset_row_display(self, idx: int):
        """Очищает ячейки строки и её статус (визуально)."""
        for pos in range(1, 13):
            tag = f"cell_{idx}_{pos}"
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, "-")
        tag = f"status_{idx}"
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, "")

    # ---------- Разбраковка ----------

    def _evaluate_status(self, values: Dict[int, str]) -> str:
        if not self.specs:
            return "Годен"

        cap_col = self._cap_display_col()
        cap_positions = self._cap_modes_positions()

        # Собираем ёмкостные значения со всех позиций в один список —
        # их проверяем против спек той колонки, где units = F.
        all_cap_parts: List[float] = []
        for cp in cap_positions:
            raw = values.get(cp)
            if not raw:
                continue
            for mode, part in self._split_by_mode(cp, raw):
                if mode == 'CAP':
                    try:
                        all_cap_parts.append(float(part))
                    except ValueError:
                        pass

        specs_by_switch: Dict[int, List[Dict]] = {}
        for s in self.specs:
            sw = s.get('switch_id')
            if sw is None:
                continue
            specs_by_switch.setdefault(sw, []).append(s)

        any_fail = False
        for sw, specs in specs_by_switch.items():
            # Значения для проверки в колонке sw
            if sw == cap_col:
                parts_f = all_cap_parts
            elif sw in cap_positions:
                # В этой колонке в таблицу идёт только «неёмкостная» часть,
                # и разбраковка идёт только по ней
                raw = values.get(sw)
                parts_f = []
                for mode, part in self._split_by_mode(sw, raw or ''):
                    if mode == 'CAP':
                        continue
                    try:
                        parts_f.append(float(part))
                    except ValueError:
                        pass
            else:
                raw = values.get(sw)
                if raw is None:
                    continue
                parts_f = []
                for p in raw.split('/'):
                    p = p.strip()
                    if not p:
                        continue
                    try:
                        parts_f.append(float(p))
                    except ValueError:
                        pass

            for v in parts_f:
                for spec in specs:
                    if not self._check_spec(v, spec):
                        log.info(
                            "Разбраковка: switch_id=%s, value=%s, spec=%s → FAIL",
                            sw, v, spec.get('Par_Name'))
                        any_fail = True

        return "Брак" if any_fail else "Годен"


    def _format_value_for_pos(self, pos: int, raw_str: str) -> str:
        """Форматирует «сырое» значение для колонки pos.

        Правила:
          * Нет спецификации для pos           → вернуть raw_str как есть.
          * Значение ≥ 1e37 (перегрузка DM858,
            обычно 9.9e+37)                     → "OPEN".
          * Хотя бы одна спека с Par_value==0  → Pass/Fail по всем спекам позиции.
          * Сопротивление > 100 МОм            → "> <граница> <units>":
              приоритет Par_max → Par_min → "> 100 MOm".
              Границы, равные -1000000, игнорируются.
          * Иначе                              → перевод из базовой единицы
              в spec['units'] (с учётом приставки), округление до
              spec['round_Value'] знаков, дописать units.
        Многозначные ячейки (значения через '/') обрабатываются поэлементно.
        Разбраковка (_evaluate_status) работает по «сырым» значениям, поэтому
        перегрузка в ней обрабатывается обычным образом.
        """
        specs = [s for s in self.specs if s.get('switch_id') == pos]
        if not specs:
            return raw_str

        use_pass_fail = any(s.get('Par_value') == 0 for s in specs)

        parts = [p for p in raw_str.split('/') if p.strip()]
        if not parts:
            return raw_str

        out: List[str] = []
        for p in parts:
            try:
                v_base = float(p)  # базовая единица (Ом, Ф, В, …)
            except ValueError:
                out.append(p)
                continue

            # --- Перегрузка прибора (DM858 отдаёт ~9.9e+37) ---
            if abs(v_base) >= self._OVERLOAD_THRESHOLD:
                out.append("OPEN")
                continue

            # --- Pass/Fail ---
            if use_pass_fail:
                ok = all(self._check_spec(v_base, s) for s in specs)
                out.append("Pass" if ok else "Fail")
                continue

            spec = specs[0]
            units = (spec.get('units') or '').strip()
            base, _, mult = parse_units(units)

            rv = spec.get('round_Value', spec.get('round_value'))
            try:
                nd = int(rv) if rv is not None else None
            except (TypeError, ValueError):
                nd = None

            # --- Обрыв: сопротивление > 100 МОм (но не перегрузка) ---
            if base == 'Ohm' and v_base > self._OPEN_CIRCUIT_THRESHOLD:
                pmin = spec.get('Par_min')
                pmax = spec.get('Par_max')

                if pmax is not None and pmax != self._NORM_ABSENT:
                    bound, suffix = pmax, units
                elif pmin is not None and pmin != self._NORM_ABSENT:
                    bound, suffix = pmin, units
                else:
                    bound, suffix = None, None

                if bound is not None:
                    bound_disp = (f"{bound:.{nd}f}" if nd is not None
                                  else f"{bound:g}")
                    out.append(f"> {bound_disp} {suffix}".strip())
                else:
                    out.append("> 100 MOm")
                continue

            # --- Обычное значение ---
            display = v_base / mult if mult else v_base
            formatted = (f"{display:.{nd}f}" if nd is not None
                         else f"{display:.6g}")
            if units:
                formatted = f"{formatted} {units}"
            out.append(formatted)

        return "/".join(out)




    def _render_row_values(self, idx: int):
        """Перерисовывает все ячейки строки idx.

        * Позиция-агрегатор ёмкости — все CAP-значения со всех позиций
          через '/'.
        * Прочие позиции, где измерялась ёмкость — только «неёмкостные»
          значения (DIOD, RES, …). Если их нет — '-'.
        * Обычные позиции — 'как есть' через _format_value_for_pos.
        """
        values = self.rows[idx]['values']
        cap_positions = self._cap_modes_positions()
        cap_col = self._cap_display_col()

        # Собираем все ёмкостные значения со всех позиций
        all_cap_vals: List[str] = []
        for cp in cap_positions:
            raw = values.get(cp)
            if not raw:
                continue
            for mode, part in self._split_by_mode(cp, raw):
                if mode == 'CAP':
                    all_cap_vals.append(part)

        for pos in range(1, 13):
            tag = f"cell_{idx}_{pos}"
            if not dpg.does_item_exist(tag):
                continue

            raw = values.get(pos)

            # --- Колонка-агрегатор ёмкости ---
            if cap_col is not None and pos == cap_col:
                dpg.set_value(tag, self._format_cap_values(all_cap_vals)
                if all_cap_vals else "-")
                continue

            # --- Позиция, где измерялась ёмкость, но это не колонка-агрегатор ---
            if pos in cap_positions:
                non_cap = [p for m, p in self._split_by_mode(pos, raw or '')
                           if m != 'CAP']
                if non_cap:
                    dpg.set_value(tag,
                                  self._format_value_for_pos(pos, "/".join(non_cap)))
                else:
                    dpg.set_value(tag, "-")
                continue

            # --- Обычная позиция ---
            if raw is None:
                dpg.set_value(tag, "-")
            else:
                dpg.set_value(tag, self._format_value_for_pos(pos, raw))


    def _capacitance_positions(self) -> List[int]:
        """switch_id всех спецификаций, у которых базовая единица — фарад.

        Возвращает отсортированный список без дубликатов.
        """
        result: List[int] = []
        for s in self.specs:
            units = (s.get('units') or '')
            base, _, _ = parse_units(units)
            if base == 'F':
                sw = s.get('switch_id')
                if sw is not None and sw not in result:
                    result.append(sw)
        return sorted(result)

    def _compute_resistance_ranges(self) -> Dict[int, int]:
        """Пределы измерения сопротивления по спецификациям (нормам).

        Правила:
          * Pass/Fail (Par_value == 0):
              - Par_Bool == 1 (ждём звуковой сигнал / низкое R) → 1 кОм;
              - Par_Bool == 0 (ждём высокое R)                  → предел не задан.
          * Обычная норма (Par_value == 1) и units в Омах:
              - приставка k (kOhm, кОм, ...) → 100 кОм;
              - без приставки  (Ohm, Ом)     → 100 Ом;
              - приставка M (MOhm, МОм)      → 100 МОм;
              - прочие приставки (m, u, n, ...) → 100 * множитель (Ом).

        Возвращает {switch_id: предел_Ом} — только для тех позиций,
        где предел вообще имеет смысл.
        """
        out: Dict[int, int] = {}

        by_switch: Dict[int, List[Dict]] = {}
        for s in self.specs:
            sw = s.get('switch_id')
            if sw is None:
                continue
            by_switch.setdefault(sw, []).append(s)

        for pos, specs in by_switch.items():
            spec = specs[0]
            par_value = spec.get('Par_value')
            par_bool = spec.get('Par_Bool')

            # --- Pass/Fail ---
            if par_value == 0:
                if par_bool == 1:
                    out[pos] = 1_000        # 1 кОм — наличие звука
                # par_bool == 0 → ожидается «обрыв», предел не задаём
                continue

            # --- Обычная норма: смотрим на units ---
            units = (spec.get('units') or '').strip()
            base, prefix, mult = parse_units(units)
            if base != 'Ohm':
                continue

            if not prefix:
                out[pos] = 100                          # 100 Ом
            else:
                # k → 100 кОм, M → 100 МОм, m → 0.1 Ом (аварийно, вряд ли нужно)
                out[pos] = max(1, int(round(100 * mult)))

        log.info("Пределы измерения сопротивления по нормам: %s", out)
        return out

    def _check_spec(self, value: float, spec: Dict) -> bool:
        """value — в базовых единицах (Ом, Ф, …).
        Нормы в spec заданы в spec['units']. Значение -1000000 в Par_min/Par_max
        означает, что норма по этой границе отсутствует.
        """
        par_value = spec.get('Par_value')
        par_bool = spec.get('Par_Bool')
        units = (spec.get('units') or '')
        base, _, mult = parse_units(units)

        def _to_base(x):
            if x is None:
                return None
            if x == self._NORM_ABSENT:
                return None
            return x * mult

        pmin = _to_base(spec.get('Par_min'))
        pmax = _to_base(spec.get('Par_max'))

        # --- Обычный режим: значение сверяется с Par_min / Par_max ---
        if par_value == 1:
            if pmin is not None and value < pmin:
                return False
            if pmax is not None and value > pmax:
                return False
            return True

        # --- Pass/Fail-режим (par_value == 0) ---
        # Par_Bool задаёт ожидаемое поведение по сопротивлению:
        #   1 — ожидается НИЗКОЕ сопротивление (< 1500 Ом), иначе Fail;
        #   0 — ожидается ВЫСОКОЕ сопротивление (> 1500 Ом), иначе Fail.
        # Проверка применяется независимо от того, задан ли units:
        # для позиций 7–11 units = NULL, а величина в базовых единицах (Ом).
        if par_bool == 1:
            return value < 1500
        if par_bool == 0:
            return value > 1500

        # --- Резерв: Par_Bool не задан — работаем по min/max ---
        if pmin is not None and value < pmin:
            return False
        if pmax is not None and value > pmax:
            return False
        return True

    def _check_spec_3(self, value: float, spec: Dict) -> bool:
        """value — в базовых единицах (Ом, Ф, …).
        Нормы в spec заданы в spec['units']. Значение -1000000 в Par_min/Par_max
        означает, что норма по этой границе отсутствует.
        """
        par_value = spec.get('Par_value')
        par_bool = spec.get('Par_Bool')
        units = (spec.get('units') or '')
        base, _, mult = parse_units(units)

        def _to_base(x):
            if x is None:
                return None
            if x == self._NORM_ABSENT:
                return None
            return x * mult

        pmin = _to_base(spec.get('Par_min'))
        pmax = _to_base(spec.get('Par_max'))

        if par_value == 1:
            if pmin is not None and value < pmin:
                return False
            if pmax is not None and value > pmax:
                return False
            return True

        if base == 'Ohm':
            return value < 1500 if par_bool == 1 else value > 1500

        if pmin is not None and value < pmin:
            return False
        if pmax is not None and value > pmax:
            return False
        return True





# ==================== Точка входа ====================
def main():
    """Основная функция приложения."""
    log.info("Запуск приложения")

    dpg.create_context()
    log.info("DearPyGui контекст создан")

    setup_fonts(dpg, FONT_NAME)
    log.info("Шрифты загружены: %s", FONT_NAME)

    monitors = get_monitors()
    primary_monitor = monitors[0]
    log.info("Основной монитор: %dx%d",
             primary_monitor.width, primary_monitor.height)

    dpg.create_viewport(
        title='RT - Montage Control',
        width=primary_monitor.width,
        height=primary_monitor.height,
        x_pos=primary_monitor.x,
        y_pos=primary_monitor.y,
    )

    app = App()
    app._apply_theme()
    app.build()
    log.info("GUI построен")

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window(app.win_tag, True)
    log.info("Окно показано, вход в главный цикл")

    try:
        while dpg.is_dearpygui_running():
            app.process_messages()
            dpg.render_dearpygui_frame()
    finally:
        log.info("Завершение работы приложения")
        try:
            app.engine.disconnect()
        except Exception:
            log.exception("Ошибка при отключении оборудования")
        dpg.destroy_context()
        log.info("Контекст DearPyGui уничтожен")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RT Montage Control — точка входа."""

import logging

import dearpygui.dearpygui as dpg
from screeninfo import get_monitors

from fonts.Font import setup_fonts

from gui.constants import FONT_NAME
from gui.theme import ThemeMixin
from gui.table_view import TableMixin
from gui.measure_flow import MeasureMixin
from gui.spec_editor import SpecEditorMixin
from gui.pdf_export import PdfMixin
from gui.app_core import AppCoreMixin


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


class App(ThemeMixin, TableMixin, MeasureMixin, SpecEditorMixin, PdfMixin, AppCoreMixin):
    """Главное окно приложения."""
    pass


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

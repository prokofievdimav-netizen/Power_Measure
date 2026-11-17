#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Выбор и загрузка конкретного замера (сессии) для одной МСК.

Подключается из main_gui: после «Найти» вызывается offer_and_load(app).
Каждый вызов db.save_measurements создаёт новый run_id (см. db_helper).
"""

from __future__ import annotations

import logging
from typing import List, Dict, Optional, Any

import dearpygui.dearpygui as dpg

import db_helper as db

log = logging.getLogger("app")


def init_run_state(app) -> None:
    """Добавить поля состояния замера на экземпляр App (идемпотентно)."""
    if not hasattr(app, "current_run_id"):
        app.current_run_id = None
    if not hasattr(app, "current_run_legacy"):
        app.current_run_legacy = False
    if not hasattr(app, "_pending_runs"):
        app._pending_runs = []


def try_load_saved(app, run_id=None, legacy_only: bool = False) -> int:
    """Загрузить измерения выбранного замера в таблицу app.rows."""
    if not app.msk_real:
        return 0

    try:
        saved = db.load_measurements(
            app.msk_real, app.nom_id,
            run_id=run_id, legacy_only=legacy_only,
        )
    except Exception as e:
        log.exception("Ошибка загрузки сохранённых измерений")
        app.set_status(f"Ошибка загрузки сохранённых данных: {e}",
                       (255, 100, 100))
        return 0

    if not saved:
        log.info("Сохранённых измерений для МСК_Реал=%s нет", app.msk_real)
        return 0

    by_n: Dict[str, Dict] = {}
    for r in saved:
        n = r.get("N")
        if n:
            by_n[n] = r

    loaded = 0
    for i, row in enumerate(app.rows):
        s = by_n.get(row["N"])
        if not s or not s.get("values"):
            continue

        row["values"] = dict(s["values"])
        status = app._evaluate_status(row["values"])
        row["status"] = status

        app._render_row_values(i)

        tag = f"status_{i}"
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, status)

        if status == "Брак":
            app._color_row_red(i)
            app._color_failed_cells_yellow(i)

        app.measured_indices.add(i)
        loaded += 1

    log.info("Сопоставлено сохранённых строк: %d из %d", loaded, len(saved))
    return loaded


def offer_and_load(app) -> int:
    """После «Найти»: список замеров → автозагрузка одного или диалог выбора.

    Возвращает число загруженных строк (0, если диалог ещё открыт или
    пользователь выбрал новое измерение).
    """
    init_run_state(app)
    if not app.msk_real:
        return 0

    try:
        runs = db.list_measurement_runs(app.msk_real, app.nom_id)
    except Exception as e:
        log.exception("Ошибка списка замеров")
        return try_load_saved(app)

    app._pending_runs = runs or []

    if not runs:
        return 0

    if len(runs) == 1:
        r = runs[0]
        app.current_run_id = r.get("run_id")
        app.current_run_legacy = r.get("run_id") is None
        return try_load_saved(
            app,
            run_id=r.get("run_id"),
            legacy_only=(r.get("run_id") is None),
        )

    _show_run_picker(app, runs)
    return 0


def _show_run_picker(app, runs: List[Dict]) -> None:
    tag = "run_picker_window"
    if dpg.does_item_exist(tag):
        dpg.delete_item(tag)

    labels = ["— Новое измерение (не загружать) —"] + [
        r.get("label", str(r.get("run_id"))) for r in runs
    ]

    with dpg.window(
        tag=tag,
        label="Выбор замера",
        modal=True,
        show=True,
        width=640,
        height=220,
        pos=(200, 200),
        no_collapse=True,
    ):
        dpg.add_text(
            f"Для МСК {app.msk_real} найдено несколько сохранённых замеров.\n"
            "Выберите, какой загрузить, или начните новое измерение."
        )
        dpg.add_spacer(height=8)
        dpg.add_combo(
            labels, tag="run_picker_combo", width=600, default_value=labels[0]
        )
        dpg.add_spacer(height=12)
        with dpg.group(horizontal=True):
            dpg.add_button(
                label="  Загрузить  ",
                callback=lambda: _on_run_picker_ok(app),
            )
            dpg.add_spacer(width=20)
            dpg.add_button(
                label="  Отмена / новое  ",
                callback=lambda: _on_run_picker_cancel(app),
            )


def _on_run_picker_ok(app) -> None:
    tag = "run_picker_window"
    combo_val = (
        dpg.get_value("run_picker_combo")
        if dpg.does_item_exist("run_picker_combo")
        else None
    )
    if dpg.does_item_exist(tag):
        dpg.delete_item(tag)

    if not combo_val or str(combo_val).startswith("—"):
        app.current_run_id = None
        app.current_run_legacy = False
        app.set_status(
            "Новое измерение — сохранённые данные не загружены",
            (180, 200, 255),
        )
        return

    chosen = None
    for r in getattr(app, "_pending_runs", []):
        if r.get("label") == combo_val:
            chosen = r
            break
    if not chosen:
        app.set_status("Не удалось определить выбранный замер", (255, 150, 100))
        return

    app.current_run_id = chosen.get("run_id")
    app.current_run_legacy = chosen.get("run_id") is None
    loaded = try_load_saved(
        app,
        run_id=chosen.get("run_id"),
        legacy_only=(chosen.get("run_id") is None),
    )
    if loaded:
        app.set_status(
            f"Загружен замер: {chosen.get('label')} — {loaded} записей",
            (100, 200, 255),
        )
    else:
        app.set_status(
            "Замер выбран, но данных для текущих номеров нет",
            (255, 180, 100),
        )
    if hasattr(app, "_update_info_text"):
        app._update_info_text()


def _on_run_picker_cancel(app) -> None:
    tag = "run_picker_window"
    if dpg.does_item_exist(tag):
        dpg.delete_item(tag)
    app.current_run_id = None
    app.current_run_legacy = False
    app.set_status(
        "Новое измерение — сохранённые данные не загружены",
        (180, 200, 255),
    )


def handle_save_result(app, result) -> None:
    """Обработать результат db.save_measurements (dict или int)."""
    if isinstance(result, dict):
        n = result.get("saved", 0)
        run_id = result.get("run_id")
        msg = result.get("message") or f"Сохранено {n}"
        if run_id is not None:
            app.current_run_id = run_id
            app.current_run_legacy = False
        app.set_status(f"{msg} в xsr_rt_montag", (100, 255, 100))
    else:
        app.set_status(f"Сохранено {result} записей в xsr_rt_montag",
                       (100, 255, 100))

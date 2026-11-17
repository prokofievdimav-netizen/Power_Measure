# Структура GUI (ветка feature/multiple-measurements)

```
main_gui.py              — тонкая точка входа: App + main()
run_picker.py            — выбор конкретного замера при загрузке МСК
db_helper.py             — MySQL, несколько замеров (xsr_rt_montag_runs)

gui/
  __init__.py
  constants.py           — regex, SI-приставки, parse_units, generate_range
  theme.py               — ThemeMixin (_apply_theme)
  table_view.py          — TableMixin = render_a/b + check_a/b
  table_render_a.py      — rebuild таблицы, цвета строк
  table_render_b.py      — format значений, CAP helpers
  table_check_a.py       — evaluate_status, check_spec
  table_check_b.py       — yellow cells, resistance ranges
  measure_flow.py        — MeasureMixin (поток измерения, очередь)
  app_core.py            — AppCoreMixin = A + B
  app_core_a.py          — build, connect, NK selector, state
  app_core_b.py          — on_find, on_save, resolve numbers
  spec_editor.py         — SpecEditorMixin (просмотр спецификаций)
  pdf_export.py          — PdfMixin (экспорт PDF-протокола)
```

Запуск: `python main_gui.py`

Несколько замеров на одну МСК:
- Save всегда создаёт новый `run_id` в `xsr_rt_montag_runs`
- После «Найти» — диалог выбора замера (или автозагрузка, если один)
- Старые записи без run_id читаются как legacy

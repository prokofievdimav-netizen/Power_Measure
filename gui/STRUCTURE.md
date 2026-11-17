# Структура GUI

```
main_gui.py          — App (сборка окна, Найти/Сохранить/Подключить) + main()
run_picker.py        — выбор конкретного замера при загрузке МСК
gui/
  __init__.py
  constants.py       — regex, SI-приставки, parse_units, generate_range
  theme.py           — ThemeMixin (_apply_theme)
  table_view.py      — TableMixin (таблица, статусы, цвета, нормы)
  measure_flow.py    — MeasureMixin (поток измерения, очередь сообщений)
  spec_editor.py     — SpecEditorMixin (редактор спецификаций)
  pdf_export.py      — PdfMixin (экспорт PDF-протокола)
db_helper.py         — MySQL, несколько замеров (xsr_rt_montag_runs)
```

Запуск: `python main_gui.py` (как раньше).

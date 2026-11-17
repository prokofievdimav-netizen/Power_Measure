# Применение поддержки нескольких замеров

Ветка: `feature/multiple-measurements`

## Уже в репозитории

1. **db_helper.py** — таблица `xsr_rt_montag_runs`, колонка `run_id` в `xsr_rt_montag`,
   функции `ensure_measurement_schema`, `list_measurement_runs`, обновлённые
   `load_measurements` / `save_measurements`.
2. **run_picker.py** — UI выбора замера при загрузке МСК.

## Нужно применить к main_gui.py

```bash
# из корня репозитория на ветке feature/multiple-measurements:
git checkout main -- main_gui.py   # если файл испорчен placeholder
patch -p1 < main_gui_multiple_runs.patch
```

Или вручную (см. `main_gui_multiple_runs.patch`):
- `import run_picker`
- поля `current_run_id` / `current_run_legacy`
- вместо `_try_load_saved()` → `run_picker.offer_and_load(self)`
- в `on_save` — `run_picker.handle_save_result(...)`

## Поведение

- Каждый «Сохранить» создаёт **новый** замер (сессию) с новым `run_id`.
- Старые записи без `run_id` доступны как «Старые данные».
- При «Найти» по МСК, если замеров несколько — диалог выбора;
  если один — загружается сразу; можно выбрать «Новое измерение».

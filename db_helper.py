#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Работа с MySQL для приложения контроля плат КР.

Драйвер — PyMySQL (чистый Python, без бинарных DLL), что даёт
беспроблемную сборку PyInstaller --onefile.
"""

import logging
import time
from typing import Optional, List, Dict

import pymysql
import pymysql.cursors

# ------------------------------------------------------------------
# Логгер
# ------------------------------------------------------------------
log = logging.getLogger("db")


def _setup_console_logging():
    """Один раз настраивает вывод логов в консоль."""
    if log.handlers:
        return
    log.setLevel(logging.DEBUG)
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter(
        "[%(asctime)s] [DB] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    ))
    log.addHandler(h)
    log.propagate = False


_setup_console_logging()


# ------------------------------------------------------------------
# Конфигурация
# ------------------------------------------------------------------
DB_CONFIG = {
    'host':     'MES1',
    'user':     'xampp',
    'password': '43FPa!29S8HQeAW',
    'database': 'coordinator',
    'charset':  'cp1251',
}

SPEC_TABLE = 'spc_xsr_rt_montag'
NOM_MAPPER_TABLE = None

# Таблица спецификаций монтажа (ищется по NOM_ID).
SPC_MONTAGE_TABLE = 'spc_xsr_rt_montag'


# ------------------------------------------------------------------
# Соединение с логированием
# ------------------------------------------------------------------
def _conn():
    log.debug("Открытие соединения с MySQL: host=%s, user=%s, db=%s",
              DB_CONFIG['host'], DB_CONFIG['user'], DB_CONFIG['database'])
    t0 = time.perf_counter()
    try:
        c = pymysql.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            charset=DB_CONFIG['charset'],
            use_unicode=True,
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
    except Exception as e:
        log.error("Ошибка подключения к MySQL: %r", e)
        import traceback
        log.error("Traceback:\n%s", traceback.format_exc())
        raise
    dt = (time.perf_counter() - t0) * 1000
    log.info("Подключение к MySQL установлено (%.1f ms)", dt)
    return c


def _execute(sql: str, params: tuple = (), fetch: str = "none"):
    """
    Универсальный исполнитель с логированием.
    fetch: 'none' | 'one' | 'all'
    """
    log.debug("SQL: %s | params=%s", " ".join(sql.split()), params)
    t0 = time.perf_counter()
    conn = _conn()
    try:
        cur = conn.cursor()          # DictCursor задан в _conn()
        cur.execute(sql, params)

        # --- Предупреждения сервера (если есть). Формат у PyMySQL
        #     зависит от версии: может быть dict, tuple или Warning-объект,
        #     поэтому обрабатываем универсально.
        try:
            warnings = cur.fetchwarnings() or []
        except Exception:
            warnings = []
        for w in warnings:
            if isinstance(w, dict):
                log.warning("MySQL warning: %s", w)
            elif isinstance(w, (tuple, list)):
                log.warning("MySQL warning: %s", tuple(w))
            else:
                log.warning("MySQL warning: %s", w)

        if fetch == "one":
            r = cur.fetchone()
        elif fetch == "all":
            r = cur.fetchall()
        else:
            r = None

        cur.close()
        conn.commit()

        dt = (time.perf_counter() - t0) * 1000
        if fetch == "one":
            log.info("Запрос выполнен за %.1f ms, получена 1 строка: %s", dt, r)
        elif fetch == "all":
            n = len(r) if r is not None else 0
            log.info("Запрос выполнен за %.1f ms, получено строк: %d", dt, n)
        else:
            log.info("Запрос выполнен за %.1f ms", dt)
        return r

    except pymysql.MySQLError as e:
        # PyMySQL: e.args = (errno, errmsg)
        errno = e.args[0] if e.args else None
        msg = e.args[1] if len(e.args) > 1 else str(e)
        log.error("MySQL error: errno=%s msg=%r", errno, msg)
        log.debug("MySQL error raw: %r", e)
        raise
    except Exception as e:
        log.exception("Неизвестная ошибка выполнения SQL: %s", e)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ------------------------------------------------------------------
# Функции запросов
# ------------------------------------------------------------------
def find_msk_real(barcode: str) -> Optional[str]:
    """По штрих-коду (число МСК) получить мскРеал из msk_rk."""
    log.info("Поиск мскРеал по штрих-коду: %s", barcode)

    try:
        barcode_int = int(barcode)
    except (TypeError, ValueError):
        log.warning("Штрих-код %r не является целым числом", barcode)
        return None

    r = _execute(
        "SELECT `мскРеал` AS m FROM `msk_rk` WHERE `мск` = %s",
        (barcode_int,), fetch="one"
    )
    if r:
        log.info("Найдено: мскРеал=%s", r['m'])
        return r['m']
    log.warning("Штрих-код %s не найден в msk_rk", barcode)
    return None


def get_kod_nom(msk_real: str) -> Optional[str]:
    """Из msk_rk по мскРеал получить КодНоменклатуры."""
    log.info("Поиск КодНоменклатуры по мскРеал=%s", msk_real)
    r = _execute(
        "SELECT `КодНоменклатуры` AS k FROM `msk_rk` WHERE `мскРеал` = %s",
        (msk_real,), fetch="one"
    )
    if r:
        log.info("Найдено: КодНоменклатуры=%s", r['k'])
        return r['k']
    log.warning("мскРеал=%s не найден в msk_rk", msk_real)
    return None


def get_nom_id(kod) -> Optional[int]:
    """По КодНоменклатуры получить NOM_ID.

    Если маппер NOM_MAPPER_TABLE не задан или недоступен — используется
    NOM_ID = КодНоменклатуры. Отсутствие маппера — не ошибка.
    """
    try:
        kod_int = int(kod)
    except (TypeError, ValueError):
        log.warning("КодНоменклатуры=%r не является числом", kod)
        return None

    if not NOM_MAPPER_TABLE:
        log.info("NOM_ID = КодНоменклатуры = %s (маппер не задан)", kod_int)
        return kod_int

    log.info("Поиск NOM_ID по КодНоменклатуры=%s в %s",
             kod, NOM_MAPPER_TABLE)
    try:
        r = _execute(
            f"SELECT `NOM_ID` AS n FROM `{NOM_MAPPER_TABLE}` "
            f"WHERE `КодНоменклатуры` = %s",
            (kod,), fetch="one"
        )
    except Exception as e:
        log.warning(
            "Не удалось прочитать %s (%s). "
            "Использую NOM_ID = КодНоменклатуры = %s",
            NOM_MAPPER_TABLE, e, kod_int
        )
        return kod_int

    if r and r.get('n') is not None:
        log.info("Найдено: NOM_ID=%s", r['n'])
        return r['n']

    log.warning(
        "КодНоменклатуры=%s не найден в %s. "
        "Использую NOM_ID = КодНоменклатуры = %s",
        kod, NOM_MAPPER_TABLE, kod_int
    )
    return kod_int


def find_marker(msk: str):
    """По MSK получить Begin/End из таблицы marker."""
    log.info("Поиск диапазона в marker по MSK=%s", msk)
    r = _execute(
        "SELECT `Begin` AS b, `End` AS e FROM `marker` WHERE `MSK` = %s",
        (msk,), fetch="one"
    )
    if r:
        log.info("Диапазон: %s .. %s", r['b'], r['e'])
        return (r['b'], r['e'])
    log.warning("MSK=%s не найден в marker", msk)
    return None


def get_specs(nom_id: int) -> List[Dict]:
    log.info("Загрузка спецификаций для NOM_ID=%s из %s",
             nom_id, SPC_MONTAGE_TABLE)
    try:
        rows = _execute(
            f"SELECT * FROM `{SPC_MONTAGE_TABLE}` WHERE `NOM_ID` = %s",
            (nom_id,), fetch="all"
        ) or []
    except Exception as e:
        log.warning("Не удалось загрузить спецификации для NOM_ID=%s: %s",
                    nom_id, e)
        return []

    if not rows:
        log.warning(
            "Спецификации для NOM_ID=%s отсутствуют в %s — "
            "разбраковка выполняться не будет",
            nom_id, SPC_MONTAGE_TABLE
        )
        return []

    log.info("Загружено спецификаций: %d", len(rows))
    for s in rows:
        log.debug("  spec: switch_id=%s, Par_Name=%s, Par_value=%s, "
                  "Par_Bool=%s, min=%s, max=%s, units=%s",
                  s.get('switch_id'), s.get('Par_Name'), s.get('Par_value'),
                  s.get('Par_Bool'), s.get('Par_min'), s.get('Par_max'),
                  s.get('units'))
    return rows


def get_column_names(nom_id: Optional[int]) -> Dict[int, str]:
    """Возвращает {switch_id: Par_Name} из spc_xsr_rt_montag для NOM_ID.

    Используется GUI для заголовков колонок таблицы и PDF-протокола.
    Пустой dict, если для NOM_ID ничего нет или запрос упал.
    """
    if nom_id is None:
        return {}

    log.info("Загрузка названий колонок для NOM_ID=%s из %s",
             nom_id, SPC_MONTAGE_TABLE)
    try:
        rows = _execute(
            f"SELECT `switch_id`, `Par_Name` FROM `{SPC_MONTAGE_TABLE}` "
            f"WHERE `NOM_ID` = %s ORDER BY `switch_id`",
            (nom_id,), fetch="all"
        ) or []
    except Exception as e:
        log.warning("Не удалось загрузить названия колонок для NOM_ID=%s: %s",
                    nom_id, e)
        return {}

    out: Dict[int, str] = {}
    for r in rows:
        sw = r.get('switch_id')
        name = (r.get('Par_Name') or '').strip()
        if sw is None or not name:
            continue
        try:
            out[int(sw)] = name
        except (TypeError, ValueError):
            continue

    log.info("Загружено названий колонок: %d", len(out))
    for sw in sorted(out):
        log.debug("  switch_id=%s -> %s", sw, out[sw])
    return out


# ------------------------------------------------------------------
# Редактор спецификаций
# ------------------------------------------------------------------
def get_resonator_types() -> List[Dict]:
    """Все типы РК из resonatortype_rq (для выбора в редакторе)."""
    log.info("Загрузка типов РК из resonatortype_rq")
    rows = _execute(
        "SELECT `ID`, `Name`, `TU`, `Есть_РК` FROM `resonatortype_rq` "
        "ORDER BY `Name`",
        fetch="all"
    ) or []
    log.info("Загружено типов РК: %d", len(rows))
    return rows


def get_nomeklatura_by_rk(rk_id: int) -> List[Dict]:
    """Номенклатуры из nomeklatura_rk, у которых РКНомер = rk_id."""
    log.info("Загрузка номенклатур по РКНомер=%s", rk_id)
    rows = _execute(
        "SELECT `номенклатура`, `наименование`, `частота`, `РКНомер`, "
        "`КодНоменклатуры1С`, `ТипКорпуса` "
        "FROM `nomeklatura_rk` WHERE `РКНомер` = %s "
        "ORDER BY `частота`",
        (rk_id,), fetch="all"
    ) or []
    log.info("Загружено номенклатур: %d", len(rows))
    return rows


def get_specs_by_nom_id(nom_id: int) -> List[Dict]:
    """Спецификации из spc_xsr_rt_montag для указанного NOM_ID."""
    log.info("Загрузка спецификаций для NOM_ID=%s", nom_id)
    rows = _execute(
        f"SELECT * FROM `{SPC_MONTAGE_TABLE}` WHERE `NOM_ID` = %s "
        f"ORDER BY `switch_id`, `ID`",
        (nom_id,), fetch="all"
    ) or []
    log.info("Загружено спецификаций: %d", len(rows))
    return rows


def _spec_columns() -> List[str]:
    """Список полей таблицы spc_xsr_rt_montag, которые мы редактируем."""
    return ['NOM_ID', 'Spc_Name', 'Par_ID', 'Par_Name',
            'Par_min', 'Par_max', 'Par_value', 'Par_Bool',
            'units', 'switch_id', 'round_Value']


def insert_spec(spec: Dict) -> int:
    """Добавить спецификацию. Возвращает ID новой записи."""
    cols = _spec_columns()
    values = tuple(spec.get(c) for c in cols)
    col_names = ', '.join(f'`{c}`' for c in cols)
    placeholders = ', '.join(['%s'] * len(cols))
    sql = (f"INSERT INTO `{SPC_MONTAGE_TABLE}` ({col_names}) "
           f"VALUES ({placeholders})")

    log.info("INSERT spec: NOM_ID=%s, switch_id=%s, Par_Name=%s",
             spec.get('NOM_ID'), spec.get('switch_id'), spec.get('Par_Name'))
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, values)
        new_id = cur.lastrowid
        conn.commit()
        cur.close()
        log.info("Спецификация добавлена, ID=%s", new_id)
        return new_id
    except Exception as e:
        log.error("Ошибка INSERT spec: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def update_spec(spec_id: int, spec: Dict) -> None:
    """Обновить спецификацию по ID."""
    cols = _spec_columns()
    set_clause = ', '.join(f'`{c}` = %s' for c in cols)
    values = tuple(spec.get(c) for c in cols) + (spec_id,)
    sql = f"UPDATE `{SPC_MONTAGE_TABLE}` SET {set_clause} WHERE `ID` = %s"

    log.info("UPDATE spec ID=%s, NOM_ID=%s, switch_id=%s",
             spec_id, spec.get('NOM_ID'), spec.get('switch_id'))
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, values)
        conn.commit()
        cur.close()
        log.info("Спецификация ID=%s обновлена", spec_id)
    except Exception as e:
        log.error("Ошибка UPDATE spec: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def delete_spec(spec_id: int) -> None:
    """Удалить спецификацию по ID."""
    log.info("DELETE spec ID=%s", spec_id)
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"DELETE FROM `{SPC_MONTAGE_TABLE}` WHERE `ID` = %s",
            (spec_id,)
        )
        conn.commit()
        cur.close()
        log.info("Спецификация ID=%s удалена", spec_id)
    except Exception as e:
        log.error("Ошибка DELETE spec: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_parameters() -> List[Dict]:
    """Список параметров из spc_xsr_rt_parameters.

    Возвращает список словарей {'Par_ID': <ID>, 'Par_Name': <имя>}.
    Если таблицы нет или она пуста — вернёт [] (без исключения).
    """
    log.info("Загрузка параметров из spc_xsr_rt_parameters")
    try:
        rows = _execute(
            "SELECT `ID` AS `Par_ID`, `Par_Name` "
            "FROM `spc_xsr_rt_parameters` ORDER BY `Par_Name`",
            fetch="all"
        ) or []
    except Exception as e:
        log.error("Не удалось прочитать spc_xsr_rt_parameters: %s", e)
        return []

    clean: List[Dict] = []
    for r in rows:
        name = (r.get('Par_Name') or '').strip()
        if not name:
            continue
        clean.append({'Par_ID': r.get('Par_ID'), 'Par_Name': name})

    log.info("Загружено параметров: %d", len(clean))
    for p in clean:
        log.debug("  param: Par_ID=%s, Par_Name=%s",
                  p.get('Par_ID'), p.get('Par_Name'))
    return clean


# ------------------------------------------------------------------
# Схема: несколько замеров на одну МСК / номер
# ------------------------------------------------------------------
# Таблица сессий (замеров):
#   xsr_rt_montag_runs(id, msk, spc, created_at, note, row_count)
# В xsr_rt_montag добавляется колонка run_id (NULL = старые данные).
# Старые записи без run_id остаются доступными как «legacy»-замер.

RUNS_TABLE = 'xsr_rt_montag_runs'
MEAS_TABLE = 'xsr_rt_montag'

_schema_ready = False


def ensure_measurement_schema() -> bool:
    """Создать таблицу сессий и колонку run_id при необходимости.

    Возвращает True, если схема готова к записи с run_id.
    При ошибках ALTER/CREATE логирует предупреждение и возвращает False —
    тогда save_measurements пишет в старом формате (без run_id).
    """
    global _schema_ready
    if _schema_ready:
        return True

    ok = True
    conn = _conn()
    try:
        cur = conn.cursor()

        # 1) Таблица сессий (замеров)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS `{RUNS_TABLE}` (
                `id` INT NOT NULL AUTO_INCREMENT,
                `msk` VARCHAR(64) NOT NULL,
                `spc` INT NULL,
                `created_at` DATETIME NOT NULL,
                `note` VARCHAR(255) NULL,
                `row_count` INT NOT NULL DEFAULT 0,
                PRIMARY KEY (`id`),
                KEY `idx_msk_spc` (`msk`, `spc`),
                KEY `idx_created` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=cp1251
        """)
        log.info("Таблица %s проверена/создана", RUNS_TABLE)

        # 2) Колонка run_id в таблице измерений
        cur.execute(f"SHOW COLUMNS FROM `{MEAS_TABLE}` LIKE 'run_id'")
        if not cur.fetchone():
            try:
                cur.execute(
                    f"ALTER TABLE `{MEAS_TABLE}` "
                    f"ADD COLUMN `run_id` INT NULL DEFAULT NULL, "
                    f"ADD KEY `idx_run_id` (`run_id`)"
                )
                log.info("Колонка run_id добавлена в %s", MEAS_TABLE)
            except Exception as e:
                log.warning("Не удалось добавить run_id в %s: %s", MEAS_TABLE, e)
                ok = False
        else:
            log.debug("Колонка run_id уже есть в %s", MEAS_TABLE)

        conn.commit()
        cur.close()
    except Exception as e:
        log.error("ensure_measurement_schema: %s", e)
        ok = False
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    _schema_ready = ok
    return ok


def list_measurement_runs(msk_real: str,
                          nom_id: Optional[int] = None) -> List[Dict]:
    """Список доступных замеров (сессий) для МСК.

    Каждый элемент:
      {
        'run_id': int | None,   # None = legacy (старые данные без run_id)
        'created_at': str | None,
        'note': str,
        'row_count': int,
        'spc': int | None,
        'label': str,           # для отображения в UI
      }

    Сначала сессии из xsr_rt_montag_runs (новые), затем при наличии
    записей с run_id IS NULL — один синтетический «Старые данные».
    """
    if not msk_real:
        return []

    ensure_measurement_schema()
    result: List[Dict] = []

    # --- Новые сессии из runs ---
    sql = (f"SELECT `id`, `msk`, `spc`, `created_at`, `note`, `row_count` "
           f"FROM `{RUNS_TABLE}` WHERE `msk` = %s")
    params: list = [msk_real]
    if nom_id is not None:
        sql += " AND (`spc` = %s OR `spc` IS NULL)"
        params.append(nom_id)
    sql += " ORDER BY `created_at` DESC, `id` DESC"

    try:
        runs = _execute(sql, tuple(params), fetch="all") or []
    except Exception as e:
        log.warning("list_measurement_runs: не удалось прочитать %s: %s",
                    RUNS_TABLE, e)
        runs = []

    for r in runs:
        created = r.get('created_at')
        created_s = str(created) if created is not None else '?'
        note = (r.get('note') or '').strip()
        rc = int(r.get('row_count') or 0)
        rid = r.get('id')
        label = f"#{rid}  {created_s}  ({rc} шт.)"
        if note:
            label += f"  — {note}"
        result.append({
            'run_id': rid,
            'created_at': created_s,
            'note': note,
            'row_count': rc,
            'spc': r.get('spc'),
            'label': label,
        })

    # --- Legacy: записи без run_id ---
    try:
        sw_check = _execute(
            f"SELECT COUNT(*) AS c FROM `{MEAS_TABLE}` "
            f"WHERE `MSK` = %s AND (`run_id` IS NULL)",
            (msk_real,), fetch="one"
        )
        legacy_cnt = int((sw_check or {}).get('c') or 0)
    except Exception:
        # Колонки run_id ещё нет — все записи legacy
        try:
            sw_check = _execute(
                f"SELECT COUNT(*) AS c FROM `{MEAS_TABLE}` WHERE `MSK` = %s",
                (msk_real,), fetch="one"
            )
            legacy_cnt = int((sw_check or {}).get('c') or 0)
        except Exception as e:
            log.warning("list_measurement_runs legacy count: %s", e)
            legacy_cnt = 0

    if legacy_cnt > 0:
        result.append({
            'run_id': None,
            'created_at': None,
            'note': 'Старые данные (до поддержки нескольких замеров)',
            'row_count': legacy_cnt,
            'spc': nom_id,
            'label': f"Старые данные  ({legacy_cnt} шт.)",
        })

    log.info("list_measurement_runs МСК=%s: %d сессий", msk_real, len(result))
    return result


def load_measurements(msk_real: str,
                      nom_id: Optional[int] = None,
                      run_id: Optional[int] = None,
                      legacy_only: bool = False) -> List[Dict]:
    """Загрузить сохранённые измерения из xsr_rt_montag.

    Параметры:
      run_id      — конкретная сессия (новый формат).
      legacy_only — только записи без run_id (старые данные).
      Если оба False/None — поведение как раньше: все записи по МСК
      (для обратной совместимости; в UI лучше выбирать сессию явно).

    Возвращает список:
        {'N': 'AB0001', 'values': {1: '1.234', 2: '5.678/0.01', ...},
         'run_id': ...}
    """
    if not msk_real:
        return []

    log.info("Загрузка измерений: МСК=%s, NOM_ID=%s, run_id=%s, legacy=%s",
             msk_real, nom_id, run_id, legacy_only)

    sw_cols = ', '.join(f'`SW_{i}`' for i in range(1, 13))
    sql = (f"SELECT `ID`, `N`, `Spc`, {sw_cols} "
           f"FROM `{MEAS_TABLE}` WHERE `MSK` = %s")
    params: list = [msk_real]

    if nom_id is not None:
        sql += " AND `Spc` = %s"
        params.append(nom_id)

    try:
        ensure_measurement_schema()
    except Exception:
        pass

    if run_id is not None:
        sql += " AND `run_id` = %s"
        params.append(run_id)
    elif legacy_only:
        sql += " AND (`run_id` IS NULL)"

    sql += " ORDER BY `ID`"

    try:
        rows = _execute(sql, tuple(params), fetch="all") or []
    except Exception as e:
        # Возможно, колонки run_id нет — повторяем без фильтра
        if run_id is not None or legacy_only:
            log.warning("load_measurements с run_id не удался (%s), "
                        "пробуем без фильтра run_id", e)
            sql2 = (f"SELECT `ID`, `N`, `Spc`, {sw_cols} "
                    f"FROM `{MEAS_TABLE}` WHERE `MSK` = %s")
            params2: list = [msk_real]
            if nom_id is not None:
                sql2 += " AND `Spc` = %s"
                params2.append(nom_id)
            sql2 += " ORDER BY `ID`"
            try:
                rows = _execute(sql2, tuple(params2), fetch="all") or []
            except Exception as e2:
                log.warning("Не удалось загрузить измерения: %s", e2)
                return []
        else:
            log.warning("Не удалось загрузить сохранённые измерения: %s", e)
            return []

    result: List[Dict] = []
    for r in rows:
        values: Dict[int, str] = {}
        for i in range(1, 13):
            v = r.get(f'SW_{i}')
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                continue
            values[i] = s
        result.append({
            'N': str(r.get('N') or '').strip(),
            'values': values,
            'run_id': r.get('run_id') if isinstance(r, dict) and 'run_id' in r else None,
            'id': r.get('ID'),
        })

    log.info("Загружено сохранённых записей: %d", len(result))
    return result


def get_all_nomeklatura() -> List[Dict]:
    """Полный список номенклатур РК (для выбора произвольной спецификации).

    Возвращает словари с полями:
        номенклатура, наименование, частота, РКНомер.
    """
    log.info("Загрузка полного списка номенклатур РК")
    rows = _execute(
        "SELECT DISTINCT n.* FROM nomeklatura_rk n INNER JOIN spc_xsr_rt_montag s ON s.NOM_ID = n.номенклатура",
        fetch="all"
    ) or []
    log.info("Загружено номенклатур: %d", len(rows))
    return rows


def save_measurements(msk_real: str, nom_id: Optional[int],
                      rows: List[Dict],
                      note: str = '') -> Dict:
    """Сохранить измерения как новый замер (сессию).

    rows — список словарей:
      {'N': 'AB0001', 'values': {1: '...', ..., 12: '...'}}

    Возвращает dict:
      {'saved': int, 'run_id': int | None, 'message': str}
    """
    if not rows:
        log.warning("save_measurements: пустой список, нечего сохранять")
        return {'saved': 0, 'run_id': None, 'message': 'нечего сохранять'}

    log.info("Сохранение измерений: МСК_Реал=%s, NOM_ID=%s, строк=%d",
             msk_real, nom_id, len(rows))

    schema_ok = ensure_measurement_schema()
    run_id = None
    t0 = time.perf_counter()
    conn = _conn()
    n = 0
    try:
        cur = conn.cursor()

        if schema_ok:
            # Создаём сессию
            cur.execute(
                f"INSERT INTO `{RUNS_TABLE}` "
                f"(`msk`, `spc`, `created_at`, `note`, `row_count`) "
                f"VALUES (%s, %s, NOW(), %s, %s)",
                (msk_real, nom_id, (note or '')[:255], len(rows))
            )
            run_id = cur.lastrowid
            log.info("Создана сессия run_id=%s", run_id)

            cols = (['MSK', 'MSK_Code', 'N']
                    + [f'SW_{i}' for i in range(1, 13)]
                    + ['Spc', 'run_id'])
            col_names = ', '.join(f'`{c}`' for c in cols)
            placeholders = ', '.join(['%s'] * len(cols))
            sql = (f"INSERT INTO `{MEAS_TABLE}` ({col_names}) "
                   f"VALUES ({placeholders})")

            for row in rows:
                vals = [msk_real, None, row['N']]
                for i in range(1, 13):
                    vals.append(row['values'].get(i))
                vals.append(nom_id)
                vals.append(run_id)
                log.debug("INSERT: N=%s run_id=%s values=%s",
                          row['N'], run_id, row['values'])
                cur.execute(sql, tuple(vals))
                n += 1
        else:
            # Fallback: старый формат без run_id
            cols = (['MSK', 'MSK_Code', 'N']
                    + [f'SW_{i}' for i in range(1, 13)]
                    + ['Spc'])
            col_names = ', '.join(f'`{c}`' for c in cols)
            placeholders = ', '.join(['%s'] * len(cols))
            sql = (f"INSERT INTO `{MEAS_TABLE}` ({col_names}) "
                   f"VALUES ({placeholders})")
            for row in rows:
                vals = [msk_real, None, row['N']]
                for i in range(1, 13):
                    vals.append(row['values'].get(i))
                vals.append(nom_id)
                cur.execute(sql, tuple(vals))
                n += 1

        conn.commit()
        cur.close()
        dt = (time.perf_counter() - t0) * 1000
        msg = f"Сохранено {n} записей"
        if run_id is not None:
            msg += f" (замер #{run_id})"
        log.info("%s за %.1f ms", msg, dt)
        return {'saved': n, 'run_id': run_id, 'message': msg}
    except Exception as e:
        log.error("Ошибка при сохранении: %s", e)
        try:
            conn.rollback()
            log.warning("Транзакция откатана")
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

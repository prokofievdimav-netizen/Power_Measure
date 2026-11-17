#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Константы, regex и утилиты единиц измерения для GUI."""

import re
from typing import List

# Имя файла шрифта (без .otf) в папке ./fonts
FONT_NAME = 'MonoCondensed'

# Регулярные выражения
NUM_RE = re.compile(r'^([A-Z]{2})(\d{4})$')
BARCODE_RE = re.compile(r'^\d{5,}$')
MSK_RE = re.compile(r'^\d{2,3}-\d{1,4}$')

# Единицы (англ.): напряжение / сопротивление / ёмкость с приставками.
UNITS_CHOICES = [
    '',
    'V', 'mV', 'uV',
    'Ohm', 'kOhm', 'MOhm', 'GOhm',
    'F', 'mF', 'uF', 'nF', 'pF',
]

# Множитель перевода «единица с приставкой → базовая единица»
SI_PREFIXES = {
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
BASE_UNITS = {
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
OPEN_CIRCUIT_THRESHOLD = 100e6   # Ом
# Маркер «норма не задана» в Par_min / Par_max
NORM_ABSENT = -1000000
# Порог «перегрузки» DM858 (9.9e+37)
OVERLOAD_THRESHOLD = 1e37


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
    for alias in sorted(BASE_UNITS.keys(), key=len, reverse=True):
        if u.endswith(alias):
            prefix = u[:-len(alias)]
            if prefix in SI_PREFIXES:
                return (BASE_UNITS[alias], prefix, SI_PREFIXES[prefix])
    return (u, '', 1.0)

# -*- coding: utf-8 -*-

from typing import Optional, List, Dict, Any
import logging

import dearpygui.dearpygui as dpg

from gui.constants import parse_units

log = logging.getLogger("app")


class TableCheckAMixin:
    def _evaluate_status(self, values: Dict[int, str]) -> str:
        if not self.specs:
            return "Годен"

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

        any_fail = False
        for sw, specs in specs_by_switch.items():
            if sw == cap_col:
                parts_f = all_cap_parts
            elif sw in cap_positions:
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

    def _check_spec(self, value: float, spec: Dict) -> bool:
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

        if par_bool == 1:
            return value < 1500
        if par_bool == 0:
            return value > 1500

        if pmin is not None and value < pmin:
            return False
        if pmax is not None and value > pmax:
            return False
        return True

    def _get_checked_parts_for_pos(self, pos, values, cap_col,
                                   cap_positions, all_cap_parts) -> List[float]:
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

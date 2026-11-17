# -*- coding: utf-8 -*-

from typing import Optional, List, Dict, Any
import logging

import dearpygui.dearpygui as dpg

from gui.constants import parse_units

log = logging.getLogger("app")


class TableCheckBMixin:
    def _color_failed_cells_yellow(self, idx: int):
        if not self.specs:
            return

        values = self.rows[idx].get('values') or {}
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

    def _compute_resistance_ranges(self) -> Dict[int, int]:
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

            if par_value == 0:
                if par_bool == 1:
                    out[pos] = 1_000
                continue

            units = (spec.get('units') or '').strip()
            base, prefix, mult = parse_units(units)
            if base != 'Ohm':
                continue

            if not prefix:
                out[pos] = 100
            else:
                out[pos] = max(1, int(round(100 * mult)))

        log.info("Пределы измерения сопротивления по нормам: %s", out)
        return out

    def _collect_bad_cells_for_row(self, row_idx: int) -> set:
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

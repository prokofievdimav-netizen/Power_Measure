# -*- coding: utf-8 -*-

from typing import Optional, List, Dict, Any
import logging

import dearpygui.dearpygui as dpg

from gui.constants import parse_units
import relay_switch_m as rsm

log = logging.getLogger("app")


class TableRenderBMixin:
    def _format_value_for_pos(self, pos: int, raw_str: str) -> str:
        if raw_str is None:
            return ""
        specs = [s for s in self.specs if s.get('switch_id') == pos]
        if not specs:
            return str(raw_str)

        use_pass_fail = any(s.get('Par_value') == 0 for s in specs)
        parts = [p for p in str(raw_str).split('/') if p.strip()]
        if not parts:
            return str(raw_str)

        out: List[str] = []
        for p in parts:
            try:
                v_base = float(p)
            except ValueError:
                out.append(p)
                continue

            if abs(v_base) >= self._OVERLOAD_THRESHOLD:
                out.append("OPEN")
                continue

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

            if base == 'Ohm' and v_base > self._OPEN_CIRCUIT_THRESHOLD:
                pmax = spec.get('Par_max')
                pmin = spec.get('Par_min')
                bound = None
                for cand in (pmax, pmin):
                    if cand is not None and cand != self._NORM_ABSENT:
                        bound = cand
                        break
                if bound is not None:
                    out.append(f"> {bound:g} {units}".strip())
                else:
                    out.append("> 100 MOm")
                continue

            display = v_base / mult if mult else v_base
            formatted = f"{display:.{nd}f}" if nd is not None else f"{display:.6g}"
            if units:
                formatted = f"{formatted} {units}"
            out.append(formatted)

        return "/".join(out)

    def _render_row_values(self, idx: int):
        row = self.rows[idx]
        values = row.get('values') or {}
        for pos in range(1, 13):
            tag = f"cell_{idx}_{pos}"
            if not dpg.does_item_exist(tag):
                continue
            raw = values.get(pos)
            if raw is None or str(raw).strip() == '':
                dpg.set_value(tag, "-")
            else:
                dpg.set_value(tag, self._format_value_for_pos(pos, str(raw)))

    def _capacitance_positions(self) -> List[int]:
        result: List[int] = []
        for s in self.specs:
            units = (s.get('units') or '')
            base, _, _ = parse_units(units)
            if base == 'F':
                sw = s.get('switch_id')
                if sw is not None and sw not in result:
                    result.append(sw)
        return sorted(result)

    def _cap_modes_positions(self) -> List[int]:
        out: List[int] = []
        for pos in range(1, 13):
            modes = rsm.POSITION_MEASURE_SEQUENCE.get(pos, [])
            if any(str(m).upper() == 'CAP' for m in modes):
                out.append(pos)
        return out

    def _cap_display_col(self) -> Optional[int]:
        for s in self.specs:
            base, _, _ = parse_units(s.get('units') or '')
            if base == 'F':
                return s.get('switch_id')
        return None

    def _split_by_mode(self, pos: int, raw: str):
        parts = [p.strip() for p in (raw or '').split('/') if p.strip()]
        seq = rsm.POSITION_MEASURE_SEQUENCE.get(pos, [])
        result = []
        for i, p in enumerate(parts):
            m = str(seq[i]).upper() if i < len(seq) else None
            result.append((m, p))
        return result

    def _format_cap_values(self, vals: List[str]) -> str:
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

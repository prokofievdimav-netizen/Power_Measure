# -*- coding: utf-8 -*-

from typing import Optional, List, Dict, Any
import logging

import dearpygui.dearpygui as dpg

from gui.constants import parse_units

log = logging.getLogger("app")


class TableRenderAMixin:
    def _get_column_name(self, pos: int) -> str:
        name = (self.column_names.get(pos) or '').strip()
        if name:
            return name
        for s in self.specs:
            if s.get('switch_id') == pos:
                n = (s.get('Par_Name') or '').strip()
                if n:
                    return n
        return ''

    def _get_column_title(self, pos: int,
                          max_len: Optional[int] = None) -> str:
        name = self._get_column_name(pos)
        if not name:
            return str(pos)
        if max_len is not None and len(name) > max_len:
            name = name[:max_len - 3].rstrip() + '...'
        return f"{pos}. {name}"

    def _rebuild_table(self):
        for tag in self._row_registry_tags:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._row_registry_tags = []

        if dpg.does_item_exist(self.table_tag):
            dpg.delete_item(self.table_tag)

        headers = (["№", "Номер резонатора"]
                   + [self._get_column_title(i, max_len=24)
                      for i in range(1, 13)]
                   + ["Статус"])

        with dpg.table(parent=self.table_container, tag=self.table_tag,
                       header_row=True,
                       borders_innerH=True, borders_outerH=True,
                       borders_innerV=True, borders_outerV=True,
                       row_background=True, scrollY=True, height=-1,
                       freeze_rows=1, freeze_columns=2):
            for h_idx, h in enumerate(headers):
                if h_idx == 0:
                    w = 50
                elif h_idx == 1:
                    w = 140
                elif h_idx >= len(headers) - 1:
                    w = 110
                else:
                    w = 170
                dpg.add_table_column(label=h, init_width_or_weight=w)

            for i, row in enumerate(self.rows):
                with dpg.table_row(tag=f"row_{i}"):
                    dpg.add_text(str(i + 1), tag=f"num_{i}")
                    dpg.add_text(row['N'], tag=f"n_{i}")
                    reg_tag = f"reg_{i}"
                    with dpg.item_handler_registry(tag=reg_tag) as reg:
                        dpg.add_item_clicked_handler(
                            callback=self.on_measure, user_data=i)
                    dpg.bind_item_handler_registry(f"n_{i}", reg)
                    self._row_registry_tags.append(reg_tag)
                    for pos in range(1, 13):
                        dpg.add_text("-", tag=f"cell_{i}_{pos}")
                    dpg.add_text("", tag=f"status_{i}")

    def _color_row_red(self, idx: int):
        red = (255, 80, 80)
        tags = [f"num_{idx}", f"n_{idx}", f"status_{idx}"]
        tags += [f"cell_{idx}_{p}" for p in range(1, 13)]
        for t in tags:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, color=red)

    def _color_row_green(self, idx: int):
        green = (100, 255, 100)
        tags = [f"num_{idx}", f"n_{idx}", f"status_{idx}"]
        tags += [f"cell_{idx}_{p}" for p in range(1, 13)]
        for t in tags:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, color=green)

    def _reset_row_color(self, idx: int):
        default = (215, 215, 220)
        tags = [f"num_{idx}", f"n_{idx}", f"status_{idx}"]
        tags += [f"cell_{idx}_{p}" for p in range(1, 13)]
        for t in tags:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, color=default)

    def _reset_row_display(self, idx: int):
        for pos in range(1, 13):
            tag = f"cell_{idx}_{pos}"
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, "-")
        tag = f"status_{idx}"
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, "")

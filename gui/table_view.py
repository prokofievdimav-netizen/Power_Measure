#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Совместимость: TableMixin = TableRenderMixin + TableCheckMixin."""

from gui.table_render import TableRenderMixin
from gui.table_check import TableCheckMixin


class TableMixin(TableRenderMixin, TableCheckMixin):
    """Полный mixin таблицы результатов."""
    pass

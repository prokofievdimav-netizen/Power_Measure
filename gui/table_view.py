#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TableMixin: полный mixin таблицы результатов."""

from gui.table_render_a import TableRenderAMixin
from gui.table_render_b import TableRenderBMixin
from gui.table_check_a import TableCheckAMixin
from gui.table_check_b import TableCheckBMixin


class TableMixin(TableRenderAMixin, TableRenderBMixin,
                 TableCheckAMixin, TableCheckBMixin):
    """Полный mixin таблицы результатов."""
    pass

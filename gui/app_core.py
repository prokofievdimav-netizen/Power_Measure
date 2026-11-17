# -*- coding: utf-8 -*-
"""AppCoreMixin = AppCoreAMixin + AppCoreBMixin."""

from gui.app_core_a import AppCoreAMixin
from gui.app_core_b import AppCoreBMixin


class AppCoreMixin(AppCoreAMixin, AppCoreBMixin):
    pass

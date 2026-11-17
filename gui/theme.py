#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тема DearPyGui."""

import dearpygui.dearpygui as dpg


class ThemeMixin:
    def _apply_theme(self):
        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (28, 28, 30))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (22, 22, 24))
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, (35, 35, 38))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (70, 70, 75))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (45, 45, 50))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (60, 60, 65))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (75, 75, 80))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (35, 35, 38))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (50, 50, 55))
                dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, (35, 35, 38))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (22, 22, 24))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (60, 60, 65))
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (200, 200, 200))
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (120, 120, 130))
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (150, 150, 160))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (55, 55, 60))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (75, 75, 85))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (95, 95, 105))
                dpg.add_theme_color(dpg.mvThemeCol_Header, (55, 55, 60))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (75, 75, 85))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (95, 95, 105))
                dpg.add_theme_color(dpg.mvThemeCol_Separator, (70, 70, 75))
                dpg.add_theme_color(dpg.mvThemeCol_ResizeGrip, (80, 80, 90))
                dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, (50, 50, 55))
                dpg.add_theme_color(dpg.mvThemeCol_TableBorderStrong, (90, 90, 95))
                dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, (60, 60, 65))
                dpg.add_theme_color(dpg.mvThemeCol_TableRowBg, (28, 28, 30))
                dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, (34, 34, 37))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (215, 215, 220))
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (120, 120, 125))

                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 2)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 2)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 2)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 2)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 2)
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 6, 4)
        dpg.bind_theme(theme)

import os

import dearpygui.dearpygui as dpg

def setup_fonts(dpg, FontName):
    # Загружаем шрифт с поддержкой кириллицы
    big_let_start = 0x00C0  # Capital "A" in cyrillic alphabet
    big_let_end = 0x00DF  # Capital "Я" in cyrillic alphabet
    small_let_end = 0x00FF  # small "я" in cyrillic alphabet
    remap_big_let = 0x0410  # Starting number for remapped cyrillic alphabet
    alph_len = big_let_end - big_let_start + 1  # adds the shift from big letters to small
    alph_shift = remap_big_let - big_let_start  # adds the shift from remapped to non-remapped

    # Текущая папка запуска программы
    current_dir = os.getcwd()
    # Полный путь к файлу шрифта
    font_path = os.path.join(current_dir, "fonts", FontName + ".otf")

    with dpg.font_registry():
        with dpg.font(font_path, 12) as default_font:
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Cyrillic)
            dpg.add_font_range(0x2500, 0x257F)  # Box Drawing
            biglet = remap_big_let  # Starting number for remapped cyrillic alphabet
            for i1 in range(big_let_start, big_let_end + 1):  # Cycle through big letters in cyrillic alphabet
                dpg.add_char_remap(i1, biglet)  # Remap the big cyrillic letter
                dpg.add_char_remap(i1 + alph_len, biglet + alph_len)  # Remap the small cyrillic letter
                biglet += 1  # choose next letter
            dpg.bind_font(default_font)

        with dpg.font(font_path, 18) as second_font:
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Cyrillic)
            dpg.add_font_range(0x2500, 0x257F)  # Box Drawing
            biglet = remap_big_let
            for i1 in range(big_let_start, big_let_end + 1):
                dpg.add_char_remap(i1, biglet)
                dpg.add_char_remap(i1 + alph_len, biglet + alph_len)
                biglet += 1
            dpg.bind_font(default_font)

        with dpg.font(font_path, 50, tag='large_font'):
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Cyrillic)
            dpg.add_font_range(0x2500, 0x257F)  # Box Drawing
            biglet = remap_big_let
            for i1 in range(big_let_start, big_let_end + 1):
                dpg.add_char_remap(i1, biglet)
                dpg.add_char_remap(i1 + alph_len, biglet + alph_len)
                biglet += 1

        with dpg.font(font_path, 30, tag='medium_font'):
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Cyrillic)
            dpg.add_font_range(0x2500, 0x257F)  # Box Drawing
            biglet = remap_big_let
            for i1 in range(big_let_start, big_let_end + 1):
                dpg.add_char_remap(i1, biglet)
                dpg.add_char_remap(i1 + alph_len, biglet + alph_len)
                biglet += 1

        with dpg.font(font_path, 20) as medium_font1:
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Cyrillic)
            dpg.add_font_range(0x2500, 0x257F)  # Box Drawing
            biglet = remap_big_let
            for i1 in range(big_let_start, big_let_end + 1):
                dpg.add_char_remap(i1, biglet)
                dpg.add_char_remap(i1 + alph_len, biglet + alph_len)
                biglet += 1


def setup_fonts_1(dpg_module, FontName):
    """
    Загружает .otf шрифт с поддержкой кириллицы.
    В DearPyGui >= 1.11 диапазоны символов определяются автоматически,
    поэтому add_font_range_hint / add_font_range / add_char_remap не нужны.
    """
    # Путь к файлу шрифта относительно этого файла (fonts/Font.py)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(base_dir, FontName + ".otf")

    if not os.path.isfile(font_path):
        raise FileNotFoundError(f"Шрифт не найден: {font_path}")

    with dpg_module.font_registry():
        with dpg_module.font(font_path, 12) as default_font:
            dpg_module.bind_font(default_font)

        dpg_module.font(font_path, 18)

        dpg_module.font(font_path, 50, tag='large_font')
        dpg_module.font(font_path, 30, tag='medium_font')
        dpg_module.font(font_path, 20, tag='medium_font1')
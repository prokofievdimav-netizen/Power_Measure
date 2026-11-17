#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Экспорт протокола в PDF."""

import logging
import os
from typing import Optional

import dearpygui.dearpygui as dpg

from gui.constants import FONT_NAME

log = logging.getLogger("app")


class PdfMixin:
    def _register_pdf_font(self) -> str:
        """Регистрирует TTF-шрифт с кириллицей для reportlab (один раз)."""
        if self._pdf_font_name is not None:
            return self._pdf_font_name

        import os
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        candidates = [
            'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/DejaVuSans.ttf',
            'C:/Windows/Fonts/segoeui.ttf',
            'C:/Windows/Fonts/tahoma.ttf',
            'C:/Windows/Fonts/calibri.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont('ProtocolFont', path))
                    log.info("PDF-шрифт зарегистрирован: %s", path)
                    self._pdf_font_name = 'ProtocolFont'
                    return 'ProtocolFont'
                except Exception as e:
                    log.warning("Не удалось зарегистрировать шрифт %s: %s",
                                path, e)
        log.warning("Не найден TTF-шрифт с кириллицей — используется Helvetica")
        self._pdf_font_name = 'Helvetica'
        return 'Helvetica'

    def _open_file(self, path: str):
        """Открывает файл системным просмотрщиком."""
        import os, sys, subprocess
        try:
            if sys.platform.startswith('win'):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            log.warning("Не удалось открыть файл %s: %s", path, e)

    def _export_protocol_pdf(self) -> str:
        """Формирует PDF-протокол и возвращает путь к файлу."""
        import os
        import datetime
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                        Paragraph, Spacer)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import mm

        font_name = self._register_pdf_font()

        # корень проекта (gui/ -> parent)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out_dir = os.path.join(base_dir, 'Протоколы')
        os.makedirs(out_dir, exist_ok=True)

        now = datetime.datetime.now()
        msk = (self.msk_real or 'MSK').strip() or 'MSK'
        safe_msk = ''.join(c if (c.isalnum() or c in '-_.') else '_'
                           for c in msk)
        ts = now.strftime('%Y-%m-%d_%H-%M-%S')
        base_name = f"{safe_msk}_{ts}"
        filepath = os.path.join(out_dir, f"{base_name}.pdf")
        counter = 1
        while os.path.exists(filepath):
            filepath = os.path.join(out_dir, f"{base_name}_{counter}.pdf")
            counter += 1

        doc = SimpleDocTemplate(
            filepath,
            pagesize=landscape(A4),
            leftMargin=10 * mm, rightMargin=10 * mm,
            topMargin=10 * mm, bottomMargin=10 * mm,
            title="Протокол проверки монтажа элементов",
            author="КР · Контроль плат",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ProtocolTitle', parent=styles['Title'],
            fontName=font_name, fontSize=16, leading=20, spaceAfter=4,
        )
        info_style = ParagraphStyle(
            'ProtocolInfo', parent=styles['Normal'],
            fontName=font_name, fontSize=10, leading=14,
        )
        cell_style = ParagraphStyle(
            'ProtocolCell', parent=styles['Normal'],
            fontName=font_name, fontSize=8, leading=10,
        )
        cell_style_bad = ParagraphStyle(
            'ProtocolCellBad', parent=cell_style,
            textColor=colors.HexColor('#8B0000'),
        )
        head_style = ParagraphStyle(
            'ProtocolHead', parent=cell_style,
            fontName=font_name, fontSize=6, leading=7, alignment=1,
        )

        story = []
        story.append(Paragraph("Протокол проверки монтажа элементов",
                               title_style))

        n_total = len(self.rows)
        n_meas = len(self.measured_indices)
        n_good = sum(1 for i in self.measured_indices
                     if self.rows[i].get('status') == 'Годен')
        n_bad = sum(1 for i in self.measured_indices
                    if self.rows[i].get('status') == 'Брак')

        info_lines = [
            f"МСК: <b>{self.msk_real or '-'}</b>",
            f"Спецификация: <b>{self._current_spec_name() or '-'}</b>",
            f"Номеров: {n_total}  |  Измерено: {n_meas}  |  "
            f"Годен: {n_good}  |  Брак: {n_bad}",
            f"Дата: {now.strftime('%d.%m.%Y %H:%M:%S')}",
        ]
        for line in info_lines:
            story.append(Paragraph(line, info_style))
        story.append(Spacer(1, 6 * mm))

        # Заголовки
        headers = ['№', 'Номер']
        for i in range(1, 13):
            headers.append(self._get_column_title(i, max_len=18))
        headers.append('Статус')

        data = [[Paragraph(h, head_style) for h in headers]]

        for idx, row in enumerate(self.rows):
            n = row.get('N') or ''
            status = row.get('status') or ''
            values = row.get('values') or {}
            cells = [
                Paragraph(str(idx + 1), cell_style),
                Paragraph(str(n), cell_style),
            ]
            for pos in range(1, 13):
                raw = values.get(pos)
                txt = self._format_value_for_pos(pos, raw) if raw is not None else ''
                style = cell_style
                cells.append(Paragraph(str(txt), style))
            st_style = cell_style_bad if status == 'Брак' else cell_style
            cells.append(Paragraph(status, st_style))
            data.append(cells)

        col_widths = [12 * mm, 22 * mm] + [18 * mm] * 12 + [18 * mm]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#32323A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#606065')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.HexColor('#1C1C1E'), colors.HexColor('#222226')]),
        ]))
        story.append(table)
        doc.build(story)
        log.info("PDF сохранён: %s", filepath)
        return filepath

    def on_export_pdf(self):
        if not self.rows:
            self.set_status("Нет данных для экспорта", (255, 150, 100))
            return
        try:
            path = self._export_protocol_pdf()
            self.set_status(f"Протокол сохранён: {path}", (100, 255, 100))
            self._open_file(path)
        except Exception as e:
            log.exception("Ошибка экспорта протокола")
            self.set_status(f"Ошибка экспорта: {e}", (255, 100, 100))

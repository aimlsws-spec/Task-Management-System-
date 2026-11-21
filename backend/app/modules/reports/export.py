"""CSV / XLSX export. Any cell that could be read as a spreadsheet formula is neutralised (OWASP CSV injection)."""

import csv
import io

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(v):
    if isinstance(v, bool):
        return "yes" if v else "no"
    if v is None:
        return ""
    if isinstance(v, str) and v.startswith(_DANGEROUS):
        return "'" + v  # a leading apostrophe forces text in Excel / Sheets / LibreOffice
    return v


def to_csv(columns: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([safe_cell(c) for c in columns])
    for r in rows:
        w.writerow([safe_cell(r.get(c)) for c in columns])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel opens UTF-8 correctly


def to_xlsx(title: str, columns: list[str], rows: list[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append([safe_cell(c) for c in columns])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([safe_cell(r.get(c)) for c in columns])
        for cell in ws[ws.max_row]:
            if cell.data_type == "f":  # belt and braces: never store a formula
                cell.data_type = "s"
    for i, col in enumerate(columns, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = min(48, max(12, len(str(col)) + 4))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

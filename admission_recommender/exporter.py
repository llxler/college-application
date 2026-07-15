from __future__ import annotations

import math
import zipfile
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MIME = "application/pdf"
JPG_MIME = "image/jpeg"
EXPORT_COLUMNS = [
    "推荐档位",
    "院校专业组代号",
    "院校专业组名称",
    "批次",
    "首选科目或类别",
    "再选科目要求",
    "投档最低分",
    "位次值",
    "专业成绩",
    "专业信息",
    "学校性质",
]

_FONT_PATH = Path(__file__).parents[1] / "assets" / "NotoSansSC-Subset.ttf"
_FONT_SIZE = 24
_HEADER_FONT_SIZE = 25
_LINE_GAP = 6
_CELL_PADDING = 12
_PDF_ROWS_PER_PAGE = 12
_COLUMN_LAYOUT = {
    "推荐档位": (100, 1),
    "院校专业组代号": (180, 2),
    "院校专业组名称": (360, 3),
    "批次": (220, 2),
    "首选科目或类别": (180, 2),
    "再选科目要求": (180, 2),
    "投档最低分": (150, 1),
    "位次值": (160, 1),
    "专业成绩": (160, 1),
    "专业信息": (560, 3),
    "学校性质": (150, 2),
}


def to_excel_bytes(result: pd.DataFrame) -> bytes:
    result = _export_columns(result)
    clean_result = result.astype(object).where(pd.notna(result), "")
    rows = [list(clean_result.columns)] + clean_result.values.tolist()
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/styles.xml", _styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(rows))
    return output.getvalue()


def to_jpg_bytes(result: pd.DataFrame) -> bytes:
    result = _export_columns(result)
    image = _render_table_image(result, compact=len(result) > 100)
    output = BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True, progressive=True)
    return output.getvalue()


def to_pdf_bytes(result: pd.DataFrame) -> bytes:
    result = _export_columns(result)
    page_count = max(math.ceil(len(result) / _PDF_ROWS_PER_PAGE), 1)
    pages: list[tuple[bytes, int, int]] = []
    for page_index in range(page_count):
        page = _render_table_image(
            result.iloc[
                page_index * _PDF_ROWS_PER_PAGE : (page_index + 1) * _PDF_ROWS_PER_PAGE
            ]
        )
        page_buffer = BytesIO()
        page.save(page_buffer, format="JPEG", quality=92)
        pixel_width, pixel_height = page.size
        page.close()
        pages.append((page_buffer.getvalue(), pixel_width, pixel_height))
    return _jpeg_pages_to_pdf(pages)


def build_export_stem(
    first_choice: str | None,
    category: str | None,
    user_score: float | None,
    user_rank: float | None,
) -> str:
    details = ""
    if first_choice:
        details = f"首选{first_choice}"
    elif category:
        details = category

    if user_score is not None:
        details += f"{_format_number(user_score)}分"
    elif user_rank is not None:
        details += f"{_format_number(user_rank)}位"

    return f"志愿生成结果（{details}）" if details else "志愿生成结果"


def _export_columns(result: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in EXPORT_COLUMNS if column in result.columns]
    return result.loc[:, columns]


def _render_table_image(result: pd.DataFrame, compact: bool = False) -> Image.Image:
    clean_result = result.astype(object).where(pd.notna(result), "")
    columns = list(clean_result.columns)
    font_size = 18 if compact else _FONT_SIZE
    header_font_size = 19 if compact else _HEADER_FONT_SIZE
    line_gap = 4 if compact else _LINE_GAP
    cell_padding = 8 if compact else _CELL_PADDING
    width_scale = 0.7 if compact else 1.0
    font = _load_font(font_size, "Regular")
    header_font = _load_font(header_font_size, "Medium")
    measuring_image = Image.new("RGB", (1, 1), "white")
    measuring_draw = ImageDraw.Draw(measuring_image)

    widths = [
        round(_COLUMN_LAYOUT.get(column, (240, 2))[0] * width_scale)
        for column in columns
    ]
    header_lines = [
        _wrap_text(measuring_draw, str(column), header_font, width - 2 * cell_padding, 2)
        for column, width in zip(columns, widths)
    ]
    row_lines: list[list[list[str]]] = []
    for row in clean_result.itertuples(index=False, name=None):
        row_lines.append(
            [
                _wrap_text(
                    measuring_draw,
                    str(value),
                    font,
                    width - 2 * cell_padding,
                    min(_COLUMN_LAYOUT.get(column, (240, 2))[1], 2)
                    if compact
                    else _COLUMN_LAYOUT.get(column, (240, 2))[1],
                )
                for column, value, width in zip(columns, row, widths)
            ]
        )

    header_height = _row_height(header_lines, header_font_size, line_gap, cell_padding)
    row_heights = [
        _row_height(lines, font_size, line_gap, cell_padding) for lines in row_lines
    ]
    table_width = max(sum(widths) + 1, 1)
    table_height = max(header_height + sum(row_heights) + 1, 1)
    image = Image.new("RGB", (table_width, table_height), "white")
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, table_width - 1, header_height), fill="#E8EEF7")
    _draw_row(
        draw,
        header_lines,
        widths,
        0,
        header_height,
        header_font,
        line_gap,
        cell_padding,
        bold=True,
    )
    y = header_height
    for index, (lines, row_height) in enumerate(zip(row_lines, row_heights)):
        if index % 2:
            draw.rectangle((0, y, table_width - 1, y + row_height), fill="#F8FAFC")
        _draw_row(draw, lines, widths, y, row_height, font, line_gap, cell_padding)
        y += row_height

    return image


def _jpeg_pages_to_pdf(pages: list[tuple[bytes, int, int]]) -> bytes:
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    page_ids: list[int] = []
    for jpeg, pixel_width, pixel_height in pages:
        page_id = len(objects) + 1
        content_id = page_id + 1
        image_id = page_id + 2
        page_ids.append(page_id)
        width = pixel_width * 72 / 180
        height = pixel_height * 72 / 180
        width_text = _pdf_number(width)
        height_text = _pdf_number(height)
        content = f"q {width_text} 0 0 {height_text} 0 0 cm /Im0 Do Q".encode("ascii")
        objects.extend(
            [
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width_text} {height_text}] "
                    f"/Resources << /XObject << /Im0 {image_id} 0 R >> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode("ascii"),
                b"<< /Length "
                + str(len(content)).encode("ascii")
                + b" >>\nstream\n"
                + content
                + b"\nendstream",
                (
                    f"<< /Type /XObject /Subtype /Image /Width {pixel_width} "
                    f"/Height {pixel_height} /ColorSpace /DeviceRGB "
                    f"/BitsPerComponent 8 /Filter /DCTDecode /Length {len(jpeg)} >>\nstream\n"
                ).encode("ascii")
                + jpeg
                + b"\nendstream",
            ]
        )

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

    output = BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, content in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{object_id} 0 obj\n".encode("ascii"))
        output.write(content)
        output.write(b"\nendobj\n")

    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return output.getvalue()


def _pdf_number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _draw_row(
    draw: ImageDraw.ImageDraw,
    cells: list[list[str]],
    widths: list[int],
    y: int,
    height: int,
    font: ImageFont.FreeTypeFont,
    line_gap: int,
    cell_padding: int,
    bold: bool = False,
) -> None:
    x = 0
    color = "#172033" if bold else "#202939"
    for lines, width in zip(cells, widths):
        draw.rectangle((x, y, x + width, y + height), outline="#AAB4C3", width=1)
        line_height = font.size + line_gap
        text_y = y + max((height - len(lines) * line_height) // 2, cell_padding)
        for line in lines:
            draw.text((x + cell_padding, text_y), line, fill=color, font=font)
            text_y += line_height
        x += width


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    if not text:
        return [""]

    lines: list[str] = []
    current = ""
    truncated = False
    for char in text.replace("\r", "").replace("\n", " "):
        candidate = current + char
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = char
            if len(lines) == max_lines:
                truncated = True
                break
        else:
            current = candidate

    if not truncated and current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    if truncated:
        lines[-1] = _with_ellipsis(draw, lines[-1], font, max_width)
    return lines or [""]


def _with_ellipsis(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> str:
    suffix = "..."
    while text and draw.textlength(text + suffix, font=font) > max_width:
        text = text[:-1]
    return text + suffix


def _row_height(
    cells: list[list[str]],
    font_size: int,
    line_gap: int,
    cell_padding: int,
) -> int:
    line_count = max((len(lines) for lines in cells), default=1)
    return line_count * (font_size + line_gap) + 2 * cell_padding


def _load_font(size: int, variation: str) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(_FONT_PATH), size)
    font.set_variation_by_name(variation)
    return font


def _format_number(value: float) -> str:
    numeric = float(value)
    if math.isclose(numeric, round(numeric)):
        return str(int(round(numeric)))
    return f"{numeric:.3f}".rstrip("0").rstrip(".")


def _worksheet_xml(rows: list[list[object]]) -> str:
    dimension = f"A1:{_column_name(max(len(rows[0]) if rows else 1, 1))}{max(len(rows), 1)}"
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = [
            _cell_xml(row_index, column_index, value)
            for column_index, value in enumerate(row, start=1)
            if value != ""
        ]
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="{dimension}"/>'
        "<sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>"
        "<sheetFormatPr defaultRowHeight=\"15\"/>"
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )


def _cell_xml(row_index: int, column_index: int, value: object) -> str:
    cell_ref = f"{_column_name(column_index)}{row_index}"
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return f'<c r="{cell_ref}"><v>{value}</v></c>'
    text = _valid_xml_text(str(value))
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _valid_xml_text(value: str) -> str:
    return "".join(
        char
        for char in value
        if char in "\t\n\r" or ord(char) >= 32
    )


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets><sheet name=\"推荐结果\" sheetId=\"1\" r:id=\"rId1\"/></sheets>"
        "</workbook>"
    )


def _workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<fonts count=\"1\"><font><sz val=\"11\"/><name val=\"Calibri\"/></font></fonts>"
        "<fills count=\"1\"><fill><patternFill patternType=\"none\"/></fill></fills>"
        "<borders count=\"1\"><border/></borders>"
        "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>"
        "<cellXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/></cellXfs>"
        "<cellStyles count=\"1\"><cellStyle name=\"Normal\" xfId=\"0\" builtinId=\"0\"/></cellStyles>"
        "</styleSheet>"
    )

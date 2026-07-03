from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd

from .cleaning import STANDARD_COLUMNS, clean_sheet_rows

MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
OFFICE_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def load_workbook_data(path: str | Path) -> pd.DataFrame:
    workbook_rows = read_xlsx_rows(path)
    frames = [
        clean_sheet_rows(rows, sheet_name)
        for sheet_name, rows in workbook_rows.items()
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(
        [frame.dropna(axis=1, how="all") for frame in frames],
        ignore_index=True,
    )
    for column in STANDARD_COLUMNS:
        if column not in combined.columns:
            combined[column] = pd.NA
    return combined[STANDARD_COLUMNS]


def read_xlsx_rows(path: str | Path) -> dict[str, list[list[Any]]]:
    workbook_path = Path(path)
    with zipfile.ZipFile(workbook_path) as archive:
        shared_strings = _read_shared_strings(archive)
        relationships = _read_workbook_relationships(archive)
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))

        sheets: dict[str, list[list[Any]]] = {}
        for sheet in workbook_root.find(f"{MAIN_NS}sheets").findall(f"{MAIN_NS}sheet"):
            sheet_name = sheet.attrib["name"]
            relationship_id = sheet.attrib[f"{OFFICE_REL_NS}id"]
            target = relationships[relationship_id]
            sheet_path = _resolve_workbook_target(target)
            sheets[sheet_name] = _read_sheet_rows(archive, sheet_path, shared_strings)
        return sheets


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall(f"{MAIN_NS}si"):
        strings.append("".join(text.text or "" for text in item.iter(f"{MAIN_NS}t")))
    return strings


def _read_workbook_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    return {
        relationship.attrib["Id"]: relationship.attrib["Target"]
        for relationship in root.findall(f"{PACKAGE_REL_NS}Relationship")
    }


def _resolve_workbook_target(target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return f"xl/{target}"


def _read_sheet_rows(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
) -> list[list[Any]]:
    root = ET.fromstring(archive.read(sheet_path))
    sheet_data = root.find(f"{MAIN_NS}sheetData")
    if sheet_data is None:
        return []

    rows: list[list[Any]] = []
    for row in sheet_data.findall(f"{MAIN_NS}row"):
        values: list[Any] = []
        last_index = 0
        for cell in row.findall(f"{MAIN_NS}c"):
            cell_index = _column_index(cell.attrib.get("r", ""))
            while last_index + 1 < cell_index:
                values.append(None)
                last_index += 1
            values.append(_cell_value(cell, shared_strings))
            last_index = cell_index
        rows.append(values)
    return rows


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    value = cell.find(f"{MAIN_NS}v")

    if cell_type == "s":
        if value is None or value.text is None:
            return None
        return shared_strings[int(value.text)]
    if cell_type == "inlineStr":
        inline = cell.find(f"{MAIN_NS}is")
        if inline is None:
            return None
        return "".join(text.text or "" for text in inline.iter(f"{MAIN_NS}t"))
    if value is None:
        return None
    return value.text


def _column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return 0
    index = 0
    for char in match.group(1):
        index = index * 26 + ord(char) - 64
    return index

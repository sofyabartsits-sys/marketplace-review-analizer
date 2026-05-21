from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from models import Product
from services.report_generator import category_display

logger = logging.getLogger(__name__)

COLUMN_SYNONYMS = {
    "product": ["продукт", "товар", "название", "наименование"],
    "url": ["ссылка", "link", "url"],
    "article": ["артикул", "nm", "sku", "offer", "id"],
    "category": ["категория", "группа", "тип"],
    "variant": ["вариант", "оттенок", "тон", "цвет"],
}


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _is_empty(value: object) -> bool:
    return _norm(value) in {"", "nan", "none"}


def _canonical_column(name: object) -> str | None:
    normalized = _norm(name)
    for canonical, variants in COLUMN_SYNONYMS.items():
        if any(v in normalized for v in variants):
            return canonical
    return None


def _marketplace_from_text(text: str) -> str | None:
    lower = text.lower()
    if "wildberries" in lower or lower == "wb" or " wb " in f" {lower} " or "вб" in lower or "вайлд" in lower:
        return "WB"
    if "ozon" in lower or "озон" in lower:
        return "Ozon"
    return None


def _marketplace_from_context(sheet_name: str, values: list[object]) -> str | None:
    return _marketplace_from_text(" ".join([sheet_name] + [str(v) for v in values]))


def read_products(excel_file: str | Path | bytes) -> list[Product]:
    """Read products from Excel without relying on a fixed number of rows.

    The reader supports two common layouts:
    1. Separate sheets/blocks for WB and Ozon.
    2. Side-by-side blocks on one sheet, for example:
       WB: Product | Link | Article | Category, then Ozon: Product | Link | Article | Category.

    A key fix: duplicated Excel headers like two columns named "Продукт" are processed by
    column positions, not by pandas column names. This prevents product names like
    "product ... Name: ..., dtype: str" from appearing in the report.
    """
    xls = pd.ExcelFile(excel_file)
    partials: list[dict[str, str | None]] = []

    for sheet_name in xls.sheet_names:
        raw = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str).fillna("")
        if raw.empty:
            continue

        for header_idx in _detect_header_rows(raw):
            partials.extend(_read_blocks_from_header(raw, sheet_name, header_idx))

    return _merge_partials(partials)


def _detect_header_rows(df: pd.DataFrame) -> list[int]:
    rows: list[int] = []
    for idx in range(min(len(df), 80)):
        values = [_norm(v) for v in df.iloc[idx].tolist()]
        canonical = [_canonical_column(v) for v in values]
        product_count = canonical.count("product")
        has_url_or_article = "url" in canonical or "article" in canonical
        if product_count >= 1 and has_url_or_article:
            rows.append(idx)
    return rows


def _read_blocks_from_header(df: pd.DataFrame, sheet_name: str, header_idx: int) -> list[dict[str, str | None]]:
    headers = df.iloc[header_idx].tolist()
    canonical = [_canonical_column(h) for h in headers]
    product_cols = [i for i, c in enumerate(canonical) if c == "product"]
    partials: list[dict[str, str | None]] = []

    for block_no, product_col in enumerate(product_cols):
        next_product_col = product_cols[block_no + 1] if block_no + 1 < len(product_cols) else len(headers)
        block_cols = list(range(product_col, next_product_col))

        # Stop block on a fully blank separator column at the beginning of the next group.
        useful_cols = [c for c in block_cols if canonical[c] is not None]
        if not useful_cols:
            continue

        col_map: dict[str, int] = {}
        for col in useful_cols:
            kind = canonical[col]
            if kind and kind not in col_map:
                col_map[kind] = col

        # In some user files the category column has no header, but values like
        # "Новинка" / "Фокусные товары" / "Проблемные продукты" are placed
        # right after the article column. Detect this unlabeled category column.
        if "category" not in col_map:
            known = set(col_map.values())
            candidate_cols = [c for c in block_cols if c not in known and canonical[c] is None]
            for candidate in candidate_cols:
                sample = [str(v).strip() for v in df.iloc[header_idx + 1: min(len(df), header_idx + 15), candidate].tolist()]
                non_empty = [v for v in sample if v]
                if non_empty and any(_looks_like_category(v) for v in non_empty):
                    col_map["category"] = candidate
                    break

        if "product" not in col_map or ("url" not in col_map and "article" not in col_map):
            continue

        context_values: list[object] = []
        for r in range(max(0, header_idx - 3), header_idx + 1):
            context_values.extend(df.iloc[r, max(0, product_col - 1): min(df.shape[1], next_product_col + 1)].tolist())
        marketplace = _marketplace_from_context(sheet_name, context_values)

        for row_idx in range(header_idx + 1, len(df)):
            row = df.iloc[row_idx]
            product_name_raw = _cell(row, col_map.get("product"))
            url = _cell(row, col_map.get("url")) or None
            article = _cell(row, col_map.get("article")) or None
            category = _cell(row, col_map.get("category")) or None
            variant = _cell(row, col_map.get("variant")) or _extract_variant(product_name_raw)

            # Skip empty rows and accidental repeated headers.
            if not product_name_raw and not url and not article:
                continue
            if _canonical_column(product_name_raw) == "product":
                continue

            row_marketplace = marketplace or _infer_marketplace_from_url(url)
            product_name = _clean_product_name(product_name_raw)
            partials.append({
                "name": product_name,
                "category": category,
                "variant": variant,
                "marketplace": row_marketplace,
                "url": url,
                "article": article,
            })

    return partials


def _cell(row: pd.Series, col: int | None) -> str:
    if col is None:
        return ""
    value = row.iloc[col]
    return "" if _is_empty(value) else str(value).strip()


def _infer_marketplace_from_url(url: str | None) -> str | None:
    lower = (url or "").lower()
    if "wildberries" in lower or "wb.ru" in lower:
        return "WB"
    if "ozon" in lower:
        return "Ozon"
    return None

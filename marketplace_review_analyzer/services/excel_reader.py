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


def _canonical_column(name: object) -> str | None:
    normalized = _norm(name)
    for canonical, variants in COLUMN_SYNONYMS.items():
        if any(v in normalized for v in variants):
            return canonical
    return None


def _marketplace_from_context(sheet_name: str, columns: list[str], row: pd.Series | None = None) -> str | None:
    text = " ".join([sheet_name] + columns + ([] if row is None else [str(v) for v in row.to_list()[:3]]))
    lower = text.lower()
    if "wildberries" in lower or "wb" in lower or "вб" in lower or "вайлд" in lower:
        return "WB"
    if "ozon" in lower or "озон" in lower:
        return "Ozon"
    return None


def read_products(excel_file: str | Path | bytes) -> list[Product]:
    xls = pd.ExcelFile(excel_file)
    partials: list[dict[str, str | None]] = []

    for sheet_name in xls.sheet_names:
        raw = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str).fillna("")
        if raw.empty:
            continue
        header_rows = _detect_header_rows(raw)
        for header_idx in header_rows:
            headers = [_norm(v) for v in raw.iloc[header_idx].tolist()]
            canonical = [_canonical_column(h) for h in headers]
            if "product" not in canonical or ("url" not in canonical and "article" not in canonical):
                continue
            marketplace = _marketplace_from_context(sheet_name, headers)
            data = raw.iloc[header_idx + 1 :].copy()
            data.columns = [c or f"col_{i}" for i, c in enumerate(canonical)]
            for _, row in data.iterrows():
                if not any(_norm(v) for v in row.to_list()):
                    continue
                row_marketplace = marketplace or _marketplace_from_context(sheet_name, headers, row)
                product_name = str(row.get("product", "")).strip()
                url = str(row.get("url", "")).strip() or None
                article = str(row.get("article", "")).strip() or None
                category = str(row.get("category", "")).strip() or None
                variant = str(row.get("variant", "")).strip() or _extract_variant(product_name)
                if not product_name and not (url or article):
                    continue
                product_name = _clean_product_name(product_name)
                if not row_marketplace:
                    row_marketplace = _infer_marketplace_from_url(url)
                partials.append({
                    "name": product_name,
                    "category": category,
                    "variant": variant,
                    "marketplace": row_marketplace,
                    "url": url,
                    "article": article,
                })

    return _merge_partials(partials)


def _detect_header_rows(df: pd.DataFrame) -> list[int]:
    rows: list[int] = []
    for idx in range(min(len(df), 50)):
        values = [_norm(v) for v in df.iloc[idx].tolist()]
        score = sum(1 for v in values if _canonical_column(v))
        if score >= 2:
            rows.append(idx)
    return rows


def _infer_marketplace_from_url(url: str | None) -> str | None:
    lower = (url or "").lower()
    if "wildberries" in lower or "wb.ru" in lower:
        return "WB"
    if "ozon" in lower:
        return "Ozon"
    return None


def _extract_variant(name: str) -> str | None:
    match = re.search(r"(?:тон|оттенок|цвет)\s*[:№#-]?\s*([\w\-А-Яа-яёЁ ]{1,20})", name or "", flags=re.I)
    return match.group(0).strip() if match else None


def _clean_product_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip()
    name = re.sub(r"\s*[-–—]?\s*(тон|оттенок|цвет)\s*[:№#-]?\s*[\w\-А-Яа-яёЁ ]{1,20}$", "", name, flags=re.I).strip()
    return name or "Без названия"


def _merge_partials(partials: list[dict[str, str | None]]) -> list[Product]:
    merged: dict[tuple[str, str], dict[str, str | None]] = {}
    for item in partials:
        name = item.get("name") or "Без названия"
        variant = item.get("variant") or ""
        key = (_norm(name), _norm(variant))
        entry = merged.setdefault(key, {"name": name, "variant": item.get("variant"), "category": item.get("category")})
        if item.get("category") and category_display(entry.get("category")) == "Без категории":
            entry["category"] = item.get("category")
        if item.get("marketplace") == "WB":
            entry["wb_url"] = item.get("url") or entry.get("wb_url")
            entry["wb_article"] = item.get("article") or entry.get("wb_article")
        elif item.get("marketplace") == "Ozon":
            entry["ozon_url"] = item.get("url") or entry.get("ozon_url")
            entry["ozon_article"] = item.get("article") or entry.get("ozon_article")
        else:
            if _infer_marketplace_from_url(item.get("url")) == "WB":
                entry["wb_url"] = item.get("url") or entry.get("wb_url")
                entry["wb_article"] = item.get("article") or entry.get("wb_article")
            elif _infer_marketplace_from_url(item.get("url")) == "Ozon":
                entry["ozon_url"] = item.get("url") or entry.get("ozon_url")
                entry["ozon_article"] = item.get("article") or entry.get("ozon_article")
    return [Product(**v) for v in merged.values()]

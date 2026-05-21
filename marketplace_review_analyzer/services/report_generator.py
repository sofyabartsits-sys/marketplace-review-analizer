from __future__ import annotations

from datetime import date
from itertools import groupby

from models import ProductReport

CATEGORY_ORDER = ["Новинки", "Фокусные товары", "Проблемные продукты", "Без категории"]


def pluralize_review(count: int) -> str:
    n = abs(count)
    if 11 <= n % 100 <= 14:
        word = "отзывов"
    elif n % 10 == 1:
        word = "отзыв"
    elif 2 <= n % 10 <= 4:
        word = "отзыва"
    else:
        word = "отзывов"
    return f"{count} {word}"


def category_display(category: str | None) -> str:
    raw = (category or "").strip().lower()
    if "нов" in raw:
        return "Новинки"
    if "фокус" in raw:
        return "Фокусные товары"
    if "проблем" in raw:
        return "Проблемные продукты"
    return "Без категории"


def rating_text(value: float | None) -> str:
    if value is None:
        return "нет данных"
    return f"{value:.1f}".replace(".", ",")


def _product_title(report: ProductReport) -> str:
    category = category_display(report.product.category)
    prefix = "Новинка: " if category == "Новинки" else ""
    variant = f" ({report.product.variant})" if report.product.variant else ""
    return f"{prefix}{report.product.name}{variant}"


def generate_text_report(reports: list[ProductReport], date_from: date, date_to: date, title: str = "MAKE UP") -> str:
    lines: list[str] = []
    lines.append(f"{title} ({date_from.strftime('%d.%m')}-{date_to.strftime('%d.%m')})")
    lines.append("")

    sorted_reports = sorted(reports, key=lambda r: (CATEGORY_ORDER.index(category_display(r.product.category)), r.product.name.lower(), r.product.variant or ""))
    for category in CATEGORY_ORDER:
        category_reports = [r for r in sorted_reports if category_display(r.product.category) == category]
        if not category_reports:
            continue
        lines.append(f"{category}:")
        lines.append("")
        for report in category_reports:
            lines.append(_product_title(report))
            lines.append(f"Рейтинг ВБ - {rating_text(report.wb_rating)}")
            lines.append(f"Рейтинг ОЗОН - {rating_text(report.ozon_rating)}")
            if report.problem_groups:
                for group in report.problem_groups:
                    lines.append(f"{pluralize_review(group.count)}: {group.problem}")
            else:
                lines.append("Нет новых негативных отзывов")
            lines.append("")
    return "\n".join(lines).strip() + "\n"

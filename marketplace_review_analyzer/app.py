from __future__ import annotations

import logging
import random
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from models import ProcessingError, Product, ProductReport, Review
from parsers.ozon_parser import OzonParser
from parsers.wb_parser import WildberriesParser
from services.cache_service import CacheService
from services.excel_reader import read_products
from services.export_service import export_docx, export_txt, export_xlsx
from services.problem_counter import count_problem_groups
from services.report_generator import category_display, generate_text_report
from services.review_classifier import is_negative_review

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "logs" / "app.log"
OUTPUT_DIR = BASE_DIR / "outputs"

load_dotenv(BASE_DIR / ".env")
LOG_PATH.parent.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def load_css() -> None:
    css_path = BASE_DIR / "assets" / "style.css"
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def serialize_reviews(reviews: list[Review]) -> list[dict]:
    return [r.model_dump(mode="json") for r in reviews]


def deserialize_reviews(data: list[dict]) -> list[Review]:
    return [Review(**item) for item in data]


def get_cached_rating(cache: CacheService, parser, product: Product, marketplace: str) -> float | None:
    article = product.wb_article if marketplace == "WB" else product.ozon_article
    key = cache.make_key(marketplace, article, None, None, "rating")
    cached = cache.get(key)
    if cached is not None:
        return cached
    rating = parser.get_rating(product)
    cache.set(key, rating)
    return rating


def get_cached_reviews(cache: CacheService, parser, product: Product, marketplace: str, date_from: date, date_to: date) -> list[Review]:
    article = product.wb_article if marketplace == "WB" else product.ozon_article
    key = cache.make_key(marketplace, article, date_from, date_to, "reviews")
    cached = cache.get(key)
    if cached is not None:
        return deserialize_reviews(cached)
    reviews = parser.get_reviews(product, date_from, date_to)
    cache.set(key, serialize_reviews(reviews))
    return reviews


def make_mock_reviews(product: Product, date_from: date, date_to: date) -> list[Review]:
    samples = [
        (2, "Тушь сухая, осыпается и склеивает ресницы"),
        (3, "Сильно липнет, не впитывается, остается пленка"),
        (2, "Дозатор поломан, неудобно распылять на лицо"),
        (3, "Оттенок уходит в рыжину, цвет не совпал"),
        (2, "Нет фиксации, гель не держит брови"),
        (5, "Хороший продукт, понравился"),
    ]
    days = max((date_to - date_from).days, 0)
    result: list[Review] = []
    for rating, text in random.sample(samples, k=min(len(samples), random.randint(1, 4))):
        result.append(Review(
            marketplace=random.choice(["WB", "Ozon"]),
            product_name=product.name,
            product_article=product.wb_article or product.ozon_article,
            rating=rating,
            text=text,
            date=date_from + timedelta(days=random.randint(0, days)),
        ))
    return result


def process_products(products: list[Product], date_from: date, date_to: date, mock_mode: bool) -> tuple[list[ProductReport], list[ProcessingError]]:
    cache = CacheService(BASE_DIR / "outputs" / "cache.json")
    wb_parser = WildberriesParser()
    ozon_parser = OzonParser()
    reports: list[ProductReport] = []
    errors: list[ProcessingError] = []

    progress = st.progress(0)
    status = st.empty()
    stats = {"processed": 0, "errors": 0, "negative": 0}

    for idx, product in enumerate(products, start=1):
        report = ProductReport(product=product)
        reviews: list[Review] = []

        if mock_mode:
            report.wb_rating = round(random.uniform(4.3, 5.0), 1) if product.wb_article or product.wb_url else None
            report.ozon_rating = round(random.uniform(4.3, 5.0), 1) if product.ozon_article or product.ozon_url else None
            reviews = make_mock_reviews(product, date_from, date_to)
        else:
            if product.wb_article or product.wb_url:
                try:
                    report.wb_rating = get_cached_rating(cache, wb_parser, product, "WB")
                    reviews.extend(get_cached_reviews(cache, wb_parser, product, "WB", date_from, date_to))
                except Exception as exc:
                    message = str(exc)
                    logger.exception("WB error for %s", product.name)
                    report.errors.append(f"WB: {message}")
                    errors.append(ProcessingError(product_name=product.name, marketplace="WB", error_message=message))
            if product.ozon_article or product.ozon_url:
                try:
                    report.ozon_rating = get_cached_rating(cache, ozon_parser, product, "Ozon")
                    reviews.extend(get_cached_reviews(cache, ozon_parser, product, "Ozon", date_from, date_to))
                except Exception as exc:
                    message = str(exc)
                    logger.exception("Ozon error for %s", product.name)
                    report.errors.append(f"Ozon: {message}")
                    errors.append(ProcessingError(product_name=product.name, marketplace="Ozon", error_message=message))

        report.negative_reviews = [review for review in reviews if is_negative_review(review)]
        report.problem_groups = count_problem_groups(report.negative_reviews)
        stats["processed"] += 1
        stats["errors"] = len(errors)
        stats["negative"] += len(report.negative_reviews)
        reports.append(report)

        progress.progress(idx / max(len(products), 1))
        status.markdown(
            f"""
            <div class='status-card'>
              <b>Статус обработки</b><br>
              Найдено товаров: {len(products)} · Обработано: {stats['processed']} ·
              Ошибок: {stats['errors']} · Негативных отзывов: {stats['negative']}
            </div>
            """,
            unsafe_allow_html=True,
        )
    return reports, errors


def render_report_cards(reports: list[ProductReport]) -> None:
    for report in reports:
        problems_html = "".join(
            f"<span class='problem-badge'>{g.count} · {g.problem}</span>" for g in report.problem_groups
        ) or "<span class='small-muted'>Нет новых негативных отзывов</span>"
        st.markdown(
            f"""
            <div class='result-card'>
              <h3>{report.product.name}</h3>
              <div class='small-muted'>Категория: {category_display(report.product.category)} · Вариант: {report.product.variant or '—'}</div>
              <hr>
              <b>WB:</b> {report.wb_rating if report.wb_rating is not None else 'нет данных'} &nbsp;&nbsp;
              <b>Ozon:</b> {report.ozon_rating if report.ozon_rating is not None else 'нет данных'} &nbsp;&nbsp;
              <b>Негативных отзывов:</b> {len(report.negative_reviews)}
              <div style='margin-top:12px'>{problems_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def main() -> None:
    st.set_page_config(page_title="Анализ WB / Ozon", page_icon="☕", layout="wide")
    load_css()

    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
    st.title("Анализ рейтингов и негативных отзывов WB / Ozon")
    st.write("Загрузите Excel-файл, выберите период и получите готовый отчёт по рейтингу и проблематикам негативных отзывов.")
    st.markdown("</div>", unsafe_allow_html=True)

    left, right = st.columns([1.2, 1])
    with left:
        uploaded_file = st.file_uploader("Excel-файл со списком товаров", type=["xlsx"])
    with right:
        date_from = st.date_input("Дата начала", value=date.today() - timedelta(days=7))
        date_to = st.date_input("Дата окончания", value=date.today())
        mock_mode = st.toggle("Тестовый режим — данные искусственные", value=False)

    cache = CacheService(BASE_DIR / "outputs" / "cache.json")
    if st.button("Очистить кэш"):
        cache.clear()
        st.success("Кэш очищен")

    if st.button("Сформировать отчёт", type="primary", use_container_width=True):
        if not uploaded_file:
            st.error("Загрузите Excel-файл .xlsx")
            return
        if date_from > date_to:
            st.error("Дата начала не может быть позже даты окончания")
            return

        try:
            buffer = BytesIO(uploaded_file.getvalue())
            products = read_products(buffer)
        except Exception as exc:
            logger.exception("Excel read error")
            st.error(f"Не удалось прочитать Excel: {exc}")
            return

        if not products:
            st.warning("В Excel не найдено товаров. Проверьте заголовки: Продукт, Ссылка, Артикул, Категория.")
            return

        st.session_state["products_found"] = len(products)
        reports, errors = process_products(products, date_from, date_to, mock_mode)
        st.session_state["reports"] = reports
        st.session_state["errors"] = errors
        st.session_state["report_text"] = generate_text_report(reports, date_from, date_to)
        st.session_state["date_from"] = date_from
        st.session_state["date_to"] = date_to

    reports = st.session_state.get("reports")
    if reports:
        st.subheader("Карточки результатов")
        render_report_cards(reports)

        report_text = st.session_state["report_text"]
        st.subheader("Готовый текстовый отчёт")
        st.text_area("Текст отчёта", value=report_text, height=420)

        txt_path = export_txt(report_text, OUTPUT_DIR / "report.txt")
        docx_path = export_docx(report_text, OUTPUT_DIR / "report.docx")
        xlsx_path = export_xlsx(reports, OUTPUT_DIR / "report.xlsx")

        c1, c2, c3 = st.columns(3)
        c1.download_button("Скачать TXT", txt_path.read_bytes(), file_name="report.txt")
        c2.download_button("Скачать DOCX", docx_path.read_bytes(), file_name="report.docx")
        c3.download_button("Скачать XLSX", xlsx_path.read_bytes(), file_name="report.xlsx")

        errors = st.session_state.get("errors", [])
        if errors:
            st.subheader("Ошибки обработки")
            st.dataframe([e.model_dump() for e in errors], use_container_width=True)


if __name__ == "__main__":
    main()

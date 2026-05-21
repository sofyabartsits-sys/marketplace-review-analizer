from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup

from models import Product, Review
from parsers.base import MarketplaceParser

logger = logging.getLogger(__name__)


class OzonParser(MarketplaceParser):
    marketplace_name = "Ozon"

    def _article(self, product: Product) -> str | None:
        if product.ozon_article:
            return str(product.ozon_article).strip()
        if product.ozon_url:
            for pattern in [r"/product/[^/]+-(\d+)/", r"sku=(\d+)", r"/(\d+)(?:/|$)"]:
                match = re.search(pattern, product.ozon_url)
                if match:
                    return match.group(1)
        return None

    def get_rating(self, product: Product) -> float | None:
        article = self._article(product)
        if not article and not product.ozon_url:
            raise ValueError("Не указан Ozon артикул или ссылка")

        client_id = os.getenv("OZON_CLIENT_ID", "").strip()
        api_key = os.getenv("OZON_API_KEY", "").strip()
        if client_id and api_key and article:
            return self._get_rating_from_seller_api(article, client_id, api_key)

        # Public HTML fallback. Ozon often blocks/changes HTML; in production prefer Seller API.
        if not product.ozon_url:
            raise ValueError("Для публичного fallback Ozon нужна ссылка")
        html = self.session.get(product.ozon_url, timeout=self.timeout).text
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ")
        match = re.search(r"(?:рейтинг|rating)[^0-9]{0,20}([1-5][,.]\d)", text, flags=re.I)
        if match:
            return float(match.group(1).replace(",", "."))
        raise ValueError("Не удалось получить рейтинг Ozon: HTML изменился или запрос заблокирован")

    def _get_rating_from_seller_api(self, article: str, client_id: str, api_key: str) -> float | None:
        # Seller API has product info endpoints but exact availability depends on account permissions.
        url = "https://api-seller.ozon.ru/v2/product/info"
        headers = {"Client-Id": client_id, "Api-Key": api_key}
        payload: dict[str, Any] = {}
        if article.isdigit():
            payload["product_id"] = int(article)
        else:
            payload["offer_id"] = article
        data = self._post_json(url, payload=payload, headers=headers)
        result = data.get("result") or {}
        rating = result.get("rating") or result.get("rating_value") or result.get("reviews_rating")
        return float(rating) if rating not in (None, "") else None

    def get_reviews(self, product: Product, date_from: date, date_to: date) -> list[Review]:
        article = self._article(product)
        client_id = os.getenv("OZON_CLIENT_ID", "").strip()
        api_key = os.getenv("OZON_API_KEY", "").strip()
        if client_id and api_key:
            return self._get_reviews_from_seller_api(product, article, date_from, date_to, client_id, api_key)
        raise ValueError(
            "Для выгрузки отзывов Ozon в обычном режиме укажите OZON_CLIENT_ID и OZON_API_KEY. "
            "Публичный HTML Ozon нестабилен; фейковые данные доступны только в mock-режиме."
        )

    def _get_reviews_from_seller_api(
        self,
        product: Product,
        article: str | None,
        date_from: date,
        date_to: date,
        client_id: str,
        api_key: str,
    ) -> list[Review]:
        headers = {"Client-Id": client_id, "Api-Key": api_key}
        url = "https://api-seller.ozon.ru/v1/review/list"
        payload: dict[str, Any] = {"limit": 100, "sort_dir": "DESC", "status": "ALL"}
        if article:
            # Depending on account API version it can be sku, product_id, or offer_id.
            payload["sku"] = int(article) if article.isdigit() else article

        reviews: list[Review] = []
        last_id: str | None = None
        for _ in range(50):
            if last_id:
                payload["last_id"] = last_id
            data = self._post_json(url, payload=payload, headers=headers)
            result = data.get("result") or {}
            raw_reviews = result.get("reviews") or []
            if not raw_reviews:
                break
            reviews.extend(self._normalize_reviews(raw_reviews, product, article, date_from, date_to))
            last_id = result.get("last_id")
            if not last_id:
                break
        return reviews

    def _normalize_reviews(
        self, raw_reviews: list[dict[str, Any]], product: Product, article: str | None, date_from: date, date_to: date
    ) -> list[Review]:
        reviews: list[Review] = []
        for item in raw_reviews:
            try:
                dt_raw = item.get("published_at") or item.get("created_at") or item.get("date")
                if not dt_raw:
                    logger.warning("Ozon: не распознана дата отзыва: %s", item)
                    continue
                dt = datetime.fromisoformat(str(dt_raw).replace("Z", "+00:00")).date()
                if not (date_from <= dt <= date_to):
                    continue
                text = " ".join(filter(None, [item.get("text"), item.get("pros"), item.get("cons")])).strip()
                reviews.append(Review(
                    marketplace="Ozon",
                    product_name=product.name,
                    product_article=article,
                    rating=item.get("rating"),
                    text=text,
                    date=dt,
                ))
            except Exception as exc:
                logger.exception("Ozon: ошибка нормализации отзыва: %s", exc)
        return reviews

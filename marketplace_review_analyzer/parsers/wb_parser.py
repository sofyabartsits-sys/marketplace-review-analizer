from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from typing import Any

from models import Product, Review
from parsers.base import MarketplaceParser

logger = logging.getLogger(__name__)


class WildberriesParser(MarketplaceParser):
    marketplace_name = "WB"

    def _article(self, product: Product) -> str | None:
        if product.wb_article:
            return str(product.wb_article).strip()
        if product.wb_url:
            match = re.search(r"catalog/(\d+)", product.wb_url)
            if match:
                return match.group(1)
        return None

    def get_rating(self, product: Product) -> float | None:
        article = self._article(product)
        if not article:
            raise ValueError("Не указан WB артикул или ссылка")

        # Public card endpoint. WB can change it; Seller API token can be added later without changing interface.
        url = "https://card.wb.ru/cards/v2/detail"
        params = {"appType": 1, "curr": "rub", "dest": -1257786, "spp": 30, "nm": article}
        data = self._get_json(url, params=params)
        products = data.get("data", {}).get("products", [])
        if not products:
            raise ValueError(f"WB товар не найден: {article}")
        rating = products[0].get("reviewRating") or products[0].get("rating")
        return float(rating) if rating is not None else None

    def get_reviews(self, product: Product, date_from: date, date_to: date) -> list[Review]:
        article = self._article(product)
        if not article:
            raise ValueError("Не указан WB артикул или ссылка")

        token = os.getenv("WB_API_TOKEN", "").strip()
        if token:
            return self._get_reviews_from_seller_api(product, article, date_from, date_to, token)

        # Fallback public endpoint. It can be rate-limited or changed by WB.
        url = f"https://feedbacks1.wb.ru/feedbacks/v1/{article}"
        data = self._get_json(url)
        raw_reviews = data.get("feedbacks") or data.get("data", {}).get("feedbacks") or []
        return self._normalize_reviews(raw_reviews, product, article, date_from, date_to)

    def _get_reviews_from_seller_api(
        self, product: Product, article: str, date_from: date, date_to: date, token: str
    ) -> list[Review]:
        url = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks"
        headers = {"Authorization": token}
        params = {"isAnswered": "false", "take": 5000, "skip": 0, "nmId": article, "order": "dateDesc"}
        data = self._get_json(url, headers=headers, params=params)
        raw_reviews = data.get("data", {}).get("feedbacks") or data.get("feedbacks") or []
        return self._normalize_reviews(raw_reviews, product, article, date_from, date_to)

    def _normalize_reviews(
        self, raw_reviews: list[dict[str, Any]], product: Product, article: str, date_from: date, date_to: date
    ) -> list[Review]:
        reviews: list[Review] = []
        for item in raw_reviews:
            try:
                dt_raw = item.get("createdDate") or item.get("date") or item.get("createdAt")
                if not dt_raw:
                    logger.warning("WB: не распознана дата отзыва: %s", item)
                    continue
                dt = datetime.fromisoformat(str(dt_raw).replace("Z", "+00:00")).date()
                if not (date_from <= dt <= date_to):
                    continue
                text = " ".join(filter(None, [
                    item.get("text"), item.get("pros"), item.get("cons"),
                    item.get("answer", {}).get("text") if isinstance(item.get("answer"), dict) else None,
                ])).strip()
                reviews.append(Review(
                    marketplace="WB",
                    product_name=product.name,
                    product_article=article,
                    rating=item.get("productValuation") or item.get("rating"),
                    text=text,
                    date=dt,
                ))
            except Exception as exc:
                logger.exception("WB: ошибка нормализации отзыва: %s", exc)
        return reviews

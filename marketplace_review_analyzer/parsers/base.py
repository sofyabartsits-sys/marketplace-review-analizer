from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from models import Product, Review

logger = logging.getLogger(__name__)


class MarketplaceParser(ABC):
    marketplace_name: str

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept": "application/json,text/html,*/*",
        })

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((requests.RequestException, TimeoutError)),
        reraise=True,
    )
    def _get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.session.get(url, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        if not response.text.strip():
            raise ValueError(f"Пустой ответ от {self.marketplace_name}: {url}")
        return response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((requests.RequestException, TimeoutError)),
        reraise=True,
    )
    def _post_json(self, url: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        response = self.session.post(url, json=payload or {}, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        if not response.text.strip():
            raise ValueError(f"Пустой ответ от {self.marketplace_name}: {url}")
        return response.json()

    @abstractmethod
    def get_rating(self, product: Product) -> float | None:
        raise NotImplementedError

    @abstractmethod
    def get_reviews(self, product: Product, date_from: date, date_to: date) -> list[Review]:
        raise NotImplementedError

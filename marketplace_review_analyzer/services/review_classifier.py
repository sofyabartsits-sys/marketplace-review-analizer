from __future__ import annotations

import os
import re
from functools import lru_cache

from models import Review

PROBLEM_PATTERNS: dict[str, list[str]] = {
    "плохое качество": [r"плох(ое|ая|ой).*качеств", r"некачествен", r"ужасн", r"брак"],
    "плохой эффект на ресницах": [r"ресниц.*нет.*эффект", r"не удлин", r"не прида[её]т.*об[ъь]ем"],
    "осыпается": [r"осып", r"крош", r"сып.*к вечеру"],
    "склеивает": [r"скле", r"слипа.*ресниц", r"паучьи лап"],
    "слишком сухая": [r"сух(ая|ой|оват)", r"засох", r"сухая тушь"],
    "не фиксирует": [r"не фикс", r"нет фиксац", r"держит плохо", r"не держит"],
    "сильно липнет": [r"липк", r"сильно лип", r"кле[и]?тся"],
    "не впитывается": [r"не впит", r"плохо впит", r"пленк"],
    "скатывается тон": [r"скатыв", r"катыш", r"тон.*скат"],
    "плохо пахнет": [r"плохо пах", r"вон", r"неприятн.*запах"],
    "не понравился аромат": [r"не понрав.*аромат", r"аромат.*не понрав"],
    "странный аромат": [r"странн.*аромат", r"странн.*запах"],
    "щиплет губы": [r"щип.*губ", r"жж[её]т.*губ", r"пек.*губ"],
    "неравномерно наносится": [r"неравномер", r"пятн", r"полос(ит|ами)", r"плохо нанос"],
    "нестойкая": [r"нестойк", r"быстро стира", r"не держится", r"сходит"],
    "растекается на губах": [r"растека", r"теч[её]т.*губ", r"расплыва"],
    "поломан дозатор": [r"дозатор.*(слом|полом|не работ)", r"слом.*дозатор"],
    "неудобно распылять на лицо": [r"неудоб.*распыл", r"плю[её]тся", r"стру[её]й", r"распылитель"],
    "отсутствует матирование": [r"нет матир", r"не матир", r"блестит", r"жирный блеск"],
    "проблема с оттенком": [r"оттен(ок|ка).*не", r"цвет.*не", r"не тот цвет", r"не совпал.*цвет"],
    "уходит в рыжину": [r"рыжин", r"рыж(ий|ая)", r"оранж"],
    "белит губы": [r"белит.*губ", r"белес", r"белые губы"],
    "плохо лежит на губах": [r"плохо лежит.*губ", r"забива.*склад", r"подчеркива.*шелуш"],
    "проблема с кисточкой": [r"кисточк.*(плох|неудоб|жестк|лезет)", r"ворс.*лезет"],
    "нет результата": [r"нет результат", r"не работает", r"ноль эффект", r"бесполез"],
    "проблема с упаковкой": [r"упаковк.*(плох|мята|поврежд|разбит)", r"приш[её]л.*поврежд"],
}

NEGATIVE_HINTS = [
    r"не понрав", r"ужас", r"плохо", r"разочар", r"верну", r"не рекоменд", r"брак",
    r"слом", r"не работает", r"запах", r"сух", r"лип", r"скат", r"осып", r"щип",
    r"растека", r"не держ", r"не фикс", r"нет эффект", r"качество",
]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


@lru_cache(maxsize=4096)
def classify_problems_text(text: str) -> tuple[str, ...]:
    normalized = normalize_text(text)
    problems: list[str] = []
    for problem, patterns in PROBLEM_PATTERNS.items():
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns):
            problems.append(problem)
    return tuple(dict.fromkeys(problems))


def is_negative_review(review: Review) -> bool:
    if review.rating is not None:
        try:
            if float(review.rating) <= 3:
                return True
        except (TypeError, ValueError):
            pass
    text = normalize_text(review.text)
    if not text:
        return False
    if classify_problems_text(text):
        return True
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in NEGATIVE_HINTS)


def classify_problems(review: Review) -> list[str]:
    problems = list(classify_problems_text(review.text))
    if problems:
        return problems
    if os.getenv("OPENAI_API_KEY"):
        # Hook for LLM/NLP classifier. Kept intentionally non-blocking: no fake categories are invented.
        # Add an implementation here without changing problem_counter/report_generator.
        pass
    return ["другая проблема"]

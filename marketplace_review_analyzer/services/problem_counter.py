from __future__ import annotations

from collections import defaultdict

from models import ProblemGroup, Review
from services.review_classifier import classify_problems


def count_problem_groups(negative_reviews: list[Review], max_examples: int = 3) -> list[ProblemGroup]:
    counters: dict[str, int] = defaultdict(int)
    examples: dict[str, list[str]] = defaultdict(list)

    for review in negative_reviews:
        problems = classify_problems(review)
        for problem in problems:
            counters[problem] += 1
            if review.text and len(examples[problem]) < max_examples:
                examples[problem].append(review.text[:500])

    groups = [ProblemGroup(problem=problem, count=count, examples=examples[problem]) for problem, count in counters.items()]
    groups.sort(key=lambda group: (-group.count, group.problem))
    return groups

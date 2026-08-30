"""Detección de URLs duplicadas dentro del dataset."""

from collections import Counter


def find_duplicate_urls(records: list[dict], url_key: str = "URL") -> list[dict]:
    urls = [r.get(url_key) for r in records if r.get(url_key)]
    counts = Counter(urls)
    duplicadas = {u for u, c in counts.items() if c > 1}
    return [r for r in records if r.get(url_key) in duplicadas]

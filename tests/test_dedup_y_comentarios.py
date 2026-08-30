import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.dedup import find_duplicate_urls
from src.scraper.base_scraper import FetchResult


def test_sin_duplicados():
    registros = [{"URL": "https://a.com/1"}, {"URL": "https://a.com/2"}]
    assert find_duplicate_urls(registros) == []


def test_detecta_url_duplicada():
    registros = [
        {"URL": "https://a.com/1", "n": 1},
        {"URL": "https://a.com/1", "n": 2},
        {"URL": "https://a.com/2", "n": 3},
    ]
    dup = find_duplicate_urls(registros)
    assert len(dup) == 2
    assert all(r["URL"] == "https://a.com/1" for r in dup)


def test_comentario_personal_se_preserva_textual():
    """El comentario personal nunca debe corregirse ni resumirse."""
    from src.scraper.record_builder import build_record

    comentario_original = "Comentario de prueba, con signos!! y mayúsculas RARAS."
    planilla_row = {
        "URL": "https://www.remax.com.ar/listings/fake-test-url",
        "Tipo": "Casa",
        "Localidad / Barrio": "Lanús",
        "Fuente": "RE/MAX",
        "Comentario personal": comentario_original,
        "Ranking": 1,
        "Prioridad de zona": "1 - Lanús",
    }

    fake_fetch = FetchResult(
        url=planilla_row["URL"],
        scrape_status="ERROR",
        error="simulado en test, sin red",
    )

    with patch("src.scraper.record_builder.base_scraper.fetch", return_value=fake_fetch):
        record = build_record(planilla_row, use_cache=False)

    assert record["comentario_personal"] == comentario_original


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    ok, fail = 0, 0
    for t in tests:
        try:
            t()
            ok += 1
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            fail += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            fail += 1
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{ok} OK, {fail} FAIL de {ok + fail} tests")

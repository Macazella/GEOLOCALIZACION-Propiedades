"""
Cubre apply_geocode_review_reasons() sin red: la mini-validación real
sobre BuscadorProp/O'Higgins terminó con geocode_status=EXACT (Nominatim
sí encontró la dirección), así que la rama NOT_FOUND no se ejerció en
vivo. Este test prueba esa rama de forma determinística.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.geocoding.geocoder import apply_geocode_review_reasons


def test_geocode_not_found_activa_needs_manual_review():
    record = {"geocode_status": "NOT_FOUND", "needs_manual_review": False, "needs_manual_review_reasons": []}
    apply_geocode_review_reasons(record)
    assert record["needs_manual_review"] is True
    assert "geocode_not_found" in record["needs_manual_review_reasons"]


def test_geocode_error_activa_needs_manual_review():
    record = {"geocode_status": "ERROR", "needs_manual_review": False, "needs_manual_review_reasons": []}
    apply_geocode_review_reasons(record)
    assert record["needs_manual_review"] is True
    assert "geocode_error" in record["needs_manual_review_reasons"]


def test_geocode_exact_no_agrega_motivo():
    record = {"geocode_status": "EXACT", "needs_manual_review": False, "needs_manual_review_reasons": []}
    apply_geocode_review_reasons(record)
    assert record["needs_manual_review"] is False
    assert record["needs_manual_review_reasons"] == []


def test_geocode_not_found_preserva_razones_previas():
    record = {
        "geocode_status": "NOT_FOUND",
        "needs_manual_review": True,
        "needs_manual_review_reasons": ["conflicto_direccion"],
    }
    apply_geocode_review_reasons(record)
    assert record["needs_manual_review_reasons"] == ["conflicto_direccion", "geocode_not_found"]


def test_geocode_no_duplica_motivo_si_se_llama_dos_veces():
    record = {"geocode_status": "NOT_FOUND", "needs_manual_review": False, "needs_manual_review_reasons": []}
    apply_geocode_review_reasons(record)
    apply_geocode_review_reasons(record)
    assert record["needs_manual_review_reasons"].count("geocode_not_found") == 1


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
    print(f"\n{ok} OK, {fail} FAIL de {ok + fail} tests")

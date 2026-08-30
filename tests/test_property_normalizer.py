import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.normalization import property_normalizer as prop


def test_tipo_casa():
    r = prop.normalize_tipo("Venta Casa 3 Ambientes en Lanús")
    assert r["tipo_propiedad_normalizado"] == "CASA"
    assert r["tipo_propiedad_original"] == "Casa"


def test_tipo_duplex_familia_casa():
    r = prop.normalize_tipo("Dúplex en Lanusita 2 amb posible 3")
    assert r["tipo_propiedad_original"] == "Duplex"
    assert r["tipo_propiedad_normalizado"] == "CASA"


def test_tipo_ph():
    r = prop.normalize_tipo("Venta PH 2 ambientes y medio en Almagro")
    assert r["tipo_propiedad_normalizado"] == "PH"


def test_tipo_departamento():
    r = prop.normalize_tipo("Departamento de 2 ambientes en Lanús")
    assert r["tipo_propiedad_normalizado"] == "DEPARTAMENTO"


def test_tipo_loft_familia_departamento():
    r = prop.normalize_tipo("Loft luminoso a estrenar")
    assert r["tipo_propiedad_original"] == "Loft"
    assert r["tipo_propiedad_normalizado"] == "DEPARTAMENTO"


def test_tipo_ausente():
    r = prop.normalize_tipo(None)
    assert r["tipo_propiedad_original"] is None
    assert r["tipo_propiedad_normalizado"] == "OTRO"


def test_precio_usd():
    r = prop.normalize_precio("Venta USD 48.000 - Excelente PH")
    assert r["precio"] == 48000
    assert r["moneda"] == "USD"


def test_precio_us_dolar_variant():
    r = prop.normalize_precio("U$S 65.000")
    assert r["precio"] == 65000
    assert r["moneda"] == "USD"


def test_precio_sin_dato():
    r = prop.normalize_precio("Consultar precio")
    assert r["precio"] is None
    assert r["moneda"] is None


def test_ambientes_y_superficie():
    r = prop.normalize_ambientes_superficie("Casa de 3 ambientes, 2 dormitorios, 1 baño, 120 m2 totales")
    assert r["ambientes"] == 3
    assert r["dormitorios"] == 2
    assert r["banos"] == 1
    assert r["superficie_total_m2"] == 120.0


def test_ambientes_ausentes_son_none_no_cero():
    r = prop.normalize_ambientes_superficie("Terreno en venta, apto construcción")
    assert r["ambientes"] is None
    assert r["dormitorios"] is None


def test_amenity_cochera_detectada():
    r = prop.normalize_amenities("Casa con cochera y patio")
    assert r["cochera"] is True
    assert r["patio"] is True
    assert r["terraza"] is None  # no mencionado -> None, no False


def test_amenity_apto_credito():
    r = prop.normalize_amenities("Apto crédito, excelente ubicación")
    assert r["apto_credito"] is True


# --- Negaciones de apto_credito (bug confirmado en piloto v2) ---

def test_apto_credito_negacion_no_apto_credito():
    r = prop.normalize_amenities("Casa a la venta. NO APTO CREDITO.")
    assert r["apto_credito"] is False


def test_apto_credito_negacion_no_es_apto_credito_bancario():
    r = prop.normalize_amenities("NO ES APTO CREDITO BANCARIO.")
    assert r["apto_credito"] is False


def test_apto_credito_negacion_no_apto_a_credito():
    r = prop.normalize_amenities("No apto a crédito, solo contado")
    assert r["apto_credito"] is False


def test_apto_credito_negacion_no_apto_para_credito():
    r = prop.normalize_amenities("No apto para crédito")
    assert r["apto_credito"] is False


def test_apto_credito_negacion_no_es_apto_para_credito():
    r = prop.normalize_amenities("No es apto para crédito")
    assert r["apto_credito"] is False


def test_apto_credito_negacion_no_califica_para_credito():
    r = prop.normalize_amenities("La propiedad no califica para crédito hipotecario")
    assert r["apto_credito"] is False


def test_apto_credito_afirmacion_sigue_funcionando():
    """El fix de negaciones no debe romper el caso afirmativo normal."""
    r = prop.normalize_amenities("Hermosa casa, apto crédito, a estrenar")
    assert r["apto_credito"] is True


def test_apto_credito_no_mencionado_es_none():
    r = prop.normalize_amenities("Hermosa casa a estrenar, sin mención de financiación")
    assert r["apto_credito"] is None


# --- Superficies: fuente después del calificador, no antes (bug piloto v2) ---

def test_superficie_total_cubierta_descubierta_coviella():
    texto = "Casa venta Lanus Este de 4 ambientes, total 139 m2, cubierta 67 m2, libre 72 m2"
    r = prop.normalize_ambientes_superficie(texto)
    assert r["superficie_total_m2"] == 139.0
    assert r["superficie_cubierta_m2"] == 67.0
    assert r["superficie_descubierta_m2"] == 72.0


def test_superficie_absurda_invalida_los_tres_componentes():
    texto = "Departamento Tipo Casa venta Lanus Este de 3 ambientes, total 1 m2, cubierta 1 m2, libre 1 m2"
    r = prop.normalize_ambientes_superficie(texto)
    assert r["superficie_total_m2"] is None
    assert r["superficie_cubierta_m2"] is None
    assert r["superficie_descubierta_m2"] is None
    assert r["superficie_total_confidence"] == prop.INVALIDA_INCONSISTENTE_CON_AMBIENTES
    assert r["superficie_cubierta_confidence"] == prop.INVALIDA_INCONSISTENTE_CON_AMBIENTES
    assert r["superficie_descubierta_confidence"] == prop.INVALIDA_INCONSISTENTE_CON_AMBIENTES


def test_superficie_cubierta_no_puede_superar_total():
    texto = "Casa de 3 ambientes, total 80 m2, cubierta 200 m2"
    r = prop.normalize_ambientes_superficie(texto)
    assert r["superficie_total_m2"] == 80.0
    assert r["superficie_cubierta_m2"] is None
    assert r["superficie_cubierta_confidence"] == prop.INVALIDA_MAYOR_QUE_TOTAL


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

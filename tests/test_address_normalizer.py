import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.normalization import address_normalizer as addr


def test_lanus():
    r = addr.normalize_localidad_o_caba("Lanús")
    assert r["localidad"] == "Lanús"
    assert r["partido"] == "Lanús"
    assert r["provincia"] == "Buenos Aires"


def test_lanus_oeste():
    r = addr.normalize_localidad_o_caba("Lanús Oeste")
    assert r["localidad"] == "Lanús Oeste"
    assert r["partido"] == "Lanús"


def test_remedios_de_escalada():
    r = addr.normalize_localidad_o_caba("Remedios de Escalada")
    assert r["partido"] == "Lanús"


def test_lomas_de_zamora():
    r = addr.normalize_localidad_o_caba("Lomas de Zamora")
    assert r["partido"] == "Lomas de Zamora"


def test_temperley():
    r = addr.normalize_localidad_o_caba("Temperley")
    assert r["partido"] == "Lomas de Zamora"


def test_caba_variantes():
    for variante in ["CABA", "Capital Federal", "Ciudad Autónoma de Buenos Aires"]:
        r = addr.normalize_localidad_o_caba(variante)
        assert r["provincia"] == "Ciudad Autónoma de Buenos Aires"
        assert r["partido"] is None


def test_caba_con_barrio():
    r = addr.normalize_localidad_o_caba("Almagro (CABA)")
    assert r["localidad"] == "Almagro"
    assert r["provincia"] == "Ciudad Autónoma de Buenos Aires"


def test_localidad_no_catalogada_no_inventa_partido():
    r = addr.normalize_localidad_o_caba("Villa Elisa")
    assert r["localidad"] == "Villa Elisa"
    assert r["partido"] is None  # nunca se inventa


def test_parse_calle_numero_exacto():
    p = addr.parse_calle_numero("Sarandí 206")
    assert p.calle == "Sarandí"
    assert p.numero == "206"
    assert p.es_aproximado is False


def test_parse_calle_numero_aproximado_al():
    p = addr.parse_calle_numero("Av. Hipólito Yrigoyen al 4000")
    assert p.calle == "Av. Hipólito Yrigoyen"
    assert p.numero == "4000"
    assert p.es_aproximado is True


def test_parse_calle_sin_numero():
    p = addr.parse_calle_numero("Av. Hipólito Yrigoyen")
    assert p.calle == "Av. Hipólito Yrigoyen"
    assert p.numero is None


def test_build_address_exact():
    r = addr.build_normalized_address("Sarandí", "206", False, "Balvanera", None, "Ciudad Autónoma de Buenos Aires")
    assert r["address_precision"] == "EXACT_ADDRESS"
    assert "Sarandí 206" in r["address_normalized"]


def test_build_address_block_approximation():
    r = addr.build_normalized_address("Av. Hipólito Yrigoyen", "4000", True, "Lanús Oeste", "Lanús", "Buenos Aires")
    assert r["address_precision"] == "BLOCK_APPROXIMATION"


def test_build_address_street_only():
    r = addr.build_normalized_address("Av. Hipólito Yrigoyen", None, False, "Lanús", "Lanús", "Buenos Aires")
    assert r["address_precision"] == "STREET_ONLY"


def test_build_address_locality_only():
    r = addr.build_normalized_address(None, None, False, "Lanús", "Lanús", "Buenos Aires")
    assert r["address_precision"] == "LOCALITY_ONLY"


def test_build_address_unknown():
    r = addr.build_normalized_address(None, None, False, None, None, None)
    assert r["address_precision"] == "UNKNOWN"
    assert r["address_normalized"] is None


def test_no_concatenacion_absurda():
    """No debe repetir localidad/partido/provincia si son iguales."""
    r = addr.build_normalized_address("Calle Falsa", "123", False, "Lanús", "Lanús", "Buenos Aires")
    partes = r["address_normalized"].split(", ")
    assert len(partes) == len(set(partes))


# --- Fixes post piloto v2 ---

def test_localidad_placeholder_no_identificado_es_none():
    """'No identificado' es el placeholder de la planilla, no una localidad real."""
    r = addr.normalize_localidad_o_caba("No identificado")
    assert r["localidad"] is None
    assert r["partido"] is None
    assert r["provincia"] is None


def test_localidad_placeholder_case_insensitive():
    r = addr.normalize_localidad_o_caba("SIN ESPECIFICAR")
    assert r["localidad"] is None


def test_build_address_calle_numero_sin_geo_no_es_exact():
    """Calle+número sin NINGÚN dato geográfico no alcanza para EXACT_ADDRESS
    (la misma calle puede repetirse en decenas de localidades)."""
    r = addr.build_normalized_address("Ohiggins", "49", False, None, None, None)
    assert r["address_precision"] == "STREET_ONLY"
    assert r["address_precision"] != "EXACT_ADDRESS"


def test_canonicalize_calle_ohiggins():
    assert addr.canonicalize_calle("Ohiggins") == "O'Higgins"
    assert addr.canonicalize_calle("ohiggins") == "O'Higgins"


def test_canonicalize_calle_desconocida_no_se_toca():
    assert addr.canonicalize_calle("Sarandí") == "Sarandí"


def test_strip_known_brand_prefix_buscadorprop():
    r = addr.strip_known_brand_prefix("BuscadorProp Ohiggins", fuente_sitio="BuscadorProp")
    assert r == "Ohiggins"


def test_strip_known_brand_prefix_fuente_dinamica():
    """El nombre de la inmobiliaria puntual (columna Fuente) también se limpia,
    sin necesidad de estar hardcodeado en la lista genérica."""
    r = addr.strip_known_brand_prefix("Coviella Propiedades Sarandí", fuente_sitio="Coviella Propiedades")
    assert r == "Sarandí"


def test_strip_known_brand_prefix_sin_brand_no_cambia():
    r = addr.strip_known_brand_prefix("Sarandí", fuente_sitio="BuscadorProp")
    assert r == "Sarandí"


if __name__ == "__main__":
    import inspect

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

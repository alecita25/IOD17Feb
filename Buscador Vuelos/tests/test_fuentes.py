"""Pruebas de las fuentes con respuestas de ejemplo (sin conectarse a internet).

Ejecutar desde la carpeta "Buscador Vuelos":  python -m pytest tests
"""

import sys
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import buscador_vuelos as bv  # noqa: E402
import fuentes  # noqa: E402

FECHA = date(2026, 12, 10)

SERPAPI = {
    "best_flights": [{
        "flights": [
            {"departure_airport": {"id": "BNE", "time": "2026-12-10 10:00"},
             "arrival_airport": {"id": "YVR", "time": "2026-12-10 06:30"},
             "duration": 810, "airline": "Air Canada"},
            {"departure_airport": {"id": "YVR", "time": "2026-12-10 09:30"},
             "arrival_airport": {"id": "LIM", "time": "2026-12-10 20:05"},
             "duration": 575, "airline": "Air Canada"},
        ],
        "total_duration": 1565, "price": 1102,
    }],
    "other_flights": [
        {"flights": [
            {"departure_airport": {"id": "BNE", "time": "2026-12-10 11:00"},
             "arrival_airport": {"id": "SCL", "time": "2026-12-10 08:00"},
             "duration": 780, "airline": "LATAM"},
            {"departure_airport": {"id": "SCL", "time": "2026-12-10 11:00"},
             "arrival_airport": {"id": "LIM", "time": "2026-12-10 13:30"},
             "duration": 210, "airline": "JetSMART"},
        ], "total_duration": 1170, "price": 990},
        {"flights": [], "price": 5},  # sin tramos: se ignora
    ],
}

DUFFEL = {"data": {"offers": [{
    "total_amount": "1500.00", "total_currency": "AUD",
    "slices": [{"duration": "PT26H5M", "segments": [
        {"departing_at": "2026-12-10T10:00:00", "arriving_at": "2026-12-10T06:30:00",
         "destination": {"iata_code": "YVR"}, "operating_carrier": {"name": "Air Canada"},
         "duration": "PT13H30M"},
        {"departing_at": "2026-12-10T09:30:00", "arriving_at": "2026-12-10T20:05:00",
         "destination": {"iata_code": "LIM"}, "operating_carrier": {"name": "Air Canada"},
         "duration": "PT9H35M"},
    ]}],
}]}}

KIWI = {"data": [{
    "price": 870, "deep_link": "https://www.kiwi.com/deep?x=1",
    "duration": {"total": 90000},
    "route": [
        {"flyFrom": "BNE", "flyTo": "SYD", "airline": "JQ",
         "local_departure": "2026-12-10T06:00:00.000Z", "local_arrival": "2026-12-10T07:35:00.000Z"},
        {"flyFrom": "SYD", "flyTo": "SCL", "airline": "LA",
         "local_departure": "2026-12-10T11:00:00.000Z", "local_arrival": "2026-12-10T08:00:00.000Z"},
        {"flyFrom": "SCL", "flyTo": "LIM", "airline": "H2",
         "local_departure": "2026-12-10T12:00:00.000Z", "local_arrival": "2026-12-10T14:30:00.000Z"},
    ],
}]}


def test_serpapi():
    vuelos = fuentes.parsear_serpapi(SERPAPI, "BNE", "LIM", FECHA)
    assert len(vuelos) == 2
    ac, latam = vuelos
    assert ac["aerolinea"] == "Air Canada" and ac["via"] == "YVR" and ac["escalas"] == 1
    assert ac["precio_usd"] == 1102 and ac["duracion_h"] == 26.1
    assert ac["salida"] == datetime(2026, 12, 10, 10, 0)
    assert latam["aerolinea"] == "LATAM + JetSMART" and latam["via"] == "SCL"


def test_duffel_convierte_moneda():
    (v,) = fuentes.parsear_duffel(DUFFEL, "BNE", "LIM", FECHA)
    assert v["precio_usd"] == round(1500 * fuentes.TASAS_A_USD["AUD"])
    assert v["duracion_h"] == 26.1 and v["via"] == "YVR" and v["fuente"] == "Duffel"


def test_kiwi():
    (v,) = fuentes.parsear_kiwi(KIWI, "BNE", "LIM", FECHA)
    assert v["aerolinea"] == "Jetstar + LATAM + Sky Airline"
    assert v["via"] == "SYD - SCL" and v["escalas"] == 2
    assert v["duracion_h"] == 25.0 and v["enlace"].startswith("https://www.kiwi.com")


def test_duracion_iso():
    assert fuentes._duracion_iso("PT13H25M") == 805
    assert fuentes._duracion_iso("P1DT2H") == 1560
    assert fuentes._duracion_iso(None) == 0


def _respuesta(datos, status=200):
    r = mock.Mock(status_code=status)
    r.json.return_value = datos
    return r


@pytest.fixture
def cache_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(fuentes, "CARPETA_CACHE", tmp_path)
    yield tmp_path
    bv.configurar_fuentes([])


def test_buscador_junta_fuentes_y_quita_repetidos(cache_temporal):
    serp, duffel = fuentes.FuenteSerpApi("x"), fuentes.FuenteDuffel("y")
    bv.configurar_fuentes([serp, duffel])
    with mock.patch("fuentes.requests.get", return_value=_respuesta(SERPAPI)), \
         mock.patch("fuentes.requests.post", return_value=_respuesta(DUFFEL)):
        df = bv.buscar_vuelos("BNE", "LIM", FECHA)
    # El Air Canada aparece en ambas fuentes: queda una sola fila, la más barata (Duffel)
    ac = df[df["aerolinea"] == "Air Canada"]
    assert len(ac) == 1
    assert ac.iloc[0]["fuente"] == "Duffel"
    assert "Google Flights US$1102" in ac.iloc[0]["precios_por_fuente"]
    assert df.iloc[0]["precio_usd"] == 990  # ordenado por precio


def test_cache_evita_repetir_consultas(cache_temporal):
    serp = fuentes.FuenteSerpApi("x")
    bv.configurar_fuentes([serp])
    with mock.patch("fuentes.requests.get", return_value=_respuesta(SERPAPI)) as get:
        primera = bv.buscar_vuelos("BNE", "LIM", FECHA)
        segunda = bv.buscar_vuelos("BNE", "LIM", FECHA)
    assert get.call_count == 1 and serp.consultas == 1
    assert primera.equals(segunda)


def test_fuente_con_error_no_bota_la_busqueda(cache_temporal):
    bv.configurar_fuentes([fuentes.FuenteSerpApi("mala"), fuentes.FuenteKiwi("k")])
    with mock.patch("fuentes.requests.get", side_effect=[
            _respuesta({"error": "Invalid API key"}, 401), _respuesta(KIWI)]):
        df = bv.buscar_vuelos("BNE", "LIM", FECHA)
    assert len(df) == 1 and df.iloc[0]["fuente"] == "Kiwi.com"
    assert "Google Flights" in bv.ERRORES_FUENTES


def test_fuente_sin_clave_no_se_activa():
    bv.configurar_fuentes([fuentes.FuenteSerpApi(""), fuentes.FuenteDuffel("  ")])
    assert bv.fuentes_activas() == ["Demo"]


def test_demo_sigue_funcionando():
    bv.configurar_fuentes([])
    df = bv.buscar_vuelos("BNE", "LIM", FECHA, hoy="2026-10-14")
    assert not df.empty and set(df["fuente"]) == {"Demo"}
    ref, rutas = bv.rutas_alternativas("BNE", "LIM", FECHA, max_hubs=3, hoy="2026-10-14")
    assert ref is not None and not rutas.empty


def test_clave_rechazada_no_se_reintenta(cache_temporal):
    serp = fuentes.FuenteSerpApi("mala")
    bv.configurar_fuentes([serp])
    with mock.patch("fuentes.requests.get", return_value=_respuesta({"error": "Invalid API key"}, 401)) as get:
        bv.buscar_vuelos("BNE", "LIM", FECHA, date(2026, 12, 12))
    assert get.call_count == 1 and serp.bloqueada
    assert "Google Flights" in bv.ERRORES_FUENTES

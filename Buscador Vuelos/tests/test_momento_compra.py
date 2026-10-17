"""Pruebas de la recomendación de cuándo comprar."""

import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fuentes  # noqa: E402
import momento_compra as mc  # noqa: E402

HOY = date(2026, 10, 17)


def vuelos(precio, rango=None, historial=None):
    fila = {"precio_usd": precio, "rango_tipico_min": rango[0] if rango else None,
            "rango_tipico_max": rango[1] if rango else None,
            "historial_google": json.dumps(historial) if historial else None}
    return pd.DataFrame([fila])


def test_precio_bajo_dice_comprar():
    r = mc.evaluar("BNE", "LIM", "2026-12-20", vuelos(700, (800, 1000)), hoy=HOY)
    assert r["estado"] == "comprar" and r["nivel"] == "bajo" and r["objetivo_usd"] == 665  # bajo el precio de hoy


def test_precio_alto_con_tiempo_dice_esperar():
    r = mc.evaluar("BNE", "LIM", "2027-02-20", vuelos(1300, (800, 1000)), hoy=HOY)
    assert r["estado"] == "esperar" and r["nivel"] == "alto"
    assert any("dentro de la ventana" in t for t in r["razones"])


def test_menos_de_3_semanas_compra_ya():
    r = mc.evaluar("BNE", "LIM", "2026-10-30", vuelos(1300, (800, 1000)), hoy=HOY)
    assert r["estado"] == "comprar" and r["dias_faltan"] == 13


def test_ida_y_vuelta_suma_rangos():
    r = mc.evaluar("BNE", "LIM", "2027-04-10", vuelos(900, (800, 1000)), "2027-04-24",
                   vuelos(950, (850, 1050)), hoy=HOY)
    assert r["rango_usd"] == (1650, 2050) and r["nivel"] == "normal" and r["precio_usd"] == 1850


def test_temporada_alta_tiene_ventana_mas_larga():
    assert mc.ventana_ideal("2026-12-20") == (120, 300)
    assert mc.ventana_ideal("2027-04-20") == (60, 180)


def test_sin_rango_real_no_inventa_nivel():
    r = mc.evaluar("BNE", "LIM", "2027-04-10", vuelos(900), hoy=HOY, demo=False)
    assert r["nivel"] is None and r["rango_usd"] is None


def test_demo_estima_rango():
    r = mc.evaluar("BNE", "LIM", "2027-04-10", vuelos(900), hoy=HOY, demo=True)
    assert r["rango_usd"] is not None and r["nivel"] in {"bajo", "normal", "alto"}


def test_tendencia_de_alerta():
    r = mc.evaluar("BNE", "LIM", "2027-04-10", vuelos(900, (800, 1000)), hoy=HOY,
                   precios_alerta=[850, 870, 900])
    assert any("sube" in t for t in r["razones"])


def test_sin_vuelos():
    assert mc.evaluar("BNE", "LIM", "2027-04-10", pd.DataFrame(), hoy=HOY)["estado"] == "sin_vuelos"


def test_lee_price_insights_de_serpapi():
    datos = {"best_flights": [{"flights": [
        {"departure_airport": {"id": "BNE", "time": "2026-12-10 10:00"},
         "arrival_airport": {"id": "LIM", "time": "2026-12-10 20:00"}, "duration": 900, "airline": "LATAM"}],
        "total_duration": 1500, "price": 990}],
        "price_insights": {"lowest_price": 990, "price_level": "low", "typical_price_range": [1050, 1400],
                           "price_history": [[1760000000, 1200], [1760086400, 1100]]}}
    (v,) = fuentes.parsear_serpapi(datos, "BNE", "LIM", date(2026, 12, 10))
    assert v["nivel_precio"] == "bajo" and (v["rango_tipico_min"], v["rango_tipico_max"]) == (1050, 1400)
    hist = mc.historial_google(pd.DataFrame([v]))
    assert list(hist["precio_usd"]) == [1200, 1100]
    assert hist["dia"].iloc[0] == datetime.fromtimestamp(1760000000).date()

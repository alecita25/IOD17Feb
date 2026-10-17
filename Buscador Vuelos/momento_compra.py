"""
¿Conviene comprar ahora o esperar?

Nadie puede predecir los precios con seguridad, pero hay tres señales útiles:

1. Cuánto falta para el vuelo. En vuelos internacionales lo más barato suele estar
   entre 2 y 6 meses antes (entre 4 y 10 meses en temporada alta: diciembre, enero
   y julio). A menos de 3 semanas los precios casi siempre suben.
2. Si el precio de hoy está bajo, normal o alto comparado con el rango típico de la
   ruta. Con Google Flights (SerpApi) se usa su propio "price_insights"; con datos de
   demo se estima con el modelo.
3. Hacia dónde se ha movido el precio (historial de Google o de tus alertas).
"""

import json
from datetime import date, datetime, timedelta

import pandas as pd

import buscador_vuelos as bv

MESES_TEMPORADA_ALTA = {12, 1, 7}


def ventana_ideal(fecha_vuelo):
    """(días mínimos, días máximos) de anticipación en que suele estar el mejor precio."""
    return (120, 300) if bv._a_fecha(fecha_vuelo).month in MESES_TEMPORADA_ALTA else (60, 180)


def _rango_google(vuelos):
    """Rango típico que informa Google Flights para ese tramo (o None)."""
    if vuelos is None or vuelos.empty or "rango_tipico_min" not in vuelos:
        return None
    filas = vuelos.dropna(subset=["rango_tipico_min", "rango_tipico_max"])
    if filas.empty:
        return None
    return float(filas.iloc[0]["rango_tipico_min"]), float(filas.iloc[0]["rango_tipico_max"])


def _rango_demo(origen, destino, fecha):
    """Con datos de demo: rango típico = precio con la anticipación ideal ± 12 %."""
    fecha = bv._a_fecha(fecha)
    desde, hasta = ventana_ideal(fecha)
    vuelos = bv.generar_vuelos(origen, destino, fecha, hoy=fecha - timedelta(days=(desde + hasta) // 2))
    if not vuelos:
        return None
    base = min(v["precio_usd"] for v in vuelos)
    return base * 0.88, base * 1.12


def historial_google(vuelos):
    """Historial de precios que entrega Google Flights para el tramo, como DataFrame (o vacío)."""
    if vuelos is None or vuelos.empty or "historial_google" not in vuelos:
        return pd.DataFrame(columns=["dia", "precio_usd"])
    serie = vuelos["historial_google"].dropna()
    if serie.empty:
        return pd.DataFrame(columns=["dia", "precio_usd"])
    puntos = json.loads(serie.iloc[0])
    return pd.DataFrame({"dia": [datetime.fromtimestamp(t).date() for t, _ in puntos],
                         "precio_usd": [p for _, p in puntos]})


def evaluar(origen, destino, fecha_ida, vuelos_ida, fecha_vuelta=None, vuelos_vuelta=None,
            demo=False, precios_alerta=None, hoy=None):
    """Recomendación de compra para la combinación de fechas dada.

    vuelos_ida / vuelos_vuelta: DataFrames con los vuelos de ese día (de buscar_vuelos).
    precios_alerta: precios totales que has ido viendo en una alerta (opcional).
    Devuelve un dict con: estado ("comprar", "buen_momento", "esperar", "sin_vuelos"), titulo,
    razones, precio_usd, rango_usd, nivel, dias_faltan, ventana, objetivo_usd.
    """
    hoy = bv._a_fecha(hoy) if hoy else date.today()
    fecha_ida = bv._a_fecha(fecha_ida)
    tramos = [(origen, destino, fecha_ida, vuelos_ida)]
    if fecha_vuelta is not None:
        tramos.append((destino, origen, bv._a_fecha(fecha_vuelta), vuelos_vuelta))

    if any(v is None or v.empty for *_, v in tramos):
        return {"estado": "sin_vuelos", "titulo": "No hay vuelos para evaluar en esas fechas.", "razones": []}

    precio = float(sum(v["precio_usd"].min() for *_, v in tramos))

    # Rango típico: Google si lo informa para todos los tramos; si no, el modelo (solo en demo)
    rangos = [_rango_google(v) for *_, v in tramos]
    fuente_rango = "Google Flights"
    if any(r is None for r in rangos):
        rangos = [_rango_demo(o, d, f) for o, d, f, _ in tramos] if demo else [None]
        fuente_rango = "estimado por el modelo de demo"
    rango = None if any(r is None for r in rangos) else (sum(r[0] for r in rangos), sum(r[1] for r in rangos))

    nivel = None
    if rango:
        nivel = "bajo" if precio < rango[0] else "alto" if precio > rango[1] else "normal"

    dias = (fecha_ida - hoy).days
    desde, hasta = ventana_ideal(fecha_ida)
    temporada = " (temporada alta)" if fecha_ida.month in MESES_TEMPORADA_ALTA else ""
    razones = []

    if dias < desde:
        razones.append(f"Faltan **{dias} días**: ya pasó la ventana en que suele estar el mejor precio "
                       f"({desde // 30}–{hasta // 30} meses antes{temporada}). Desde aquí los precios tienden a subir.")
    elif dias > hasta:
        razones.append(f"Faltan **{dias} días**: todavía es temprano; el mejor precio suele aparecer "
                       f"entre {desde // 30} y {hasta // 30} meses antes{temporada}.")
    else:
        razones.append(f"Faltan **{dias} días**: estás **dentro de la ventana** en que suele estar el mejor "
                       f"precio ({desde // 30}–{hasta // 30} meses antes{temporada}).")

    if rango:
        razones.append(f"El precio de hoy está **{nivel}** comparado con el rango típico de esta ruta "
                       f"({fuente_rango}).")
    else:
        razones.append("No hay rango típico para comparar (Google no lo informó para esta ruta/fecha).")

    tendencia = None
    if precios_alerta is not None and len(precios_alerta) >= 3:
        ultimos = list(precios_alerta)[-3:]
        if ultimos[-1] > ultimos[0] * 1.03:
            tendencia = "sube"
        elif ultimos[-1] < ultimos[0] * 0.97:
            tendencia = "baja"
        else:
            tendencia = "estable"
        razones.append(f"En tus últimas revisiones el precio **{tendencia}**.")

    # Decisión
    if dias < 21:
        estado, titulo = "comprar", "Compra ya: faltan menos de 3 semanas y los precios suelen subir rápido."
    elif nivel == "bajo":
        estado, titulo = "comprar", "Buen precio: está por debajo de lo normal para esta ruta. Es un buen momento para comprar."
    elif nivel == "alto" and dias >= desde:
        estado, titulo = "esperar", "Precio alto y todavía hay tiempo: conviene esperar y crear una alerta."
    elif nivel == "alto":
        estado, titulo = "esperar", ("Precio alto, pero queda poco tiempo: vigílalo unos días con una alerta, "
                                     "sin esperar demasiado.")
    elif dias < desde or tendencia == "sube":
        estado, titulo = "buen_momento", "Precio normal y el tiempo corre: comprar ahora es razonable."
    elif dias > hasta:
        estado, titulo = "esperar", "Precio normal pero es temprano: crea una alerta y espera una baja."
    else:
        estado, titulo = "buen_momento", ("Precio normal dentro de la ventana ideal: comprar ahora es razonable; "
                                          "si quieres arriesgar, crea una alerta con el precio sugerido.")

    return {"estado": estado, "titulo": titulo, "razones": razones, "precio_usd": precio, "rango_usd": rango,
            "nivel": nivel, "dias_faltan": dias, "ventana": (desde, hasta),
            # Objetivo para una alerta: la parte baja del rango, y siempre por debajo del precio de hoy
            "objetivo_usd": round(min(rango[0], precio * 0.95)) if rango else round(precio * 0.92)}

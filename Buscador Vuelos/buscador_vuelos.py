"""
Buscador de vuelos baratos (versión demo).

Genera ofertas de vuelos SIMULADAS pero realistas y permite buscar las más
baratas en un rango de fechas, combinar ida y vuelta, y explorar destinos.

Los precios no son reales: se calculan a partir de la distancia entre
aeropuertos y factores que sí afectan los precios de verdad (día de la
semana, temporada alta, anticipación de compra, escalas y aerolínea).
Son deterministas: la misma búsqueda (el mismo día) da los mismos resultados.

Para usar datos reales basta con reemplazar `generar_vuelos()` por una
función que llame a una API (Google Flights vía SerpApi, Duffel, etc.) y
devuelva la misma lista de diccionarios.
"""

import hashlib
import math
import random
from datetime import date, datetime, timedelta

import pandas as pd

# código IATA: (ciudad, país, latitud, longitud)
AEROPUERTOS = {
    "SCL": ("Santiago", "Chile", -33.39, -70.79),
    "LIM": ("Lima", "Perú", -12.02, -77.11),
    "EZE": ("Buenos Aires", "Argentina", -34.82, -58.54),
    "GRU": ("São Paulo", "Brasil", -23.43, -46.47),
    "GIG": ("Río de Janeiro", "Brasil", -22.81, -43.25),
    "BOG": ("Bogotá", "Colombia", 4.70, -74.15),
    "MEX": ("Ciudad de México", "México", 19.44, -99.07),
    "CUN": ("Cancún", "México", 21.04, -86.87),
    "PTY": ("Panamá", "Panamá", 9.07, -79.38),
    "MIA": ("Miami", "EE.UU.", 25.80, -80.29),
    "JFK": ("Nueva York", "EE.UU.", 40.64, -73.78),
    "LAX": ("Los Ángeles", "EE.UU.", 33.94, -118.41),
    "MAD": ("Madrid", "España", 40.49, -3.57),
    "BCN": ("Barcelona", "España", 41.30, 2.08),
    "LHR": ("Londres", "Reino Unido", 51.47, -0.45),
    "CDG": ("París", "Francia", 49.01, 2.55),
    "FCO": ("Roma", "Italia", 41.80, 12.25),
    "SYD": ("Sídney", "Australia", -33.94, 151.18),
    "MEL": ("Melbourne", "Australia", -37.67, 144.84),
    "AKL": ("Auckland", "Nueva Zelanda", -37.01, 174.79),
    "NRT": ("Tokio", "Japón", 35.77, 140.39),
}

# nombre: (factor de precio, aeropuertos donde hace escala, distancia máxima en km)
SIN_LIMITE = float("inf")
AEROLINEAS = {
    "LATAM": (1.00, ["SCL", "LIM", "GRU", "BOG"], SIN_LIMITE),
    "Sky Airline": (0.78, ["SCL", "LIM"], 5000),
    "JetSMART": (0.70, ["SCL", "LIM", "EZE"], 5000),
    "Avianca": (0.95, ["BOG", "LIM"], 9000),
    "Copa Airlines": (0.97, ["PTY"], 9000),
    "Aerolíneas Argentinas": (0.90, ["EZE"], 9000),
    "American Airlines": (1.10, ["MIA", "JFK", "LAX"], SIN_LIMITE),
    "Iberia": (1.05, ["MAD"], SIN_LIMITE),
    "Air France": (1.12, ["CDG"], SIN_LIMITE),
    "Qantas": (1.15, ["SYD", "MEL"], SIN_LIMITE),
    "Air New Zealand": (1.08, ["AKL"], SIN_LIMITE),
}
# Una escala solo tiene sentido si no alarga demasiado el viaje
DESVIO_MAXIMO = 1.25

# Meses de temporada alta (vacaciones de verano sur, invierno norte, etc.)
FACTOR_TEMPORADA = {1: 1.30, 2: 1.20, 3: 0.95, 4: 0.90, 5: 0.85, 6: 0.95,
                    7: 1.20, 8: 1.05, 9: 0.92, 10: 0.90, 11: 0.95, 12: 1.35}
# Lunes=0 ... Domingo=6. Martes y miércoles suelen ser los días más baratos.
FACTOR_DIA_SEMANA = [1.00, 0.88, 0.86, 0.98, 1.15, 1.08, 1.12]
FACTOR_ESCALAS = {0: 1.00, 1: 0.82, 2: 0.70}

DIAS_SEMANA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _a_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


def _validar_aeropuerto(codigo):
    codigo = codigo.upper()
    if codigo not in AEROPUERTOS:
        disponibles = ", ".join(sorted(AEROPUERTOS))
        raise ValueError(f"Aeropuerto desconocido: {codigo}. Disponibles: {disponibles}")
    return codigo


def distancia_km(origen, destino):
    """Distancia en línea recta (fórmula de Haversine) entre dos aeropuertos."""
    _, _, lat1, lon1 = AEROPUERTOS[origen]
    _, _, lat2, lon2 = AEROPUERTOS[destino]
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def _factor_anticipacion(dias):
    """Comprar muy encima de la fecha es caro; 1-3 meses antes es lo ideal."""
    if dias < 7:
        return 1.60
    if dias < 21:
        return 1.25
    if dias < 45:
        return 1.05
    if dias <= 120:
        return 0.92
    return 1.00


def _rng(*partes):
    """Generador aleatorio con semilla estable a partir de un texto."""
    semilla = hashlib.md5("|".join(map(str, partes)).encode()).hexdigest()
    return random.Random(int(semilla[:12], 16))


def generar_vuelos(origen, destino, fecha, hoy=None):
    """Devuelve una lista de vuelos (diccionarios) simulados para un día."""
    origen, destino = _validar_aeropuerto(origen), _validar_aeropuerto(destino)
    fecha = _a_fecha(fecha)
    hoy = _a_fecha(hoy) if hoy else date.today()
    if origen == destino or fecha < hoy:
        return []

    km = distancia_km(origen, destino)
    precio_base = 45 + km * 0.085  # en USD
    factor_fecha = (FACTOR_TEMPORADA[fecha.month]
                    * FACTOR_DIA_SEMANA[fecha.weekday()]
                    * _factor_anticipacion((fecha - hoy).days))
    rng = _rng(origen, destino, fecha.isoformat(), hoy.isoformat())

    # Qué aerolíneas pueden operar la ruta: directo si vuela desde/hacia uno de
    # sus hubs, o con escala en un hub que quede "de camino".
    operadores = {}
    for aerolinea, (_, hubs, alcance) in sorted(AEROLINEAS.items()):
        if km > alcance:
            continue
        directo = origen in hubs or destino in hubs
        hubs_utiles = [h for h in hubs if h not in (origen, destino)
                       and distancia_km(origen, h) + distancia_km(h, destino) <= km * DESVIO_MAXIMO]
        if directo or hubs_utiles:
            operadores[aerolinea] = (directo, hubs_utiles)
    if not operadores:  # ruta sin aerolíneas: siempre hay alguna opción directa
        operadores["LATAM"] = (True, [])

    vuelos = []
    for aerolinea in rng.sample(sorted(operadores), k=min(len(operadores), rng.randint(3, 6))):
        factor_aerolinea = AEROLINEAS[aerolinea][0]
        directo, hubs_utiles = operadores[aerolinea]
        for _ in range(rng.randint(1, 3)):
            pesos = [3, 4, 2] if km > 3000 else [6, 3, 1]
            if not directo:
                pesos[0] = 0
            escalas = rng.choices([0, 1, 2], weights=pesos)[0]
            via = sorted(rng.sample(hubs_utiles, k=min(escalas, len(hubs_utiles))),
                         key=lambda h: distancia_km(origen, h))
            escalas = len(via)
            ruta = [origen, *via, destino]
            km_volados = sum(distancia_km(a, b) for a, b in zip(ruta, ruta[1:]))

            salida = datetime.combine(fecha, datetime.min.time()) + timedelta(
                hours=rng.randint(0, 23), minutes=rng.choice([0, 15, 30, 45]))
            duracion = timedelta(minutes=int(km_volados / 800 * 60 + 30 + escalas * rng.randint(70, 300)))
            precio = (precio_base * factor_fecha * factor_aerolinea
                      * FACTOR_ESCALAS[escalas] * rng.uniform(0.85, 1.20))

            vuelos.append({
                "fecha": fecha,
                "dia": DIAS_SEMANA[fecha.weekday()],
                "origen": origen,
                "destino": destino,
                "aerolinea": aerolinea,
                "salida": salida,
                "llegada": salida + duracion,
                "duracion_h": round(duracion.total_seconds() / 3600, 1),
                "escalas": escalas,
                "via": " - ".join(via) if via else "directo",
                "precio_usd": round(precio),
            })
    return vuelos


def _filtrar(df, max_escalas=None, aerolineas=None, precio_max=None, max_duracion_h=None):
    if df.empty:
        return df
    if max_escalas is not None:
        df = df[df["escalas"] <= max_escalas]
    if aerolineas:
        df = df[df["aerolinea"].isin(aerolineas)]
    if precio_max is not None:
        df = df[df["precio_usd"] <= precio_max]
    if max_duracion_h is not None:
        df = df[df["duracion_h"] <= max_duracion_h]
    return df


def buscar_vuelos(origen, destino, fecha_desde, fecha_hasta=None, hoy=None, **filtros):
    """Todos los vuelos entre dos fechas (inclusive), ordenados del más barato al más caro.

    Filtros opcionales: max_escalas, aerolineas (lista), precio_max, max_duracion_h.
    """
    desde = _a_fecha(fecha_desde)
    hasta = _a_fecha(fecha_hasta) if fecha_hasta else desde
    if hasta < desde:
        raise ValueError("fecha_hasta debe ser igual o posterior a fecha_desde")

    vuelos = []
    for i in range((hasta - desde).days + 1):
        vuelos += generar_vuelos(origen, destino, desde + timedelta(days=i), hoy=hoy)

    df = _filtrar(pd.DataFrame(vuelos), **filtros)
    if df.empty:
        return df
    return df.sort_values(["precio_usd", "duracion_h"]).reset_index(drop=True)


def mas_barato_por_dia(df):
    """El vuelo más barato de cada día: sirve como 'calendario de precios'."""
    if df.empty:
        return df
    idx = df.groupby("fecha")["precio_usd"].idxmin()
    return df.loc[idx].sort_values("fecha").reset_index(drop=True)


def buscar_ida_y_vuelta(origen, destino, ida_desde, ida_hasta, min_noches, max_noches,
                        top=10, hoy=None, **filtros):
    """Mejores combinaciones de ida y vuelta según precio total.

    Prueba cada fecha de ida en el rango con estadías de min_noches a max_noches.
    """
    ida_desde, ida_hasta = _a_fecha(ida_desde), _a_fecha(ida_hasta)
    idas = mas_barato_por_dia(
        buscar_vuelos(origen, destino, ida_desde, ida_hasta, hoy=hoy, **filtros))
    vueltas = mas_barato_por_dia(
        buscar_vuelos(destino, origen, ida_desde + timedelta(days=min_noches),
                      ida_hasta + timedelta(days=max_noches), hoy=hoy, **filtros))
    if idas.empty or vueltas.empty:
        return pd.DataFrame()

    combos = idas.merge(vueltas, how="cross", suffixes=("_ida", "_vuelta"))
    combos["noches"] = (pd.to_datetime(combos["fecha_vuelta"])
                        - pd.to_datetime(combos["fecha_ida"])).dt.days
    combos = combos[combos["noches"].between(min_noches, max_noches)]
    combos["precio_total_usd"] = combos["precio_usd_ida"] + combos["precio_usd_vuelta"]

    columnas = ["fecha_ida", "dia_ida", "aerolinea_ida", "via_ida", "precio_usd_ida",
                "fecha_vuelta", "dia_vuelta", "aerolinea_vuelta", "via_vuelta",
                "precio_usd_vuelta", "noches", "precio_total_usd"]
    return (combos.sort_values("precio_total_usd")[columnas]
            .head(top).reset_index(drop=True))


def explorar_destinos(origen, fecha_desde, fecha_hasta, destinos=None, hoy=None, **filtros):
    """¿A dónde puedo ir barato? El vuelo más económico a cada destino del rango."""
    origen = _validar_aeropuerto(origen)
    destinos = destinos or [d for d in AEROPUERTOS if d != origen]

    filas = []
    for destino in destinos:
        df = buscar_vuelos(origen, destino, fecha_desde, fecha_hasta, hoy=hoy, **filtros)
        if df.empty:
            continue
        mejor = df.iloc[0].to_dict()
        ciudad, pais, _, _ = AEROPUERTOS[mejor["destino"]]
        mejor["ciudad"] = f"{ciudad} ({pais})"
        mejor["usd_por_1000km"] = round(mejor["precio_usd"] / distancia_km(origen, destino) * 1000, 1)
        filas.append(mejor)

    columnas = ["destino", "ciudad", "fecha", "dia", "aerolinea", "via",
                "duracion_h", "precio_usd", "usd_por_1000km"]
    if not filas:
        return pd.DataFrame(columns=columnas)
    return pd.DataFrame(filas)[columnas].sort_values("precio_usd").reset_index(drop=True)

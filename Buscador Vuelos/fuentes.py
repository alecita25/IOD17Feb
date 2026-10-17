"""
Fuentes de datos del buscador de vuelos.

Cada fuente sabe buscar los vuelos de un día entre dos aeropuertos y los
devuelve en el mismo formato (lista de diccionarios), así el buscador puede
juntar los resultados de todas:

    FuenteDemo       precios simulados (no necesita nada)
    FuenteSerpApi    Google Flights vía SerpApi      (https://serpapi.com)
    FuenteDuffel     más de 300 aerolíneas            (https://duffel.com)
    FuenteKiwi       Kiwi.com Tequila, combina aerolíneas con pasajes separados
                                                      (https://tequila.kiwi.com)

Las respuestas de las APIs se guardan unas horas en la carpeta `.cache_vuelos`
para no gastar búsquedas repitiendo la misma consulta.
"""

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

import buscador_vuelos as bv

CARPETA_CACHE = Path(__file__).with_name(".cache_vuelos")
HORAS_CACHE = 6
TIMEOUT_S = 40

# Tipo de cambio aproximado a dólares (para fuentes que no permiten elegir moneda).
# Actualízalo si quieres más precisión.
TASAS_A_USD = {
    "USD": 1.0, "AUD": 0.69, "NZD": 0.60, "CAD": 0.73, "EUR": 1.08, "GBP": 1.27,
    "CLP": 0.00105, "PEN": 0.27, "ARS": 0.001, "BRL": 0.18, "COP": 0.00025, "MXN": 0.055,
}

HORAS_TIPO_CAMBIO = 12


def tipo_cambio_usd_aud():
    """Cuántos dólares australianos vale 1 dólar estadounidense.

    Consulta el tipo de cambio del día (open.er-api.com, gratis y sin clave) y lo guarda 12 horas.
    Si no hay conexión, usa el valor aproximado de TASAS_A_USD. Devuelve (tasa, descripción).
    """
    archivo = CARPETA_CACHE / "tipo_cambio.json"
    try:
        guardado = json.loads(archivo.read_text(encoding="utf-8"))
        if datetime.now() - datetime.fromisoformat(guardado["guardado"]) < timedelta(hours=HORAS_TIPO_CAMBIO):
            return guardado["tasa"], f"tipo de cambio del {guardado['dia']}"
    except (OSError, ValueError, KeyError):
        pass
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        tasa = float(r.json()["rates"]["AUD"])
        dia = date.today().strftime("%d/%m/%Y")
        CARPETA_CACHE.mkdir(exist_ok=True)
        archivo.write_text(json.dumps({"guardado": datetime.now().isoformat(), "tasa": tasa, "dia": dia}),
                           encoding="utf-8")
        return tasa, f"tipo de cambio del {dia}"
    except Exception:
        return 1 / TASAS_A_USD["AUD"], "tipo de cambio aproximado (sin conexión al servicio de divisas)"


# Nombres de aerolíneas para fuentes que solo entregan el código IATA
NOMBRES_AEROLINEAS = {
    "LA": "LATAM", "H2": "Sky Airline", "JA": "JetSMART", "AV": "Avianca", "CM": "Copa Airlines",
    "AR": "Aerolíneas Argentinas", "AA": "American Airlines", "DL": "Delta", "UA": "United",
    "AC": "Air Canada", "Y4": "Volaris", "IB": "Iberia", "AF": "Air France", "QF": "Qantas",
    "VA": "Virgin Australia", "JQ": "Jetstar", "NZ": "Air New Zealand", "FJ": "Fiji Airways",
    "AM": "Aeroméxico", "2I": "Star Perú", "XL": "LATAM Ecuador", "LP": "LATAM Perú",
}


class ClaveInvalida(RuntimeError):
    """La API rechazó la clave: no tiene sentido seguir consultando esa fuente."""


class Fuente:
    """Base: maneja la caché y el contador de consultas."""

    nombre = "Fuente"
    real = True

    def __init__(self, clave=""):
        self.clave = (clave or "").strip()
        self.consultas = 0  # llamadas reales a la API (sin contar la caché)
        self.bloqueada = None  # mensaje si la clave fue rechazada

    @property
    def activa(self):
        return bool(self.clave) or not self.real

    def buscar(self, origen, destino, fecha, hoy=None):
        fecha = bv._a_fecha(fecha)
        archivo = self._archivo_cache(origen, destino, fecha)
        if archivo and archivo.exists():
            guardado = json.loads(archivo.read_text(encoding="utf-8"))
            antiguedad = datetime.now() - datetime.fromisoformat(guardado["guardado"])
            if antiguedad < timedelta(hours=HORAS_CACHE):
                return [_desde_json(v) for v in guardado["vuelos"]]

        if self.bloqueada:
            raise ClaveInvalida(self.bloqueada)
        self.consultas += 1
        try:
            vuelos = self._consultar(origen, destino, fecha)
        except ClaveInvalida as e:
            self.bloqueada = str(e)
            raise
        for v in vuelos:
            v.setdefault("fuente", self.nombre)
        if archivo:
            archivo.parent.mkdir(exist_ok=True)
            archivo.write_text(json.dumps(
                {"guardado": datetime.now().isoformat(), "vuelos": [_a_json(v) for v in vuelos]},
                ensure_ascii=False), encoding="utf-8")
        return vuelos

    def _archivo_cache(self, origen, destino, fecha):
        if not self.real:
            return None
        llave = hashlib.md5(f"{self.nombre}|{self.clave}|{origen}|{destino}|{fecha}".encode()).hexdigest()
        return CARPETA_CACHE / f"{llave}.json"

    def _consultar(self, origen, destino, fecha):
        raise NotImplementedError


class FuenteDemo(Fuente):
    nombre = "Demo"
    real = False

    def buscar(self, origen, destino, fecha, hoy=None):
        return [dict(v, fuente=self.nombre) for v in bv.generar_vuelos(origen, destino, fecha, hoy=hoy)]


class FuenteSerpApi(Fuente):
    """Google Flights a través de SerpApi (engine=google_flights)."""

    nombre = "Google Flights"

    def _consultar(self, origen, destino, fecha):
        r = requests.get("https://serpapi.com/search.json", timeout=TIMEOUT_S, params={
            "engine": "google_flights", "departure_id": origen, "arrival_id": destino,
            "outbound_date": fecha.isoformat(), "type": 2,  # 2 = solo ida
            "currency": "USD", "hl": "es", "api_key": self.clave,
        })
        datos = _json_o_error(r)
        if "error" in datos:
            raise RuntimeError(datos["error"])
        return parsear_serpapi(datos, origen, destino, fecha)


class FuenteDuffel(Fuente):
    """Duffel: ofertas de más de 300 aerolíneas (incluye low cost como Jetstar)."""

    nombre = "Duffel"

    def _consultar(self, origen, destino, fecha):
        r = requests.post(
            "https://api.duffel.com/air/offer_requests",
            params={"return_offers": "true", "supplier_timeout": 20000},
            headers={"Authorization": f"Bearer {self.clave}", "Duffel-Version": "v2",
                     "Accept": "application/json", "Content-Type": "application/json"},
            json={"data": {
                "slices": [{"origin": origen, "destination": destino, "departure_date": fecha.isoformat()}],
                "passengers": [{"type": "adult"}],
                "cabin_class": "economy",
            }},
            timeout=TIMEOUT_S + 20,
        )
        datos = _json_o_error(r)
        if datos.get("errors"):
            raise RuntimeError("; ".join(e.get("message", str(e)) for e in datos["errors"]))
        return parsear_duffel(datos, origen, destino, fecha)


class FuenteKiwi(Fuente):
    """Kiwi.com Tequila: también arma rutas con distintas aerolíneas en pasajes separados."""

    nombre = "Kiwi.com"

    def _consultar(self, origen, destino, fecha):
        dia = fecha.strftime("%d/%m/%Y")
        r = requests.get("https://api.tequila.kiwi.com/v2/search", timeout=TIMEOUT_S,
                         headers={"apikey": self.clave}, params={
                             "fly_from": origen, "fly_to": destino, "date_from": dia, "date_to": dia,
                             "flight_type": "oneway", "curr": "USD", "adults": 1,
                             "max_stopovers": 2, "limit": 50, "sort": "price",
                         })
        datos = _json_o_error(r)
        if "error" in datos and not datos.get("data"):
            raise RuntimeError(datos["error"])
        return parsear_kiwi(datos, origen, destino, fecha)


# ---------- Traducción de cada respuesta al formato común ----------

def _vuelo(fecha, origen, destino, aerolinea, salida, llegada, duracion_min, via, precio_usd, fuente,
           enlace=None):
    return {
        "fecha": fecha,
        "dia": bv.DIAS_SEMANA[fecha.weekday()],
        "origen": origen,
        "destino": destino,
        "aerolinea": aerolinea,
        "salida": salida,
        "llegada": llegada,
        "duracion_h": round(duracion_min / 60, 1),
        "escalas": len(via),
        "via": " - ".join(via) if via else "directo",
        "precio_usd": round(precio_usd),
        "fuente": fuente,
        "enlace": enlace,
    }


def parsear_serpapi(datos, origen, destino, fecha):
    # "price_insights": lo que Google Flights opina del precio de hoy para esta ruta y fecha
    # (bajo / normal / alto, rango típico e historial). No siempre viene.
    insights = datos.get("price_insights") or {}
    rango = insights.get("typical_price_range") or [None, None]
    extra = {
        "nivel_precio": {"low": "bajo", "typical": "normal", "high": "alto"}.get(insights.get("price_level")),
        "rango_tipico_min": rango[0] if len(rango) == 2 else None,
        "rango_tipico_max": rango[1] if len(rango) == 2 else None,
        "historial_google": json.dumps(insights["price_history"]) if insights.get("price_history") else None,
    }
    vuelos = []
    for opcion in datos.get("best_flights", []) + datos.get("other_flights", []):
        tramos = opcion.get("flights") or []
        if not tramos or opcion.get("price") is None:
            continue
        aerolineas = list(dict.fromkeys(t.get("airline", "?") for t in tramos))
        via = [t["arrival_airport"]["id"] for t in tramos[:-1]]
        salida = _hora(tramos[0]["departure_airport"]["time"])
        llegada = _hora(tramos[-1]["arrival_airport"]["time"])
        duracion = opcion.get("total_duration") or sum(t.get("duration", 0) for t in tramos)
        vuelos.append(dict(_vuelo(fecha, origen, destino, " + ".join(aerolineas), salida, llegada,
                                  duracion, via, opcion["price"], FuenteSerpApi.nombre), **extra))
    return vuelos


def parsear_duffel(datos, origen, destino, fecha):
    vuelos = []
    for oferta in (datos.get("data") or {}).get("offers", []):
        tramos = oferta["slices"][0]["segments"]
        moneda = oferta.get("total_currency", "USD")
        if moneda not in TASAS_A_USD:
            continue
        aerolineas = list(dict.fromkeys(
            (t.get("operating_carrier") or t.get("marketing_carrier") or {}).get("name", "?") for t in tramos))
        via = [t["destination"]["iata_code"] for t in tramos[:-1]]
        salida = _hora(tramos[0]["departing_at"])
        llegada = _hora(tramos[-1]["arriving_at"])
        duracion = _duracion_iso(oferta["slices"][0].get("duration")) or \
            sum(_duracion_iso(t.get("duration")) for t in tramos)
        precio = float(oferta["total_amount"]) * TASAS_A_USD[moneda]
        vuelos.append(_vuelo(fecha, origen, destino, " + ".join(aerolineas), salida, llegada,
                             duracion, via, precio, FuenteDuffel.nombre))
    return vuelos


def parsear_kiwi(datos, origen, destino, fecha):
    vuelos = []
    for opcion in datos.get("data", []):
        tramos = opcion.get("route") or []
        if not tramos:
            continue
        aerolineas = list(dict.fromkeys(NOMBRES_AEROLINEAS.get(t.get("airline"), t.get("airline", "?"))
                                        for t in tramos))
        via = [t["flyTo"] for t in tramos[:-1]]
        salida = _hora(tramos[0]["local_departure"])
        llegada = _hora(tramos[-1]["local_arrival"])
        if opcion.get("duration", {}).get("total"):
            duracion = opcion["duration"]["total"] / 60
        else:
            utc_sal, utc_lle = tramos[0].get("utc_departure"), tramos[-1].get("utc_arrival")
            duracion = ((_hora(utc_lle) - _hora(utc_sal)).total_seconds() / 60) if utc_sal and utc_lle else 0
        vuelos.append(_vuelo(fecha, origen, destino, " + ".join(aerolineas), salida, llegada,
                             duracion, via, opcion["price"], FuenteKiwi.nombre, opcion.get("deep_link")))
    return vuelos


# ---------- Utilidades ----------

def _json_o_error(respuesta):
    try:
        datos = respuesta.json()
    except ValueError:
        respuesta.raise_for_status()
        raise RuntimeError(f"Respuesta inesperada ({respuesta.status_code})")
    if respuesta.status_code >= 400 and not isinstance(datos, dict):
        respuesta.raise_for_status()
    if respuesta.status_code in (401, 403):
        raise ClaveInvalida("La clave no es válida o no tiene permiso (revisa que esté bien copiada).")
    if respuesta.status_code == 429:
        raise RuntimeError("Se acabaron las búsquedas disponibles por ahora (límite de la API).")
    return datos


def _hora(texto):
    """Convierte '2026-12-10 08:30', '2026-12-10T08:30:00' o '...Z' en datetime (hora local, sin zona)."""
    texto = texto.replace("Z", "").split("+")[0].split(".")[0].replace("T", " ")
    return datetime.fromisoformat(texto)


def _duracion_iso(texto):
    """'PT13H25M' / 'P1DT2H' -> minutos."""
    if not texto:
        return 0
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", texto)
    if not m:
        return 0
    dias, horas, minutos = (int(x or 0) for x in m.groups())
    return dias * 1440 + horas * 60 + minutos


def _a_json(vuelo):
    return {k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in vuelo.items()}


def _desde_json(vuelo):
    v = dict(vuelo)
    v["fecha"] = date.fromisoformat(v["fecha"])
    v["salida"] = datetime.fromisoformat(v["salida"])
    v["llegada"] = datetime.fromisoformat(v["llegada"])
    return v

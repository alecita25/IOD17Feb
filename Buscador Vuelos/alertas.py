"""
Alertas de precio: revisa tus vuelos guardados y te avisa cuando bajan.

Uso:
    python alertas.py            revisa todas las alertas activas y avisa si bajó algún precio

Lo ideal es que Windows lo ejecute solo una vez al día (ver README). Cada
revisión guarda el precio en historial_precios.csv, así puedes ver cómo cambia.

Avisos disponibles (se usan los que estén configurados en .streamlit/secrets.toml):
    - Notificación en el escritorio de Windows (siempre, si está instalado plyer)
    - Email (Gmail con "contraseña de aplicación")
    - Telegram (a tu celular, con un bot propio)
"""

import json
import os
import smtplib
import sys
import tomllib
import uuid
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
import requests

import buscador_vuelos as bv
import fuentes

CARPETA = Path(__file__).resolve().parent
ARCHIVO_ALERTAS = CARPETA / "alertas.json"
ARCHIVO_HISTORIAL = CARPETA / "historial_precios.csv"
ARCHIVO_SECRETOS = CARPETA / ".streamlit" / "secrets.toml"

# Avisar si el precio baja al menos este porcentaje respecto del mínimo anterior
BAJADA_MINIMA_PCT = 3


# ---------- Guardar y leer alertas ----------

def leer_alertas():
    if not ARCHIVO_ALERTAS.exists():
        return []
    return json.loads(ARCHIVO_ALERTAS.read_text(encoding="utf-8"))


def guardar_alertas(alertas):
    ARCHIVO_ALERTAS.write_text(json.dumps(alertas, ensure_ascii=False, indent=2), encoding="utf-8")


def crear_alerta(origen, destino, fecha_ida, fecha_vuelta=None, precio_objetivo=None, max_escalas=2,
                 flex_dias=0, cada_dias=1):
    """flex_dias: también vigila N días antes y después de cada fecha. cada_dias: cada cuántos días revisa."""
    alerta = {
        "id": uuid.uuid4().hex[:8],
        "origen": origen,
        "destino": destino,
        "fecha_ida": bv._a_fecha(fecha_ida).isoformat(),
        "fecha_vuelta": bv._a_fecha(fecha_vuelta).isoformat() if fecha_vuelta else None,
        "precio_objetivo": float(precio_objetivo) if precio_objetivo else None,
        "max_escalas": max_escalas,
        "flex_dias": int(flex_dias),
        "cada_dias": int(cada_dias),
        "creada": date.today().isoformat(),
        "activa": True,
    }
    alertas = leer_alertas()
    alertas.append(alerta)
    guardar_alertas(alertas)
    return alerta


def borrar_alerta(id_alerta):
    guardar_alertas([a for a in leer_alertas() if a["id"] != id_alerta])
    historial = leer_historial()
    if not historial.empty:
        historial[historial["alerta_id"] != id_alerta].to_csv(ARCHIVO_HISTORIAL, index=False)


def describir(alerta):
    ida = date.fromisoformat(alerta["fecha_ida"])
    texto = f"{alerta['origen']} → {alerta['destino']} · ida {ida:%d/%m/%Y}"
    if alerta["fecha_vuelta"]:
        texto += f" · vuelta {date.fromisoformat(alerta['fecha_vuelta']):%d/%m/%Y}"
    if alerta.get("flex_dias"):
        texto += f" (±{alerta['flex_dias']} días)"
    return texto


def consultas_por_revision(alerta):
    """Cuántas consultas a la API usa cada revisión (por fuente)."""
    dias = 2 * alerta.get("flex_dias", 0) + 1
    return dias * (2 if alerta.get("fecha_vuelta") else 1)


def consultas_al_mes(alerta):
    return round(consultas_por_revision(alerta) * 30 / alerta.get("cada_dias", 1))


def leer_historial():
    if not ARCHIVO_HISTORIAL.exists():
        return pd.DataFrame(columns=["revisado", "alerta_id", "precio_total_usd", "detalle", "fuente"])
    return pd.read_csv(ARCHIVO_HISTORIAL, parse_dates=["revisado"])


# ---------- Configuración (claves y avisos) ----------

def leer_secretos():
    """Lee .streamlit/secrets.toml (el mismo archivo que usa la app) y variables de entorno."""
    secretos = {}
    if ARCHIVO_SECRETOS.exists():
        secretos = tomllib.loads(ARCHIVO_SECRETOS.read_text(encoding="utf-8"))
    for nombre in ["SERPAPI_KEY", "DUFFEL_TOKEN", "KIWI_API_KEY", "EMAIL_REMITENTE", "EMAIL_CLAVE_APP",
                   "EMAIL_DESTINO", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]:
        secretos.setdefault(nombre, os.environ.get(nombre, ""))
    return secretos


def busquedas_al_mes():
    """Búsquedas al mes del plan de SerpApi (250 en el plan gratis, o lo que hayas guardado)."""
    try:
        return int(leer_secretos().get("BUSQUEDAS_MES") or 250)
    except (ValueError, tomllib.TOMLDecodeError):
        return 250


def configurar_fuentes_desde(secretos):
    bv.configurar_fuentes([fuentes.FuenteSerpApi(secretos.get("SERPAPI_KEY")),
                           fuentes.FuenteDuffel(secretos.get("DUFFEL_TOKEN")),
                           fuentes.FuenteKiwi(secretos.get("KIWI_API_KEY"))])


# ---------- Revisar precios ----------

def precio_actual(alerta, hoy=None):
    """El precio más barato hoy para la alerta, considerando sus días flexibles.

    Devuelve {"precio_total_usd", "detalle", "fuente"} o None si no hay vuelos.
    """
    hoy = bv._a_fecha(hoy) if hoy else date.today()
    filtros = {"max_escalas": alerta.get("max_escalas", 2)}
    flex = timedelta(days=alerta.get("flex_dias", 0))

    def mas_baratos_por_dia(a, b, centro):
        centro = date.fromisoformat(centro)
        desde, hasta = max(centro - flex, hoy), centro + flex
        if hasta < desde:
            return pd.DataFrame()
        return bv.mas_barato_por_dia(bv.buscar_vuelos(a, b, desde, hasta, hoy=hoy, **filtros))

    def tramo(v, nombre):
        return f"{nombre} {v['fecha']:%d/%m}: {v['aerolinea']} ({v['via']})"

    idas = mas_baratos_por_dia(alerta["origen"], alerta["destino"], alerta["fecha_ida"])
    if idas.empty:
        return None
    if not alerta["fecha_vuelta"]:
        v = idas.loc[idas["precio_usd"].idxmin()]
        return {"precio_total_usd": int(v["precio_usd"]), "detalle": tramo(v, "Ida"), "fuente": v["fuente"]}

    vueltas = mas_baratos_por_dia(alerta["destino"], alerta["origen"], alerta["fecha_vuelta"])
    if vueltas.empty:
        return None
    combos = idas.merge(vueltas, how="cross", suffixes=("_i", "_v"))
    combos = combos[combos["fecha_v"] > combos["fecha_i"]]
    if combos.empty:
        return None
    combos["total"] = combos["precio_usd_i"] + combos["precio_usd_v"]
    m = combos.loc[combos["total"].idxmin()]
    ida = {k[:-2]: m[k] for k in m.index if k.endswith("_i")}
    vuelta = {k[:-2]: m[k] for k in m.index if k.endswith("_v")}
    fuente = ida["fuente"] if ida["fuente"] == vuelta["fuente"] else f"{ida['fuente']} / {vuelta['fuente']}"
    return {"precio_total_usd": int(m["total"]),
            "detalle": f"{tramo(ida, 'Ida')} · {tramo(vuelta, 'Vuelta')}", "fuente": fuente}


def revisar_alertas(notificar=True, hoy=None, solo_ids=None, forzar=False):
    """Revisa las alertas activas (o solo las de solo_ids), guarda el historial y avisa si bajó algún precio.

    Cada alerta se revisa cada "cada_dias" días; forzar=True la revisa igual (botón "Revisar ahora").
    Devuelve la lista de mensajes de aviso generados.
    """
    hoy = bv._a_fecha(hoy) if hoy else date.today()
    historial = leer_historial()
    nuevas_filas, avisos = [], []

    for alerta in leer_alertas():
        ultimo_dia_ida = date.fromisoformat(alerta["fecha_ida"]) + timedelta(days=alerta.get("flex_dias", 0))
        if not alerta.get("activa", True) or ultimo_dia_ida < hoy:
            continue
        if solo_ids is not None and alerta["id"] not in solo_ids:
            continue
        revisiones = historial[historial["alerta_id"] == alerta["id"]]
        if not forzar and not revisiones.empty:
            ultima = pd.to_datetime(revisiones["revisado"]).max().date()
            if (hoy - ultima).days < alerta.get("cada_dias", 1):
                continue
        actual = precio_actual(alerta, hoy=hoy)
        if actual is None:
            continue

        anteriores = historial[historial["alerta_id"] == alerta["id"]]["precio_total_usd"]
        minimo_anterior = anteriores.min() if not anteriores.empty else None
        precio = actual["precio_total_usd"]
        nuevas_filas.append({"revisado": datetime.now().replace(microsecond=0), "alerta_id": alerta["id"],
                             **actual})

        objetivo = alerta.get("precio_objetivo")
        if objetivo and precio <= objetivo:
            motivo = f"¡Bajó de tu precio objetivo (US$ {objetivo:,.0f})!"
        elif minimo_anterior is not None and precio <= minimo_anterior * (1 - BAJADA_MINIMA_PCT / 100):
            motivo = f"Nuevo precio más bajo: antes el mínimo era US$ {minimo_anterior:,.0f}."
        else:
            continue
        avisos.append(f"✈️ {describir(alerta)}\nAhora: US$ {precio:,.0f} — {motivo}\n"
                      f"{actual['detalle']} [{actual['fuente']}]")

    if nuevas_filas:
        nuevas = pd.DataFrame(nuevas_filas)
        historial = nuevas if historial.empty else pd.concat([historial, nuevas], ignore_index=True)
        historial.to_csv(ARCHIVO_HISTORIAL, index=False)
    if avisos and notificar:
        enviar_avisos(avisos)
    return avisos


def guardar_secretos(cambios):
    """Guarda claves en .streamlit/secrets.toml (sin borrar las que ya estaban)."""
    secretos = {}
    if ARCHIVO_SECRETOS.exists():
        secretos = tomllib.loads(ARCHIVO_SECRETOS.read_text(encoding="utf-8"))
    secretos.update({k: v.strip() for k, v in cambios.items() if v is not None})
    ARCHIVO_SECRETOS.parent.mkdir(exist_ok=True)
    lineas = ["# Claves del buscador de vuelos. Este archivo NO se sube a GitHub."]
    lineas += [f"{k} = {json.dumps(str(v), ensure_ascii=False)}" for k, v in secretos.items()]
    ARCHIVO_SECRETOS.write_text("\n".join(lineas) + "\n", encoding="utf-8")


# ---------- Revisión diaria automática (Windows) ----------

NOMBRE_TAREA = "Alertas de vuelos"
ARCHIVO_BAT = CARPETA / "revisar_alertas.bat"


def crear_bat():
    """Crea el archivo que ejecuta la revisión con el mismo Python que usa la app."""
    ARCHIVO_BAT.write_text(
        "@echo off\n"
        f'cd /d "{CARPETA}"\n'
        f'"{sys.executable}" alertas.py >> alertas.log 2>&1\n',
        encoding="utf-8", newline="\r\n")  # saltos de línea de Windows en cualquier sistema
    return ARCHIVO_BAT


def activar_revision_diaria(hora="09:00"):
    """Programa la revisión diaria en el Programador de tareas de Windows. Devuelve (ok, mensaje)."""
    import subprocess
    bat = crear_bat()
    r = subprocess.run(["schtasks", "/create", "/tn", NOMBRE_TAREA, "/tr", f'"{bat}"',
                        "/sc", "daily", "/st", hora, "/f"], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout or r.stderr).strip()


def desactivar_revision_diaria():
    import subprocess
    r = subprocess.run(["schtasks", "/delete", "/tn", NOMBRE_TAREA, "/f"], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout or r.stderr).strip()


def revision_diaria_activa():
    import subprocess
    try:
        r = subprocess.run(["schtasks", "/query", "/tn", NOMBRE_TAREA], capture_output=True, text=True)
    except FileNotFoundError:  # no es Windows
        return False
    return r.returncode == 0


# ---------- Enviar avisos ----------

def enviar_avisos(avisos, secretos=None):
    """Envía los avisos por todos los canales configurados. Devuelve los canales que funcionaron."""
    secretos = secretos if secretos is not None else leer_secretos()
    texto = "\n\n".join(avisos)
    usados = []
    for canal, funcion in [("escritorio", _aviso_escritorio), ("email", _aviso_email),
                           ("telegram", _aviso_telegram)]:
        try:
            if funcion(texto, len(avisos), secretos):
                usados.append(canal)
        except Exception as e:
            print(f"No se pudo avisar por {canal}: {e}", file=sys.stderr)
    return usados


def _aviso_escritorio(texto, cantidad, secretos):
    try:
        from plyer import notification
    except ImportError:
        return False
    titulo = "Bajó el precio de tu vuelo" if cantidad == 1 else f"Bajaron {cantidad} vuelos"
    notification.notify(title=titulo, message=texto[:250], app_name="Buscador de vuelos", timeout=20)
    return True


def _aviso_email(texto, cantidad, secretos):
    remitente, clave = secretos.get("EMAIL_REMITENTE"), secretos.get("EMAIL_CLAVE_APP")
    if not (remitente and clave):
        return False
    mensaje = EmailMessage()
    mensaje["Subject"] = "✈️ Bajó el precio de tu vuelo" if cantidad == 1 else f"✈️ Bajaron {cantidad} vuelos"
    mensaje["From"] = remitente
    mensaje["To"] = secretos.get("EMAIL_DESTINO") or remitente
    mensaje.set_content(texto + "\n\nConfirma el precio en la página antes de comprar.")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as servidor:
        servidor.login(remitente, clave.replace(" ", ""))
        servidor.send_message(mensaje)
    return True


def _aviso_telegram(texto, cantidad, secretos):
    token, chat_id = secretos.get("TELEGRAM_TOKEN"), secretos.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return False
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": texto}, timeout=30)
    r.raise_for_status()
    return True


if __name__ == "__main__":
    configurar_fuentes_desde(leer_secretos())
    if bv.fuentes_activas() == ["Demo"]:
        print("Aviso: no hay claves configuradas; se usan precios de DEMO (no reales).")
    alertas_activas = [a for a in leer_alertas() if a.get("activa", True)]
    print(f"{datetime.now():%d/%m/%Y %H:%M} · revisando {len(alertas_activas)} alerta(s) "
          f"con {', '.join(bv.fuentes_activas())}")
    resultado = revisar_alertas()
    for nombre, error in bv.ERRORES_FUENTES.items():
        print(f"  {nombre} no respondió: {error}")
    print("\n\n".join(resultado) if resultado else "Sin bajadas de precio por ahora.")

"""
App web del buscador de vuelos baratos.

Junta resultados de varias fuentes (Google Flights vía SerpApi, Duffel y
Kiwi.com) cuando les pones su clave; sin claves funciona con datos de demo.

Ejecutar con:
    python -m streamlit run app.py
"""

import hashlib
import os
from datetime import date, timedelta
from urllib.parse import quote

import altair as alt
import pandas as pd
import streamlit as st

import alertas as al
import buscador_vuelos as bv
import fuentes
import momento_compra as mc

AZUL, NARANJA = "#2a78d6", "#eb6834"
COLORES_SERIES = [AZUL, NARANJA, "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]

st.set_page_config(page_title="Buscador de vuelos baratos", page_icon="✈️", layout="wide")


def nombre_aeropuerto(codigo):
    ciudad, pais, _, _ = bv.AEROPUERTOS[codigo]
    return f"{ciudad}, {pais} ({codigo})"


def usd(valor):
    return f"US$ {valor:,.0f}".replace(",", ".")


def aud(valor_usd):
    return f"A$ {valor_usd * TASA_AUD:,.0f}".replace(",", ".")


def precio(valor_usd):
    """Precio en la moneda principal, con la otra entre paréntesis."""
    if MONEDA == "A$":
        return f"{aud(valor_usd)} ({usd(valor_usd)})"
    return f"{usd(valor_usd)} ({aud(valor_usd)})"


def precio_corto(valor_usd):
    return aud(valor_usd) if MONEDA == "A$" else usd(valor_usd)


def precio_otro(valor_usd):
    return usd(valor_usd) if MONEDA == "A$" else aud(valor_usd)


def a_moneda(serie_usd):
    """Convierte una columna en US$ a la moneda principal (para gráficos)."""
    return (serie_usd * FACTOR).round(0)


@st.cache_data(ttl=3600 * 6, show_spinner=False)
def cargar_tipo_cambio():
    return fuentes.tipo_cambio_usd_aud()


def clave_guardada(nombre):
    """Clave desde .streamlit/secrets.toml o variable de entorno (si existe)."""
    try:
        return al.leer_secretos().get(nombre, "")
    except Exception:  # archivo con errores de formato
        return os.environ.get(nombre, "")


# ---------- Fuentes de datos ----------
with st.sidebar:
    with st.expander("🔑 Fuentes de datos", expanded=False):
        st.caption("Pega la clave de cada servicio que quieras usar. Sin claves, la app usa datos de demo.")
        clave_serp = st.text_input("SerpApi (Google Flights)", clave_guardada("SERPAPI_KEY"), type="password",
                                   help="Cuenta gratis en serpapi.com → Dashboard → Your Private API Key")
        clave_duffel = st.text_input("Duffel", clave_guardada("DUFFEL_TOKEN"), type="password",
                                     help="Cuenta en duffel.com → Developers → Access tokens")
        clave_kiwi = st.text_input("Kiwi.com (Tequila)", clave_guardada("KIWI_API_KEY"), type="password",
                                   help="tequila.kiwi.com → My solutions → API key")

    MONEDA = st.radio("💱 Moneda principal", ["A$", "US$"], horizontal=True,
                      help="Los precios se muestran en ambas monedas; esta es la que va primero y en los gráficos.")
    TASA_AUD, origen_tasa = cargar_tipo_cambio()
    st.caption(f"1 US\\$ = {TASA_AUD:.2f} A\\$ ({origen_tasa})".replace(".", ",", 1))
FACTOR = TASA_AUD if MONEDA == "A$" else 1.0

claves = (clave_serp.strip(), clave_duffel.strip(), clave_kiwi.strip())
if "fuentes" not in st.session_state or st.session_state["claves"] != claves:
    st.session_state["claves"] = claves
    st.session_state["fuentes"] = [fuentes.FuenteSerpApi(claves[0]), fuentes.FuenteDuffel(claves[1]),
                                   fuentes.FuenteKiwi(claves[2])]
bv.configurar_fuentes(st.session_state["fuentes"])
modo_real = bv.fuentes_activas() != ["Demo"]
# Para la caché de Streamlit: qué fuentes están activas (sin guardar las claves en claro)
fuentes_key = tuple(f"{f.nombre}:{hashlib.md5(f.clave.encode()).hexdigest()[:8]}"
                    for f in st.session_state["fuentes"] if f.activa)

# ---------- Formulario ----------
with st.sidebar:
    with st.form("formulario"):
        st.header("✈️ Tu búsqueda")
        codigos = sorted(bv.AEROPUERTOS, key=nombre_aeropuerto)
        origen = st.selectbox("Origen", codigos, index=codigos.index("BNE"), format_func=nombre_aeropuerto)
        destino = st.selectbox("Destino", codigos, index=codigos.index("LIM"), format_func=nombre_aeropuerto)

        hoy = date.today()
        fecha_ida = st.date_input("Fecha de ida", hoy + timedelta(days=60), min_value=hoy)
        fecha_vuelta = st.date_input("Fecha de vuelta", hoy + timedelta(days=74), min_value=hoy)
        flex = st.slider("Días flexibles (antes y después)", 0, 7, 2 if modo_real else 3)

        st.subheader("Filtros")
        max_escalas = st.radio("Escalas máximas", [0, 1, 2], index=2, horizontal=True,
                               format_func=lambda n: "Directo" if n == 0 else str(n))
        precio_max = st.number_input(f"Precio máximo por tramo ({MONEDA}, 0 = sin límite)",
                                     min_value=0, value=0, step=50)

        st.subheader("Rutas alternativas")
        escala_min, escala_max = st.slider(
            "Espera en cada conexión (horas)", 1, 24, (3, 10),
            help="Para pasajes separados conviene dejar al menos 3 h: si se atrasa un vuelo, "
                 "la otra aerolínea no te espera.")

        consultas_fechas = 2 * (2 * flex + 1)
        if modo_real:
            st.caption(f"Esta búsqueda usa ~{consultas_fechas} consultas por fuente "
                       "(las repetidas salen de la caché y no se cobran).")
        buscar = st.form_submit_button("🔎 Buscar vuelos", type="primary", width="stretch")

    st.caption("Fuentes activas: " + ", ".join(bv.fuentes_activas()))

if buscar or ("busqueda" not in st.session_state and not modo_real):
    st.session_state["busqueda"] = dict(
        origen=origen, destino=destino, fecha_ida=fecha_ida, fecha_vuelta=fecha_vuelta, flex=flex,
        filtros=(("max_escalas", max_escalas), ("precio_max", round(precio_max / FACTOR) if precio_max else None)),
        escala_min=escala_min, escala_max=escala_max)

if "busqueda" not in st.session_state:
    st.title("✈️ Buscador de vuelos baratos")
    st.info("Completa tu búsqueda en la barra de la izquierda y presiona **🔎 Buscar vuelos**.")
    st.stop()

b = st.session_state["busqueda"]
origen, destino, fecha_ida, fecha_vuelta, flex = b["origen"], b["destino"], b["fecha_ida"], b["fecha_vuelta"], b["flex"]
filtros_key, filtros = b["filtros"], dict(b["filtros"])

if origen == destino:
    st.error("El origen y el destino tienen que ser distintos.")
    st.stop()
if fecha_vuelta <= fecha_ida:
    st.error("La fecha de vuelta tiene que ser posterior a la de ida.")
    st.stop()

st.title(f"{bv.AEROPUERTOS[origen][0]} → {bv.AEROPUERTOS[destino][0]}")
st.markdown(f"**Ida:** {bv.DIAS_COMPLETOS[fecha_ida.weekday()]} {fecha_ida:%d/%m/%Y} · "
            f"**Vuelta:** {bv.DIAS_COMPLETOS[fecha_vuelta.weekday()]} {fecha_vuelta:%d/%m/%Y} · "
            f"{(fecha_vuelta - fecha_ida).days} noches" + (f" · ±{flex} días flexibles" if flex else ""))
if modo_real:
    st.caption(f"Precios reales de: **{', '.join(bv.fuentes_activas())}**, convertidos a dólares. "
               "Los precios cambian a cada rato: confírmalos siempre en la página antes de comprar.")
else:
    st.caption("⚠️ Precios **simulados** con fines de demostración. Para precios reales, agrega tus claves "
               "en **🔑 Fuentes de datos** (barra izquierda).")

# Comparar la misma búsqueda en otras páginas
ida_txt, vuelta_txt = fecha_ida.isoformat(), fecha_vuelta.isoformat()
enlaces = {
    "Google Flights": "https://www.google.com/travel/flights?q=" + quote(
        f"Flights to {destino} from {origen} on {ida_txt} through {vuelta_txt}"),
    "Skyscanner": f"https://www.skyscanner.net/transport/flights/{origen.lower()}/{destino.lower()}/"
                  f"{fecha_ida:%y%m%d}/{fecha_vuelta:%y%m%d}/",
    "Kayak": f"https://www.kayak.com/flights/{origen}-{destino}/{ida_txt}/{vuelta_txt}",
    "Momondo": f"https://www.momondo.com/flight-search/{origen}-{destino}/{ida_txt}/{vuelta_txt}",
    "Kiwi.com": "https://www.kiwi.com/",
    "JetSMART": "https://jetsmart.com/",
    "Sky Airline": "https://www.skyairline.com/",
    "Jetstar": "https://www.jetstar.com/",
}
with st.expander("🔗 Comparar esta búsqueda en otras páginas"):
    columnas = st.columns(4)
    for i, (nombre, url) in enumerate(enlaces.items()):
        columnas[i % 4].link_button(nombre, url, width="stretch")
    st.caption("Google Flights, Skyscanner, Kayak y Momondo se abren con tus fechas; en Kiwi.com y en las "
               "low cost tienes que escribir la búsqueda.")


# Cada función devuelve (resultado, errores de las fuentes) para que los avisos
# sigan apareciendo aunque el resultado salga de la caché.
def _con_errores(funcion, *args, **kwargs):
    bv.ERRORES_FUENTES.clear()
    resultado = funcion(*args, **kwargs)
    return resultado, dict(bv.ERRORES_FUENTES)


@st.cache_data(show_spinner="Buscando vuelos…", ttl=3600)
def cargar_combinaciones(origen, destino, ida, vuelta, flex, filtros, fuentes_key):
    return _con_errores(bv.combinaciones_flexibles, origen, destino, ida, vuelta, flex, **dict(filtros))


@st.cache_data(show_spinner="Buscando vuelos…", ttl=3600)
def cargar_vuelos(origen, destino, desde, hasta, filtros, fuentes_key):
    return _con_errores(bv.buscar_vuelos, origen, destino, desde, hasta, **dict(filtros))


@st.cache_data(show_spinner="Armando rutas alternativas…", ttl=3600)
def cargar_rutas(origen, destino, fecha, escala_min, escala_max, max_escalas, max_hubs, fuentes_key):
    return _con_errores(bv.rutas_alternativas, origen, destino, fecha, escala_min_h=escala_min,
                        escala_max_h=escala_max, max_escalas=max_escalas, max_hubs=max_hubs)


@st.cache_data(show_spinner="Revisando destinos…", ttl=3600)
def cargar_destinos(origen, desde, hasta, filtros, fuentes_key):
    return _con_errores(bv.explorar_destinos, origen, desde, hasta, **dict(filtros))


def mostrar_errores(errores):
    for nombre, error in errores.items():
        st.warning(f"**{nombre}** no respondió: {error}")


combos, errores = cargar_combinaciones(origen, destino, fecha_ida, fecha_vuelta, flex, filtros_key, fuentes_key)
mostrar_errores(errores)

tab_fechas, tab_vuelos, tab_rutas, tab_destinos, tab_alertas = st.tabs(
    ["📅 Mejores fechas", "🛫 Todos los vuelos", "🔀 Rutas alternativas", "🌎 Explorar destinos", "🔔 Alertas"])

# ---------- Mejores fechas ----------
with tab_fechas:
    if combos.empty:
        st.warning("No hay vuelos con esos filtros. Prueba con más escalas o sin precio máximo.")
    else:
        mejor = combos.iloc[0]

        # ---- ¿Conviene comprar ahora? (para la combinación más barata) ----
        v_ida, _ = cargar_vuelos(origen, destino, mejor["fecha_ida"], mejor["fecha_ida"], filtros_key, fuentes_key)
        v_vuelta, _ = cargar_vuelos(destino, origen, mejor["fecha_vuelta"], mejor["fecha_vuelta"],
                                    filtros_key, fuentes_key)
        consejo = mc.evaluar(origen, destino, mejor["fecha_ida"], v_ida, mejor["fecha_vuelta"], v_vuelta,
                             demo=not modo_real)
        if consejo["estado"] != "sin_vuelos":
            with st.container(border=True):
                st.subheader("🛒 ¿Conviene comprar ahora?")
                caja, icono = {"comprar": (st.success, "🟢"), "buen_momento": (st.info, "🔵"),
                               "esperar": (st.warning, "🟡")}[consejo["estado"]]
                caja(f"{icono} **{consejo['titulo']}**")
                for razon in consejo["razones"]:
                    st.markdown("- " + razon)
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Faltan", f"{consejo['dias_faltan']} días",
                          help=f"Ventana ideal: {consejo['ventana'][0]}–{consejo['ventana'][1]} días antes")
                k2.metric("Precio de hoy", (consejo["nivel"] or "sin dato").capitalize())
                if consejo["rango_usd"]:
                    r_min, r_max = consejo["rango_usd"]
                    k3.metric(f"Rango típico ({MONEDA})",
                              f"{r_min * FACTOR:,.0f}–{r_max * FACTOR:,.0f}".replace(",", "."),
                              help=f"{precio_otro(r_min)}–{precio_otro(r_max)}")
                k4.metric("Precio objetivo sugerido", precio_corto(consejo["objetivo_usd"]),
                          help="Para una alerta: la parte baja del rango típico.")
                if st.button("🔔 Avisarme si baja a ese precio", key="alerta_sugerida"):
                    nueva = al.crear_alerta(origen, destino, mejor["fecha_ida"], mejor["fecha_vuelta"],
                                            consejo["objetivo_usd"], filtros.get("max_escalas", 2))
                    al.revisar_alertas(notificar=False, solo_ids=[nueva["id"]], forzar=True)
                    st.success("Alerta creada: la ves en la pestaña 🔔 Alertas. Recuerda activar la revisión diaria.")

                hist = mc.historial_google(v_ida)
                if len(hist) > 1:
                    hist = hist.assign(precio_m=a_moneda(hist["precio_usd"]))
                    linea = alt.Chart(hist).mark_line(point=True, strokeWidth=2, color=AZUL).encode(
                        x=alt.X("dia:T", title=None),
                        y=alt.Y("precio_m:Q", title=MONEDA, scale=alt.Scale(zero=False)),
                        tooltip=[alt.Tooltip("dia:T", title="Día", format="%d/%m/%Y"),
                                 alt.Tooltip("precio_m:Q", title=MONEDA, format=",.0f")])
                    st.markdown(f"**Cómo ha cambiado el precio de la ida ({bv.fecha_txt(mejor['fecha_ida'])}) "
                                "según Google Flights**")
                    st.altair_chart(linea.properties(height=200), width="stretch")
                st.caption("Es una guía basada en patrones habituales de precios; nadie puede asegurar cómo se "
                           "moverá el precio. " + ("Con datos de demo el rango es estimado." if not modo_real else ""))

        c1, c2, c3 = st.columns([1, 1.4, 1])
        c1.metric("Ida y vuelta más barata", precio_corto(mejor["precio_total_usd"]),
                  help=precio_otro(mejor["precio_total_usd"]))
        c2.metric("Fechas", f"{bv.fecha_txt(mejor['fecha_ida'])} → {bv.fecha_txt(mejor['fecha_vuelta'])}",
                  help=f"{mejor['noches']} noches")
        if "ahorro_vs_tus_fechas_usd" in combos:
            c3.metric("Ahorro vs. tus fechas", precio_corto(mejor["ahorro_vs_tus_fechas_usd"]),
                      help=precio_otro(mejor["ahorro_vs_tus_fechas_usd"]))
        else:
            c3.metric("Ahorro vs. tus fechas", "—", help="No hay vuelos en tus fechas exactas.")

        st.subheader(f"Las 3 combinaciones más baratas (de {len(combos)} revisadas)")
        top = combos.head(3).copy()
        tabla = pd.DataFrame({
            "Ida": top["fecha_ida"].map(lambda f: f"{bv.DIAS_SEMANA[f.weekday()]} {f:%d/%m/%Y}"),
            "Aerolínea ida": top["aerolinea_ida"] + " (" + top["via_ida"] + ")",
            "Vuelta": top["fecha_vuelta"].map(lambda f: f"{bv.DIAS_SEMANA[f.weekday()]} {f:%d/%m/%Y}"),
            "Aerolínea vuelta": top["aerolinea_vuelta"] + " (" + top["via_vuelta"] + ")",
            "Noches": top["noches"],
            "Total (A$)": (top["precio_total_usd"] * TASA_AUD).round(0),
            "Total (US$)": top["precio_total_usd"],
        })
        if "ahorro_vs_tus_fechas_usd" in top:
            tabla["Ahorro (A$)"] = (top["ahorro_vs_tus_fechas_usd"] * TASA_AUD).round(0)
            tabla["Ahorro (US$)"] = top["ahorro_vs_tus_fechas_usd"]
        if modo_real:
            tabla["Fuente"] = top["fuente_ida"] + " / " + top["fuente_vuelta"]
        st.dataframe(tabla, hide_index=True, width="stretch")

        st.subheader("Precio total según fechas de ida y vuelta")
        orden_ida = [bv.fecha_txt(f) for f in sorted(combos["fecha_ida"].unique())]
        orden_vuelta = [bv.fecha_txt(f) for f in sorted(combos["fecha_vuelta"].unique())]
        mapa = combos.assign(
            ida=combos["fecha_ida"].map(bv.fecha_txt),
            vuelta=combos["fecha_vuelta"].map(bv.fecha_txt),
            precio_m=a_moneda(combos["precio_total_usd"]),
        )
        eje_x = alt.X("ida:O", title="Ida", sort=orden_ida)
        eje_y = alt.Y("vuelta:O", title="Vuelta", sort=orden_vuelta)
        calor = alt.Chart(mapa).mark_rect(cornerRadius=3, stroke="white", strokeWidth=2).encode(
            x=eje_x, y=eje_y,
            color=alt.Color("precio_m:Q", title=MONEDA,
                            scale=alt.Scale(scheme="blues", reverse=True)),
            tooltip=[alt.Tooltip("ida:O", title="Ida"), alt.Tooltip("vuelta:O", title="Vuelta"),
                     alt.Tooltip("noches:Q", title="Noches"),
                     alt.Tooltip("precio_m:Q", title=f"Total {MONEDA}", format=",.0f")],
        )
        mediana = float(mapa["precio_m"].median())
        texto = alt.Chart(mapa).mark_text(fontSize=11).encode(
            x=eje_x, y=eje_y,
            text=alt.Text("precio_m:Q", format=",.0f"),
            color=alt.condition(alt.datum.precio_m < mediana,
                                alt.value("white"), alt.value("#0b0b0b")),
        )
        st.altair_chart((calor + texto).properties(height=340), width="stretch")
        st.caption("Más oscuro = más barato. Pasa el mouse sobre cada celda para ver el detalle.")

# ---------- Todos los vuelos ----------
with tab_vuelos:
    sentido = st.radio("Tramo", ["Ida", "Vuelta"], horizontal=True)
    if sentido == "Ida":
        a, b_, centro = origen, destino, fecha_ida
    else:
        a, b_, centro = destino, origen, fecha_vuelta
    vuelos, _ = cargar_vuelos(a, b_, centro - timedelta(days=flex), centro + timedelta(days=flex),
                              filtros_key, fuentes_key)

    if vuelos.empty:
        st.warning("No hay vuelos con esos filtros.")
    else:
        por_dia = bv.mas_barato_por_dia(vuelos)
        minimo = por_dia["precio_usd"].min()
        por_dia = por_dia.assign(
            dia_txt=por_dia["fecha"].map(lambda f: f"{bv.DIAS_SEMANA[f.weekday()]} {f:%d/%m}"),
            mejor=por_dia["precio_usd"] == minimo,
            precio_m=a_moneda(por_dia["precio_usd"]),
        )
        barras = alt.Chart(por_dia).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("dia_txt:N", title=None, sort=list(por_dia["dia_txt"])),
            y=alt.Y("precio_m:Q", title=f"{MONEDA} (más barato del día)"),
            color=alt.condition(alt.datum.mejor, alt.value(NARANJA), alt.value(AZUL)),
            tooltip=[alt.Tooltip("dia_txt:N", title="Día"), alt.Tooltip("aerolinea:N", title="Aerolínea"),
                     alt.Tooltip("via:N", title="Escalas"),
                     alt.Tooltip("precio_m:Q", title=MONEDA, format=",.0f")],
        )
        st.altair_chart(barras.properties(height=280), width="stretch")

        vuelos = vuelos.assign(precio_aud=(vuelos["precio_usd"] * TASA_AUD).round(0))
        columnas = ["fecha", "dia", "aerolinea", "salida", "llegada", "duracion_h", "via", "precio_aud",
                    "precio_usd", "fuente", "precios_por_fuente", "enlace"]
        columnas = [c for c in columnas if c in vuelos.columns and vuelos[c].notna().any()]
        st.dataframe(
            vuelos[columnas]
            .rename(columns={"fecha": "Fecha", "dia": "Día", "aerolinea": "Aerolínea", "salida": "Salida",
                             "llegada": "Llegada", "duracion_h": "Duración (h)", "via": "Escalas en",
                             "precio_aud": "Precio (A$)", "precio_usd": "Precio (US$)", "fuente": "Fuente",
                             "precios_por_fuente": "Precio en cada fuente", "enlace": "Comprar"}),
            hide_index=True, width="stretch",
            column_config={"Salida": st.column_config.DatetimeColumn(format="DD/MM HH:mm"),
                           "Llegada": st.column_config.DatetimeColumn(format="DD/MM HH:mm"),
                           "Comprar": st.column_config.LinkColumn(display_text="Abrir")},
        )
        st.caption("Horas locales de cada aeropuerto. \"Precio en cada fuente\" aparece cuando el mismo vuelo "
                   "salió en más de una fuente.")
        st.download_button("Descargar CSV", vuelos.to_csv(index=False).encode("utf-8"),
                           file_name=f"vuelos_{a}_{b_}.csv", mime="text/csv")

# ---------- Rutas alternativas ----------
with tab_rutas:
    st.markdown(
        "Combina vuelos de **distintas aerolíneas con pasajes separados** (por ejemplo una low cost "
        "hasta un hub y otra aerolínea desde ahí) y los compara con la **ruta más directa**: el vuelo "
        "directo si existe o, si no, el pasaje único más barato con menos escalas.")
    c1, c2, c3 = st.columns(3)
    dia_ruta = c1.date_input("Fecha del tramo de ida", fecha_ida, key="fecha_ruta", min_value=date.today())
    c1.caption(f"{bv.DIAS_COMPLETOS[dia_ruta.weekday()].capitalize()} {dia_ruta:%d/%m/%Y}")
    escalas_ruta = c2.radio("Escalas", [1, 2], index=0 if modo_real else 1, horizontal=True)
    max_hubs = c3.slider("Ciudades de conexión a probar", 1, 12, 4 if modo_real else 12,
                         help="Se prueban primero las que quedan más de camino.")

    armar = True
    if modo_real:
        consultas = 1 + max_hubs * 4 + (max_hubs * (max_hubs - 1) // 2) * 3 * (escalas_ruta == 2)
        st.caption(f"Usa hasta ~{consultas} consultas por fuente.")
        armar = st.button("Armar rutas alternativas", type="primary")
        armar = armar or st.session_state.get("rutas_listas") == (dia_ruta, escalas_ruta, max_hubs, b)

    if armar:
        if modo_real:
            st.session_state["rutas_listas"] = (dia_ruta, escalas_ruta, max_hubs, b)
        (referencia, rutas), errores = cargar_rutas(origen, destino, dia_ruta, b["escala_min"],
                                                    b["escala_max"], escalas_ruta, max_hubs, fuentes_key)
        mostrar_errores(errores)

        if referencia is None or rutas.empty:
            st.warning("No encontré vuelos para esa fecha.")
        else:
            ref_txt = "vuelo directo" if referencia["escalas"] == 0 else f"vía {referencia['via']}"
            st.info(f"**Referencia:** {referencia['aerolinea']} ({ref_txt}) · "
                    f"{referencia['duracion_h']} h · **{precio(referencia['precio_usd'])}**".replace("$", "\\$"))

            orden = st.radio("Ordenar por", ["Precio", "Escala más corta", "Duración total"], horizontal=True)
            columna_orden = {"Precio": ["precio_usd", "duracion_h"],
                             "Escala más corta": ["escala_mas_larga_h", "precio_usd"],
                             "Duración total": ["duracion_h", "precio_usd"]}[orden]
            solo_ahorro = st.toggle("Mostrar solo rutas que ahorran", value=False)
            vista = rutas[rutas["ahorro_usd"] > 0] if solo_ahorro else rutas
            vista = vista.sort_values(columna_orden, na_position="first")

            vista = vista.assign(escala_txt=vista["escala_mas_larga_h"].map(
                lambda h: "protegida" if pd.isna(h) else f"{h:.1f} h"),
                precio_aud=(vista["precio_usd"] * TASA_AUD).round(0),
                ahorro_aud=(vista["ahorro_usd"] * TASA_AUD).round(0))
            st.dataframe(
                vista[["ruta", "aerolineas", "tipo", "precio_aud", "precio_usd", "ahorro_aud", "ahorro_usd", "ahorro_pct",
                       "escalas", "escala_txt", "duracion_h", "detalle"]]
                .rename(columns={"tipo": "Tipo", "ruta": "Ruta", "aerolineas": "Aerolíneas",
                                 "escalas": "Escalas", "escala_txt": "Escala más larga",
                                 "duracion_h": "Duración total (h)", "precio_usd": "Precio (US$)",
                                 "ahorro_usd": "Ahorro (US$)", "ahorro_pct": "Ahorro (%)",
                                 "precio_aud": "Precio (A$)", "ahorro_aud": "Ahorro (A$)",
                                 "detalle": "Detalle"}),
                hide_index=True, width="stretch",
                column_config={"Ahorro (%)": st.column_config.NumberColumn(format="%.1f %%")},
            )
            st.caption("Ahorro negativo = sale más caro que la referencia. En pasajes separados la "
                       "\"escala más larga\" es el tiempo de espera entre tus vuelos; si uno se atrasa y "
                       "pierdes el siguiente, la otra aerolínea no está obligada a reubicarte."
                       + ("" if modo_real else " Las horas no consideran zonas horarias (demo)."))

# ---------- Explorar destinos ----------
with tab_destinos:
    # Con fuentes reales se revisa solo la fecha de ida (cada destino y día es una consulta)
    desde = fecha_ida if modo_real else fecha_ida - timedelta(days=flex)
    hasta = fecha_ida if modo_real else fecha_ida + timedelta(days=flex)
    st.markdown(f"El vuelo más barato desde **{nombre_aeropuerto(origen)}** a cada destino, "
                f"saliendo entre el {desde:%d/%m} y el {hasta:%d/%m}.")
    if modo_real:
        st.caption(f"Usa ~{len(bv.AEROPUERTOS) - 1} consultas por fuente.")
    if st.button("Explorar destinos"):
        destinos, errores = cargar_destinos(origen, desde, hasta, filtros_key, fuentes_key)
        mostrar_errores(errores)
        if destinos.empty:
            st.warning("No hay vuelos con esos filtros.")
        else:
            destinos = destinos.assign(precio_m=a_moneda(destinos["precio_usd"]),
                                       precio_aud=(destinos["precio_usd"] * TASA_AUD).round(0))
            grafico = alt.Chart(destinos).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
                                                   color=AZUL).encode(
                x=alt.X("precio_m:Q", title=MONEDA),
                y=alt.Y("ciudad:N", title=None, sort="x"),
                tooltip=[alt.Tooltip("ciudad:N", title="Destino"), alt.Tooltip("fecha:T", title="Fecha"),
                         alt.Tooltip("aerolinea:N", title="Aerolínea"),
                         alt.Tooltip("precio_m:Q", title=MONEDA, format=",.0f")],
            )
            st.altair_chart(grafico.properties(height=26 * len(destinos)), width="stretch")
            st.dataframe(destinos, hide_index=True, width="stretch")

# ---------- Alertas de precio ----------
with tab_alertas:
    st.markdown("Guarda un vuelo y la app revisa su precio **automáticamente** (todos los días o cada los días "
                "que elijas), en tus fechas o en días flexibles. Te avisa cuando baja de tu precio objetivo o "
                "cuando aparece un nuevo precio más bajo.")
    if not modo_real:
        st.warning("Sin claves, las alertas usan precios de **demo**. Para alertas reales, guarda tu clave de "
                   "SerpApi en **⚙️ Configurar avisos y claves** (más abajo).")

    with st.container(border=True):
        st.subheader("➕ Nueva alerta")
        st.caption(f"Ruta: **{nombre_aeropuerto(origen)} → {nombre_aeropuerto(destino)}** "
                   "(cámbiala en la barra izquierda y presiona Buscar).")
        c1, c2, c3 = st.columns(3)
        a_ida = c1.date_input("Ida", fecha_ida, min_value=date.today(), key="alerta_ida")
        c1.caption(bv.DIAS_COMPLETOS[a_ida.weekday()].capitalize())
        a_solo_ida = c1.checkbox("Solo ida", value=False, key="alerta_solo_ida")
        a_vuelta = c1.date_input("Vuelta", fecha_vuelta, min_value=date.today(), key="alerta_vuelta",
                                 disabled=a_solo_ida)
        if not a_solo_ida:
            c1.caption(bv.DIAS_COMPLETOS[a_vuelta.weekday()].capitalize())
        a_flex = c2.select_slider("Días flexibles (±)", options=[0, 1, 2, 3], value=0, key="alerta_flex",
                                  help="También vigila esa cantidad de días antes y después de cada fecha.")
        a_cada = c2.select_slider("Revisar", options=[1, 2, 3, 7], value=1, key="alerta_cada",
                                  format_func=lambda n: "todos los días" if n == 1 else f"cada {n} días")
        a_objetivo = c3.number_input(f"Precio objetivo total ({MONEDA})", min_value=0, value=0, step=50,
                                     key="alerta_objetivo",
                                     help="Te avisa cuando el precio baje de este valor. "
                                          "Con 0, te avisa cada vez que aparezca un precio más bajo.")
        a_escalas = c3.radio("Escalas máximas", [0, 1, 2], index=2, horizontal=True, key="alerta_escalas",
                             format_func=lambda n: "Directo" if n == 0 else str(n))

        borrador = {"fecha_vuelta": None if a_solo_ida else a_vuelta, "flex_dias": a_flex, "cada_dias": a_cada}
        uso_nueva = al.consultas_al_mes(borrador)
        uso_actual = sum(al.consultas_al_mes(a) for a in al.leer_alertas())
        cupo = al.busquedas_al_mes()
        muy_alto = uso_actual + uso_nueva > cupo * 0.8
        texto_uso = (f"Esta alerta usa **{al.consultas_por_revision(borrador)} consultas por revisión**, "
                     f"unas **{uso_nueva} al mes** por fuente. Con tus otras alertas sumarías "
                     f"**{uso_actual + uso_nueva} de {cupo}** búsquedas al mes de tu plan de SerpApi.")
        (st.warning if muy_alto else st.caption)(
            texto_uso + (" Te quedaría poco para buscar: prueba revisar cada más días o con menos días "
                         "flexibles." if muy_alto else ""))

        if st.button("🔔 Crear alerta", type="primary"):
            if not a_solo_ida and a_vuelta <= a_ida:
                st.error("La vuelta tiene que ser posterior a la ida.")
            else:
                objetivo_usd = round(a_objetivo / FACTOR) if a_objetivo else None  # se guarda en US$
                nueva = al.crear_alerta(origen, destino, a_ida, None if a_solo_ida else a_vuelta,
                                        objetivo_usd, a_escalas, flex_dias=a_flex, cada_dias=a_cada)
                with st.spinner("Revisando el precio de hoy…"):
                    al.revisar_alertas(notificar=False, solo_ids=[nueva["id"]], forzar=True)
                st.session_state["avisos_alertas"] = ["Alerta creada. Ya quedó guardado el precio de hoy."]
                st.rerun()

    lista = al.leer_alertas()
    historial = al.leer_historial()
    st.subheader("Tus alertas")
    for aviso in st.session_state.pop("avisos_alertas", []):
        # "$" se escapa para que Streamlit no lo lea como fórmula matemática
        texto = aviso.replace("$", "\\$").replace("\n", "  \n")
        (st.success if aviso.startswith(("✈️", "Alerta creada")) else st.info)(texto)
    if not lista:
        st.info("Todavía no tienes alertas.")
    else:
        for alerta in lista:
            precios = historial[historial["alerta_id"] == alerta["id"]].sort_values("revisado")
            with st.container(border=True):
                c1, c2 = st.columns([6, 1])
                objetivo = (f"Objetivo: {precio(alerta['precio_objetivo'])}" if alerta.get("precio_objetivo")
                            else "Avisa con cualquier bajada")
                cada = alerta.get("cada_dias", 1)
                objetivo += (" · revisa " + ("todos los días" if cada == 1 else f"cada {cada} días")
                             + f" · ~{al.consultas_al_mes(alerta)} consultas/mes")
                c1.markdown(f"**{al.describir(alerta)}**  \n{objetivo}".replace("$", "\\$"))
                if c2.button("🗑️ Borrar", key=f"borrar_{alerta['id']}"):
                    al.borrar_alerta(alerta["id"])
                    st.rerun()
                if precios.empty:
                    st.caption("Todavía sin revisiones.")
                else:
                    ultimo, primero = precios.iloc[-1]["precio_total_usd"], precios.iloc[0]["precio_total_usd"]
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Último precio", precio_corto(ultimo), help=precio_otro(ultimo),
                              delta=(f"{(ultimo - primero) * FACTOR:+,.0f} {MONEDA} vs. el inicio"
                                     if ultimo != primero else None),
                              delta_color="inverse")
                    minimo_visto = precios["precio_total_usd"].min()
                    m2.metric("Mínimo visto", precio_corto(minimo_visto), help=precio_otro(minimo_visto))
                    st.caption("Mejor opción en la última revisión: " + str(precios.iloc[-1]["detalle"]))
                    m3.metric("Revisiones", len(precios))

        if not historial.empty:
            nombres = {a["id"]: al.describir(a) for a in lista}
            datos = historial[historial["alerta_id"].isin(nombres)].assign(
                alerta=lambda d: d["alerta_id"].map(nombres),
                precio_m=lambda d: a_moneda(d["precio_total_usd"]))
            if not datos.empty:
                st.markdown("**Cómo ha cambiado el precio**")
                linea = alt.Chart(datos).mark_line(point=alt.OverlayMarkDef(size=60), strokeWidth=2).encode(
                    x=alt.X("revisado:T", title="Fecha de revisión"),
                    y=alt.Y("precio_m:Q", title=MONEDA, scale=alt.Scale(zero=False)),
                    color=alt.Color("alerta:N", title=None, legend=alt.Legend(orient="bottom", labelLimit=400),
                                    scale=alt.Scale(range=COLORES_SERIES)),
                    tooltip=[alt.Tooltip("alerta:N", title="Alerta"),
                             alt.Tooltip("revisado:T", title="Revisado", format="%d/%m %H:%M"),
                             alt.Tooltip("precio_m:Q", title=MONEDA, format=",.0f"),
                             alt.Tooltip("detalle:N", title="Vuelos")],
                )
                st.altair_chart(linea.properties(height=260), width="stretch")

        if st.button("🔄 Revisar todas ahora"):
            with st.spinner("Revisando precios…"):
                st.session_state["avisos_alertas"] = al.revisar_alertas(notificar=True, forzar=True) or \
                    ["Ningún precio bajó por ahora."]
            st.rerun()

    st.divider()
    st.subheader("⏰ Revisión automática diaria")
    if os.name == "nt":
        activa = al.revision_diaria_activa()
        st.markdown(("✅ **Activada.** " if activa else "⏸️ **Desactivada.** ")
                    + "Windows revisa tus alertas solo, una vez al día, aunque la app esté cerrada. "
                      "El computador tiene que estar encendido a esa hora.")
        c1, c2, c3 = st.columns([1, 1, 2])
        hora = c1.time_input("Hora", value=pd.Timestamp("09:00").time(), step=1800)
        if c2.button("Activar" if not activa else "Cambiar hora", type="primary"):
            ok, msg = al.activar_revision_diaria(hora.strftime("%H:%M"))
            (st.success if ok else st.error)(msg)
        if activa and c3.button("Desactivar"):
            ok, msg = al.desactivar_revision_diaria()
            (st.success if ok else st.error)(msg)
    else:
        st.markdown("Programa `python alertas.py` para que se ejecute una vez al día "
                    "(en Windows, la app lo hace con un botón).")

    with st.expander("⚙️ Configurar avisos y claves"):
        secretos = al.leer_secretos()
        st.markdown("Para que la revisión diaria funcione con la app cerrada, las claves se guardan en tu "
                    "computador (`.streamlit/secrets.toml`, que **no** se sube a GitHub).\n\n"
                    "- **Escritorio**: siempre activo; aparece una notificación de Windows.\n"
                    "- **Email**: con Gmail necesitas una *contraseña de aplicación* "
                    "(myaccount.google.com → Seguridad → Contraseñas de aplicaciones).\n"
                    "- **Telegram**: te llega al celular. Ver los pasos en el README.")
        with st.form("config_avisos"):
            n_serp = st.text_input("Clave de SerpApi", secretos.get("SERPAPI_KEY", ""), type="password")
            c1, c2 = st.columns(2)
            n_email = c1.text_input("Tu Gmail", secretos.get("EMAIL_REMITENTE", ""))
            n_clave = c2.text_input("Contraseña de aplicación de Gmail", secretos.get("EMAIL_CLAVE_APP", ""),
                                    type="password")
            n_tg_token = c1.text_input("Token del bot de Telegram", secretos.get("TELEGRAM_TOKEN", ""),
                                       type="password")
            n_tg_chat = c2.text_input("Chat ID de Telegram", secretos.get("TELEGRAM_CHAT_ID", ""))
            n_cupo = c1.number_input("Búsquedas al mes de tu plan de SerpApi", min_value=1, step=50,
                                     value=al.busquedas_al_mes(),
                                     help="El plan gratis trae 250. Míralo en tu Dashboard de serpapi.com.")
            if st.form_submit_button("💾 Guardar"):
                al.guardar_secretos({"BUSQUEDAS_MES": str(int(n_cupo)), "SERPAPI_KEY": n_serp,
                                     "EMAIL_REMITENTE": n_email,
                                     "EMAIL_CLAVE_APP": n_clave, "TELEGRAM_TOKEN": n_tg_token,
                                     "TELEGRAM_CHAT_ID": n_tg_chat})
                st.success("Guardado.")
        if st.button("📨 Enviar aviso de prueba"):
            canales = al.enviar_avisos(["✈️ Prueba: así te llegará el aviso cuando baje el precio de tu vuelo."])
            if canales:
                st.success("Aviso enviado por: " + ", ".join(canales))
            else:
                st.warning("No se pudo enviar por ningún canal. Revisa los datos guardados.")

if modo_real:
    usadas = " · ".join(f"{f.nombre}: {f.consultas}" for f in st.session_state["fuentes"] if f.activa)
    st.sidebar.caption(f"Consultas a las APIs en esta sesión: {usadas}")

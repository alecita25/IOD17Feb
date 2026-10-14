"""
App web del buscador de vuelos baratos (datos de demo).

Ejecutar con:
    streamlit run app.py
"""

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

import buscador_vuelos as bv

AZUL, NARANJA = "#2a78d6", "#eb6834"

st.set_page_config(page_title="Buscador de vuelos baratos", page_icon="✈️", layout="wide")


def nombre_aeropuerto(codigo):
    ciudad, pais, _, _ = bv.AEROPUERTOS[codigo]
    return f"{ciudad}, {pais} ({codigo})"


def usd(valor):
    return f"US$ {valor:,.0f}".replace(",", ".")


# ---------- Formulario ----------
with st.sidebar:
    st.header("✈️ Tu búsqueda")
    codigos = sorted(bv.AEROPUERTOS, key=nombre_aeropuerto)
    origen = st.selectbox("Origen", codigos, index=codigos.index("BNE"),
                          format_func=nombre_aeropuerto)
    destino = st.selectbox("Destino", codigos, index=codigos.index("LIM"),
                           format_func=nombre_aeropuerto)

    hoy = date.today()
    fecha_ida = st.date_input("Fecha de ida", hoy + timedelta(days=60), min_value=hoy)
    fecha_vuelta = st.date_input("Fecha de vuelta", fecha_ida + timedelta(days=14),
                                 min_value=fecha_ida + timedelta(days=1))
    flex = st.slider("Días flexibles (antes y después)", 0, 7, 3)

    st.subheader("Filtros")
    max_escalas = st.radio("Escalas máximas", [0, 1, 2], index=2, horizontal=True,
                           format_func=lambda n: "Directo" if n == 0 else str(n))
    precio_max = st.number_input("Precio máximo por tramo (US$, 0 = sin límite)",
                                 min_value=0, value=0, step=50)

    st.subheader("Rutas alternativas")
    escala_min, escala_max = st.slider("Espera en cada conexión (horas)", 1, 24, (3, 10),
                                       help="Para pasajes separados conviene dejar al menos "
                                            "3 h: si se atrasa un vuelo, la otra aerolínea no te espera.")

if origen == destino:
    st.error("El origen y el destino tienen que ser distintos.")
    st.stop()

filtros = dict(max_escalas=max_escalas, precio_max=precio_max or None)

st.title(f"{bv.AEROPUERTOS[origen][0]} → {bv.AEROPUERTOS[destino][0]}")
st.caption("⚠️ Precios **simulados** con fines de demostración (distancia, temporada, día de la semana, "
           "anticipación, escalas y aerolínea). No son tarifas reales.")


@st.cache_data(show_spinner="Buscando vuelos…")
def cargar_combinaciones(origen, destino, ida, vuelta, flex, filtros):
    return bv.combinaciones_flexibles(origen, destino, ida, vuelta, flex, **dict(filtros))


@st.cache_data(show_spinner="Buscando vuelos…")
def cargar_vuelos(origen, destino, desde, hasta, filtros):
    return bv.buscar_vuelos(origen, destino, desde, hasta, **dict(filtros))


@st.cache_data(show_spinner="Armando rutas alternativas…")
def cargar_rutas(origen, destino, fecha, escala_min, escala_max, max_escalas):
    return bv.rutas_alternativas(origen, destino, fecha, escala_min_h=escala_min,
                                 escala_max_h=escala_max, max_escalas=max_escalas)


filtros_key = tuple(sorted(filtros.items()))
combos = cargar_combinaciones(origen, destino, fecha_ida, fecha_vuelta, flex, filtros_key)

tab_fechas, tab_vuelos, tab_rutas, tab_destinos = st.tabs(
    ["📅 Mejores fechas", "🛫 Todos los vuelos", "🔀 Rutas alternativas", "🌎 Explorar destinos"])

# ---------- Mejores fechas ----------
with tab_fechas:
    if combos.empty:
        st.warning("No hay vuelos con esos filtros. Prueba con más escalas o sin precio máximo.")
    else:
        mejor = combos.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Ida y vuelta más barata", usd(mejor["precio_total_usd"]))
        c2.metric("Fechas", f"{mejor['fecha_ida']:%d/%m} → {mejor['fecha_vuelta']:%d/%m}",
                  help=f"{mejor['noches']} noches")
        if "ahorro_vs_tus_fechas_usd" in combos:
            c3.metric("Ahorro vs. tus fechas", usd(mejor["ahorro_vs_tus_fechas_usd"]))
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
            "Total (US$)": top["precio_total_usd"],
        })
        if "ahorro_vs_tus_fechas_usd" in top:
            tabla["Ahorro vs. tus fechas (US$)"] = top["ahorro_vs_tus_fechas_usd"]
        st.dataframe(tabla, hide_index=True, width="stretch")

        st.subheader("Precio total según fechas de ida y vuelta")
        orden_ida = [f"{f:%d/%m}" for f in sorted(combos["fecha_ida"].unique())]
        orden_vuelta = [f"{f:%d/%m}" for f in sorted(combos["fecha_vuelta"].unique())]
        mapa = combos.assign(
            ida=combos["fecha_ida"].map(lambda f: f"{f:%d/%m}"),
            vuelta=combos["fecha_vuelta"].map(lambda f: f"{f:%d/%m}"),
        )
        eje_x = alt.X("ida:O", title="Ida", sort=orden_ida)
        eje_y = alt.Y("vuelta:O", title="Vuelta", sort=orden_vuelta)
        calor = alt.Chart(mapa).mark_rect(cornerRadius=3, stroke="white", strokeWidth=2).encode(
            x=eje_x, y=eje_y,
            color=alt.Color("precio_total_usd:Q", title="US$",
                            scale=alt.Scale(scheme="blues", reverse=True)),
            tooltip=[alt.Tooltip("ida:O", title="Ida"), alt.Tooltip("vuelta:O", title="Vuelta"),
                     alt.Tooltip("noches:Q", title="Noches"),
                     alt.Tooltip("precio_total_usd:Q", title="Total US$", format=",.0f")],
        )
        mediana = float(mapa["precio_total_usd"].median())
        texto = alt.Chart(mapa).mark_text(fontSize=11).encode(
            x=eje_x, y=eje_y,
            text=alt.Text("precio_total_usd:Q", format=",.0f"),
            color=alt.condition(alt.datum.precio_total_usd < mediana,
                                alt.value("white"), alt.value("#0b0b0b")),
        )
        st.altair_chart((calor + texto).properties(height=340), width="stretch")
        st.caption("Más oscuro = más barato. Pasa el mouse sobre cada celda para ver el detalle.")

# ---------- Todos los vuelos ----------
with tab_vuelos:
    sentido = st.radio("Tramo", ["Ida", "Vuelta"], horizontal=True)
    if sentido == "Ida":
        a, b, centro = origen, destino, fecha_ida
    else:
        a, b, centro = destino, origen, fecha_vuelta
    vuelos = cargar_vuelos(a, b, centro - timedelta(days=flex), centro + timedelta(days=flex), filtros_key)

    if vuelos.empty:
        st.warning("No hay vuelos con esos filtros.")
    else:
        por_dia = bv.mas_barato_por_dia(vuelos)
        minimo = por_dia["precio_usd"].min()
        por_dia = por_dia.assign(
            dia_txt=por_dia["fecha"].map(lambda f: f"{bv.DIAS_SEMANA[f.weekday()]} {f:%d/%m}"),
            mejor=por_dia["precio_usd"] == minimo,
        )
        barras = alt.Chart(por_dia).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("dia_txt:N", title=None, sort=list(por_dia["dia_txt"])),
            y=alt.Y("precio_usd:Q", title="US$ (más barato del día)"),
            color=alt.condition(alt.datum.mejor, alt.value(NARANJA), alt.value(AZUL)),
            tooltip=[alt.Tooltip("dia_txt:N", title="Día"), alt.Tooltip("aerolinea:N", title="Aerolínea"),
                     alt.Tooltip("via:N", title="Escalas"),
                     alt.Tooltip("precio_usd:Q", title="US$", format=",.0f")],
        )
        st.altair_chart(barras.properties(height=280), width="stretch")

        st.dataframe(
            vuelos[["fecha", "dia", "aerolinea", "salida", "llegada", "duracion_h", "via", "precio_usd"]]
            .rename(columns={"fecha": "Fecha", "dia": "Día", "aerolinea": "Aerolínea", "salida": "Salida",
                             "llegada": "Llegada", "duracion_h": "Duración (h)", "via": "Escalas en",
                             "precio_usd": "Precio (US$)"}),
            hide_index=True, width="stretch",
            column_config={"Salida": st.column_config.DatetimeColumn(format="DD/MM HH:mm"),
                           "Llegada": st.column_config.DatetimeColumn(format="DD/MM HH:mm")},
        )
        st.download_button("Descargar CSV", vuelos.to_csv(index=False).encode("utf-8"),
                           file_name=f"vuelos_{a}_{b}.csv", mime="text/csv")

# ---------- Rutas alternativas ----------
with tab_rutas:
    st.markdown(
        "Combina vuelos de **distintas aerolíneas con pasajes separados** (por ejemplo una low cost "
        "hasta un hub y otra aerolínea desde ahí) y los compara con la **ruta más directa**: el vuelo "
        "directo si existe o, si no, el pasaje único más barato con menos escalas.")
    dia_ruta = st.date_input("Fecha del tramo de ida", fecha_ida, key="fecha_ruta",
                             min_value=date.today())
    referencia, rutas = cargar_rutas(origen, destino, dia_ruta, escala_min, escala_max, max_escalas)

    if referencia is None or rutas.empty:
        st.warning("No encontré vuelos para esa fecha.")
    else:
        ref_txt = "vuelo directo" if referencia["escalas"] == 0 else f"vía {referencia['via']}"
        st.info(f"**Referencia:** {referencia['aerolinea']} ({ref_txt}) · "
                f"{referencia['duracion_h']} h · **{usd(referencia['precio_usd'])}**")

        orden = st.radio("Ordenar por", ["Precio", "Escala más corta", "Duración total"], horizontal=True)
        columna_orden = {"Precio": ["precio_usd", "duracion_h"],
                         "Escala más corta": ["escala_mas_larga_h", "precio_usd"],
                         "Duración total": ["duracion_h", "precio_usd"]}[orden]
        solo_ahorro = st.toggle("Mostrar solo rutas que ahorran", value=False)
        vista = rutas[rutas["ahorro_usd"] > 0] if solo_ahorro else rutas
        vista = vista.sort_values(columna_orden, na_position="first")

        vista = vista.assign(escala_txt=vista["escala_mas_larga_h"].map(
            lambda h: "protegida" if pd.isna(h) else f"{h:.1f} h"))
        st.dataframe(
            vista[["ruta", "aerolineas", "tipo", "precio_usd", "ahorro_usd", "ahorro_pct",
                   "escalas", "escala_txt", "duracion_h", "detalle"]]
            .rename(columns={"tipo": "Tipo", "ruta": "Ruta", "aerolineas": "Aerolíneas",
                             "escalas": "Escalas", "escala_txt": "Escala más larga",
                             "duracion_h": "Duración total (h)", "precio_usd": "Precio (US$)",
                             "ahorro_usd": "Ahorro (US$)", "ahorro_pct": "Ahorro (%)",
                             "detalle": "Detalle"}),
            hide_index=True, width="stretch",
            column_config={"Ahorro (%)": st.column_config.NumberColumn(format="%.1f %%")},
        )
        st.caption("Ahorro negativo = sale más caro que la referencia. En pasajes separados la "
                   "\"escala más larga\" es el tiempo de espera entre tus vuelos; si uno se atrasa y "
                   "pierdes el siguiente, la otra aerolínea no está obligada a reubicarte. "
                   "Las horas no consideran zonas horarias (demo).")

# ---------- Explorar destinos ----------
with tab_destinos:
    st.markdown(f"El vuelo más barato desde **{nombre_aeropuerto(origen)}** a cada destino, "
                f"saliendo entre el {fecha_ida - timedelta(days=flex):%d/%m} y el "
                f"{fecha_ida + timedelta(days=flex):%d/%m}.")
    if st.button("Explorar destinos"):
        with st.spinner("Revisando destinos…"):
            destinos = bv.explorar_destinos(origen, fecha_ida - timedelta(days=flex),
                                            fecha_ida + timedelta(days=flex), **filtros)
        if destinos.empty:
            st.warning("No hay vuelos con esos filtros.")
        else:
            grafico = alt.Chart(destinos).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
                                                   color=AZUL).encode(
                x=alt.X("precio_usd:Q", title="US$"),
                y=alt.Y("ciudad:N", title=None, sort="x"),
                tooltip=[alt.Tooltip("ciudad:N", title="Destino"), alt.Tooltip("fecha:T", title="Fecha"),
                         alt.Tooltip("aerolinea:N", title="Aerolínea"),
                         alt.Tooltip("precio_usd:Q", title="US$", format=",.0f")],
            )
            st.altair_chart(grafico.properties(height=26 * len(destinos)), width="stretch")
            st.dataframe(destinos, hide_index=True, width="stretch")

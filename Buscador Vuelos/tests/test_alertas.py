"""Pruebas de las alertas de precio (sin internet: se usan datos de demo y avisos simulados)."""

import sys
import tomllib
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import alertas as al  # noqa: E402
import buscador_vuelos as bv  # noqa: E402

HOY = "2026-10-17"


@pytest.fixture(autouse=True)
def archivos_temporales(tmp_path, monkeypatch):
    monkeypatch.setattr(al, "ARCHIVO_ALERTAS", tmp_path / "alertas.json")
    monkeypatch.setattr(al, "ARCHIVO_HISTORIAL", tmp_path / "historial.csv")
    monkeypatch.setattr(al, "ARCHIVO_SECRETOS", tmp_path / ".streamlit" / "secrets.toml")
    monkeypatch.setattr(al, "ARCHIVO_BAT", tmp_path / "revisar.bat")
    bv.configurar_fuentes([])
    yield tmp_path


def test_crear_y_borrar_alerta():
    a = al.crear_alerta("BNE", "LIM", "2026-12-10", "2026-12-24", 1500)
    assert al.leer_alertas() == [a]
    assert al.describir(a) == "BNE → LIM · ida jue 10/12/2026 · vuelta jue 24/12/2026"
    al.borrar_alerta(a["id"])
    assert al.leer_alertas() == []


def test_primera_revision_guarda_precio_sin_avisar():
    a = al.crear_alerta("BNE", "LIM", "2026-12-10", "2026-12-24")
    avisos = al.revisar_alertas(notificar=False, hoy=HOY)
    historial = al.leer_historial()
    assert avisos == []  # sin precio anterior ni objetivo, no hay con qué comparar
    assert len(historial) == 1 and historial.iloc[0]["alerta_id"] == a["id"]
    assert historial.iloc[0]["precio_total_usd"] > 0


def test_avisa_cuando_baja_del_objetivo():
    al.crear_alerta("BNE", "LIM", "2026-12-10", "2026-12-24", precio_objetivo=99999)
    avisos = al.revisar_alertas(notificar=False, hoy=HOY)
    assert len(avisos) == 1 and "precio objetivo" in avisos[0]


def test_avisa_nuevo_minimo_y_no_repite_si_no_baja():
    a = al.crear_alerta("BNE", "LIM", "2026-12-10")
    precio = al.precio_actual(a)["precio_total_usd"]
    # Simula que ayer estaba bastante más caro
    al.leer_historial()
    import pandas as pd
    pd.DataFrame([{"revisado": "2026-10-16 09:00:00", "alerta_id": a["id"], "precio_total_usd": precio + 200,
                   "detalle": "x", "fuente": "Demo"}]).to_csv(al.ARCHIVO_HISTORIAL, index=False)
    with mock.patch.object(al, "date") as fecha:
        fecha.today.return_value = bv._a_fecha(HOY)
        fecha.fromisoformat.side_effect = lambda s: bv._a_fecha(s)
        avisos = al.revisar_alertas(notificar=False, hoy=HOY)
    assert len(avisos) == 1 and "Nuevo precio más bajo" in avisos[0]
    # Misma revisión otra vez: el precio no bajó respecto del nuevo mínimo -> sin aviso
    assert al.revisar_alertas(notificar=False, hoy=HOY) == []


def test_ignora_alertas_con_fecha_pasada():
    al.crear_alerta("BNE", "LIM", "2026-10-01")
    assert al.revisar_alertas(notificar=False, hoy=HOY) == []
    assert al.leer_historial().empty


def test_envia_por_email_y_telegram():
    secretos = {"EMAIL_REMITENTE": "yo@gmail.com", "EMAIL_CLAVE_APP": "abcd efgh", "EMAIL_DESTINO": "",
                "TELEGRAM_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "42"}
    with mock.patch.object(al.smtplib, "SMTP_SSL") as smtp, mock.patch.object(al.requests, "post") as post, \
         mock.patch.object(al, "_aviso_escritorio", return_value=False):
        canales = al.enviar_avisos(["✈️ bajó"], secretos)
    assert canales == ["email", "telegram"]
    servidor = smtp.return_value.__enter__.return_value
    servidor.login.assert_called_once_with("yo@gmail.com", "abcdefgh")
    assert post.call_args.kwargs["json"] == {"chat_id": "42", "text": "✈️ bajó"}


def test_sin_configuracion_no_envia_nada():
    with mock.patch.object(al, "_aviso_escritorio", return_value=False):
        assert al.enviar_avisos(["x"], {}) == []


def test_guardar_secretos_conserva_los_anteriores():
    al.guardar_secretos({"SERPAPI_KEY": "abc"})
    al.guardar_secretos({"TELEGRAM_CHAT_ID": "42", "EMAIL_REMITENTE": 'con "comillas"'})
    datos = tomllib.loads(al.ARCHIVO_SECRETOS.read_text(encoding="utf-8"))
    assert datos == {"SERPAPI_KEY": "abc", "TELEGRAM_CHAT_ID": "42", "EMAIL_REMITENTE": 'con "comillas"'}
    assert al.leer_secretos()["SERPAPI_KEY"] == "abc"


def test_bat_usa_el_python_actual():
    contenido = al.crear_bat().read_bytes().decode("utf-8")
    assert sys.executable in contenido and "alertas.py" in contenido
    assert contenido.count("\r\n") == 3 and "\r\r" not in contenido


def test_dias_flexibles_encuentra_precio_igual_o_mas_barato():
    exacta = al.crear_alerta("BNE", "LIM", "2026-12-10", "2026-12-24")
    flexible = al.crear_alerta("BNE", "LIM", "2026-12-10", "2026-12-24", flex_dias=2)
    p_exacta = al.precio_actual(exacta, hoy=HOY)["precio_total_usd"]
    p_flex = al.precio_actual(flexible, hoy=HOY)
    assert p_flex["precio_total_usd"] <= p_exacta
    assert "Ida " in p_flex["detalle"] and "Vuelta " in p_flex["detalle"]
    assert al.describir(flexible).endswith("(±2 días)")


def test_consultas_al_mes():
    assert al.consultas_al_mes(al.crear_alerta("BNE", "LIM", "2026-12-10", "2026-12-24")) == 60
    assert al.consultas_al_mes(al.crear_alerta("BNE", "LIM", "2026-12-10", flex_dias=1, cada_dias=3)) == 30
    assert al.consultas_por_revision(al.crear_alerta("BNE", "LIM", "2026-12-10", "2026-12-24", flex_dias=2)) == 10


def test_respeta_frecuencia_salvo_que_se_fuerce():
    al.crear_alerta("BNE", "LIM", "2026-12-10", cada_dias=3)
    al.revisar_alertas(notificar=False, hoy=HOY)
    al.revisar_alertas(notificar=False, hoy="2026-10-18")  # 1 día después: no toca
    assert len(al.leer_historial()) == 1
    al.revisar_alertas(notificar=False, hoy="2026-10-18", forzar=True)
    al.revisar_alertas(notificar=False, hoy="2026-10-21")  # 3 días después del 18: sí toca
    assert len(al.leer_historial()) == 3


def test_no_consulta_fechas_pasadas():
    bv.configurar_fuentes([])
    with mock.patch.object(bv, "obtener_vuelos", return_value=[]) as obtener:
        bv.buscar_vuelos("BNE", "LIM", "2026-10-15", "2026-10-19", hoy=HOY)
    assert [c.args[2].isoformat() for c in obtener.call_args_list] == ["2026-10-17", "2026-10-18", "2026-10-19"]


def test_busquedas_al_mes_por_defecto_y_guardado():
    assert al.busquedas_al_mes() == 250
    al.guardar_secretos({"BUSQUEDAS_MES": "1000"})
    assert al.busquedas_al_mes() == 1000

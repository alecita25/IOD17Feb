# Buscador de vuelos baratos

Metabuscador de vuelos: junta resultados de varias fuentes, quita los repetidos y te muestra el más barato,
con fechas flexibles y rutas alternativas. Sin claves funciona con **datos de demo** (precios simulados).

- `app.py`: la **app web** (Streamlit).
- `fuentes.py`: las fuentes de datos (demo, Google Flights vía SerpApi, Duffel y Kiwi.com).
- `buscador_vuelos.py`: la lógica de búsqueda (fechas flexibles, rutas alternativas, explorar destinos).
- `Buscador de vuelos baratos.ipynb`: versión notebook (usa datos de demo).
- `alertas.py`: alertas de precio (revisión diaria y avisos).
- `tests/`: pruebas (`python -m pytest tests`).

## Cómo abrir la app (Windows, PowerShell)

```
cd "$HOME\Downloads\IOD17Feb-buscador-vuelos\Buscador Vuelos"
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Se abre en el navegador en `http://localhost:8501`. No cierres la ventana negra mientras la usas.

## Fuentes de precios reales

La app consulta cada fuente que tenga clave y junta los resultados. Las claves se pegan en la barra
izquierda, en **🔑 Fuentes de datos**.

| Fuente | Qué aporta | Cómo obtener la clave |
|---|---|---|
| **Google Flights (SerpApi)** | La mayoría de las aerolíneas y agencias, incluidas low cost (JetSMART, Sky, Jetstar) | Crea una cuenta gratis en [serpapi.com](https://serpapi.com) → *Dashboard* → *Your Private API Key*. Incluye unas 100 búsquedas al mes. |
| **Duffel** | Más de 300 aerolíneas conectadas directamente | Crea una cuenta en [duffel.com](https://duffel.com) → *Developers* → *Access tokens*. Usa un token de prueba (`duffel_test_...`) para practicar; los precios reales requieren un token *live*. |
| **Kiwi.com (Tequila)** | Combina aerolíneas distintas con pasajes separados para bajar el precio | Solicita acceso en [tequila.kiwi.com](https://tequila.kiwi.com). El acceso para nuevos usuarios no está garantizado. |

Para no escribir las claves cada vez: copia `.streamlit/secrets.toml.ejemplo` como `.streamlit/secrets.toml`
y pégalas ahí. Ese archivo está en `.gitignore`, así que **nunca se sube a GitHub**.

### Para no gastar búsquedas
- La app solo consulta las APIs cuando presionas **🔎 Buscar vuelos**, y muestra cuántas consultas usará cada búsqueda.
- Las respuestas se guardan 6 horas en la carpeta `.cache_vuelos`: repetir una búsqueda no gasta consultas.
- Con fuentes reales, **Rutas alternativas** y **Explorar destinos** se ejecutan con su propio botón, porque usan más consultas.
- Si una clave es rechazada, la app deja de usar esa fuente y te muestra el aviso.

### Limitaciones
- Duffel puede devolver precios en otra moneda; se convierten a dólares con el tipo de cambio aproximado de
  `TASAS_A_USD` en `fuentes.py`.
- Las páginas que no tienen API (por ejemplo, las de JetSMART o Sky) no se consultan directamente: sus vuelos
  llegan a través de Google Flights. La app tiene botones para abrir tu búsqueda en Skyscanner, Kayak,
  Momondo y Google Flights.
- Los precios cambian a cada rato: confírmalos siempre en la página de la aerolínea o agencia antes de comprar.

## La app

- **📅 Mejores fechas**: revisa todas las combinaciones de ida y vuelta moviendo cada fecha ± N días,
  muestra las 3 más baratas, cuánto ahorran frente a tus fechas exactas y un mapa de calor de precios.
- **🛫 Todos los vuelos**: calendario de precios por día y la lista completa, con la fuente de cada vuelo y su
  precio en cada fuente (descargable en CSV).
- **🔀 Rutas alternativas**: arma rutas con 1 o 2 escalas combinando aerolíneas con pasajes separados
  (low cost incluidas) y muestra cuánto ahorra cada una frente a la ruta más directa.
- **🌎 Explorar destinos**: el vuelo más barato a cada destino desde tu origen.
- **🔔 Alertas**: guarda vuelos y te avisa cuando bajan de precio (ver abajo).

## Alertas de precio

1. En la pestaña **🔔 Alertas**, elige las fechas y (opcional) un **precio objetivo**, y presiona **🔔 Crear alerta**.
   La app guarda el precio de hoy.
2. Te avisa cuando el precio baja de tu objetivo o, si no pusiste objetivo, cuando aparece un precio al menos
   3 % más bajo que el mínimo visto hasta ahora.
3. En **⏰ Revisión automática diaria** presiona **Activar**: Windows revisará tus alertas una vez al día a la hora
   que elijas, aunque la app esté cerrada (el computador tiene que estar encendido). También puedes revisar
   cuando quieras con **🔄 Revisar todas ahora**.
4. El gráfico muestra cómo ha cambiado el precio de cada alerta día a día.

Cada revisión usa 1 consulta por fuente (2 si es ida y vuelta). Con una alerta de ida y vuelta revisada a
diario gastas unas 60 consultas al mes, dentro de las 100 gratis de SerpApi.

**Importante:** para que la revisión diaria use precios reales, guarda tu clave de SerpApi en
**⚙️ Configurar avisos y claves** (la revisión automática no ve las claves pegadas en la barra lateral).

### Cómo te llegan los avisos
- **Notificación de Windows**: siempre activa, no necesita configuración.
- **Email (Gmail)**: necesitas una *contraseña de aplicación* (no tu contraseña normal):
  1. Activa la verificación en dos pasos en tu cuenta de Google.
  2. Entra a <https://myaccount.google.com/apppasswords>, crea una contraseña llamada "Vuelos" y copia las 16 letras.
  3. En la app, pon tu Gmail y esa contraseña en **⚙️ Configurar avisos y claves** y presiona **💾 Guardar**.
- **Telegram (al celular)**:
  1. En Telegram, busca **@BotFather**, escríbele `/newbot` y sigue los pasos. Te entrega un **token**.
  2. Busca tu bot nuevo y mándale cualquier mensaje (por ejemplo "hola").
  3. Abre en el navegador `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` y copia el número que aparece en
     `"chat":{"id": ...}`. Ese es tu **Chat ID**.
  4. Pega el token y el Chat ID en **⚙️ Configurar avisos y claves** y presiona **💾 Guardar**.

Después presiona **📨 Enviar aviso de prueba** para comprobar que te llegan.

Si prefieres algo sin configurar nada, Google Flights también tiene alertas: busca tu vuelo en
<https://www.google.com/travel/flights> y activa **"Seguir precios"**; te llegan por email.

## Datos de demo

Sin claves, los vuelos se generan con una fórmula que imita los precios reales: distancia, temporada
(diciembre, enero y julio son más caros), día de la semana (martes y miércoles más baratos), anticipación de
compra, escalas y aerolínea (las low cost son más baratas). Las fechas son reales, pero **los vuelos y precios no**.

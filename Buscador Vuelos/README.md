# Buscador de vuelos baratos

Metabuscador de vuelos: junta resultados de varias fuentes, quita los repetidos y te muestra el más barato,
con fechas flexibles y rutas alternativas. Sin claves funciona con **datos de demo** (precios simulados).

- `app.py`: la **app web** (Streamlit).
- `fuentes.py`: las fuentes de datos (demo, Google Flights vía SerpApi, Duffel y Kiwi.com).
- `buscador_vuelos.py`: la lógica de búsqueda (fechas flexibles, rutas alternativas, explorar destinos).
- `Buscador de vuelos baratos.ipynb`: versión notebook (usa datos de demo).
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

## Datos de demo

Sin claves, los vuelos se generan con una fórmula que imita los precios reales: distancia, temporada
(diciembre, enero y julio son más caros), día de la semana (martes y miércoles más baratos), anticipación de
compra, escalas y aerolínea (las low cost son más baratas). Las fechas son reales, pero **los vuelos y precios no**.

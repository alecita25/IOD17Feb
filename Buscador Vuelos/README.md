# Buscador de vuelos baratos (demo)

Busca los vuelos más baratos entre dos ciudades, con fechas flexibles y rutas alternativas.

- `app.py`: **app web** (Streamlit). Ejecuta `pip install -r requirements.txt` y luego `streamlit run app.py`.
- `Buscador de vuelos baratos.ipynb`: la versión notebook; cambia los parámetros y ejecuta todo.
- `buscador_vuelos.py`: la lógica de búsqueda que usan ambos.

## La app web

En la barra lateral eliges origen, destino, fechas de ida y vuelta, cuántos días flexibles (±),
escalas máximas, precio máximo y cuántas horas aceptas esperar en cada conexión. Pestañas:

- **📅 Mejores fechas**: revisa todas las combinaciones de ida y vuelta moviendo cada fecha ± N días,
  muestra las 3 más baratas, cuánto ahorran frente a tus fechas exactas y un mapa de calor de precios.
- **🛫 Todos los vuelos**: calendario de precios por día y la lista completa (descargable en CSV).
- **🔀 Rutas alternativas**: arma rutas con 1 o 2 escalas combinando aerolíneas con pasajes separados
  (low cost incluidas) y muestra cuánto ahorra cada una frente a la ruta más directa. Se puede ordenar por
  precio, escala más corta o duración total.
- **🌎 Explorar destinos**: el vuelo más barato a cada destino desde tu origen.

## El notebook

Qué incluye:
1. Los vuelos más baratos del período (con filtros de escalas, aerolínea, precio y duración).
2. Calendario de precios: el vuelo más barato de cada día, en un gráfico.
3. Qué día de la semana conviene volar y comparación por aerolínea.
4. Mejores combinaciones de ida y vuelta según las noches de estadía.
5. Explorar destinos: a dónde se puede ir más barato desde tu origen.
6. Exportar resultados a CSV.

**Los precios son simulados.** Se calculan con la distancia y factores que sí influyen en los precios reales
(día de la semana, temporada, anticipación de compra, escalas, aerolínea). Para precios reales, reemplaza
`generar_vuelos()` por una llamada a una API (por ejemplo SerpApi Google Flights o Duffel) que devuelva
la misma lista de diccionarios; el resto del notebook sigue funcionando igual.

Requisitos: ver `requirements.txt`.

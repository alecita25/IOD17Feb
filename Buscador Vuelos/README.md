# Buscador de vuelos baratos (demo)

Notebook que busca los vuelos más baratos entre dos ciudades en un rango de fechas.

- `Buscador de vuelos baratos.ipynb`: cambia origen, destino, fechas y filtros en la celda de parámetros y ejecuta todo.
- `buscador_vuelos.py`: la lógica de búsqueda.

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

Requisitos: `pandas`, `matplotlib`, `jupyter`.

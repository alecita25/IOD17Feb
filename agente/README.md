# Mi agente anti-scroll

Un agente que conoce mis pendientes, mis metas y mi horario semanal, y me da
opciones concretas de qué hacer en vez de abrir el celular a hacer scroll.

## Archivos

| Archivo | Qué guarda |
|---|---|
| `perfil.md` | Zona horaria, energía según la hora, qué me engancha al scroll |
| `horario.md` | Mi semana tipo: bloques fijos (trabajo, clases, gym, etc.) |
| `pendientes.md` | Tareas concretas por hacer, con duración y energía estimadas |
| `metas.md` | Cosas que quiero lograr a mediano/largo plazo, desglosadas en pasos |
| `ideas.md` | Cosas que me gustaría hacer por gusto (hobbies, salidas, lecturas) |
| `historial.md` | Qué elegí hacer y cómo me fue (el agente aprende de esto) |

## Cómo se usa (en Claude Code, dentro de este repo)

- `/que-hago` → mira la hora, tu horario y tu energía y te da 3 opciones.
  Puedes agregar contexto: `/que-hago tengo 20 min y estoy cansada`.
- `/anotar ...` → agrega un pendiente, meta, idea o cambio de horario.
  Ej: `/anotar pagar la cuenta de luz antes del viernes`.
- O simplemente escríbele en lenguaje normal: "terminé el lab 8", "esta semana no tengo gym".

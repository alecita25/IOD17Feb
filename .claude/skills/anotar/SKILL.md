---
name: anotar
description: Agrega o actualiza pendientes, metas, ideas, horario o perfil del agente anti-scroll a partir de lo que la usuaria dice en lenguaje normal. Úsala con "/anotar ...", "anota que...", "terminé...", "tengo que...", "quiero lograr...", o cambios de horario.
---

# Anotar

Toma lo que dijo la usuaria ($ARGUMENTS) y guárdalo en el archivo correcto de `agente/`:

- Tarea concreta con fin claro → `pendientes.md` (sección "Por hacer").
- Algo a lograr en semanas/meses → `metas.md`, con su porqué y 2–4 pasos de ≤ 1 hora.
- Algo por gusto / hobby / salida → `ideas.md`.
- Bloque fijo o cambio en la semana → `horario.md`.
- Algo sobre ella (energía, gatillos, zona horaria) → `perfil.md`.
- "Terminé X" → marca `[x]`, mueve a "Hechos" y anótalo con ✅ en `historial.md`.

Respeta el formato de cada archivo. Si falta la duración o energía, estímala tú y
márcala con `~` (ej. `⏱ ~30m`) en vez de preguntar. Si una fecha es relativa
("el viernes"), conviértela a fecha absoluta usando la fecha actual.
Confirma en una sola línea qué guardaste y dónde.

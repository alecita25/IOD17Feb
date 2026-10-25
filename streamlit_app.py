"""
Punto de entrada para Streamlit Community Cloud.

La app está en la carpeta "Buscador Vuelos"; este archivo solo la ejecuta desde ahí.
En Streamlit Cloud, "Main file path" = streamlit_app.py
"""

import os
import runpy
import sys

CARPETA_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Buscador Vuelos")
if CARPETA_APP not in sys.path:
    sys.path.insert(0, CARPETA_APP)

runpy.run_path(os.path.join(CARPETA_APP, "app.py"), run_name="__main__")

"""
registroLlm.py
Registro (log) de cada recomendacion o respuesta emitida por el modelo de
lenguaje, en data/salidas/recomendaciones.csv: fecha, fondo, perfil,
proveedor, accion, tokens, costo estimado y duracion. Sirve para auditar
lo que dijo la IA, contar las llamadas del dia (limite diario) y estimar
el costo por cada 100 recomendaciones.
"""

import csv
from datetime import datetime
from pathlib import Path

from config import RUTA_SALIDAS
from src.utilidades import registrarEvento

ARCHIVO_REGISTRO = "recomendaciones.csv"
COLUMNAS = ["fecha", "tipo", "ticker", "perfil", "proveedor", "modelo", "accion", "accionCoincide", "nivelConfianza",
            "cifrasSospechosas", "problemasFormato", "tokensEntrada", "tokensSalida", "costoUsd", "duracionSeg"]


def rutaRegistro():
    return Path(RUTA_SALIDAS) / ARCHIVO_REGISTRO


def registrarRecomendacion(registro):
    """Agrega una fila al registro (crea el archivo con cabecera si no existe). Nunca interrumpe la app."""
    try:
        ruta = rutaRegistro()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        nuevo = not ruta.exists()
        fila = {c: registro.get(c, "") for c in COLUMNAS}
        fila["fecha"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(ruta, "a", newline="", encoding="utf-8") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)
            if nuevo:
                escritor.writeheader()
            escritor.writerow(fila)
    except OSError as error:
        registrarEvento(f"No se pudo escribir el registro de recomendaciones: {error}", "WARN")


def leerRegistro():
    """Todas las filas del registro (lista de dicts), o [] si no existe."""
    try:
        with open(rutaRegistro(), newline="", encoding="utf-8") as archivo:
            return list(csv.DictReader(archivo))
    except (OSError, ValueError):
        return []


def llamadasHoy():
    """Cuantas llamadas al LLM (informes y chat) se registraron hoy."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    return sum(1 for fila in leerRegistro() if str(fila.get("fecha", "")).startswith(hoy))


def resumenCostos():
    """Promedio de costo y tokens de los informes registrados, y el costo estimado por 100 recomendaciones."""
    filas = [f for f in leerRegistro() if f.get("tipo") == "informe" and f.get("costoUsd") not in ("", None)]
    costos = []
    for f in filas:
        try:
            costos.append(float(f["costoUsd"]))
        except ValueError:
            continue
    if not costos:
        return {"informes": 0, "costoPromedioUsd": None, "costoPor100Usd": None}
    promedio = sum(costos) / len(costos)
    return {"informes": len(costos), "costoPromedioUsd": promedio, "costoPor100Usd": promedio * 100}
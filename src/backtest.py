"""
backtest.py
Prueba historica de la senal de reglas (sin el pronostico ni el sentimiento,
que no tienen historia suficiente): en cada cierre semanal se calcula la
senal SOLO con datos hasta ese dia y se mide el retorno de los 'dias'
habiles siguientes.

Responde: cuando la senal dijo COMPRAR / MANTENER / REDUCIR, que paso
despues, y como se compara con simplemente comprar y mantener.
"""

import numpy as np
import pandas as pd

from src.datosEstructurados import calcularMetricasDescriptivas, clasificarRiesgo
from src.datosNoticias import resumirSentimiento
from src.motorPrescriptivo import generarSenal
from src.utilidades import registrarEvento

VENTANA_METRICAS = 756  # 3 anios de historia para las metricas en cada corte


def backtestSenal(historico, benchmark, dias=21, tasaLibre=0.045, benchmarkComparable=True, maximoSemanas=260):
    """
    Devuelve (tabla, resumen). tabla: una fila por semana con la senal y el
    retorno posterior. resumen: por accion, retorno medio posterior y acierto.
    """
    if historico is None or len(historico) < 300 + dias:
        return pd.DataFrame(), {}

    nav = historico["nav"].dropna()
    fechas = nav.index.to_series()
    cortes = fechas.groupby(fechas.index.to_period("W")).max()
    cortes = [pd.Timestamp(f) for f in cortes.values]
    posicion = {f: i for i, f in enumerate(nav.index)}
    cortes = [f for f in cortes if 260 <= posicion[f] < len(nav) - dias][-maximoSemanas:]

    sinNoticias = resumirSentimiento(pd.DataFrame())
    sinPronostico = {"rentabilidadProyectada": np.nan, "tieneHabilidad": False}
    filas = []
    for fecha in cortes:
        i = posicion[fecha]
        tramo = historico.iloc[max(0, i - VENTANA_METRICAS + 1): i + 1]
        tramoB = benchmark.loc[benchmark.index <= fecha] if benchmark is not None and not benchmark.empty else None
        if tramoB is not None:
            tramoB = tramoB.loc[tramoB.index >= tramo.index[0]]
        metricas = calcularMetricasDescriptivas(tramo, tramoB, tasaLibre, benchmarkComparable)
        senal = generarSenal(metricas, sinPronostico, clasificarRiesgo(metricas), sinNoticias, dias)
        retorno = float(nav.iloc[i + dias] / nav.iloc[i] - 1)
        filas.append({"fecha": fecha, "accion": senal["accion"], "puntaje": senal["puntaje"], "retornoPosterior": retorno})

    tabla = pd.DataFrame(filas)
    if tabla.empty:
        return tabla, {}

    tabla["acierto"] = np.where(
        tabla["accion"] == "COMPRAR", tabla["retornoPosterior"] > 0,
        np.where(tabla["accion"] == "REDUCIR", tabla["retornoPosterior"] < 0, np.nan),
    )
    # Estrategia simple: invertido salvo cuando la senal es REDUCIR (en liquidez).
    # Ventanas solapadas: es un indicador, no una rentabilidad realizable.
    liquidezPeriodo = (1 + tasaLibre) ** (dias / 252) - 1
    tabla["retornoEstrategia"] = np.where(tabla["accion"] == "REDUCIR", liquidezPeriodo, tabla["retornoPosterior"])

    porAccion = tabla.groupby("accion").agg(
        semanas=("accion", "size"), retornoMedio=("retornoPosterior", "mean"),
        proporcionAlza=("retornoPosterior", lambda r: float((r > 0).mean())),
    )
    resumen = {
        "semanas": int(len(tabla)),
        "desde": tabla["fecha"].min(), "hasta": tabla["fecha"].max(), "dias": int(dias),
        "porAccion": porAccion,
        "retornoMedioComprarMantener": float(tabla["retornoPosterior"].mean()),
        "retornoMedioEstrategia": float(tabla["retornoEstrategia"].mean()),
        "proporcionAlzaGeneral": float((tabla["retornoPosterior"] > 0).mean()),
        "vecesReducir": int((tabla["accion"] == "REDUCIR").sum()),
    }
    registrarEvento(f"Backtest de la señal: {len(tabla)} semanas, {resumen['vecesReducir']} con REDUCIR.")
    return tabla, resumen

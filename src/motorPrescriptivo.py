"""
motorPrescriptivo.py
Componente prescriptivo del proyecto.

Tres capas:
  1. Reglas deterministas -> senal del fondo (COMPRAR / MANTENER / REDUCIR).
  2. Asignacion por perfil -> renta variable, renta fija SEGMENTADA en los
     bonos del perfil (segun el ranking) y liquidez, con un ajuste tactico
     acotado por la senal.
  3. IA generativa -> explicacion en lenguaje natural. Qwen3 (Ollama, local)
     primero; Gemini como respaldo; texto por reglas si no hay ninguno. El LLM
     no decide: explica factores ya calculados, y sus cifras se verifican
     contra los datos que recibio.
"""

import json
import re
import time
from datetime import date, datetime

import numpy as np
import pandas as pd
import requests

from config import (
    GEMINI_API_KEY,
    GEMINI_MODELO,
    GEMINI_TEMPERATURA,
    GEMINI_TIMEOUT,
    GEMINI_URL,
    OLLAMA_HOST,
    OLLAMA_MODELO,
    OLLAMA_PUERTO,
    OLLAMA_TEMPERATURA,
    OLLAMA_TIMEOUT,
    PROVEEDOR_LLM_FORZADO,
    PROVEEDOR_LLM_TTL,
)
from src.catalogoBonos import PARAMETROS_PERFIL, PERFILES
from src.utilidades import esNulo, formatearPorcentaje, numeroSeguro, registrarEvento

URL_OLLAMA = f"{OLLAMA_HOST}:{OLLAMA_PUERTO}"
URL_GEMINI = f"{GEMINI_URL}/{GEMINI_MODELO}:generateContent"
NOMBRES_PROVEEDOR = {"qwen3": f"Qwen3 local ({OLLAMA_MODELO})", "gemini": f"Gemini ({GEMINI_MODELO})"}

DIAS_HABILES_ANIO = 252
NIVELES_HORIZONTE = ("1-3 años", "3-5 años", "5+ años")
AJUSTE_HORIZONTE_POR_PERFIL = {"Conservador": 1, "Moderado": 0, "Agresivo": -1}
# Ajuste tactico por la senal sobre la clase del fondo analizado (acotado: la senal de UN
# fondo no debe mover toda la cartera)
AJUSTE_TACTICO = {"COMPRAR": 0.05, "MANTENER": 0.0, "REDUCIR": -0.05}
UMBRAL_COMPRAR = 3.0
UMBRAL_REDUCIR = -3.0


# ---------------------------------------------------------------------------
# 1. Senal del fondo
# ---------------------------------------------------------------------------
def calcularHorizonteOptimo(volatilidadAnual, perfil="Moderado"):
    """Horizonte de permanencia sugerido segun la volatilidad del fondo y el perfil."""
    volatilidad = 0.15 if esNulo(volatilidadAnual) else float(volatilidadAnual)
    indice = 2 if volatilidad > 0.25 else (1 if volatilidad > 0.12 else 0)
    indice += AJUSTE_HORIZONTE_POR_PERFIL.get(perfil, 0)
    return NIVELES_HORIZONTE[int(np.clip(indice, 0, len(NIVELES_HORIZONTE) - 1))]


def umbralRentabilidad(volatilidadAnual, dias):
    """Retorno minimo (en valor absoluto) para que el pronostico cuente: 0.25 desviaciones del horizonte."""
    volatilidad = 0.15 if esNulo(volatilidadAnual) else float(volatilidadAnual)
    return max(0.005, 0.25 * volatilidad * np.sqrt(max(dias, 1) / DIAS_HABILES_ANIO))


REGLAS_SENAL = [
    ("Pronóstico del modelo", "±2 si el retorno proyectado supera ±0.25 desviaciones del horizonte; solo si el modelo superó a las líneas base"),
    ("Tendencia", "+2 si está sobre su media de 200 días y sube en 6 meses; −2 si está bajo la media y cae; si no, 0"),
    ("Sharpe 12 meses", "+1.5 si > 1.0; −1.5 si < 0; si no, 0"),
    ("Desempeño vs benchmark 12 meses", "±1 si la diferencia supera ±2 pp; solo con benchmark de retorno total"),
    ("Nivel de riesgo", "Alto −2 · Bajo +1 · Moderado 0 (volatilidad, caída máxima y beta)"),
    ("Sentimiento de noticias", "Tono de prensa (GDELT): ±1 si el promedio de 30 días se aleja más de 1 desviación de su último año "
     "(con ≥ 120 días de historia). Sin esa historia, titulares: ±1 si su promedio de 30 días supera ±0.15 (con ≥ 10 titulares)"),
]


def generarSenal(metricas, resumenPronostico, riesgo, sentimiento, dias=30):
    """
    Traduce indicadores en una senal. Cada factor se registra con su valor,
    su regla y los puntos que aporto (o el motivo por el que no participo).
    Rango real del puntaje: -9.5 a +8.5. >= 3 COMPRAR, <= -3 REDUCIR.
    """
    factores, motivos, alertas = [], [], []

    def registrar(nombre, valorTexto, puntos, activo, nota=""):
        factores.append({"factor": nombre, "valor": valorTexto, "puntos": float(puntos), "activo": bool(activo),
                         "regla": dict(REGLAS_SENAL)[nombre], "nota": nota})

    # 1. Pronostico (solo si tiene habilidad comprobada)
    proyectada = resumenPronostico.get("rentabilidadProyectada")
    umbral = umbralRentabilidad(metricas.get("volatilidadAnual"), dias)
    if esNulo(proyectada):
        registrar("Pronóstico del modelo", "Sin dato", 0, False, "Sin pronóstico.")
    elif not resumenPronostico.get("tieneHabilidad"):
        registrar("Pronóstico del modelo", formatearPorcentaje(proyectada, 1, True), 0, False,
                  "No participa: ningún modelo superó a las líneas base.")
    else:
        puntos = 2 if proyectada > umbral else (-2 if proyectada < -umbral else 0)
        registrar("Pronóstico del modelo", f"{formatearPorcentaje(proyectada, 1, True)} (umbral ±{umbral:.1%})", puntos, True)
        if puntos > 0:
            motivos.append(f"El modelo, que supera a las líneas base, proyecta {formatearPorcentaje(proyectada, 1, True)} en {dias} días.")
        elif puntos < 0:
            alertas.append(f"El modelo proyecta {formatearPorcentaje(proyectada, 1, True)} en {dias} días.")

    # 2. Tendencia
    sobre, ret6 = metricas.get("sobreMedia200"), metricas.get("retorno6m")
    if sobre is None or esNulo(ret6):
        registrar("Tendencia", "Sin dato", 0, False, "Se necesitan 200 días de historia.")
    else:
        texto = f"{'sobre' if sobre else 'bajo'} media 200d · 6m {ret6:+.1%}"
        puntos = 2 if (sobre and ret6 > 0) else (-2 if (not sobre and ret6 < 0) else 0)
        registrar("Tendencia", texto, puntos, True)
        if puntos > 0:
            motivos.append(f"Tendencia alcista: sobre su media de 200 días y {ret6:+.1%} en 6 meses.")
        elif puntos < 0:
            alertas.append(f"Tendencia bajista: bajo su media de 200 días y {ret6:+.1%} en 6 meses.")

    # 3. Sharpe 12 meses
    sharpe = metricas.get("sharpe12m")
    if esNulo(sharpe):
        registrar("Sharpe 12 meses", "Sin dato", 0, False, "Se necesitan ~6 meses de historia.")
    else:
        puntos = 1.5 if sharpe > 1.0 else (-1.5 if sharpe < 0 else 0)
        registrar("Sharpe 12 meses", f"{sharpe:.2f}", puntos, True)
        if puntos > 0:
            motivos.append(f"Sharpe de 12 meses de {sharpe:.2f}: buena compensación por el riesgo.")
        elif puntos < 0:
            alertas.append(f"Sharpe de 12 meses de {sharpe:.2f}: rindió menos que la liquidez.")

    # 4. Benchmark (solo comparable)
    diferencial = metricas.get("diferencialBenchmark12m")
    if not metricas.get("benchmarkComparable", True):
        registrar("Desempeño vs benchmark 12 meses", formatearPorcentaje(diferencial, 1, True), 0, False,
                  "No participa: el benchmark no incluye dividendos.")
    elif esNulo(diferencial):
        registrar("Desempeño vs benchmark 12 meses", "Sin dato", 0, False, "Sin benchmark o sin 12 meses comunes.")
    else:
        puntos = 1 if diferencial > 0.02 else (-1 if diferencial < -0.02 else 0)
        registrar("Desempeño vs benchmark 12 meses", formatearPorcentaje(diferencial, 1, True), puntos, True)
        if puntos > 0:
            motivos.append(f"Supera a su benchmark en {diferencial:+.1%} en 12 meses.")
        elif puntos < 0:
            alertas.append(f"Queda {abs(diferencial):.1%} por debajo de su benchmark en 12 meses.")

    # 5. Riesgo
    categoria = riesgo.get("categoria")
    puntos = -2 if categoria == "Alto" else (1 if categoria == "Bajo" else 0)
    registrar("Nivel de riesgo", f"{categoria} ({riesgo.get('puntaje')}/10)", puntos, categoria is not None)
    if puntos < 0:
        alertas.append(f"El riesgo del fondo es Alto ({riesgo.get('puntaje')}/10).")
    elif puntos > 0:
        motivos.append(f"El riesgo del fondo es Bajo ({riesgo.get('puntaje')}/10).")

    # 6. Sentimiento: tono de prensa frente a su propia historia, o titulares recientes
    fuente = sentimiento.get("fuenteSenal")
    if fuente == "tono":
        z, tono = sentimiento.get("zTono"), sentimiento.get("tonoReciente")
        puntos = 1 if z >= 1 else (-1 if z <= -1 else 0)
        registrar("Sentimiento de noticias", f"tono 30 días {tono:+.2f} ({z:+.1f} desv. vs su año)", puntos, True)
        if puntos > 0:
            motivos.append(f"El tono de la prensa está más positivo que de costumbre ({z:+.1f} desviaciones).")
        elif puntos < 0:
            alertas.append(f"El tono de la prensa está más negativo que de costumbre ({z:+.1f} desviaciones).")
    elif fuente == "titulares":
        promedio = sentimiento.get("promedioReciente", 0.0)
        puntos = 1 if promedio >= 0.15 else (-1 if promedio <= -0.15 else 0)
        registrar("Sentimiento de noticias", f"titulares {promedio:+.2f} ({sentimiento.get('recientes')} en 30 días)", puntos, True)
        if puntos > 0:
            motivos.append(f"Titulares recientes positivos ({promedio:+.2f}).")
        elif puntos < 0:
            alertas.append(f"Titulares recientes negativos ({promedio:+.2f}).")
    else:
        registrar("Sentimiento de noticias", f"{sentimiento.get('diasTono', 0)} días de tono · {sentimiento.get('recientes', 0)} titulares", 0, False,
                  "No participa: falta historia de tono (≥ 120 días) y hay menos de 10 titulares recientes.")

    puntaje = round(float(sum(f["puntos"] for f in factores)), 1)
    accion = "COMPRAR" if puntaje >= UMBRAL_COMPRAR else ("REDUCIR" if puntaje <= UMBRAL_REDUCIR else "MANTENER")
    activos = [f for f in factores if f["activo"]]
    signos = [np.sign(f["puntos"]) for f in activos if f["puntos"]]
    concordancia = abs(sum(signos)) / len(activos) if activos else 0.0
    confianza = "Alta" if concordancia >= 0.5 else ("Media" if concordancia >= 0.25 else "Baja")

    return {
        "accion": accion, "puntaje": puntaje, "confianza": confianza, "concordancia": concordancia,
        "factoresActivos": len(activos), "motivos": motivos, "alertas": alertas, "factores": factores,
        "horizonte": calcularHorizonteOptimo(metricas.get("volatilidadAnual"), "Moderado"),
    }


def calcularRetornoEsperado(metricas, resumenPronostico, dias):
    """
    Retorno anual esperado del fondo. Si el modelo tiene habilidad, combina
    70% historico + 30% pronostico anualizado con el HORIZONTE REAL; si no,
    solo el historico.
    """
    historico = metricas.get("retornoAnual")
    if esNulo(historico):
        return np.nan
    proyectado = resumenPronostico.get("rentabilidadProyectada")
    if esNulo(proyectado) or not resumenPronostico.get("tieneHabilidad"):
        return float(historico)
    proyectadoAnual = (1 + proyectado) ** (DIAS_HABILES_ANIO / max(dias, 1)) - 1
    return float(0.7 * historico + 0.3 * np.clip(proyectadoAnual, -0.5, 0.5))


# ---------------------------------------------------------------------------
# 2. Asignacion por perfil con bonos segmentados
# ---------------------------------------------------------------------------
def esFondoDeRentaVariable(ticker, ficha=None):
    """True si el fondo analizado parece de acciones (no esta en el catalogo de bonos ni se declara de bonos)."""
    from src.catalogoBonos import todosLosTickersBonos

    categoria = str((ficha or {}).get("categoria", "")).lower()
    return ticker not in todosLosTickersBonos() and not any(p in categoria for p in ("bond", "fixed", "income", "bono"))


def claseDelFondo(ticker, ficha=None):
    """'Renta fija' si el fondo analizado es de bonos (catalogo o ficha); si no, 'Renta variable'."""
    return "Renta variable" if esFondoDeRentaVariable(ticker, ficha) else "Renta fija"


def construirAsignacion(perfil, senal, tablaRanking=None, seleccion=None, fondoElegido=None,
                        fondoAnalizado=None, maximoFondos=2, claseSenal="Renta variable", soloLiquidez=False):
    """
    Asignacion de cartera para el perfil. Devuelve {'filas', 'nota', 'ajusteTactico'};
    cada fila {clase, detalle, ticker, cusip, veredicto, peso} y los pesos suman 1.

    - Ajuste tactico de +-5 pp segun la senal, sobre la clase del fondo
      analizado (claseSenal):
        * fondo de acciones -> COMPRAR suma 5 pp a renta variable (desde la
          renta fija); REDUCIR los pasa de renta variable a liquidez.
        * fondo de bonos    -> COMPRAR suma 5 pp a renta fija (desde la renta
          variable); REDUCIR los pasa de renta fija a liquidez.
      Si el fondo analizado es de acciones, la parte de EE.UU. ES ese fondo.
    - Renta fija, en este orden de prioridad:
        1. los BONOS ESPECIFICOS que eligio el usuario (partes iguales);
        2. el FONDO de bonos que eligio;
        3. los mejores fondos del ranking, uno por segmento (hasta 2).
      Si nada califica, o si el usuario lo pide (soloLiquidez), la renta
      fija queda en liquidez.
    """
    base = PARAMETROS_PERFIL.get(perfil, PARAMETROS_PERFIL["Moderado"])
    ajuste = AJUSTE_TACTICO.get(senal.get("accion"), 0.0)
    if claseSenal == "Renta fija":
        rentaFija = float(np.clip(base["rentaFija"] + ajuste, 0.0, 0.95))
        rentaVariable = base["rentaVariable"] - (ajuste if ajuste > 0 else 0.0)
    else:
        rentaVariable = float(np.clip(base["rentaVariable"] + ajuste, 0.05, 0.95))
        rentaFija = base["rentaFija"] - (ajuste if ajuste > 0 else 0.0)
    liquidez = 1 - rentaVariable - rentaFija

    nombreRvUs = (f"Renta variable EE.UU. — {fondoAnalizado} (fondo analizado)" if fondoAnalizado
                  else "Renta variable EE.UU. (fondo indexado amplio)")
    filas = [
        {"clase": "Renta variable", "detalle": nombreRvUs, "ticker": fondoAnalizado or "", "cusip": "", "veredicto": "", "peso": rentaVariable * 0.70},
        {"clase": "Renta variable", "detalle": "Renta variable internacional (diversificación)", "ticker": "", "cusip": "", "veredicto": "", "peso": rentaVariable * 0.30},
    ]

    if soloLiquidez:
        liquidez += rentaFija
        nota = "Elegiste no invertir en bonos por ahora: la renta fija se mantiene en liquidez."
    elif seleccion is not None and not seleccion.empty:
        from src.bonosIndividuales import describirBono

        for _, bono in seleccion.iterrows():
            filas.append({"clase": "Renta fija", "detalle": describirBono(bono), "ticker": bono.get("fondo", fondoElegido or ""),
                          "cusip": bono.get("cusip", ""), "veredicto": bono["veredicto"], "peso": rentaFija / len(seleccion)})
        nota = f"Renta fija repartida en partes iguales entre los {len(seleccion)} bono(s) que elegiste."
    elif fondoElegido and tablaRanking is not None and fondoElegido in set(tablaRanking["ticker"]):
        fila = tablaRanking.set_index("ticker").loc[fondoElegido]
        filas.append({"clase": "Renta fija", "detalle": f"Fondo de bonos: {fila['segmento']}", "ticker": fondoElegido,
                      "cusip": "", "veredicto": fila["veredicto"], "peso": rentaFija})
        nota = f"Renta fija en el fondo {fondoElegido} completo (aún no elegiste bonos específicos)."
    else:
        elegibles = pd.DataFrame()
        if tablaRanking is not None and not tablaRanking.empty:
            elegibles = (tablaRanking.loc[tablaRanking["veredicto"].isin(["Recomendable", "Aceptable"])]
                         .drop_duplicates("segmento").head(maximoFondos))
        if elegibles.empty:
            liquidez += rentaFija
            nota = "Ningún fondo de bonos del perfil califica hoy: la renta fija se mantiene en liquidez."
        else:
            for _, fondo in elegibles.iterrows():
                filas.append({"clase": "Renta fija", "detalle": f"Fondo de bonos: {fondo['segmento']}", "ticker": fondo["ticker"],
                              "cusip": "", "veredicto": fondo["veredicto"], "peso": rentaFija / len(elegibles)})
            nota = f"Renta fija repartida entre {len(elegibles)} fondo(s) de segmentos distintos según el ranking."
    filas.append({"clase": "Liquidez", "detalle": "Letras del Tesoro / mercado monetario", "ticker": "", "cusip": "", "veredicto": "", "peso": liquidez})

    for fila in filas:
        fila["peso"] = round(float(fila["peso"]), 4)
    filas[0]["peso"] = round(filas[0]["peso"] + 1 - sum(f["peso"] for f in filas), 4)
    return {"filas": [f for f in filas if f["peso"] > 0], "nota": nota, "ajusteTactico": ajuste, "claseAjuste": claseSenal,
            "rentaFijaObjetivo": round(float(rentaFija), 4)}


def evaluarAlertaPerfil(riesgo, senal, perfil, riesgoFuturoMl=None):
    """
    Avisa cuando el perfil no calza con el riesgo del fondo, sin cambiar la
    senal. riesgoFuturoMl = resultado del clasificador (si supera a la
    persistencia, su prediccion tambien cuenta). Devuelve (tono, mensaje) o None.
    """
    categoria = riesgo.get("categoria")
    accion = senal.get("accion")
    futuroAlto = bool(
        riesgoFuturoMl and riesgoFuturoMl.get("superaPersistencia")
        and riesgoFuturoMl.get("probabilidades", {}).get("Alto", 0) >= 0.5
    )
    if perfil == "Conservador" and (categoria == "Alto" or futuroAlto):
        motivo = "riesgo **Alto**" if categoria == "Alto" else "probabilidad ≥ 50% de riesgo **Alto** en los próximos 3 meses (clasificador)"
        return ("ambar", f"Este fondo tiene {motivo}, por encima de lo habitual para un perfil **Conservador**. "
                         f"Si sigues la señal **{accion}**, usa una posición pequeña o entra de forma escalonada.")
    if perfil == "Conservador" and accion == "COMPRAR" and categoria == "Moderado":
        return ("azul", "La señal es **COMPRAR**, pero con un perfil **Conservador** conviene entrar de forma escalonada.")
    if perfil == "Agresivo" and accion == "REDUCIR" and categoria == "Bajo":
        return ("azul", "La señal es **REDUCIR** aunque el riesgo es **Bajo**: con un perfil **Agresivo** puedes "
                        "reducir de forma parcial si tu horizonte es largo.")
    return None


def compararPerfiles(senal, metricas, riesgo, perfilActual, rankingsPorPerfil, claseSenal="Renta variable"):
    """Horizonte, asignacion y fondos de bonos sugeridos para los tres perfiles, lado a lado."""
    filas = []
    for perfil in PERFILES:
        tabla, resumen = rankingsPorPerfil.get(perfil, (pd.DataFrame(), {}))
        asignacion = construirAsignacion(perfil, senal, tabla, claseSenal=claseSenal)
        pesos = pd.DataFrame(asignacion["filas"]).groupby("clase")["peso"].sum()
        bonos = [f["ticker"] for f in asignacion["filas"] if f["clase"] == "Renta fija"]
        alerta = evaluarAlertaPerfil(riesgo, senal, perfil)
        filas.append(
            {
                "Perfil": perfil, "Seleccionado": "● Actual" if perfil == perfilActual else "",
                "Horizonte": calcularHorizonteOptimo(metricas.get("volatilidadAnual"), perfil),
                "Renta variable": f"{pesos.get('Renta variable', 0):.0%}",
                "Renta fija": f"{pesos.get('Renta fija', 0):.0%}",
                "Liquidez": f"{pesos.get('Liquidez', 0):.0%}",
                "Fondos de bonos sugeridos": ", ".join(bonos) if bonos else "Ninguno (liquidez)",
                "Alerta": re.sub(r"\*\*", "", alerta[1]) if alerta else "—",
            }
        )
    return pd.DataFrame(filas)


def validarRetrospectivamente(senal, resumenPronostico, historicoCompleto, fechaCorte, dias,
                              benchmarkCompleto=None, volatilidadAnual=None):
    """
    En una semana pasada, compara la senal y el pronostico con lo que ocurrio
    despues. Criterio (heuristico): COMPRAR acierta si el retorno real fue
    positivo; REDUCIR si fue negativo; MANTENER si quedo dentro de +-0.5
    desviaciones esperadas del horizonte.
    """
    if fechaCorte is None or historicoCompleto is None or historicoCompleto.empty:
        return None
    finDelDia = pd.Timestamp(fechaCorte).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    hastaCorte = historicoCompleto.loc[historicoCompleto.index <= finDelDia, "nav"]
    posterior = historicoCompleto.loc[historicoCompleto.index > finDelDia, "nav"]
    if hastaCorte.empty or posterior.empty:
        return None

    diasEvaluados = int(min(dias, len(posterior)))
    navCorte = float(hastaCorte.iloc[-1])
    navFinal = float(posterior.iloc[diasEvaluados - 1])
    fechaFinal = posterior.index[diasEvaluados - 1]
    retornoReal = navFinal / navCorte - 1
    completo = len(posterior) >= dias

    retornoBenchmark = np.nan
    if benchmarkCompleto is not None and not benchmarkCompleto.empty:
        navB = benchmarkCompleto["nav"]
        antesB, hastaB = navB.loc[navB.index <= finDelDia], navB.loc[navB.index <= fechaFinal]
        if not antesB.empty and not hastaB.empty:
            retornoBenchmark = float(hastaB.iloc[-1] / antesB.iloc[-1] - 1)

    inferior, superior = resumenPronostico.get("bandaInferior"), resumenPronostico.get("bandaSuperior")
    dentroDeBanda = bool(inferior <= navFinal <= superior) if completo and not esNulo(inferior) and not esNulo(superior) else None

    accion = senal.get("accion")
    margen = 0.5 * (0.15 if esNulo(volatilidadAnual) else volatilidadAnual) * np.sqrt(dias / DIAS_HABILES_ANIO)
    acierto = retornoReal > 0 if accion == "COMPRAR" else (retornoReal < 0 if accion == "REDUCIR" else abs(retornoReal) <= margen)
    return {
        "accion": accion, "fechaCorte": pd.Timestamp(fechaCorte).normalize(), "fechaFinal": fechaFinal,
        "diasEvaluados": diasEvaluados, "diasSolicitados": int(dias), "completo": completo,
        "retornoReal": float(retornoReal), "retornoProyectado": resumenPronostico.get("rentabilidadProyectada", np.nan),
        "retornoBenchmark": retornoBenchmark, "dentroDeBanda": dentroDeBanda, "acierto": bool(acierto),
        "margenMantener": float(margen),
    }


def construirPlanAccion(senal, ticker, riesgo, perfil, resumenBonos, asignacion, planCompra=None,
                        capital=None, coherencia=None, fondoElegido=None):
    """Plan de accion; el primer paso depende de si el fondo analizado es de bonos o de acciones."""
    if asignacion.get("claseAjuste") == "Renta fija":
        return _planFondoDeBonos(senal, ticker, riesgo, resumenBonos, asignacion, planCompra, capital, coherencia, fondoElegido)
    return _planFondoDeAcciones(senal, ticker, riesgo, resumenBonos, asignacion, planCompra, capital, coherencia, fondoElegido)


def _pasosRentaFija(plan, asignacion, planCompra, coherencia, fondoElegido, resumenBonos):
    """Pasos comunes de la renta fija: bonos especificos, fondo completo o liquidez."""
    if coherencia and coherencia.get("estado") == "riesgo":
        plan.append({"accion": "Antes de comprar: reemplazar los bonos marcados como no recomendables para tu perfil", "plazo": "Antes de invertir"})
    if planCompra is not None and not planCompra.empty:
        for _, bono in planCompra.iterrows():
            if bono["lotes"] <= 0:
                plan.append({"accion": f"{bono['bono']}: el monto asignado no alcanza un lote de ${bono['lote']:,.0f} nominal", "plazo": "—"})
                continue
            plan.append({"accion": f"Comprar ${bono['nominalComprado']:,.0f} nominal de {bono['bono']} (CUSIP {bono['cusip']}) "
                                   f"a ~{bono['precio']:.2f}: costo ≈ ${bono['costo']:,.0f}", "plazo": "1 mes"})
        plan.append({"accion": "Conservar cada bono hasta su vencimiento y reinvertir los cupones; revisar el ranking cada trimestre", "plazo": "Trimestral"})
    elif fondoElegido:
        pesoRf = sum(f["peso"] for f in asignacion["filas"] if f["clase"] == "Renta fija")
        plan.append({"accion": f"Invertir {pesoRf:.0%} de la cartera en el fondo {fondoElegido}", "plazo": "1 mes"})
    elif resumenBonos.get("invertir") is False:
        plan.append({"accion": "No comprar bonos de este perfil por ahora; mantener esa porción en liquidez y revisar cada mes", "plazo": "Mensual"})


def _cerrarPlan(plan, ticker, riesgo):
    if riesgo.get("categoria") == "Alto":
        plan.append({"accion": f"Definir de antemano una pérdida máxima aceptable para {ticker}", "plazo": "1 semana"})
    plan.append({"accion": "Volver a ejecutar el análisis con datos nuevos", "plazo": "1 mes"})
    for indice, paso in enumerate(plan, start=1):
        paso["prioridad"] = indice
    return plan


def _planFondoDeBonos(senal, ticker, riesgo, resumenBonos, asignacion, planCompra, capital, coherencia, fondoElegido):
    """Fondo analizado de bonos: la senal decide el ritmo de entrada a la renta fija."""
    accion = senal["accion"]
    pesoRf = sum(f["peso"] for f in asignacion["filas"] if f["clase"] == "Renta fija")
    montoRf = f" (≈ ${capital * pesoRf:,.0f})" if capital else ""
    plan = [{
        "COMPRAR": {"accion": f"Señal COMPRAR en {ticker}: entrar ahora a la renta fija (+5 pp sobre la base del perfil)", "plazo": "1 mes"},
        "REDUCIR": {"accion": f"Señal REDUCIR en {ticker}: comprar en 3 partes y dejar 5 pp en liquidez hasta que mejore", "plazo": "2-3 meses"},
    }.get(accion, {"accion": f"Señal MANTENER en {ticker}: invertir según la base del perfil, sin sobreponderar", "plazo": "1 mes"})]
    plan.append({"accion": f"Llevar la renta fija a {pesoRf:.0%} de la cartera{montoRf}", "plazo": "1 mes"})
    _pasosRentaFija(plan, asignacion, planCompra, coherencia, fondoElegido, resumenBonos)
    return _cerrarPlan(plan, ticker, riesgo)


def _planFondoDeAcciones(senal, ticker, riesgo, resumenBonos, asignacion, planCompra=None,
                         capital=None, coherencia=None, fondoElegido=None):
    """
    Plan de accion priorizado, construido SOLO con lo que el analisis calculo
    y con lo que el usuario eligio (fondo y bonos especificos).
    """
    plan = []
    accion = senal["accion"]
    pesoRv = sum(f["peso"] for f in asignacion["filas"] if f["clase"] == "Renta variable")
    montoRv = f" (≈ ${capital * pesoRv:,.0f})" if capital else ""
    if accion == "COMPRAR":
        plan.append({"accion": f"Aumentar la posición en {ticker} en 3 aportes mensuales", "plazo": "1-3 meses"})
    elif accion == "REDUCIR":
        plan.append({"accion": f"Reducir gradualmente {ticker} y pasar el excedente a liquidez", "plazo": "2-4 semanas"})
    else:
        plan.append({"accion": f"Mantener {ticker}; reequilibrar si se desvía más de 5 pp del objetivo", "plazo": "Revisión mensual"})
    plan.append({"accion": f"Llevar la renta variable a {pesoRv:.0%} de la cartera{montoRv}", "plazo": "1 mes"})
    _pasosRentaFija(plan, asignacion, planCompra, coherencia, fondoElegido, resumenBonos)
    return _cerrarPlan(plan, ticker, riesgo)


# ---------------------------------------------------------------------------
# 3. IA generativa
# ---------------------------------------------------------------------------
def verificarOllama():
    """Comprueba si Ollama esta activo y si el modelo EXACTO configurado esta descargado."""
    estado = {"disponible": False, "modeloListo": False, "mensaje": "", "modelos": []}
    try:
        respuesta = requests.get(f"{URL_OLLAMA}/api/tags", timeout=3)
        respuesta.raise_for_status()
        modelos = [m.get("name", "") for m in respuesta.json().get("models", [])]
        buscado = OLLAMA_MODELO if ":" in OLLAMA_MODELO else f"{OLLAMA_MODELO}:latest"
        estado.update(disponible=True, modelos=modelos, modeloListo=buscado in modelos)
        estado["mensaje"] = (
            f"Ollama activo con el modelo {OLLAMA_MODELO}." if estado["modeloListo"]
            else f"Ollama está activo pero falta el modelo {OLLAMA_MODELO}. Ejecuta: ollama pull {OLLAMA_MODELO}"
        )
    except requests.exceptions.ConnectionError:
        estado["mensaje"] = f"No se pudo conectar con Ollama en {URL_OLLAMA}. Ejecuta 'ollama serve'."
    except requests.exceptions.RequestException as error:
        estado["mensaje"] = f"Error al verificar Ollama: {error}"
    return estado


def verificarGemini():
    """Comprueba la clave de Gemini consultando solo la metadata del modelo."""
    estado = {"disponible": False, "modeloListo": False, "mensaje": "", "modelos": []}
    if not GEMINI_API_KEY:
        estado["mensaje"] = "GEMINI_API_KEY no está configurada en el .env."
        return estado
    try:
        respuesta = requests.get(f"{GEMINI_URL}/{GEMINI_MODELO}", headers={"x-goog-api-key": GEMINI_API_KEY}, timeout=8)
        respuesta.raise_for_status()
        estado.update(disponible=True, modeloListo=True, mensaje=f"Gemini activo con el modelo {GEMINI_MODELO}.")
    except requests.exceptions.HTTPError as error:
        codigo = error.response.status_code if error.response is not None else None
        if codigo == 429:
            estado.update(disponible=True, modeloListo=True, mensaje="Gemini activo, pero cerca del límite de la cuota gratuita.")
        elif codigo in (401, 403):
            estado["mensaje"] = "GEMINI_API_KEY inválida o sin permisos."
        elif codigo == 404:
            estado["mensaje"] = f"El modelo {GEMINI_MODELO} no existe o no está disponible para esta clave."
        else:
            estado["mensaje"] = f"Error al verificar Gemini ({codigo})."
    except requests.exceptions.RequestException as error:
        estado["mensaje"] = f"Error al verificar Gemini: {error}"
    return estado


_CACHE_PROVEEDOR = {"momento": 0.0, "valor": None}


def determinarProveedorActivo(forzarVerificacion=False):
    """
    Decide que proveedor usar: el forzado en el .env, o Qwen3 si esta listo y
    Gemini si no. El resultado se reutiliza PROVEEDOR_LLM_TTL segundos para no
    consultar a los servicios en cada interaccion.
    Devuelve (proveedor, estado, forzado).
    """
    ahora = time.monotonic()
    if not forzarVerificacion and _CACHE_PROVEEDOR["valor"] and ahora - _CACHE_PROVEEDOR["momento"] < PROVEEDOR_LLM_TTL:
        return _CACHE_PROVEEDOR["valor"]

    if PROVEEDOR_LLM_FORZADO in ("qwen3", "gemini"):
        estado = verificarOllama() if PROVEEDOR_LLM_FORZADO == "qwen3" else verificarGemini()
        valor = (PROVEEDOR_LLM_FORZADO, estado, True)
    else:
        estadoOllama = verificarOllama()
        if estadoOllama["disponible"] and estadoOllama["modeloListo"]:
            valor = ("qwen3", estadoOllama, False)
        else:
            estadoGemini = verificarGemini()
            valor = ("gemini", estadoGemini, False) if estadoGemini["disponible"] else ("qwen3", estadoOllama, False)
    _CACHE_PROVEEDOR.update(momento=ahora, valor=valor)
    return valor


def proveedorListo(estado):
    """True si el proveedor puede generar texto."""
    return bool(estado.get("disponible") and estado.get("modeloListo", True))


def nombreProveedor(clave):
    """Nombre legible del proveedor."""
    return NOMBRES_PROVEEDOR.get(clave, clave)


def limpiarRazonamiento(texto):
    """Quita los bloques <think>...</think> que Qwen3 agrega en modo razonamiento."""
    return re.sub(r"<think>.*?</think>", "", texto or "", flags=re.DOTALL).strip()


def _pct(valor, decimales=2):
    """Fraccion -> porcentaje numerico (0.1351 -> 13.51) apto para JSON."""
    return None if esNulo(valor) else numeroSeguro(float(valor) * 100, decimales)


def construirContexto(datos, perfil, decision=None):
    """
    Contexto numerico para el LLM. Los porcentajes van como NUMEROS en
    puntos porcentuales (campos ...Pct), para poder verificar despues cada
    cifra que el modelo escriba. 'decision' = lo que el usuario eligio en el
    Prescriptivo (fondo, bonos especificos, proyeccion), para que la IA hable
    de ESA seleccion y no de otra.
    """
    metricas, resumen, senal = datos["metricas"], datos["resumenPronostico"], datos["senal"]
    sentimiento = datos["sentimiento"]
    tablaBonos, resumenBonos = datos.get("rankingsPorPerfil", {}).get(perfil, (pd.DataFrame(), {}))
    decision = decision or {}
    asignacion = decision.get("asignacion") or construirAsignacion(perfil, senal, tablaBonos,
                                                                   claseSenal=datos.get("claseFondo", "Renta variable"))
    titulares = datos["titulares"].head(5).to_dict("records") if not datos["titulares"].empty else []
    for titular in titulares:
        if isinstance(titular.get("fecha"), (pd.Timestamp, datetime, date)):
            titular["fecha"] = titular["fecha"].strftime("%Y-%m-%d")
        titular["sentimiento"] = numeroSeguro(titular.get("sentimiento"), 3)

    bonos = []
    if not tablaBonos.empty:
        for _, fila in tablaBonos.head(5).iterrows():
            bonos.append({
                "puesto": int(fila["puesto"]), "ticker": fila["ticker"], "segmento": fila["segmento"],
                "veredicto": fila["veredicto"], "puntaje": numeroSeguro(fila["puntaje"], 1),
                "rendimientoEsperadoPct": _pct(fila["rendimientoEsperado"]), "volatilidadPct": _pct(fila["volatilidad"]),
                "caidaMaximaPct": _pct(fila["caidaMaxima"]),
            })

    return {
        "fondo": {"ticker": datos["ticker"], "nombre": datos["ficha"].get("nombre"),
                  "clase": datos.get("claseFondo"), "grupoDePerfil": datos.get("perfilFondo"),
                  "segmento": (datos.get("fichaCatalogo") or {}).get("segmento"),
                  "noticiasDeOtroTicker": datos.get("tickerNoticias") if datos.get("tickerNoticias") != datos["ticker"] else None},
        "perfilInversor": perfil,
        "indicadores": {
            "valorActual": numeroSeguro(metricas.get("valorActual"), 2),
            "retornoAnualPct": _pct(metricas.get("retornoAnual")), "volatilidadAnualPct": _pct(metricas.get("volatilidadAnual")),
            "sharpe12m": numeroSeguro(metricas.get("sharpe12m"), 2), "beta": numeroSeguro(metricas.get("beta"), 2),
            "varDiario95Pct": _pct(metricas.get("varDiario95")), "maxDrawdownPct": _pct(metricas.get("maxDrawdown")),
            "retorno6mPct": _pct(metricas.get("retorno6m")), "retorno12mPct": _pct(metricas.get("retorno12m")),
            "diferencialBenchmark12mPct": _pct(metricas.get("diferencialBenchmark12m")),
            "tasaLibreRiesgoPct": _pct(metricas.get("tasaLibre")),
        },
        "pronostico": {
            "diasHabiles": datos.get("diasPronostico"),
            "retornoProyectadoPct": _pct(resumen.get("rentabilidadProyectada")),
            "bandaInferior": numeroSeguro(resumen.get("bandaInferior"), 2), "bandaSuperior": numeroSeguro(resumen.get("bandaSuperior"), 2),
            "modeloSuperaLineaBase": bool(resumen.get("tieneHabilidad")),
        },
        "riesgo": {"categoria": datos["riesgo"].get("categoria"), "puntaje": datos["riesgo"].get("puntaje"),
                   "clasificadorProximos3Meses": datos.get("clasificadorRiesgo", {}).get("categoriaActual")},
        "sentimiento": {"fuenteEnSenal": sentimiento.get("fuenteSenal"),
                        "tonoPrensa30dias": numeroSeguro(sentimiento.get("tonoReciente"), 2),
                        "tonoPrensaDesviacionesVsAnio": numeroSeguro(sentimiento.get("zTono"), 2),
                        "titulares30diasPromedio": numeroSeguro(sentimiento.get("promedioReciente"), 3),
                        "titularesRecientes": sentimiento.get("recientes")},
        "senal": {
            "accion": senal["accion"], "puntaje": senal["puntaje"], "confianza": senal["confianza"],
            "factores": [{"factor": f["factor"], "valor": f["valor"], "puntos": f["puntos"], "participa": f["activo"]}
                         for f in senal["factores"]],
        },
        "bonosDelPerfil": {"recomendacion": resumenBonos.get("recomendacion"), "ranking": bonos},
        "asignacion": [{"detalle": f["detalle"], "ticker": f["ticker"], "pesoPct": _pct(f["peso"], 1)} for f in asignacion["filas"]],
        "seleccionDelUsuario": _contextoSeleccion(decision),
        "proyeccionCarteraCompleta": _contextoCartera(decision.get("proyeccionCartera")),
        "titulares": titulares,
    }


def _contextoSeleccion(decision):
    """Fondo y bonos especificos elegidos, con su evaluacion y la proyeccion."""
    seleccion = decision.get("seleccion")
    if not decision.get("fondo"):
        return None
    bonos = []
    if seleccion is not None and not seleccion.empty:
        for _, b in seleccion.iterrows():
            bonos.append({
                "emisor": str(b["emisor"]), "cusip": str(b["cusip"]), "vencimiento": f"{b['vencimiento']:%Y-%m-%d}",
                "cuponPct": _pct(b["cupon"], 3), "tirPct": _pct(b["tir"]), "rendimientoEsperadoPct": _pct(b["rendimientoEsperado"]),
                "calidadImplicita": b["calidad"], "duracion": numeroSeguro(b["duracion"], 2), "veredicto": b["veredicto"],
                "motivo": b["motivo"],
            })
    proyeccion = decision.get("proyeccion") or {}
    coherencia = decision.get("coherencia") or {}
    return {
        "fondoDeBonos": decision.get("fondo"), "bonosEspecificos": bonos,
        "coherenciaConPerfil": coherencia.get("mensaje"),
        "proyeccion": {
            "meses": proyeccion.get("meses"), "montoInvertido": numeroSeguro(proyeccion.get("montoTotal"), 0),
            "valorFinalMediano": numeroSeguro(proyeccion.get("valorMediano"), 0),
            "gananciaMediana": numeroSeguro(proyeccion.get("gananciaMediana"), 0),
            "gananciaPesimistaP10": numeroSeguro(proyeccion.get("gananciaPesimista"), 0),
            "gananciaOptimistaP90": numeroSeguro(proyeccion.get("gananciaOptimista"), 0),
            "probabilidadPerdidaPct": _pct(proyeccion.get("probabilidadPerdida"), 1),
            "rendimientoAnualPct": _pct(proyeccion.get("rendimientoAnual")),
        } if proyeccion else None,
    }


def _contextoCartera(cartera):
    """Proyeccion de toda la cartera (acciones + renta fija + liquidez) para el LLM."""
    if not cartera:
        return None
    return {
        "meses": cartera.get("meses"), "montoInvertido": numeroSeguro(cartera.get("montoTotal"), 0),
        "valorFinalMediano": numeroSeguro(cartera.get("valorMediano"), 0),
        "gananciaMediana": numeroSeguro(cartera.get("gananciaMediana"), 0),
        "gananciaPesimistaP10": numeroSeguro(cartera.get("gananciaPesimista"), 0),
        "gananciaOptimistaP90": numeroSeguro(cartera.get("gananciaOptimista"), 0),
        "rendimientoAnualPct": _pct(cartera.get("rendimientoAnual")),
        "probabilidadPerdidaPct": _pct(cartera.get("probabilidadPerdida"), 1),
    }


INSTRUCCION_SISTEMA = (
    "Eres un analista financiero que explica, a un inversor no especializado, el análisis de un fondo mutuo. "
    "Usas ÚNICAMENTE las cifras del JSON: no calcules ni inventes cifras nuevas; si un dato no está, dilo. "
    "Los campos que terminan en 'Pct' ya están en puntos porcentuales (13.51 significa 13.51%). "
    "Si 'fondo.noticiasDeOtroTicker' no es nulo, aclara que las noticias son de ese ETF equivalente. "
    "Si un factor tiene 'participa': false, no lo uses como argumento. "
    "Escribe en español claro. Indica que el análisis es educativo y no constituye asesoría financiera. "
    "Responde directamente, sin mostrar razonamiento interno."
)


def construirPromptExplicacion(contexto, perfil):
    """Mensaje de sistema y plantilla del informe (compartidos por Qwen3 y Gemini)."""
    plantilla = f"""Explica este análisis para un inversor de perfil {perfil}.

DATOS (JSON):
{json.dumps(contexto, ensure_ascii=False, indent=2, default=str)}

Escribe exactamente estas cuatro secciones en markdown:

### Cómo se ha comportado el fondo
Dos o tres frases con los indicadores.

### Qué factores explican la señal
Explica la señal y sus factores tal como vienen en 'senal.factores' (puntos de cada uno, y cuáles no participan y por qué). No la justifiques más allá de esos factores.

### Bonos para tu perfil y asignación
Si 'seleccionDelUsuario' no es nulo, explica el fondo y los bonos específicos que eligió (emisor, vencimiento, rendimiento esperado, veredicto y su motivo), su coherencia con el perfil y la proyección. Si no, resume 'bonosDelPerfil'. Luego la asignación. Distingue la ganancia de la renta fija ('seleccionDelUsuario.proyeccion') de la de toda la cartera ('proyeccionCarteraCompleta'), que incluye las acciones.

### Riesgos a vigilar
Tres viñetas con riesgos concretos que se desprenden de los datos.

Máximo 350 palabras. No repitas el JSON."""
    return INSTRUCCION_SISTEMA, plantilla


def _numerosPermitidos(objeto, salida=None):
    """Todos los numeros del contexto (recorrido recursivo), incluidos los que vienen dentro de textos."""
    salida = set() if salida is None else salida
    if isinstance(objeto, dict):
        for valor in objeto.values():
            _numerosPermitidos(valor, salida)
    elif isinstance(objeto, (list, tuple)):
        for valor in objeto:
            _numerosPermitidos(valor, salida)
    elif isinstance(objeto, bool) or objeto is None:
        pass
    elif isinstance(objeto, (int, float, np.integer, np.floating)):
        salida.add(abs(float(objeto)))
    elif isinstance(objeto, str):
        for texto in re.findall(r"\d+(?:[.,]\d+)?", objeto):
            salida.add(abs(float(texto.replace(",", "."))))
    return salida


def _numerosPorcentuales(objeto, salida=None, clave=""):
    """Cifras porcentuales del contexto: campos ...Pct y numeros seguidos de % dentro de textos."""
    salida = set() if salida is None else salida
    if isinstance(objeto, dict):
        for k, valor in objeto.items():
            _numerosPorcentuales(valor, salida, str(k))
    elif isinstance(objeto, (list, tuple)):
        for valor in objeto:
            _numerosPorcentuales(valor, salida, clave)
    elif isinstance(objeto, str):
        for texto in re.findall(r"(\d+(?:[.,]\d+)?)\s*%", objeto):
            salida.add(abs(float(texto.replace(",", "."))))
    elif not isinstance(objeto, bool) and isinstance(objeto, (int, float, np.integer, np.floating)) and clave.endswith("Pct"):
        salida.add(abs(float(objeto)))
    return salida


def validarCifrasInforme(texto, contexto):
    """
    Devuelve las cifras del texto que NO aparecen en el contexto (tolerancia
    de redondeo). Una cifra con % solo se acepta si coincide con un dato
    PORCENTUAL del contexto. Se ignoran enteros pequenos sin % (conteos,
    secciones), anios y las cifras propias de la plantilla (banda del 90%).
    """
    generales = _numerosPermitidos(contexto) | {90.0, 350.0, 100.0, 0.0}
    porcentuales = _numerosPorcentuales(contexto) | {90.0, 100.0, 0.0}
    sospechosas = []
    for coincidencia in re.finditer(r"(?<![\w.])[-−+]?(\d+(?:[.,]\d+)?)\s*(%|pp)?", texto or ""):
        cifra = coincidencia.group(1)
        numero = float(cifra.replace(",", "."))
        esPorcentaje = coincidencia.group(2) is not None
        if not esPorcentaje and "." not in cifra and "," not in cifra and (numero <= 12 or 1900 <= numero <= 2100):
            continue
        tolerancia = max(0.051, numero * 0.005)
        permitidos = porcentuales if esPorcentaje else generales
        if not any(abs(numero - p) <= tolerancia for p in permitidos):
            sospechosas.append(coincidencia.group(0).strip())
    return list(dict.fromkeys(sospechosas))


def _llamarOllama(cuerpo, ruta):
    respuesta = requests.post(f"{URL_OLLAMA}{ruta}", json=cuerpo, timeout=OLLAMA_TIMEOUT)
    respuesta.raise_for_status()
    return respuesta.json()


def generarExplicacionQwen(contexto, perfil="Moderado"):
    """Informe con Qwen3 via Ollama. Devuelve el texto o None."""
    sistema, plantilla = construirPromptExplicacion(contexto, perfil)
    cuerpo = {"model": OLLAMA_MODELO, "prompt": plantilla, "system": sistema, "stream": False, "think": False,
              "options": {"temperature": OLLAMA_TEMPERATURA, "num_predict": 900}}
    try:
        texto = limpiarRazonamiento(_llamarOllama(cuerpo, "/api/generate").get("response", ""))
        return texto or None
    except requests.exceptions.RequestException as error:
        registrarEvento(f"Error al consultar Qwen3: {error}", "ERROR")
        return None


def extraerTextoGemini(datosRespuesta):
    """Texto de una respuesta de Gemini, sin las partes de razonamiento."""
    candidatos = datosRespuesta.get("candidates", [])
    if not candidatos:
        return None
    partes = candidatos[0].get("content", {}).get("parts", [])
    texto = "".join(p.get("text", "") for p in partes if p.get("text") and not p.get("thought")).strip()
    return texto or None


def _llamarGemini(contenidos, sistema, maximoTokens):
    if not GEMINI_API_KEY:
        return None
    cuerpo = {
        "contents": contenidos,
        "systemInstruction": {"parts": [{"text": sistema}]},
        # En Gemini 3.x el razonamiento cuenta dentro de maxOutputTokens: se baja
        # su nivel y se deja margen para que la respuesta no se corte.
        "generationConfig": {"temperature": GEMINI_TEMPERATURA, "maxOutputTokens": maximoTokens,
                             "thinkingConfig": {"thinkingLevel": "low"}},
    }
    try:
        respuesta = requests.post(URL_GEMINI, headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                                  json=cuerpo, timeout=GEMINI_TIMEOUT)
        respuesta.raise_for_status()
        return extraerTextoGemini(respuesta.json())
    except requests.exceptions.RequestException as error:
        registrarEvento(f"Error al consultar Gemini: {error}", "ERROR")
        return None


def generarExplicacionGemini(contexto, perfil="Moderado"):
    """Informe con Gemini (respaldo). Devuelve el texto o None."""
    sistema, plantilla = construirPromptExplicacion(contexto, perfil)
    return _llamarGemini([{"role": "user", "parts": [{"text": plantilla}]}], sistema, 2048)


def generarExplicacionLLM(contexto, perfil="Moderado", proveedorInfo=None):
    """
    Informe con el proveedor que corresponda (reutiliza proveedorInfo si se
    pasa). Devuelve (texto_o_None, proveedorUsado, cifrasNoVerificadas).
    """
    proveedor, estado, forzado = proveedorInfo or determinarProveedorActivo()
    intentos = [proveedor] if forzado else [proveedor] + [p for p in ("qwen3", "gemini") if p != proveedor]
    for candidato in intentos:
        if candidato == proveedor and not proveedorListo(estado):
            continue
        texto = generarExplicacionQwen(contexto, perfil) if candidato == "qwen3" else generarExplicacionGemini(contexto, perfil)
        if texto:
            return texto, candidato, validarCifrasInforme(texto, contexto)
    return None, proveedor, []


MAXIMO_MENSAJES_HISTORIAL = 16


def construirSistemaChat(contexto, perfil="Moderado"):
    """Mensaje de sistema del chat asesor, con el mismo JSON del informe."""
    return (
        f"{INSTRUCCION_SISTEMA} Eres el asistente de FundScope; el usuario ya vio los dashboards. "
        f"Perfil del inversor: {perfil}. No tienes acceso a internet ni a precios en vivo: si preguntan algo "
        "que el JSON no cubre, acláralo. Responde en pocas frases.\n\n"
        f"DATOS DEL ANÁLISIS (JSON):\n{json.dumps(contexto, ensure_ascii=False, default=str)}"
    )


def chatearConLLM(mensajes, contexto, perfil="Moderado", proveedorInfo=None):
    """Chat con el proveedor que corresponda. Devuelve (texto_o_None, proveedorUsado)."""
    proveedor, estado, forzado = proveedorInfo or determinarProveedorActivo()
    sistema = construirSistemaChat(contexto, perfil)
    historial = mensajes[-MAXIMO_MENSAJES_HISTORIAL:]
    intentos = [proveedor] if forzado else [proveedor] + [p for p in ("qwen3", "gemini") if p != proveedor]
    for candidato in intentos:
        if candidato == proveedor and not proveedorListo(estado):
            continue
        if candidato == "qwen3":
            cuerpo = {"model": OLLAMA_MODELO, "messages": [{"role": "system", "content": sistema}, *historial],
                      "stream": False, "think": False, "options": {"temperature": OLLAMA_TEMPERATURA, "num_predict": 500}}
            try:
                texto = limpiarRazonamiento(_llamarOllama(cuerpo, "/api/chat").get("message", {}).get("content", ""))
            except requests.exceptions.RequestException as error:
                registrarEvento(f"Error al chatear con Qwen3: {error}", "ERROR")
                texto = None
        else:
            contenidos = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                          for m in historial]
            texto = _llamarGemini(contenidos, sistema, 1024)
        if texto:
            return texto, candidato
    return None, proveedor


def explicacionDeRespaldo(datos, perfil):
    """Explicacion construida con reglas para cuando no hay proveedor de IA."""
    metricas, senal = datos["metricas"], datos["senal"]
    _, resumenBonos = datos.get("rankingsPorPerfil", {}).get(perfil, (pd.DataFrame(), {}))
    lineas = [
        "### Cómo se ha comportado el fondo",
        f"Retorno anualizado de {formatearPorcentaje(metricas.get('retornoAnual'))}, volatilidad de "
        f"{formatearPorcentaje(metricas.get('volatilidadAnual'))} y peor caída de {formatearPorcentaje(metricas.get('maxDrawdown'))}. "
        f"En los últimos 12 meses rindió {formatearPorcentaje(metricas.get('retorno12m'), 1, True)}.",
        "\n### Qué factores explican la señal",
        f"La señal es **{senal['accion']}** (puntaje {senal['puntaje']}, confianza {senal['confianza'].lower()}).",
    ]
    for factor in senal["factores"]:
        estado = f"{factor['puntos']:+.1f} puntos" if factor["activo"] else f"no participa ({factor['nota']})"
        lineas.append(f"- {factor['factor']}: {factor['valor']} → {estado}")
    lineas += ["\n### Bonos para tu perfil y asignación", resumenBonos.get("recomendacion", "Sin datos de bonos."),
               "\n### Riesgos a vigilar"]
    alertas = senal.get("alertas") or [f"El riesgo del fondo es {datos['riesgo'].get('categoria')}.",
                                       "Toda proyección pierde precisión a medida que crece el horizonte."]
    lineas += [f"- {a}" for a in alertas[:3]]
    lineas.append("\n_Explicación generada con reglas porque no hay un proveedor de IA disponible. "
                  "Este análisis es educativo y no constituye asesoría financiera._")
    return "\n".join(lineas)

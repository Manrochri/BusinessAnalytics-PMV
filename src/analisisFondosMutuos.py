"""
analisisFondosMutuos.py
Evaluacion de los FONDOS MUTUOS del catalogo para cada perfil.

- Fondos de bonos: se evaluan con su propia historia y las mismas reglas que
  los ETF del ranking (prima sobre la liquidez, Sharpe, volatilidad, caida,
  tendencia y los vetos del perfil). Si su historia no alcanza, heredan la
  fila del ETF gemelo (misma cartera).
- Fondos de acciones y mixtos: no hay «prima sobre la liquidez» que juzgar;
  se mide si su riesgo (volatilidad y peor caida de 3 anios) cabe en la
  tolerancia del perfil, su relacion rendimiento/riesgo (Sharpe) y su
  tendencia. Mas alla de 1.25x la tolerancia: «No recomendable».
"""

import numpy as np
import pandas as pd

from src.analisisBonos import _escala, metricasBono, puntuarBono
from src.catalogoBonos import UMBRAL_ACEPTABLE, UMBRAL_RECOMENDABLE, buscarBono
from src.catalogoFondosMutuos import (
    CLASE_BONOS,
    SHARPE_RECOMENDABLE,
    TOLERANCIAS_RENTA_VARIABLE,
    fondosMutuosDelPerfil,
)
from src.datosEstructurados import descargarHistorico, obtenerInfoFondo
from src.utilidades import esNulo, registrarEvento

PESOS_RENTA_VARIABLE = {"sharpe": 0.35, "volatilidad": 0.25, "caida": 0.25, "tendencia": 0.15}
ORDEN_VEREDICTO = {"Recomendable": 0, "Aceptable": 1, "No recomendable": 2, "Sin datos": 3}


def descargarUniversoMutuos(periodo="5y", usarCache=True, tickers=None):
    """Historico y ficha de cada fondo mutuo del catalogo (y de sus referencias). {ticker: {historico, ficha}}."""
    from src.catalogoFondosMutuos import tickersReferencia, todosLosTickersMutuos

    universo = {}
    for ticker in tickers or (todosLosTickersMutuos() + tickersReferencia()):
        try:
            historico = descargarHistorico(ticker, periodo, usarCache)
            ficha = obtenerInfoFondo(ticker, usarCache)
        except Exception as error:  # un fondo que falla no detiene a los demas
            registrarEvento(f"No se pudo descargar {ticker}: {error}", "WARN")
            historico, ficha = pd.DataFrame(), {}
        universo[ticker] = {"historico": historico if historico is not None else pd.DataFrame(), "ficha": ficha or {}}
    registrarEvento(f"Fondos mutuos: {sum(1 for v in universo.values() if not v['historico'].empty)} con datos.")
    return universo


def puntuarRentaVariable(metricas, perfil):
    """Puntaje 0-100, componentes, veredicto y motivos de un fondo de acciones o mixto para un perfil."""
    t = TOLERANCIAS_RENTA_VARIABLE[perfil]
    if metricas["observaciones"] < 200:
        return np.nan, {}, "Sin datos", ["Menos de un año de historia."]
    tendenciaPrecio = _escala(metricas["retorno6m"], -0.10, 0.10)
    componentes = {
        "sharpe": _escala(metricas["sharpe"], -0.5, 1.0),
        "volatilidad": 1 - _escala(metricas["volatilidad"], 0, 2 * t["volatilidadMaxima"]),
        "caida": 1 - _escala(abs(metricas["caidaMaxima"]), 0, 2 * abs(t["caidaTolerada"])),
        "tendencia": 0.5 * (0.5 if esNulo(tendenciaPrecio) else tendenciaPrecio)
        + 0.5 * (1.0 if metricas["sobreMedia200"] else 0.0),
    }
    componentes = {k: (0.5 if esNulo(v) else v) for k, v in componentes.items()}
    puntaje = 100 * sum(componentes[k] * PESOS_RENTA_VARIABLE[k] for k in PESOS_RENTA_VARIABLE)

    vetos, avisos = [], []
    vol, caida = metricas["volatilidad"], metricas["caidaMaxima"]
    if not esNulo(vol) and vol > 1.25 * t["volatilidadMaxima"]:
        vetos.append(f"Volatilidad {vol:.0%}, demasiada para un perfil {perfil} (tolera hasta {t['volatilidadMaxima']:.0%}).")
    elif not esNulo(vol) and vol > t["volatilidadMaxima"]:
        avisos.append(f"Volatilidad {vol:.0%}, algo por encima de lo que tolera tu perfil ({t['volatilidadMaxima']:.0%}).")
    if not esNulo(caida) and caida < 1.25 * t["caidaTolerada"]:
        vetos.append(f"Peor caída {caida:.0%}, más de lo que soporta un perfil {perfil} ({t['caidaTolerada']:.0%}).")
    elif not esNulo(caida) and caida < t["caidaTolerada"]:
        avisos.append(f"Peor caída {caida:.0%}, algo más de lo que tolera tu perfil ({t['caidaTolerada']:.0%}).")
    if metricas["sobreMedia200"] is False and not esNulo(metricas["retorno6m"]) and metricas["retorno6m"] < -0.10:
        avisos.append(f"Tendencia bajista: {metricas['retorno6m']:+.0%} en 6 meses y bajo su media de 200 días.")

    if vetos:
        return puntaje, componentes, "No recomendable", vetos
    if puntaje < UMBRAL_ACEPTABLE:
        return puntaje, componentes, "No recomendable", avisos + [
            f"Relación rendimiento/riesgo pobre (Sharpe {metricas['sharpe']:.2f}) para lo que arriesga."]
    if not avisos and puntaje >= UMBRAL_RECOMENDABLE and not esNulo(metricas["sharpe"]) and metricas["sharpe"] >= SHARPE_RECOMENDABLE:
        return puntaje, componentes, "Recomendable", [
            f"Riesgo dentro de tu perfil (volatilidad {vol:.0%}, peor caída {caida:.0%}) y buena relación rendimiento/riesgo "
            f"(Sharpe {metricas['sharpe']:.2f})."]
    motivo = avisos or [f"Riesgo dentro de tu perfil, pero relación rendimiento/riesgo intermedia (Sharpe {metricas['sharpe']:.2f})."]
    return puntaje, componentes, "Aceptable", motivo


def _filaGemelo(ficha, rankingBonos):
    """Fila del ETF gemelo en el ranking de bonos del perfil (o None)."""
    if rankingBonos is None or rankingBonos.empty or not ficha.get("gemelo"):
        return None
    tabla = rankingBonos.set_index("ticker")
    return tabla.loc[ficha["gemelo"]] if ficha["gemelo"] in tabla.index else None


def evaluarFondoMutuo(ficha, historico, fichaYahoo, perfil, tasaLibre, rankingBonos=None):
    """Una fila del ranking de fondos mutuos: veredicto, motivo y cifras clave para el perfil."""
    m = metricasBono(historico, fichaYahoo, tasaLibre, 0.0)
    fila = {
        "ticker": ficha["ticker"], "nombre": ficha["nombreSimple"], "clase": ficha["clase"], "categoria": ficha["categoria"],
        "gemelo": ficha.get("gemelo"), "gastoAnual": ((fichaYahoo or {}).get("gastoAnual") or ficha["gastoAnual"]),
        "minimo": ficha["minimo"], "retornoAnual3a": m["retornoAnual"], "volatilidad": m["volatilidad"],
        "sharpe": m["sharpe"], "caidaMaxima": m["caidaMaxima"], "retorno6m": m["retorno6m"],
        "sobreMedia200": m["sobreMedia200"], "rendimiento": m["rendimiento"], "rendimientoEsperado": np.nan,
        "prima": np.nan, "fuenteRendimiento": m["fuenteRendimiento"], "fuenteVeredicto": "propio",
    }
    if ficha["clase"] == CLASE_BONOS:
        bono = buscarBono(ficha.get("gemelo")) or {}
        m = metricasBono(historico, fichaYahoo, tasaLibre, bono.get("perdidaCreditoEsperada", 0.0))
        fila.update(rendimientoEsperado=m["rendimientoEsperado"], prima=m["prima"])
        puntaje, componentes, veredicto, motivos = puntuarBono(m, perfil)
        gemelo = _filaGemelo(ficha, rankingBonos)
        if veredicto == "Sin datos" and gemelo is not None:  # sin historia propia: hereda la del ETF gemelo
            puntaje, componentes, veredicto, motivos = gemelo["puntaje"], gemelo["componentes"], gemelo["veredicto"], [gemelo["motivo"]]
            fila.update(rendimientoEsperado=gemelo["rendimientoEsperado"], prima=gemelo["prima"], fuenteVeredicto="gemelo",
                        volatilidad=gemelo["volatilidad"], caidaMaxima=gemelo["caidaMaxima"], sharpe=gemelo["sharpe"])
        # «Rinde» de un fondo de bonos: lo que paga al anio (ya descontados impagos esperados)
        fila["rinde"] = fila["rendimientoEsperado"]
    else:
        puntaje, componentes, veredicto, motivos = puntuarRentaVariable(m, perfil)
        fila["rinde"] = m["retornoAnual"]  # retorno anual de los ultimos 3 anios
    fila.update(puntaje=puntaje, componentes=componentes, veredicto=veredicto, motivo=" ".join(motivos))
    return fila


def rankingFondosMutuos(universoMutuos, perfil, tasaLibre, rankingBonos=None):
    """
    Ranking de los fondos mutuos del perfil (mejor primero). Devuelve (tabla, resumen).
    La tabla tiene una fila por fondo con puesto, clase, veredicto, motivo, rinde y costos.
    """
    filas = []
    for ficha in fondosMutuosDelPerfil(perfil):
        datos = (universoMutuos or {}).get(ficha["ticker"], {})
        filas.append(evaluarFondoMutuo(ficha, datos.get("historico"), datos.get("ficha"), perfil, tasaLibre, rankingBonos))
    tabla = pd.DataFrame(filas)
    if tabla.empty:
        return tabla, {"recomendables": 0, "aceptables": 0, "evaluados": 0}
    tabla["ordenVeredicto"] = tabla["veredicto"].map(ORDEN_VEREDICTO)
    tabla = tabla.sort_values(["ordenVeredicto", "puntaje"], ascending=[True, False], na_position="last")
    tabla = tabla.drop(columns="ordenVeredicto").reset_index(drop=True)
    tabla.insert(0, "puesto", range(1, len(tabla) + 1))
    resumen = {"perfil": perfil, "recomendables": int((tabla["veredicto"] == "Recomendable").sum()),
               "aceptables": int((tabla["veredicto"] == "Aceptable").sum()),
               "evaluados": int((tabla["veredicto"] != "Sin datos").sum())}
    return tabla, resumen


def recortarUniversoMutuos(universo, fechaCorte):
    """Universo recortado a una fecha (evaluacion por semana)."""
    if fechaCorte is None or not universo:
        return universo
    fin = pd.Timestamp(fechaCorte).normalize() + pd.Timedelta(days=1)
    return {t: {"historico": d["historico"].loc[d["historico"].index < fin] if not d["historico"].empty else d["historico"],
                "ficha": d["ficha"]} for t, d in universo.items()}


def veredictoParaPerfil(datos, perfil):
    """
    Veredicto del FONDO ANALIZADO para el perfil, de donde corresponda:
    el ranking de ETF de bonos o el de fondos mutuos. Devuelve
    {veredicto, motivo, alternativa, origen} (veredicto None si no esta en ninguno).
    """
    ticker = datos["ticker"]
    tablaBonos, _ = (datos.get("rankingsPorPerfil") or {}).get(perfil, (pd.DataFrame(), {}))
    if tablaBonos is not None and not tablaBonos.empty and ticker in set(tablaBonos["ticker"]):
        fila = tablaBonos.set_index("ticker").loc[ticker]
        otros = tablaBonos.loc[tablaBonos["veredicto"].isin(["Recomendable", "Aceptable"]) & (tablaBonos["ticker"] != ticker)]
        return {"veredicto": fila["veredicto"], "motivo": fila.get("motivo", ""), "origen": "bonos",
                "alternativa": otros.iloc[0]["ticker"] if not otros.empty else None}
    tablaMutuos, _ = (datos.get("rankingsMutuosPorPerfil") or {}).get(perfil, (pd.DataFrame(), {}))
    if tablaMutuos is not None and not tablaMutuos.empty and ticker in set(tablaMutuos["ticker"]):
        fila = tablaMutuos.set_index("ticker").loc[ticker]
        mismaClase = tablaMutuos.loc[tablaMutuos["veredicto"].isin(["Recomendable", "Aceptable"])
                                     & (tablaMutuos["ticker"] != ticker) & (tablaMutuos["clase"] == fila["clase"])]
        return {"veredicto": fila["veredicto"], "motivo": fila.get("motivo", ""), "origen": "mutuos",
                "alternativa": mismaClase.iloc[0]["ticker"] if not mismaClase.empty else None}
    return {"veredicto": None, "motivo": "", "origen": None, "alternativa": None}
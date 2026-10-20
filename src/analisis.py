"""
analisis.py
Orquestacion del flujo CRISP-ML(Q): descarga (una vez) y analisis completo.

Separado de la interfaz para que la app y el notebook usen exactamente el
mismo flujo, y para poder probarlo sin Streamlit.
"""

from datetime import datetime

import numpy as np
import pandas as pd

from config import NOTICIAS_LIMITE, TICKER_RENTA_VARIABLE
from src.analisisBonos import descargarUniversoBonos, rankingBonos, recortarUniverso
from src.backtest import backtestSenal
from src.bonosIndividuales import TICKERS_CURVA, construirCurva
from src.catalogoBonos import PERFILES, buscarBono, perfilDelFondo
from src.datosEstructurados import (
    benchmarkEsRetornoTotal,
    calcularMetricasDescriptivas,
    clasificarRiesgo,
    compararConBenchmark,
    descargarHistorico,
    obtenerInfoFondo,
    obtenerPrincipalesPosiciones,
    obtenerTasaLibreRiesgo,
    resumirRentabilidadPorPeriodo,
)
from src.datosNoticias import (
    construirSerieSentimiento,
    descargarNoticias,
    descargarTonoPrensa,
    obtenerTitularesDestacados,
    resumirSentimiento,
    sugerirTickerNoticias,
    temaTonoPrensa,
)
from src.modeloClasificacionRiesgo import entrenarClasificadorRiesgo, etiquetarRiesgo
from src.modeloPredictivo import (
    entrenarYEvaluar,
    evaluarRiesgoFuturo,
    obtenerImportanciaVariables,
    pronosticarHorizonte,
    resumirPronostico,
)
from src.motorPrescriptivo import calcularRetornoEsperado, claseDelFondo, generarSenal, validarRetrospectivamente
from src.preparacionDatos import (
    construirCaracteristicas,
    describirGranularidad,
    recortarHastaFecha,
    unirNavYSentimiento,
    verificarCalidadDatos,
)
from src.utilidades import describirOrigen, registrarEvento

PERIODO_BONOS = "5y"


def descargarComun(usarCache=True, incluirBonos=True):
    """
    Datos compartidos por todos los fondos: universo de fondos de bonos por
    perfil, curva del Tesoro y tasa libre de riesgo. Se descargan UNA vez y
    permiten rankear los fondos de cada perfil antes de elegir cual analizar.
    """
    tasaLibre, fuenteTasa = obtenerTasaLibreRiesgo(usarCache)
    return {
        "tasaLibre": tasaLibre,
        "fuenteTasa": fuenteTasa,
        "bonos": descargarUniversoBonos(PERIODO_BONOS, usarCache) if incluirBonos else {},
        # Tasas del Tesoro a 3 meses, 5, 10 y 30 anios: curva actual y su historia
        # (para valorar bonos individuales y simular cambios de tasas)
        "curvaSeries": {t: descargarHistorico(t, "10y", usarCache) for t in TICKERS_CURVA} if incluirBonos else {},
        # ETF de acciones de referencia: proyeccion de la parte de renta variable de la cartera
        "rentaVariable": _historicoSeguro(TICKER_RENTA_VARIABLE, "10y", usarCache) if incluirBonos else pd.DataFrame(),
        "tickerRentaVariable": TICKER_RENTA_VARIABLE,
        "fechaDescargaComun": datetime.now(),
    }


def _historicoSeguro(ticker, periodo, usarCache):
    """Historico o tabla vacia si no se pudo descargar (no detiene la app)."""
    try:
        tabla = descargarHistorico(ticker, periodo, usarCache)
    except Exception as error:  # red o ticker invalido
        registrarEvento(f"No se pudo descargar {ticker}: {error}", "WARN")
        return pd.DataFrame()
    return tabla if tabla is not None else pd.DataFrame()


def rankingsComunes(comun, fechaCorte=None):
    """Ranking de los fondos de bonos de cada perfil con los datos comunes."""
    universo = recortarUniverso((comun or {}).get("bonos", {}), fechaCorte)
    tasaLibre = (comun or {}).get("tasaLibre", 0.0)
    return {perfil: rankingBonos(universo, perfil, tasaLibre) for perfil in PERFILES}


def descargarFondo(ticker, benchmark, periodo, tickerNoticias=None, usarCache=True, comun=None):
    """
    Descarga (o lee de la cache) lo propio de UN fondo: precios, benchmark,
    ficha, posiciones, titulares y tono de prensa. Se combina con los datos
    comunes para formar la 'base' que consume ejecutarAnalisis.
    """
    historico = descargarHistorico(ticker, periodo, usarCache)
    if historico is None or historico.empty:
        return None
    comun = comun if comun is not None else descargarComun(usarCache)
    tickerParaNoticias = (tickerNoticias or "").strip().upper() or sugerirTickerNoticias(ticker)
    base = dict(comun)
    base.update({
        "ticker": ticker,
        "benchmarkTicker": benchmark,
        "periodo": periodo,
        "historico": historico,
        "benchmark": descargarHistorico(benchmark, periodo, usarCache) if benchmark else pd.DataFrame(),
        "ficha": obtenerInfoFondo(ticker, usarCache),
        "posiciones": obtenerPrincipalesPosiciones(ticker, 5, usarCache),
        # Titulares recientes (Yahoo Finance, su RSS y Google News por el tema del fondo; sin clave)
        "noticias": descargarNoticias(tickerParaNoticias, NOTICIAS_LIMITE, usarCache=usarCache,
                                      tickersExtra=(ticker,) if ticker != tickerParaNoticias else (),
                                      tema=temaTonoPrensa(ticker, tickerParaNoticias)),
        "tickerNoticias": tickerParaNoticias,
        # Tono diario de la prensa sobre el tema del fondo (GDELT): la historia del sentimiento
        "temaTono": temaTonoPrensa(ticker, tickerParaNoticias),
        "fechaDescarga": datetime.now(),
    })
    base["tono"] = descargarTonoPrensa(base["temaTono"], usarCache)
    return base


def descargarBase(ticker, benchmark, periodo, tickerNoticias=None, usarCache=True, incluirBonos=True):
    """Atajo (notebook y pruebas): datos comunes + datos del fondo en una sola llamada."""
    return descargarFondo(ticker, benchmark, periodo, tickerNoticias, usarCache,
                          comun=descargarComun(usarCache, incluirBonos))


def ejecutarAnalisis(base, dias, fechaCorte=None):
    """
    Ejecuta el analisis completo sobre datos ya descargados. Con fechaCorte,
    todo se calcula "como si hoy fuera esa fecha" (sin datos posteriores).
    Devuelve un diccionario con lo que consumen los dashboards.
    """
    resultado = {"exito": False, "mensaje": "", "avisos": [], "fechaEjecucion": datetime.now()}
    if not base:
        resultado["mensaje"] = "No se pudo obtener el histórico del fondo."
        return resultado

    ticker, benchmark = base["ticker"], base["benchmarkTicker"]
    historico, historicoBenchmark, noticias = recortarHastaFecha(base["historico"], base["benchmark"], base["noticias"], fechaCorte)
    if historico is None or historico.empty:
        resultado["mensaje"] = "No hay datos del fondo hasta la fecha de corte elegida."
        return resultado

    tasaLibre = base["tasaLibre"]
    comparable = benchmarkEsRetornoTotal(benchmark)
    fechaUltima = historico.index[-1]

    # --- Datos y descriptivo --------------------------------------------------
    tono = base.get("tono")
    if tono is not None and not tono.empty:
        tono = tono.loc[tono.index < fechaUltima.normalize()]  # solo dias calendario ya cerrados
    serieSentimiento = construirSerieSentimiento(noticias, historico.index, tono)
    sentimiento = resumirSentimiento(noticias, fechaReferencia=fechaUltima, serieTono=tono)
    metricas = calcularMetricasDescriptivas(historico, historicoBenchmark, tasaLibre, comparable)
    riesgo = clasificarRiesgo(metricas)
    calidad = verificarCalidadDatos(historico, noticias, historicoBenchmark, benchmark, comparable)
    calidad.append(("ok", f"Tasa libre de riesgo: {tasaLibre:.2%} · {base['fuenteTasa']}."))
    if tono is None or tono.empty:
        motivoTono = getattr(base.get("tono"), "attrs", {}).get("motivo", "")
        calidad.append(("alerta", f"Sin tono de prensa de GDELT para {base.get('temaTono')}. {motivoTono}".strip()))
    else:
        calidad.append(("ok" if sentimiento["fuenteSenal"] == "tono" else "alerta",
                        f"Tono de prensa (GDELT, tema {base.get('temaTono')}): {len(tono)} días desde {tono.index.min():%d/%m/%Y}. "
                        + ("Participa en la señal." if sentimiento["fuenteSenal"] == "tono"
                           else "Se necesitan 120 días para usarlo en la señal: completa la historia desde la barra lateral.")))
        mesesFaltantes = int(np.ceil((tono.index.min() - historico.index.min()).days / 30.4))
        if mesesFaltantes > 3:
            calidad.append(("alerta", f"Para que el tono entre también al modelo predictivo, su historia debe cubrir el periodo de "
                                      f"entrenamiento: completa unos {mesesFaltantes} meses más (hasta {historico.index.min():%m/%Y})."))
    if riesgo["supuestos"]:
        calidad.append(("alerta", f"Riesgo calculado con valores neutros para: {', '.join(riesgo['supuestos'])}."))
    origenFicha = describirOrigen("Ficha del fondo", base["ficha"])
    if origenFicha and origenFicha[0] == "alerta":
        calidad.append(origenFicha)
    if fechaCorte is not None:
        calidad.append(("ok", f"Evaluación al {pd.Timestamp(fechaCorte):%d/%m/%Y}: solo se usan precios y noticias hasta ese día."))
        calidad.append(("alerta", "La ficha, las posiciones, los rendimientos de los bonos y la tasa libre de riesgo son los de hoy "
                                  "(Yahoo no publica su historia)."))

    # --- Predictivo -------------------------------------------------------------
    tabla = construirCaracteristicas(unirNavYSentimiento(historico, serieSentimiento), horizonte=dias)
    modelo = entrenarYEvaluar(tabla, dias) if not tabla.empty else {"exito": False, "mensaje": "Sin datos para modelar."}
    resultado["avisos"] += modelo.get("avisos", [])
    pronostico, importancia = pd.DataFrame(), pd.DataFrame()
    resumenPron = resumirPronostico(None, metricas["valorActual"])
    riesgoFuturo = evaluarRiesgoFuturo(None, metricas["valorActual"])
    if modelo.get("exito"):
        pronostico = pronosticarHorizonte(modelo, tabla, metricas["valorActual"], fechaUltima, dias)
        resumenPron = resumirPronostico(pronostico, metricas["valorActual"], modelo)
        riesgoFuturo = evaluarRiesgoFuturo(pronostico, metricas["valorActual"])
        importancia = obtenerImportanciaVariables(modelo["predictor"], modelo["columnas"])
        if importancia.empty:  # el predictor es la media historica: se muestra el mejor modelo de ML como referencia
            importancia = obtenerImportanciaVariables(modelo.get("modeloReferencia"), modelo["columnas"])
            importancia.attrs["referencia"] = True
    else:
        resultado["avisos"].append(modelo.get("mensaje") or "No se pudieron entrenar los modelos.")

    clasificador = entrenarClasificadorRiesgo(etiquetarRiesgo(tabla, historicoBenchmark))
    if clasificador.get("mensaje"):
        resultado["avisos"].append(clasificador["mensaje"])

    # --- Prescriptivo -----------------------------------------------------------
    senal = generarSenal(metricas, resumenPron, riesgo, sentimiento, dias)
    universo = recortarUniverso(base.get("bonos", {}), fechaCorte)
    rankingsPorPerfil = {perfil: rankingBonos(universo, perfil, tasaLibre) for perfil in PERFILES}
    backtest, resumenBacktest = backtestSenal(historico, historicoBenchmark, dias, tasaLibre, comparable)

    resultado.update(
        {
            "exito": True, "ticker": ticker, "benchmark": benchmark, "benchmarkComparable": comparable,
            # Clase del fondo analizado (bonos o acciones) y su grupo en el catalogo por perfil
            "claseFondo": claseDelFondo(ticker, base["ficha"]), "perfilFondo": perfilDelFondo(ticker),
            "fichaCatalogo": buscarBono(ticker),
            "tickerNoticias": base["tickerNoticias"], "temaTono": base.get("temaTono"), "tasaLibre": tasaLibre,
            "fechaCorte": pd.Timestamp(fechaCorte).normalize() if fechaCorte is not None else None,
            "fechaDatoFinal": fechaUltima, "diasPronostico": dias,
            "historico": historico, "historicoBenchmark": historicoBenchmark, "ficha": base["ficha"],
            "posiciones": base["posiciones"], "noticias": noticias, "serieSentimiento": serieSentimiento,
            "sentimiento": sentimiento, "metricas": metricas, "riesgo": riesgo,
            "comparativo": compararConBenchmark(historico, historicoBenchmark),
            "rentabilidadPeriodos": resumirRentabilidadPorPeriodo(historico), "calidad": calidad,
            "granularidad": describirGranularidad(historico, noticias), "caracteristicas": tabla,
            "modelo": modelo, "pronostico": pronostico, "resumenPronostico": resumenPron,
            "riesgoFuturo": riesgoFuturo, "importancia": importancia, "clasificadorRiesgo": clasificador,
            "importanciaEsReferencia": bool(importancia.attrs.get("referencia", False)),
            "inicioTono": tono.index.min() if tono is not None and not tono.empty else None,
            "senal": senal, "retornoEsperado": calcularRetornoEsperado(metricas, resumenPron, dias),
            "titulares": obtenerTitularesDestacados(noticias, 5), "universoBonos": universo,
            "motivoNoticias": getattr(base["noticias"], "attrs", {}).get("motivo", ""),
            "fuentesNoticias": getattr(base["noticias"], "attrs", {}).get("fuentes", {}),
            "rankingsPorPerfil": rankingsPorPerfil,
            "rentaVariableReferencia": base.get("rentaVariable", pd.DataFrame()),
            "tickerRentaVariable": base.get("tickerRentaVariable", TICKER_RENTA_VARIABLE),
            "curvaSeries": base.get("curvaSeries", {}), "curva": construirCurva(base.get("curvaSeries", {})), "backtest": backtest, "resumenBacktest": resumenBacktest,
            "validacion": validarRetrospectivamente(senal, resumenPron, base["historico"], fechaCorte, dias,
                                                    base["benchmark"], metricas.get("volatilidadAnual")),
        }
    )
    registrarEvento(f"Análisis de {ticker} completo: señal {senal['accion']} ({senal['puntaje']}).")
    return resultado

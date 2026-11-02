"""
analisis.py
Orquestacion del flujo CRISP-ML(Q): descarga (una vez) y analisis completo.

Separado de la interfaz para que la app y el notebook usen exactamente el
mismo flujo, y para poder probarlo sin Streamlit.
"""

from datetime import datetime

import numpy as np
import pandas as pd

import time

from config import NOTICIAS_LIMITE, RUTA_SALIDAS, TICKER_RENTA_VARIABLE
from src.analisisBonos import descargarUniversoBonos, rankingBonos, recortarUniverso
from src.analisisFondosMutuos import descargarUniversoMutuos, rankingFondosMutuos, recortarUniversoMutuos
from src.backtest import backtestSenal
from src.bonosIndividuales import TICKERS_CURVA, construirCurva
from src.catalogoBonos import PERFILES, buscarBono, nombreFondo, perfilDelFondo
from src.catalogoFondosMutuos import buscarFondoMutuo, condicionesDeCompra
from src.datosEstructurados import (
    benchmarkEsRetornoTotal,
    calcularMetricasDescriptivas,
    clasificarRiesgo,
    compararConBenchmark,
    descargarHistorico,
    mejorPeorTrimestre,
    obtenerInfoFondo,
    rentabilidadPorAnio,
    retornoPromedioAnual,
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
    evaluarDeterioro,
    evaluarRiesgoFuturo,
    guardarModelo,
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


def pasosDescargaComun(incluirBonos=True):
    """Cuantas descargas hace descargarComun (para la barra de avance)."""
    from src.catalogoBonos import todosLosTickersBonos
    from src.catalogoFondosMutuos import tickersReferencia, todosLosTickersMutuos

    if not incluirBonos:
        return 1
    return 1 + len(todosLosTickersBonos()) + len(todosLosTickersMutuos()) + len(tickersReferencia()) + len(TICKERS_CURVA) + 1


def descargarComun(usarCache=True, incluirBonos=True, progreso=None):
    """
    Datos compartidos por todos los fondos: universo de fondos de bonos por
    perfil, curva del Tesoro y tasa libre de riesgo. Se descargan UNA vez y
    permiten rankear los fondos de cada perfil antes de elegir cual analizar.
    progreso: funcion opcional (texto) que se llama antes de cada descarga.
    """
    def avisar(texto):
        if progreso:
            progreso(texto)

    avisar("Tasa libre de riesgo (letras del Tesoro)")
    tasaLibre, fuenteTasa = obtenerTasaLibreRiesgo(usarCache)
    comun = {"tasaLibre": tasaLibre, "fechaDescargaComun": datetime.now(), "fuenteTasa": fuenteTasa,
             "tickerRentaVariable": TICKER_RENTA_VARIABLE}
    if not incluirBonos:
        comun.update(bonos={}, mutuos={}, curvaSeries={}, rentaVariable=pd.DataFrame())
        return comun
    comun["bonos"] = descargarUniversoBonos(PERIODO_BONOS, usarCache, progreso=lambda t: avisar(f"Fondo de bonos {nombreFondo(t)}"))
    # Fondos mutuos del catalogo (acciones, mixtos y bonos) y sus referencias
    comun["mutuos"] = descargarUniversoMutuos(PERIODO_BONOS, usarCache, progreso=lambda t: avisar(f"Fondo {nombreFondo(t)}"))
    # Tasas del Tesoro a 3 meses, 5, 10 y 30 anios: curva actual y su historia
    # (para valorar bonos individuales y simular cambios de tasas)
    comun["curvaSeries"] = {}
    for t in TICKERS_CURVA:
        avisar(f"Tasas del Tesoro ({t})")
        comun["curvaSeries"][t] = descargarHistorico(t, "10y", usarCache)
    # ETF de acciones de referencia: proyeccion de la parte de renta variable de la cartera
    avisar(f"Acciones de referencia ({TICKER_RENTA_VARIABLE})")
    comun["rentaVariable"] = _historicoSeguro(TICKER_RENTA_VARIABLE, "10y", usarCache)
    return comun


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


def rankingsMutuosComunes(comun, rankingsBonos=None, fechaCorte=None):
    """Ranking de los fondos mutuos de cada perfil (acciones, mixtos y bonos) con los datos comunes."""
    universo = recortarUniversoMutuos((comun or {}).get("mutuos", {}), fechaCorte)
    tasaLibre = (comun or {}).get("tasaLibre", 0.0)
    rankingsBonos = rankingsBonos or rankingsComunes(comun, fechaCorte)
    return {perfil: rankingFondosMutuos(universo, perfil, tasaLibre, rankingsBonos.get(perfil, (None, {}))[0]) for perfil in PERFILES}


PASOS_DESCARGA_FONDO = ("Precios del fondo", "Precios de la referencia", "Ficha y posiciones", "Titulares recientes",
                        "Tono de prensa (hasta 12 meses)")


def descargarFondo(ticker, benchmark, periodo, tickerNoticias=None, usarCache=True, comun=None, progreso=None):
    """
    Descarga (o lee de la cache) lo propio de UN fondo: precios, benchmark,
    ficha, posiciones, titulares y tono de prensa. Se combina con los datos
    comunes para formar la 'base' que consume ejecutarAnalisis.
    progreso: funcion opcional (numeroDePaso, texto) con los pasos de PASOS_DESCARGA_FONDO.
    """
    def avisar(i):
        if progreso:
            progreso(i, PASOS_DESCARGA_FONDO[i])

    avisar(0)
    historico = descargarHistorico(ticker, periodo, usarCache)
    if historico is None or historico.empty:
        return None
    comun = comun if comun is not None else descargarComun(usarCache)
    tickerParaNoticias = (tickerNoticias or "").strip().upper() or sugerirTickerNoticias(ticker)
    base = dict(comun)
    base.update({"ticker": ticker, "benchmarkTicker": benchmark, "periodo": periodo, "historico": historico,
                 "tickerNoticias": tickerParaNoticias, "temaTono": temaTonoPrensa(ticker, tickerParaNoticias),
                 "fechaDescarga": datetime.now()})
    avisar(1)
    base["benchmark"] = descargarHistorico(benchmark, periodo, usarCache) if benchmark else pd.DataFrame()
    avisar(2)
    base["ficha"] = obtenerInfoFondo(ticker, usarCache)
    base["posiciones"] = obtenerPrincipalesPosiciones(ticker, 5, usarCache)
    avisar(3)
    # Titulares recientes (Google News, Yahoo Finance y su RSS por el tema del fondo; sin clave)
    base["noticias"] = descargarNoticias(tickerParaNoticias, NOTICIAS_LIMITE, usarCache=usarCache,
                                         tickersExtra=(ticker,) if ticker != tickerParaNoticias else (), tema=base["temaTono"])
    avisar(4)
    # Tono diario de la prensa sobre el tema del fondo (GDELT): la historia del sentimiento
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
    inicioTiempo = time.time()
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
    universoMutuos = recortarUniversoMutuos(base.get("mutuos", {}), fechaCorte)
    rankingsMutuosPorPerfil = {perfil: rankingFondosMutuos(universoMutuos, perfil, tasaLibre, rankingsPorPerfil[perfil][0])
                               for perfil in PERFILES}
    backtest, resumenBacktest = backtestSenal(historico, historicoBenchmark, dias, tasaLibre, comparable)
    # Modelo servido como archivo: se guarda el predictor del analisis actual (no el de fechas pasadas)
    rutaModelo = guardarModelo(modelo, ticker, RUTA_SALIDAS) if modelo.get("exito") and fechaCorte is None else None
    deterioro = evaluarDeterioro(modelo, resumenBacktest, clasificador)
    descartados = getattr(base["historico"], "attrs", {}).get("registrosDescartados")
    crudos = getattr(base["historico"], "attrs", {}).get("registrosCrudos")
    if crudos:
        calidad.append(("ok", f"Registros de precios descartados en la limpieza: {descartados} de {crudos} ({descartados / crudos:.2%})."))

    resultado.update(
        {
            "exito": True, "ticker": ticker, "benchmark": benchmark, "benchmarkComparable": comparable,
            # Clase del fondo analizado (bonos o acciones) y su grupo en el catalogo por perfil
            "claseFondo": claseDelFondo(ticker, base["ficha"]), "perfilFondo": perfilDelFondo(ticker),
            "fichaCatalogo": buscarBono(ticker),
            "nombreFondo": nombreFondo(ticker, (base.get("ficha") or {}).get("nombre")),
            "nombreCorto": nombreFondo(ticker, (base.get("ficha") or {}).get("nombre"), conTicker=False),
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
            "motivoTono": getattr(base.get("tono"), "attrs", {}).get("motivoHistoria") or getattr(base.get("tono"), "attrs", {}).get("motivo"),
            "senal": senal, "retornoEsperado": calcularRetornoEsperado(metricas, resumenPron, dias),
            "titulares": obtenerTitularesDestacados(noticias, 5), "universoBonos": universo,
            "motivoNoticias": getattr(base["noticias"], "attrs", {}).get("motivo", ""),
            "fuentesNoticias": getattr(base["noticias"], "attrs", {}).get("fuentes", {}),
            "rankingsPorPerfil": rankingsPorPerfil, "rankingsMutuosPorPerfil": rankingsMutuosPorPerfil,
            "universoMutuos": universoMutuos, "fichaMutuo": buscarFondoMutuo(ticker),
            "condiciones": condicionesDeCompra(ticker, base.get("ficha")),
            "rentabilidadAnual": rentabilidadPorAnio(historico, historicoBenchmark),
            "trimestres": mejorPeorTrimestre(historico),
            "retornosPromedio": retornoPromedioAnual(historico, historicoBenchmark),
            "rentaVariableReferencia": base.get("rentaVariable", pd.DataFrame()),
            "tickerRentaVariable": base.get("tickerRentaVariable", TICKER_RENTA_VARIABLE),
            "curvaSeries": base.get("curvaSeries", {}), "curva": construirCurva(base.get("curvaSeries", {})), "backtest": backtest, "resumenBacktest": resumenBacktest,
            "validacion": validarRetrospectivamente(senal, resumenPron, base["historico"], fechaCorte, dias,
                                                    base["benchmark"], metricas.get("volatilidadAnual")),
            "rutaModelo": str(rutaModelo) if rutaModelo else None, "deterioro": deterioro,
            "registrosDescartados": descartados, "registrosCrudos": crudos,
            "duracionAnalisisSeg": round(time.time() - inicioTiempo, 2),
        }
    )
    registrarEvento(f"Análisis de {ticker} completo: señal {senal['accion']} ({senal['puntaje']}).")
    return resultado
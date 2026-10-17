"""
datosEstructurados.py
Fuente de datos estructurados: Yahoo Finance (libreria yfinance).

Entrega:
  - NAV / valor historico del fondo (ajustado por dividendos: retorno total)
  - Serie del benchmark y verificacion de que sea comparable
  - Ficha del fondo (categoria, gasto, rendimiento por distribuciones)
  - Tasa libre de riesgo vigente (letras del Tesoro a 13 semanas, ^IRX)
  - Metricas descriptivas de riesgo y rendimiento
"""

import numpy as np
import pandas as pd

from config import TASA_LIBRE_RIESGO
from src.utilidades import (
    ORIGEN_DESCARGA,
    ORIGEN_RESPALDO,
    cacheVigente,
    esNulo,
    guardarJson,
    guardarTabla,
    leerJson,
    leerTabla,
    marcarOrigen,
    nombreSeguro,
    registrarEvento,
    valorODefecto,
)

try:  # yfinance solo se necesita para descargar; el resto funciona con la cache
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

DIAS_HABILES_ANIO = 252


def _yfTicker(ticker):
    if yf is None:
        raise RuntimeError("yfinance no esta instalado")
    return yf.Ticker(ticker)


def construirTablaNav(serieNav, volumen=None):
    """Arma la tabla estandar (nav, volumen, retornoDiario, retornoAcumulado) a partir de una serie."""
    tabla = pd.DataFrame(index=pd.to_datetime(serieNav.index))
    tabla.index.name = "Date"
    tabla["nav"] = pd.to_numeric(serieNav.values, errors="coerce")
    tabla["volumen"] = volumen.values if volumen is not None else np.nan
    tabla = tabla.dropna(subset=["nav"])
    tabla = tabla[~tabla.index.duplicated(keep="last")].sort_index()
    tabla["retornoDiario"] = tabla["nav"].pct_change()
    tabla["retornoAcumulado"] = (tabla["nav"] / tabla["nav"].iloc[0]) - 1
    return tabla


def descargarHistorico(ticker, periodo="5y", usarCache=True):
    """
    Descarga el historico de precios (NAV ajustado) de un fondo o indice.
    Devuelve un DataFrame con columnas: nav, volumen, retornoDiario, retornoAcumulado.
    El origen (descarga/cache/cache vencida) queda en df.attrs['origen'].
    """
    nombreArchivo = f"historico_{nombreSeguro(ticker)}_{periodo}.csv"

    if usarCache and cacheVigente(nombreArchivo):
        tabla = leerTabla(nombreArchivo)
        if tabla is not None and not tabla.empty:
            registrarEvento(f"Historico de {ticker} leido desde cache.")
            return tabla

    try:
        crudo = _yfTicker(ticker).history(period=periodo, auto_adjust=True)
        if crudo is None or crudo.empty:
            raise ValueError("Yahoo Finance no devolvio datos")

        indice = pd.to_datetime(crudo.index)
        if indice.tz is not None:
            indice = indice.tz_localize(None)
        serie = pd.Series(crudo["Close"].values, index=indice.normalize())
        volumen = crudo["Volume"] if "Volume" in crudo else None
        tabla = construirTablaNav(serie, volumen)

        guardarTabla(tabla, nombreArchivo)
        registrarEvento(f"Historico de {ticker} descargado: {len(tabla)} registros.")
        return marcarOrigen(tabla, ORIGEN_DESCARGA)

    except Exception as error:  # red, ticker invalido, cambios de la API
        registrarEvento(f"Error al descargar {ticker}: {error}", "ERROR")
        tabla = leerTabla(nombreArchivo)
        if tabla is not None and not tabla.empty:
            return marcarOrigen(tabla, ORIGEN_RESPALDO, tabla.attrs.get("fechaCache"))
        return pd.DataFrame()


def _normalizarTasa(valor):
    """Yahoo publica algunos rendimientos como fraccion (0.042) y otros en % (4.2)."""
    if esNulo(valor):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero / 100 if abs(numero) > 1 else numero


def obtenerInfoFondo(ticker, usarCache=True):
    """
    Ficha del fondo: nombre, categoria, moneda, familia, gasto anual,
    patrimonio y rendimiento por distribuciones (yield, util para bonos).
    """
    nombreArchivo = f"info_{nombreSeguro(ticker)}.json"

    if usarCache and cacheVigente(nombreArchivo):
        info = leerJson(nombreArchivo)
        if info:
            return info

    ficha = {
        "ticker": ticker,
        "nombre": ticker,
        "categoria": "No disponible",
        "moneda": "USD",
        "familia": "No disponible",
        "gastoAnual": None,
        "patrimonio": None,
        "rendimientoDistribucion": None,
        "benchmarkSugerido": None,
    }

    try:
        info = _yfTicker(ticker).info or {}
        ficha["nombre"] = info.get("longName") or info.get("shortName") or ticker
        ficha["categoria"] = info.get("category") or info.get("quoteType") or "No disponible"
        ficha["moneda"] = info.get("currency", "USD")
        ficha["familia"] = info.get("fundFamily") or info.get("sector") or "No disponible"
        ficha["gastoAnual"] = _normalizarTasa(
            info.get("netExpenseRatio") or info.get("annualReportExpenseRatio")
        )
        ficha["patrimonio"] = info.get("totalAssets") or info.get("marketCap")
        ficha["rendimientoDistribucion"] = _normalizarTasa(
            info.get("yield") or info.get("dividendYield") or info.get("trailingAnnualDividendYield")
        )
        ficha["benchmarkSugerido"] = info.get("benchmark")
        guardarJson(ficha, nombreArchivo)
        registrarEvento(f"Ficha de {ticker} obtenida.")
        ficha["_origen"] = ORIGEN_DESCARGA
    except Exception as error:
        registrarEvento(f"No se pudo obtener la ficha de {ticker}: {error}", "WARN")
        respaldo = leerJson(nombreArchivo)
        if respaldo:
            respaldo["_origen"] = ORIGEN_RESPALDO
            return respaldo
        ficha["_origen"] = ORIGEN_RESPALDO

    return ficha


def obtenerPrincipalesPosiciones(ticker, cantidad=5, usarCache=True):
    """
    Obtiene las principales posiciones (top holdings) del fondo.
    Yahoo Finance no las expone para todos los instrumentos; si no hay datos
    se devuelve un DataFrame vacio y el dashboard lo informa.
    """
    nombreArchivo = f"holdings_{nombreSeguro(ticker)}.csv"

    if usarCache and cacheVigente(nombreArchivo):
        tabla = leerTabla(nombreArchivo, columnaFecha=None)
        if tabla is not None and not tabla.empty:
            return tabla.head(cantidad)

    try:
        datosFondo = getattr(_yfTicker(ticker), "funds_data", None)
        posiciones = getattr(datosFondo, "top_holdings", None) if datosFondo else None
        if posiciones is None or len(posiciones) == 0:
            registrarEvento(f"Sin posiciones publicadas para {ticker}.", "WARN")
            return pd.DataFrame()

        tabla = posiciones.reset_index()
        tabla = tabla.iloc[:, :3]
        tabla.columns = ["ticker", "nombre", "peso"][: len(tabla.columns)]
        tabla["peso"] = pd.to_numeric(tabla["peso"], errors="coerce")
        tabla = tabla.dropna(subset=["peso"]).head(cantidad).reset_index(drop=True)
        guardarTabla(tabla, nombreArchivo, conIndice=False)
        return tabla

    except Exception as error:
        registrarEvento(f"No se pudieron leer las posiciones de {ticker}: {error}", "WARN")
        tabla = leerTabla(nombreArchivo, columnaFecha=None)
        return tabla.head(cantidad) if tabla is not None else pd.DataFrame()


def obtenerTasaLibreRiesgo(usarCache=True):
    """
    Tasa libre de riesgo anual vigente: rendimiento de las letras del Tesoro
    de EE.UU. a 13 semanas (^IRX, publicado en %). Si no se puede leer se usa
    TASA_LIBRE_RIESGO del .env. Devuelve (tasa, descripcionFuente).
    """
    try:
        serie = descargarHistorico("^IRX", "1mo", usarCache)
        if serie is not None and not serie.empty:
            ultimo = float(serie["nav"].dropna().iloc[-1])
            if 0 <= ultimo < 25:
                return ultimo / 100, f"Letras del Tesoro a 13 semanas (^IRX) al {serie.index[-1]:%d/%m/%Y}"
    except Exception as error:
        registrarEvento(f"No se pudo leer ^IRX: {error}", "WARN")
    return TASA_LIBRE_RIESGO, "Valor de respaldo del .env (TASA_LIBRE_RIESGO)"


def benchmarkEsRetornoTotal(ticker):
    """
    True si el benchmark incluye dividendos y es comparable con un NAV
    ajustado. Los ETF/fondos (sin '^') se descargan ajustados; entre los
    indices, solo los de retorno total (p. ej. ^SP500TR) lo son.
    """
    texto = str(ticker or "").upper()
    if not texto:
        return False
    if not texto.startswith("^"):
        return True
    return texto in INDICES_RETORNO_TOTAL or texto.endswith("TR")


# Indices de Yahoo que reinvierten dividendos (retorno total)
INDICES_RETORNO_TOTAL = {"^SP500TR", "^XNDX", "^RUTTR", "^SP400TR", "^SP600TR"}


def calcularMaximaCaida(serieNav):
    """Calcula el max drawdown (peor caida desde un maximo historico)."""
    serie = pd.Series(serieNav).dropna()
    if serie.empty:
        return np.nan
    return float((serie / serie.cummax() - 1).min())


def calcularBeta(retornosFondo, retornosBenchmark):
    """Calcula el beta del fondo respecto a su benchmark (solo fechas comunes)."""
    alineados = pd.concat([retornosFondo, retornosBenchmark], axis=1, join="inner").dropna()
    if len(alineados) < 30:
        return np.nan
    varianza = alineados.iloc[:, 1].var()
    if not varianza:
        return np.nan
    return float(alineados.iloc[:, 0].cov(alineados.iloc[:, 1]) / varianza)


def retornoEnVentana(nav, dias):
    """Retorno simple de los ultimos 'dias' habiles (NaN si no hay historia suficiente)."""
    nav = pd.Series(nav).dropna()
    if len(nav) <= dias:
        return np.nan
    return float(nav.iloc[-1] / nav.iloc[-dias - 1] - 1)


def sharpeAnual(retornos, tasaLibre):
    """Sharpe anualizado con retorno geometrico menos la tasa libre de riesgo."""
    retornos = pd.Series(retornos).dropna()
    if len(retornos) < 20:
        return np.nan
    volatilidad = float(retornos.std() * np.sqrt(DIAS_HABILES_ANIO))
    if not volatilidad:
        return np.nan
    anios = len(retornos) / DIAS_HABILES_ANIO
    retornoAnual = float((1 + retornos).prod() ** (1 / anios) - 1)
    return (retornoAnual - tasaLibre) / volatilidad


def calcularMetricasDescriptivas(historicoFondo, historicoBenchmark=None, tasaLibre=None,
                                 benchmarkComparable=True):
    """
    Indicadores del dashboard descriptivo y de la senal:
    valor actual, retorno anual, volatilidad, Sharpe (total y 12 meses), beta,
    VaR 95%, max drawdown, tendencia (media de 200 dias, retorno 6 meses) y
    comparacion con el benchmark en el periodo comun y en 12 meses.
    """
    tasaLibre = TASA_LIBRE_RIESGO if esNulo(tasaLibre) else float(tasaLibre)
    metricas = {
        "valorActual": np.nan, "retornoAnual": np.nan, "retornoAcumulado": np.nan,
        "volatilidadAnual": np.nan, "sharpeRatio": np.nan, "beta": np.nan,
        "varDiario95": np.nan, "maxDrawdown": np.nan, "caidaActual": np.nan,
        "retorno12m": np.nan, "retorno6m": np.nan, "volatilidad12m": np.nan,
        "sharpe12m": np.nan, "media200": np.nan, "sobreMedia200": None,
        "retornoBenchmark": np.nan, "diferencialBenchmark": np.nan,
        "retornoBenchmark12m": np.nan, "diferencialBenchmark12m": np.nan,
        "benchmarkComparable": bool(benchmarkComparable), "tasaLibre": tasaLibre,
        "observaciones": 0,
    }

    if historicoFondo is None or historicoFondo.empty:
        registrarEvento("No hay historico para calcular metricas.", "ERROR")
        return metricas

    nav = historicoFondo["nav"].dropna()
    retornos = nav.pct_change().dropna()
    metricas["observaciones"] = int(len(retornos))
    metricas["valorActual"] = float(nav.iloc[-1])
    metricas["retornoAcumulado"] = float(nav.iloc[-1] / nav.iloc[0] - 1)

    if len(retornos) >= 2:
        anios = max(len(retornos) / DIAS_HABILES_ANIO, 1e-6)
        metricas["retornoAnual"] = float((nav.iloc[-1] / nav.iloc[0]) ** (1 / anios) - 1)
        metricas["volatilidadAnual"] = float(retornos.std() * np.sqrt(DIAS_HABILES_ANIO))
        if metricas["volatilidadAnual"] > 0:
            metricas["sharpeRatio"] = (metricas["retornoAnual"] - tasaLibre) / metricas["volatilidadAnual"]
        metricas["varDiario95"] = float(np.percentile(retornos, 5))

    metricas["maxDrawdown"] = calcularMaximaCaida(nav)
    metricas["caidaActual"] = float(nav.iloc[-1] / nav.max() - 1)
    metricas["retorno12m"] = retornoEnVentana(nav, DIAS_HABILES_ANIO)
    metricas["retorno6m"] = retornoEnVentana(nav, 126)
    ultimos12 = retornos.tail(DIAS_HABILES_ANIO)
    if len(ultimos12) >= 120:
        metricas["volatilidad12m"] = float(ultimos12.std() * np.sqrt(DIAS_HABILES_ANIO))
        metricas["sharpe12m"] = sharpeAnual(ultimos12, tasaLibre)
    if len(nav) >= 200:
        metricas["media200"] = float(nav.tail(200).mean())
        metricas["sobreMedia200"] = bool(nav.iloc[-1] > metricas["media200"])

    if historicoBenchmark is not None and not historicoBenchmark.empty:
        navB = historicoBenchmark["nav"].dropna()
        comunes = nav.index.intersection(navB.index)
        if len(comunes) > 30:
            navF, navBc = nav.loc[comunes], navB.loc[comunes]
            metricas["beta"] = calcularBeta(navF.pct_change(), navBc.pct_change())
            metricas["retornoBenchmark"] = float(navBc.iloc[-1] / navBc.iloc[0] - 1)
            metricas["diferencialBenchmark"] = float(navF.iloc[-1] / navF.iloc[0] - 1) - metricas["retornoBenchmark"]
            metricas["retornoBenchmark12m"] = retornoEnVentana(navBc, DIAS_HABILES_ANIO)
            retornoF12 = retornoEnVentana(navF, DIAS_HABILES_ANIO)
            if not esNulo(retornoF12) and not esNulo(metricas["retornoBenchmark12m"]):
                metricas["diferencialBenchmark12m"] = retornoF12 - metricas["retornoBenchmark12m"]

    return metricas


# Escala de riesgo: cada componente se lleva a 0 (bajo) - 10 (alto).
# Solo usa medidas de RIESGO (sin Sharpe ni sentimiento, que ya entran
# por separado en la senal y no deben contarse dos veces).
PESOS_RIESGO = {"volatilidad": 0.40, "maxDrawdown": 0.35, "beta": 0.25}
ESCALA_RIESGO = {"volatilidad": 0.35, "maxDrawdown": 0.50, "beta": 1.6}


def clasificarRiesgo(metricas):
    """
    Convierte volatilidad, caida maxima y beta en un puntaje de riesgo de 0 a
    10 y una categoria (Bajo < 4, Moderado < 7, Alto). Los datos faltantes se
    reemplazan por valores neutros explicitos y se informan.
    """
    volatilidad = valorODefecto(metricas.get("volatilidadAnual"), 0.15)
    caida = valorODefecto(metricas.get("maxDrawdown"), -0.15)
    beta = valorODefecto(metricas.get("beta"), 1.0)
    supuestos = [
        nombre for nombre, clave in (("volatilidad", "volatilidadAnual"), ("caída máxima", "maxDrawdown"), ("beta", "beta"))
        if esNulo(metricas.get(clave))
    ]

    componentes = {
        "volatilidad": float(np.clip(volatilidad / ESCALA_RIESGO["volatilidad"] * 10, 0, 10)),
        "maxDrawdown": float(np.clip(abs(caida) / ESCALA_RIESGO["maxDrawdown"] * 10, 0, 10)),
        "beta": float(np.clip(abs(beta) / ESCALA_RIESGO["beta"] * 10, 0, 10)),
    }
    puntaje = sum(componentes[k] * PESOS_RIESGO[k] for k in PESOS_RIESGO)
    categoria = "Bajo" if puntaje < 4 else ("Moderado" if puntaje < 7 else "Alto")

    return {
        "puntaje": round(float(puntaje), 1),
        "categoria": categoria,
        "componentes": {k: round(v, 1) for k, v in componentes.items()},
        "supuestos": supuestos,
    }


def compararConBenchmark(historicoFondo, historicoBenchmark):
    """
    Fondo y benchmark en base 100 desde la PRIMERA FECHA COMUN, para que los
    dos arranquen en el mismo punto aunque sus historicos empiecen distinto.
    """
    if historicoFondo is None or historicoFondo.empty:
        return pd.DataFrame()

    nav = historicoFondo["nav"].dropna()
    if historicoBenchmark is None or historicoBenchmark.empty:
        return pd.DataFrame({"fondo": nav / nav.iloc[0] * 100})

    navB = historicoBenchmark["nav"].dropna()
    comunes = nav.index.intersection(navB.index)
    if len(comunes) < 2:
        return pd.DataFrame({"fondo": nav / nav.iloc[0] * 100})

    nav, navB = nav.loc[comunes], navB.loc[comunes]
    return pd.DataFrame({"fondo": nav / nav.iloc[0] * 100, "benchmark": navB / navB.iloc[0] * 100})


def resumirRentabilidadPorPeriodo(historicoFondo):
    """Calcula la rentabilidad del fondo en 1M, 3M, 6M, 1A y desde el inicio."""
    resumen = {}
    nav = historicoFondo["nav"].dropna() if historicoFondo is not None and not historicoFondo.empty else pd.Series(dtype=float)
    if nav.empty:
        return resumen
    for etiqueta, dias in {"1 mes": 21, "3 meses": 63, "6 meses": 126, "1 año": 252}.items():
        resumen[etiqueta] = retornoEnVentana(nav, dias)
    resumen["Desde inicio"] = float(nav.iloc[-1] / nav.iloc[0] - 1)
    return resumen

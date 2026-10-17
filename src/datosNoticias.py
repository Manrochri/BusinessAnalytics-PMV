"""
datosNoticias.py
Fuentes de datos NO estructurados (texto de prensa), todas gratuitas:

  1. Titulares recientes del fondo (o de su ETF equivalente), de TRES
     fuentes gratuitas y sin clave que se combinan (si una falla, quedan las
     otras), puntuados con VADER (analizador de uso general, de -1 a +1):
       - Yahoo Finance via yfinance (noticias del ticker).
       - Yahoo Finance RSS (feed publico de titulares del ticker).
       - Google News RSS (busqueda por el tema del fondo, p. ej.
         "high-yield bonds", y por el ticker; ultimos 30 dias).
     Alpha Vantage News Sentiment queda como opcion con clave
     (NOTICIAS_FUENTE=alphavantage); su plan gratuito solo entrega lo reciente.
  2. Tono diario de la prensa sobre el tema del fondo (p. ej. "S&P 500"),
     desde GDELT (gratis, sin clave). Da HISTORIA: se puede completar hacia
     atras por ventanas de 3 meses, y es lo que permite que el sentimiento
     entre al modelo predictivo.

Todo se ALINEA A DIAS BURSATILES sin mirar el futuro: un titular publicado
despues del cierre o en fin de semana cuenta para el siguiente dia de
mercado, y el tono diario de GDELT (que incluye todo el dia UTC) se usa a
partir del dia de mercado siguiente.
"""

import html
import re
import time
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import requests

from config import (
    ALPHA_VANTAGE_API_KEY,
    ALPHA_VANTAGE_URL,
    GDELT_PAUSA_SEGUNDOS,
    NOTICIAS_FUENTE,
    NOTICIAS_LIMITE,
    NOTICIAS_MAXIMO_ACUMULADO,
    TEMA_TONO_PRENSA,
)
from src.utilidades import (
    ORIGEN_CACHE,
    ORIGEN_DESCARGA,
    ORIGEN_RESPALDO,
    cacheVigente,
    guardarTabla,
    leerTabla,
    marcarOrigen,
    nombreSeguro,
    registrarEvento,
)

try:  # analizador de sentimiento para los titulares de Yahoo Finance
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    _ANALIZADOR = SentimentIntensityAnalyzer()
except ImportError:  # pragma: no cover
    _ANALIZADOR = None

URL_GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
URL_YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline"
URL_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
# Algunos servicios rechazan peticiones sin un navegador declarado
CABECERAS_RSS = {"User-Agent": "Mozilla/5.0 (FundScope; proyecto academico)", "Accept": "application/rss+xml, application/xml, text/xml"}
# Ventana maxima por consulta de GDELT y minimo de dias de tono para la senal
MESES_POR_CONSULTA_GDELT = 3
MINIMO_DIAS_TONO_SENAL = 120
# Tema de busqueda del tono de prensa por ETF (en ingles, como la prensa que indexa GDELT)
MAPEO_TEMAS_TONO = {
    "VOO": '"S&P 500"', "SPY": '"S&P 500"', "IVV": '"S&P 500"', "VTI": '"stock market"', "ITOT": '"stock market"',
    "QQQ": '"Nasdaq"', "VUG": '"growth stocks"', "VTV": '"value stocks"', "VXUS": '"international stocks"',
    "BND": '"bond market"', "AGG": '"bond market"',
    # Fondos de bonos del catalogo por perfil
    "SGOV": '"Treasury bills"', "SHY": '"Treasury yields"', "VGSH": '"Treasury yields"', "VTIP": '"inflation"',
    "VCSH": '"corporate bonds"', "VCIT": '"corporate bonds"', "IEF": '"Treasury yields"', "MUB": '"municipal bonds"',
    "HYG": '"high-yield bonds"', "JNK": '"high-yield bonds"', "ANGL": '"junk bonds"', "EMB": '"emerging market debt"',
    "TLT": '"Treasury yields"',
}

# Hora de cierre del mercado de EE.UU. (hora de Nueva York)
HORA_CIERRE = 16
# Alpha Vantage publica 'time_published' sin zona horaria; se asume hora de
# Nueva York, que es la referencia del mercado que cubre.
ZONA_MERCADO = "America/New_York"
# Minimo de noticias recientes para que el sentimiento pese en la senal
MINIMO_NOTICIAS_SENAL = 10
DIAS_RECIENTES = 30

# Alpha Vantage NEWS_SENTIMENT indexa noticias por ticker BURSATIL. Los fondos
# mutuos casi nunca tienen cobertura directa, por eso se mapean a su ETF
# equivalente solo para la busqueda de noticias.
MAPEO_TICKERS_NOTICIAS = {
    "VFIAX": "VOO", "VTSAX": "VTI", "VBTLX": "BND", "VGTSX": "VXUS", "VTIAX": "VXUS",
    "VIGAX": "VUG", "VVIAX": "VTV", "FXAIX": "SPY", "FSKAX": "ITOT", "SWPPX": "SPY",
    "SWTSX": "ITOT",
}


def sugerirTickerNoticias(ticker):
    """Ticker para buscar noticias: el ETF equivalente si se conoce, si no el mismo."""
    texto = str(ticker or "").upper()
    return MAPEO_TICKERS_NOTICIAS.get(texto, texto)


def clasificarPuntaje(puntaje):
    """Clasifica un puntaje numerico de sentimiento segun los cortes de Alpha Vantage."""
    try:
        valor = float(puntaje)
    except (TypeError, ValueError):
        return "Neutral"
    if np.isnan(valor):
        return "Neutral"
    if valor <= -0.35:
        return "Muy negativo"
    if valor <= -0.15:
        return "Negativo"
    if valor < 0.15:
        return "Neutral"
    if valor < 0.35:
        return "Positivo"
    return "Muy positivo"


def _leerCacheNoticias(nombreArchivo):
    tabla = leerTabla(nombreArchivo, columnaFecha="fecha")
    if tabla is None or tabla.empty:
        return None
    origen = tabla.attrs.get("origen")
    fecha = tabla.attrs.get("fechaCache")
    tabla = tabla.reset_index()
    if "sentimiento" in tabla.columns:  # caches antiguas usaban la etiqueta general del articulo
        tabla["etiqueta"] = tabla["sentimiento"].map(clasificarPuntaje)
    return marcarOrigen(tabla, origen, fecha)


def _consultarAlphaVantage(ticker, parametrosExtra):
    """
    Una consulta a NEWS_SENTIMENT. Devuelve (tabla, mensajeError): la tabla
    tiene una fila por articulo con el sentimiento DEL TICKER consultado.
    """
    parametros = {"function": "NEWS_SENTIMENT", "tickers": ticker, "sort": "LATEST",
                  "apikey": ALPHA_VANTAGE_API_KEY, **parametrosExtra}
    try:
        respuesta = requests.get(ALPHA_VANTAGE_URL, params=parametros, timeout=30)
        respuesta.raise_for_status()
        contenido = respuesta.json()
    except requests.exceptions.RequestException as error:
        return None, f"Error de red con Alpha Vantage: {error}"
    except ValueError as error:
        return None, f"Respuesta inválida de Alpha Vantage: {error}"
    if "Information" in contenido or "Note" in contenido:
        return None, f"Alpha Vantage limitó la consulta: {contenido.get('Information') or contenido.get('Note')}"

    filas = []
    for articulo in contenido.get("feed", []) or []:
        sentimientoTicker, relevancia = None, 0.0
        for detalle in articulo.get("ticker_sentiment", []) or []:
            if str(detalle.get("ticker", "")).upper() == ticker.upper():
                try:
                    sentimientoTicker = float(detalle.get("ticker_sentiment_score", 0))
                    relevancia = float(detalle.get("relevance_score", 0))
                except (TypeError, ValueError):
                    pass
                break
        try:
            puntaje = sentimientoTicker if sentimientoTicker is not None else float(articulo.get("overall_sentiment_score", 0))
        except (TypeError, ValueError):
            continue
        filas.append({
            "fecha": pd.to_datetime(articulo.get("time_published"), format="%Y%m%dT%H%M%S", errors="coerce"),
            "titulo": articulo.get("title", "Sin titulo"), "fuente": articulo.get("source", "Desconocida"),
            "url": articulo.get("url", ""), "resumen": (articulo.get("summary", "") or "")[:400],
            "sentimiento": puntaje, "etiqueta": clasificarPuntaje(puntaje), "relevancia": relevancia,
        })
    tabla = pd.DataFrame(filas)
    if tabla.empty:
        return tabla, None
    return tabla.dropna(subset=["fecha"]), None


def _fusionarYGuardar(nuevas, nombreArchivo):
    """
    Une las noticias nuevas con las ya guardadas (sin duplicados por URL o por
    titulo+fecha) y guarda el conjunto. Asi la historia CRECE con cada
    actualizacion en lugar de reemplazarse.
    """
    anteriores = _leerCacheNoticias(nombreArchivo)
    partes = [t for t in (nuevas, anteriores) if t is not None and not t.empty]
    if not partes:
        return pd.DataFrame(), 0
    tabla = pd.concat(partes, ignore_index=True)
    tabla["fecha"] = pd.to_datetime(tabla["fecha"], errors="coerce")
    tabla["claveNoticia"] = tabla["url"].fillna("").astype(str)
    sinUrl = tabla["claveNoticia"].str.len() < 8
    tabla.loc[sinUrl, "claveNoticia"] = tabla.loc[sinUrl, "titulo"].astype(str) + tabla.loc[sinUrl, "fecha"].astype(str)
    antes = 0 if anteriores is None else len(anteriores)
    # La misma nota puede llegar por varias fuentes con distinta URL: tambien se deduplica por titulo
    tabla["claveTitulo"] = tabla["titulo"].astype(str).str.lower().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
    tabla = (tabla.dropna(subset=["fecha"]).drop_duplicates("claveNoticia").drop_duplicates("claveTitulo")
             .drop(columns=["claveNoticia", "claveTitulo"])
             .sort_values("fecha", ascending=False).head(NOTICIAS_MAXIMO_ACUMULADO).reset_index(drop=True))
    guardarTabla(tabla.set_index("fecha"), nombreArchivo)
    return tabla, len(tabla) - antes


def puntuarTexto(texto):
    """Sentimiento de un texto de -1 a +1 (VADER, 'compound'); None si VADER no esta instalado."""
    if _ANALIZADOR is None or not texto:
        return None
    return float(_ANALIZADOR.polarity_scores(str(texto))["compound"])


def _campo(diccionario, *ruta):
    actual = diccionario
    for clave in ruta:
        if not isinstance(actual, dict):
            return None
        actual = actual.get(clave)
    return actual


def _fechaNuevaYork(valor):
    """Fecha de publicacion (epoch o ISO en UTC) en hora de Nueva York, sin zona."""
    if valor is None:
        return pd.NaT
    fecha = pd.to_datetime(valor, unit="s", utc=True) if isinstance(valor, (int, float)) else pd.to_datetime(valor, utc=True, errors="coerce")
    if pd.isna(fecha):
        return pd.NaT
    return fecha.tz_convert(ZONA_MERCADO).tz_localize(None)


def parsearNoticiasYahoo(items):
    """
    Convierte la lista de noticias de yfinance en la tabla estandar. Soporta
    el formato actual ({'content': {'title', 'summary', 'pubDate', 'provider',
    'canonicalUrl'}}) y el anterior ({'title', 'publisher', 'link',
    'providerPublishTime'}).
    """
    filas = []
    for item in items or []:
        contenido = item.get("content") if isinstance(item.get("content"), dict) else item
        titulo = contenido.get("title")
        if not titulo:
            continue
        resumen = contenido.get("summary") or contenido.get("description") or ""
        fecha = contenido.get("pubDate") or contenido.get("displayTime") or contenido.get("providerPublishTime")
        url = (_campo(contenido, "canonicalUrl", "url") or _campo(contenido, "clickThroughUrl", "url")
               or contenido.get("link") or "")
        puntaje = puntuarTexto(f"{titulo}. {resumen}")
        filas.append({
            "fecha": _fechaNuevaYork(fecha), "titulo": titulo,
            "fuente": _campo(contenido, "provider", "displayName") or contenido.get("publisher") or "Yahoo Finance",
            "url": url, "resumen": str(resumen)[:400], "sentimiento": puntaje,
            "etiqueta": clasificarPuntaje(puntaje) if puntaje is not None else "Sin puntaje",
            "relevancia": 1.0, "origenNoticia": "Yahoo Finance",
        })
    tabla = pd.DataFrame(filas)
    return tabla.dropna(subset=["fecha"]) if not tabla.empty else tabla


def _consultarYahoo(tickers, cantidad):
    """Titulares de Yahoo Finance de uno o mas tickers. Devuelve (tabla, mensajeError)."""
    from src.datosEstructurados import _yfTicker

    partes, errores = [], []
    for ticker in dict.fromkeys(t for t in tickers if t):
        try:
            activo = _yfTicker(ticker)
            items = activo.get_news(count=cantidad) if hasattr(activo, "get_news") else activo.news
            partes.append(parsearNoticiasYahoo(items))
        except Exception as error:  # red, cambios del formato de Yahoo
            errores.append(f"{ticker}: {error}")
    tabla = pd.concat([p for p in partes if not p.empty], ignore_index=True) if any(not p.empty for p in partes) else pd.DataFrame()
    if tabla.empty:
        return None, "Yahoo Finance no devolvió noticias" + (f" ({'; '.join(errores)})" if errores else ".")
    return tabla, None


def _limpiarHtml(texto):
    """Quita etiquetas y entidades HTML de un resumen de RSS."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(texto or "")))).strip()


def parsearRss(contenido, origen):
    """
    Feed RSS 2.0 (Yahoo Finance o Google News) -> tabla estandar de noticias.
    En Google News el titulo trae " - Medio" al final y el medio va en <source>.
    Lanza ValueError si el contenido no es un RSS valido.
    """
    try:
        raiz = ET.fromstring(contenido)
    except ET.ParseError as error:
        raise ValueError(f"respuesta que no es RSS ({error})") from error
    filas = []
    for item in raiz.iter("item"):
        titulo = _limpiarHtml(item.findtext("title"))
        if not titulo:
            continue
        nodoFuente = item.find("source")
        fuente = (nodoFuente.text or "").strip() if nodoFuente is not None else ""
        if fuente and titulo.endswith(f" - {fuente}"):
            titulo = titulo[: -len(fuente) - 3].strip()
        resumen = _limpiarHtml(item.findtext("description"))
        if resumen.startswith(titulo):  # Google News repite el titulo en la descripcion
            resumen = ""
        puntaje = puntuarTexto(f"{titulo}. {resumen}")
        filas.append({
            "fecha": _fechaNuevaYork(item.findtext("pubDate")), "titulo": titulo,
            "fuente": fuente or origen, "url": (item.findtext("link") or "").strip(), "resumen": resumen[:400],
            "sentimiento": puntaje, "etiqueta": clasificarPuntaje(puntaje) if puntaje is not None else "Sin puntaje",
            "relevancia": 1.0, "origenNoticia": origen,
        })
    tabla = pd.DataFrame(filas)
    return tabla.dropna(subset=["fecha"]) if not tabla.empty else tabla


def _consultarRss(url, parametros, origen):
    """Descarga y lee un feed RSS. Devuelve (tabla, mensajeError)."""
    try:
        respuesta = requests.get(url, params=parametros, headers=CABECERAS_RSS, timeout=20)
        respuesta.raise_for_status()
        tabla = parsearRss(respuesta.content, origen)
    except requests.exceptions.HTTPError as error:
        codigo = error.response.status_code if error.response is not None else "?"
        return None, f"{origen}: respondió con error HTTP {codigo}" + (" (demasiadas consultas; espera unos minutos)." if codigo == 429 else ".")
    except requests.exceptions.RequestException as error:
        return None, f"{origen}: sin conexión ({type(error).__name__})."
    except ValueError as error:
        return None, f"{origen}: {error}."
    if tabla.empty:
        return None, f"{origen}: sin titulares."
    return tabla, None


def _consultarYahooRss(tickers):
    """Titulares del feed RSS publico de Yahoo Finance (sin clave)."""
    partes, errores = [], []
    for ticker in dict.fromkeys(t for t in tickers if t):
        tabla, error = _consultarRss(URL_YAHOO_RSS, {"s": ticker, "region": "US", "lang": "en-US"}, "Yahoo Finance RSS")
        if tabla is not None:
            partes.append(tabla)
        elif error:
            errores.append(error)
    if not partes:
        return None, " ".join(dict.fromkeys(errores)) or "Yahoo Finance RSS: sin titulares."
    return pd.concat(partes, ignore_index=True), None


def consultaGoogleNews(tema, tickers):
    """Busqueda de Google News: el tema del fondo o sus tickers, ultimos 30 dias."""
    partes = [str(tema).strip()] if tema else []
    partes += [f'"{t} ETF"' for t in dict.fromkeys(t for t in tickers if t)]
    return " OR ".join(partes) + " when:30d"


def _consultarGoogleNews(tema, tickers, cantidad):
    """Titulares de Google News RSS (sin clave). Devuelve (tabla, mensajeError)."""
    parametros = {"q": consultaGoogleNews(tema, tickers), "hl": "en-US", "gl": "US", "ceid": "US:en"}
    tabla, error = _consultarRss(URL_GOOGLE_NEWS_RSS, parametros, "Google News")
    if tabla is not None:
        tabla = tabla.sort_values("fecha", ascending=False).head(max(cantidad, 50))
    return tabla, error


def _alphaVantageConClave():
    return bool(ALPHA_VANTAGE_API_KEY) and ALPHA_VANTAGE_API_KEY not in ("demo", "tu_clave_aqui")


def descargarNoticias(ticker, limite=None, temas=None, usarCache=True, tickersExtra=(), tema=None):
    """
    Descarga los titulares mas recientes de todas las fuentes gratuitas
    (Yahoo Finance, su feed RSS y Google News por el tema del fondo), los
    combina sin duplicados y los SUMA a los ya guardados. Alpha Vantage se usa
    primero si NOTICIAS_FUENTE=alphavantage, o como ultimo respaldo si tiene clave. Devuelve todas las noticias acumuladas: fecha,
    titulo, fuente, url, resumen, sentimiento, etiqueta y relevancia.
    """
    nombreArchivo = f"noticias_{nombreSeguro(ticker)}.csv"
    if usarCache and cacheVigente(nombreArchivo):
        tabla = _leerCacheNoticias(nombreArchivo)
        if tabla is not None:
            registrarEvento(f"Noticias de {ticker} leidas desde cache.")
            return tabla

    cantidad = limite or NOTICIAS_LIMITE
    tickers = [ticker, *tickersExtra]
    consultas = [
        ("Yahoo Finance", lambda: _consultarYahoo(tickers, cantidad)),
        ("Yahoo Finance RSS", lambda: _consultarYahooRss(tickers)),
        ("Google News", lambda: _consultarGoogleNews(tema, tickers, cantidad)),
    ]
    if NOTICIAS_FUENTE == "alphavantage":
        consultas.insert(0, ("Alpha Vantage", lambda: _consultarAlphaVantageEtiquetado(ticker, cantidad, temas)))

    partes, errores, porFuente = [], [], {}
    for nombre, consultar in consultas:
        try:
            nuevas, error = consultar()
        except Exception as falla:  # una fuente rota no debe impedir usar las demas
            nuevas, error = None, f"{nombre}: {falla}"
        if nuevas is None or nuevas.empty:
            errores.append(error or f"{nombre}: sin titulares.")
            continue
        partes.append(nuevas)
        porFuente[nombre] = len(nuevas)
    if not partes and NOTICIAS_FUENTE != "alphavantage" and _alphaVantageConClave():
        nuevas, error = _consultarAlphaVantageEtiquetado(ticker, cantidad, temas)
        if nuevas is not None and not nuevas.empty:
            partes.append(nuevas)
            porFuente["Alpha Vantage"] = len(nuevas)
        else:
            errores.append(error or "Alpha Vantage: sin titulares.")

    if partes:
        tabla, agregadas = _fusionarYGuardar(pd.concat(partes, ignore_index=True), nombreArchivo)
        detalle = ", ".join(f"{k} {v}" for k, v in porFuente.items())
        registrarEvento(f"Noticias de {ticker} ({detalle}): {agregadas} nuevas, {len(tabla)} acumuladas.")
        if errores:
            registrarEvento("Fuentes de noticias sin respuesta: " + " ".join(errores), "WARN")
        tabla = marcarOrigen(tabla, ORIGEN_DESCARGA)
        tabla.attrs.update(agregadas=agregadas, fuentes=porFuente, motivo=" ".join(errores))
        return tabla

    motivo = " ".join(errores)
    registrarEvento(motivo, "WARN")
    tabla = _leerCacheNoticias(nombreArchivo)
    if tabla is None:
        vacio = pd.DataFrame()
        vacio.attrs["motivo"] = motivo
        return vacio
    tabla = marcarOrigen(tabla, ORIGEN_RESPALDO, tabla.attrs.get("fechaCache"))
    tabla.attrs["motivo"] = motivo
    return tabla


def _consultarAlphaVantageEtiquetado(ticker, cantidad, temas):
    """Alpha Vantage (solo con clave), con la columna de origen."""
    if not _alphaVantageConClave():
        return None, "Alpha Vantage: sin clave configurada."
    nuevas, error = _consultarAlphaVantage(ticker, {"limit": cantidad, **({"topics": temas} if temas else {})})
    if nuevas is not None and not nuevas.empty:
        nuevas["origenNoticia"] = "Alpha Vantage"
    return nuevas, error


# ---------------------------------------------------------------------------
# Tono diario de la prensa (GDELT)
# ---------------------------------------------------------------------------
def temaTonoPrensa(ticker, tickerNoticias=None):
    """Tema de busqueda en GDELT: el del .env, el del mapeo por ETF, o el ticker entre comillas."""
    if TEMA_TONO_PRENSA:
        return TEMA_TONO_PRENSA
    for candidato in (tickerNoticias, ticker):
        if candidato and str(candidato).upper() in MAPEO_TEMAS_TONO:
            return MAPEO_TEMAS_TONO[str(candidato).upper()]
    return f'"{tickerNoticias or ticker}"'


def _archivoTono(tema):
    return f"tono_{re.sub(r'[^A-Za-z0-9]+', '_', tema).strip('_')}.csv"


def parsearTonoGdelt(contenido):
    """JSON de mode=timelinetone -> tabla (fecha, tono). Lanza ValueError si no es la respuesta esperada."""
    serie = (contenido.get("timeline") or [{}])[0].get("data") or []
    tabla = pd.DataFrame([{"fecha": pd.to_datetime(d.get("date"), errors="coerce", utc=True), "tono": d.get("value")} for d in serie])
    if tabla.empty:
        return pd.DataFrame(columns=["fecha", "tono"])
    tabla["fecha"] = tabla["fecha"].dt.tz_localize(None).dt.normalize()
    tabla["tono"] = pd.to_numeric(tabla["tono"], errors="coerce")
    return tabla.dropna()


def _consultarGdelt(tema, inicio, fin, reintentos=1):
    """Tono diario de 'tema' entre inicio y fin (<= 3 meses). Devuelve (tabla, mensajeError)."""
    parametros = {
        "query": f"{tema} sourcelang:english", "mode": "timelinetone", "format": "json",
        "startdatetime": pd.Timestamp(inicio).strftime("%Y%m%d%H%M%S"),
        "enddatetime": pd.Timestamp(fin).strftime("%Y%m%d%H%M%S"),
    }
    for intento in range(reintentos + 1):
        try:
            respuesta = requests.get(URL_GDELT, params=parametros, timeout=60)
            respuesta.raise_for_status()
            if "json" not in respuesta.headers.get("content-type", "") and not respuesta.text.strip().startswith("{"):
                mensaje = respuesta.text.strip()[:200]
                if "limit" in mensaje.lower() and intento < reintentos:  # pidio esperar entre consultas
                    time.sleep(GDELT_PAUSA_SEGUNDOS)
                    continue
                return None, f"GDELT: {mensaje}"
            return parsearTonoGdelt(respuesta.json()), None
        except (requests.exceptions.RequestException, ValueError) as error:
            if intento < reintentos:
                time.sleep(GDELT_PAUSA_SEGUNDOS)
                continue
            return None, f"GDELT no respondió: {error}"
    return None, "GDELT no respondió."


def _leerTono(tema):
    tabla = leerTabla(_archivoTono(tema), columnaFecha="fecha")
    return tabla if tabla is not None and not tabla.empty else None


def _fusionarTono(nuevas, tema):
    anteriores = _leerTono(tema)
    partes = [nuevas.set_index("fecha")[["tono"]]] if nuevas is not None and not nuevas.empty else []
    if anteriores is not None:
        partes.append(anteriores[["tono"]])
    if not partes:
        return pd.DataFrame(columns=["tono"])
    tabla = pd.concat(partes)
    tabla = tabla[~tabla.index.duplicated(keep="first")].sort_index()  # gana lo nuevo: un dia reciente pudo bajarse incompleto
    tabla.index.name = "fecha"
    guardarTabla(tabla, _archivoTono(tema))
    return tabla


def descargarTonoPrensa(tema, usarCache=True):
    """
    Serie diaria del tono de la prensa sobre 'tema' (GDELT). Descarga los
    ultimos 3 meses y los SUMA a la historia guardada. Devuelve un DataFrame
    con indice fecha y columna 'tono' (promedio de los articulos del dia;
    GDELT lo mide de -100 a +100, en la practica entre -10 y +10).
    """
    archivo = _archivoTono(tema)
    if usarCache and cacheVigente(archivo):
        guardado = _leerTono(tema)
        if guardado is not None:
            return marcarOrigen(guardado, ORIGEN_CACHE, guardado.attrs.get("fechaCache"))
    fin = pd.Timestamp.now().normalize()
    nuevas, error = _consultarGdelt(tema, fin - pd.DateOffset(months=MESES_POR_CONSULTA_GDELT), fin)
    if error:
        registrarEvento(error, "WARN")
        guardado = _leerTono(tema)
        if guardado is None:
            vacio = pd.DataFrame(columns=["tono"])
            vacio.attrs["motivo"] = error
            return vacio
        return marcarOrigen(guardado, ORIGEN_RESPALDO, guardado.attrs.get("fechaCache"))
    return marcarOrigen(_fusionarTono(nuevas, tema), ORIGEN_DESCARGA)


def completarHistoriaTono(tema, meses=24, progreso=None):
    """
    Completa hacia atras la historia del tono de prensa, en ventanas de 3
    meses (una consulta a GDELT cada ~5 s, como pide GDELT). 'progreso' es
    una funcion opcional (fraccion, texto) para mostrar el avance.
    Devuelve {'consultas', 'diasNuevos', 'total', 'desde', 'mensaje'}.
    """
    guardado = _leerTono(tema)
    antes = 0 if guardado is None else len(guardado)
    fin = guardado.index.min() if guardado is not None else pd.Timestamp.now().normalize()
    ventanas = int(np.ceil(meses / MESES_POR_CONSULTA_GDELT))
    consultas, mensaje, vacias = 0, "", 0
    for numero in range(ventanas):
        inicio = fin - pd.DateOffset(months=MESES_POR_CONSULTA_GDELT)
        if progreso:
            progreso(numero / ventanas, f"Tono de prensa {inicio:%m/%Y} – {fin:%m/%Y}")
        if consultas:
            time.sleep(GDELT_PAUSA_SEGUNDOS)
        nuevas, error = _consultarGdelt(tema, inicio, fin)
        consultas += 1
        if error:
            mensaje = error
            break
        if nuevas is None or nuevas.empty:
            vacias += 1
            if vacias >= 2:
                mensaje = f"GDELT no tiene tono anterior a {fin:%m/%Y} para este tema."
                break
        else:
            vacias = 0
            _fusionarTono(nuevas, tema)
        fin = inicio
    if progreso:
        progreso(1.0, "Listo")
    total = _leerTono(tema)
    return {
        "consultas": consultas, "diasNuevos": (0 if total is None else len(total)) - antes,
        "total": 0 if total is None else len(total), "desde": None if total is None else total.index.min(),
        "mensaje": mensaje,
    }


def asignarDiaBursatil(noticias, indiceBursatil, horaCierre=HORA_CIERRE):
    """
    Agrega la columna 'diaBursatil': el primer dia de mercado en que la noticia
    ya pudo influir en el precio de cierre. Antes del cierre -> ese mismo dia
    (si es habil); despues del cierre o en fin de semana/feriado -> el
    siguiente dia habil. Las noticias posteriores al ultimo dia del historico
    quedan con NaT (no se usan en el modelo, si en el resumen).
    """
    if noticias is None or noticias.empty:
        return noticias
    tabla = noticias.copy()
    fechas = pd.to_datetime(tabla["fecha"], errors="coerce")
    efectiva = fechas.dt.normalize() + pd.to_timedelta((fechas.dt.hour >= horaCierre).astype(int), unit="D")
    dias = pd.DatetimeIndex(pd.to_datetime(indiceBursatil)).normalize().sort_values()
    posiciones = dias.searchsorted(efectiva.values, side="left")
    tabla["diaBursatil"] = [dias[p] if p < len(dias) else pd.NaT for p in posiciones]
    return tabla


def alinearTonoADiasBursatiles(serieTono, indiceBursatil):
    """
    Tono diario de GDELT -> dia bursatil en que ya se conoce: el dia de mercado
    SIGUIENTE al dia calendario del tono (el promedio incluye articulos
    publicados despues del cierre). Varios dias calendario (p. ej. fin de
    semana) se promedian en el mismo dia de mercado.
    """
    if serieTono is None or serieTono.empty or indiceBursatil is None or not len(indiceBursatil):
        return pd.DataFrame()
    dias = pd.DatetimeIndex(pd.to_datetime(indiceBursatil)).normalize().sort_values()
    fechas = pd.DatetimeIndex(serieTono.index).normalize() + pd.Timedelta(days=1)
    posiciones = dias.searchsorted(fechas.values, side="left")
    tabla = pd.DataFrame({"tono": serieTono["tono"].to_numpy()}, index=serieTono.index)
    tabla["dia"] = [dias[p] if p < len(dias) else pd.NaT for p in posiciones]
    tabla = tabla.dropna(subset=["dia"])
    agrupado = tabla.groupby("dia").agg(sentimientoDiario=("tono", "mean"), cantidadNoticias=("tono", "size"))
    agrupado.index.name = "Date"
    return agrupado


def construirSerieSentimiento(noticias, indiceBursatil=None, serieTono=None, ponderarPorRelevancia=True):
    """
    Serie diaria de sentimiento alineada a dias bursatiles.
      - Si hay tono de prensa (GDELT): sentimientoDiario = tono del dia
        anterior y cantidadNoticias = dias calendario con dato.
      - Si no: promedio de los titulares de cada dia de mercado.
    Devuelve: sentimientoDiario, cantidadNoticias, mediaMovil3d; attrs['fuente'].
    """
    if serieTono is not None and not serieTono.empty and indiceBursatil is not None:
        serie = alinearTonoADiasBursatiles(serieTono, indiceBursatil)
        if not serie.empty:
            serie["mediaMovil3d"] = serie["sentimientoDiario"].rolling(3, min_periods=1).mean()
            serie.attrs["fuente"] = "Tono de prensa (GDELT)"
            return serie.sort_index()

    if noticias is None or noticias.empty:
        return pd.DataFrame()
    tabla = noticias.copy()
    tabla["fecha"] = pd.to_datetime(tabla["fecha"], errors="coerce")
    tabla = tabla.dropna(subset=["fecha", "sentimiento"])
    if indiceBursatil is not None and len(indiceBursatil):
        tabla = asignarDiaBursatil(tabla, indiceBursatil).dropna(subset=["diaBursatil"])
        tabla["dia"] = tabla["diaBursatil"]
    else:
        tabla["dia"] = tabla["fecha"].dt.normalize()
    if tabla.empty:
        return pd.DataFrame()

    tabla["peso"] = tabla["relevancia"].fillna(0).clip(lower=0.01) if ponderarPorRelevancia else 1.0
    tabla["ponderado"] = tabla["sentimiento"] * tabla["peso"]
    agrupado = tabla.groupby("dia").agg(ponderado=("ponderado", "sum"), peso=("peso", "sum"),
                                        cantidadNoticias=("sentimiento", "size"))
    serie = pd.DataFrame({"sentimientoDiario": agrupado["ponderado"] / agrupado["peso"],
                          "cantidadNoticias": agrupado["cantidadNoticias"]})
    serie["mediaMovil3d"] = serie["sentimientoDiario"].rolling(3, min_periods=1).mean()
    serie.index.name = "Date"
    serie.attrs["fuente"] = "Titulares"
    return serie.sort_index()


def resumirSentimiento(noticias, fechaReferencia=None, serieTono=None):
    """
    Resumen del sentimiento hasta fechaReferencia.

    Titulares: promedio, cantidad recientes (30 dias), positivas/negativas.
    Tono de prensa: promedio de 30 dias y su desviacion respecto al ultimo
    anio en desviaciones estandar (zTono). El tono de GDELT suele ser negativo
    en promedio, por eso se compara contra su propia historia y no contra 0.

    'fuenteSenal' dice que participa en la senal: "tono" (con >= 120 dias de
    tono), "titulares" (con >= 10 titulares recientes con puntaje) o None.
    """
    resumen = {
        "promedio": 0.0, "promedioReciente": 0.0, "categoria": "Neutral", "totalNoticias": 0, "recientes": 0,
        "suficiente": False, "positivas": 0, "neutrales": 0, "negativas": 0, "fuentePrincipal": "No disponible",
        "tonoReciente": np.nan, "tonoAnual": np.nan, "zTono": np.nan, "diasTono": 0, "fuenteSenal": None,
    }
    referencia = pd.Timestamp(fechaReferencia) if fechaReferencia is not None else None

    if noticias is not None and not noticias.empty:
        tabla = noticias.copy()
        fechas = pd.to_datetime(tabla["fecha"], errors="coerce")
        if referencia is None:
            referencia = fechas.max()
        conPuntaje = tabla.loc[tabla["sentimiento"].notna()]
        recientes = conPuntaje.loc[pd.to_datetime(conPuntaje["fecha"]) >= referencia - pd.Timedelta(days=DIAS_RECIENTES)]
        resumen["totalNoticias"] = int(len(tabla))
        if len(conPuntaje):
            resumen["promedio"] = float(conPuntaje["sentimiento"].mean())
            resumen["positivas"] = int((conPuntaje["sentimiento"] >= 0.15).sum())
            resumen["negativas"] = int((conPuntaje["sentimiento"] <= -0.15).sum())
        resumen["recientes"] = int(len(recientes))
        resumen["promedioReciente"] = float(recientes["sentimiento"].mean()) if len(recientes) else 0.0
        resumen["suficiente"] = resumen["recientes"] >= MINIMO_NOTICIAS_SENAL
        resumen["categoria"] = clasificarPuntaje(resumen["promedio"])
        resumen["neutrales"] = int(len(conPuntaje)) - resumen["positivas"] - resumen["negativas"]
        modo = tabla["fuente"].mode()
        resumen["fuentePrincipal"] = str(modo.iloc[0]) if len(modo) else "No disponible"
        if resumen["suficiente"]:
            resumen["fuenteSenal"] = "titulares"

    if serieTono is not None and not serieTono.empty:
        tono = serieTono["tono"].dropna()
        if referencia is not None:
            tono = tono.loc[tono.index < pd.Timestamp(referencia).normalize()]  # solo dias ya cerrados
        anio = tono.loc[tono.index >= (tono.index.max() - pd.Timedelta(days=365))] if len(tono) else tono
        resumen["diasTono"] = int(len(tono))
        if len(anio) >= 30:
            medias30 = anio.rolling(30, min_periods=20).mean().dropna()
            resumen["tonoReciente"] = float(anio.tail(30).mean())
            resumen["tonoAnual"] = float(anio.mean())
            if len(medias30) >= 20 and medias30.std() > 0:
                resumen["zTono"] = float((resumen["tonoReciente"] - medias30.mean()) / medias30.std())
        if resumen["diasTono"] >= MINIMO_DIAS_TONO_SENAL and not np.isnan(resumen["zTono"]):
            resumen["fuenteSenal"] = "tono"
            resumen["suficiente"] = True
    return resumen


def obtenerTitularesDestacados(noticias, cantidad=8):
    """Los titulares mas recientes (primero los de mayor relevancia el mismo dia)."""
    if noticias is None or noticias.empty:
        return pd.DataFrame()
    tabla = noticias.copy()
    tabla["fecha"] = pd.to_datetime(tabla["fecha"], errors="coerce")
    tabla["dia"] = tabla["fecha"].dt.normalize()
    tabla["prioridad"] = tabla["relevancia"].fillna(0) + tabla["sentimiento"].abs().fillna(0)
    columnas = ["fecha", "titulo", "fuente", "sentimiento", "etiqueta", "url"]
    return tabla.sort_values(["dia", "prioridad"], ascending=False).head(cantidad)[columnas].reset_index(drop=True)
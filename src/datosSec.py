"""
datosSec.py
Cartera BONO POR BONO de cada fondo, desde el formulario N-PORT de la SEC.

Todo fondo registrado en EE.UU. (fondos mutuos y ETF de fideicomisos abiertos:
iShares, Vanguard, SPDR, VanEck...) reporta su cartera completa en el
formulario N-PORT: emisor, CUSIP/ISIN, nominal, valor de mercado, % del
fondo, tipo de emisor, pais, vencimiento, cupon y si esta en impago.
El fondo mutuo y el ETF de una misma serie (p. ej. VBTLX y BND) comparten
cartera, porque el N-PORT se presenta por serie.

Flujo:
  1. ticker -> serie (company_tickers_mf.json de la SEC)
  2. serie  -> ultimo NPORT-P (browse-edgar con el ID de serie)
  3. NPORT-P -> primary_doc.xml -> tabla de posiciones

Las carteras publicas tienen un rezago de ~60 dias tras el cierre del
trimestre; la fecha del reporte se muestra siempre en la interfaz.
"""

import re
import xml.etree.ElementTree as ET
from io import BytesIO

import pandas as pd
import requests

from config import NPORT_CACHE_DIAS, SEC_USER_AGENT
from src.utilidades import (
    ORIGEN_CACHE,
    ORIGEN_DESCARGA,
    ORIGEN_RESPALDO,
    cacheVigente,
    guardarJson,
    guardarTabla,
    leerJson,
    leerTabla,
    nombreSeguro,
    registrarEvento,
)

URL_TICKERS_FONDOS = "https://www.sec.gov/files/company_tickers_mf.json"
URL_BUSQUEDA_EDGAR = "https://www.sec.gov/cgi-bin/browse-edgar"
ARCHIVO_TICKERS = "sec_company_tickers_mf.json"

# Tipos de emisor del N-PORT (issuerCat) en espanol
TIPOS_EMISOR = {
    "UST": "Tesoro de EE.UU.",
    "USGA": "Agencia del gobierno de EE.UU.",
    "USGSE": "Agencia patrocinada (GSE)",
    "MUN": "Municipal",
    "CORP": "Corporativo",
    "NUSS": "Soberano no estadounidense",
    "RF": "Fondo registrado",
    "PF": "Fondo privado",
    "OTHER": "Otro",
}
CATEGORIAS_ACTIVO = {
    "DBT": "Bono",
    "ABS-MBS": "Hipotecario (MBS)",
    "ABS-APCP": "Titulizado (papel comercial)",
    "ABS-CBDO": "Titulizado (CDO/CBO)",
    "ABS-O": "Titulizado (otros)",
    "STIV": "Inversión de corto plazo",
    "LON": "Préstamo",
}


class ErrorSec(RuntimeError):
    """Error al consultar la SEC (sin red, serie no encontrada, formato inesperado)."""


def _get(url, params=None, timeout=90):
    """GET con la identificacion que exige la SEC."""
    respuesta = requests.get(
        url, params=params, timeout=timeout,
        headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
    )
    respuesta.raise_for_status()
    return respuesta


# ---------------------------------------------------------------------------
# 1. ticker -> serie
# ---------------------------------------------------------------------------
def _tablaTickers(usarCache=True):
    if usarCache and cacheVigente(ARCHIVO_TICKERS, horas=24 * 30):
        datos = leerJson(ARCHIVO_TICKERS)
        if datos and "data" in datos:
            return datos
    datos = _get(URL_TICKERS_FONDOS).json()
    guardarJson(datos, ARCHIVO_TICKERS)
    return datos


def resolverSerie(ticker, usarCache=True):
    """Devuelve {'cik','serie','clase'} del ticker (fondo mutuo o ETF), o lanza ErrorSec."""
    try:
        datos = _tablaTickers(usarCache)
    except requests.exceptions.RequestException as error:
        datos = leerJson(ARCHIVO_TICKERS)
        if not datos:
            raise ErrorSec(f"No se pudo descargar la lista de fondos de la SEC: {error}") from error
    campos = datos.get("fields", ["cik", "seriesId", "classId", "symbol"])
    posicion = {c: i for i, c in enumerate(campos)}
    for fila in datos.get("data", []):
        if str(fila[posicion["symbol"]]).upper() == ticker.upper():
            return {"cik": fila[posicion["cik"]], "serie": fila[posicion["seriesId"]], "clase": fila[posicion["classId"]]}
    raise ErrorSec(f"La SEC no lista el ticker {ticker} entre los fondos registrados.")


def _resolverConRespaldo(ticker, usarCache=True):
    """
    Busca la serie por el ticker del ETF y, si la SEC no lo lista, por su fondo
    mutuo equivalente del catalogo (en Vanguard, ETF y fondo mutuo son clases
    de la MISMA serie y comparten cartera).
    """
    try:
        return resolverSerie(ticker, usarCache)
    except ErrorSec:
        from src.catalogoBonos import buscarBono

        equivalente = (buscarBono(ticker) or {}).get("fondoMutuo")
        if not equivalente:
            raise
        registrarEvento(f"{ticker} no figura en la SEC; se usa la serie de {equivalente}.", "WARN")
        return resolverSerie(equivalente, usarCache)


# ---------------------------------------------------------------------------
# 2. serie -> ultimo NPORT-P
# ---------------------------------------------------------------------------
def listarReportesNport(serie, cantidad=8):
    """Reportes NPORT-P de la serie (mas reciente primero): [{'fecha','url'}]."""
    respuesta = _get(URL_BUSQUEDA_EDGAR, params={
        "action": "getcompany", "CIK": serie, "type": "NPORT-P", "dateb": "", "owner": "include",
        "count": cantidad, "output": "atom",
    })
    texto = respuesta.text
    reportes = []
    for entrada in re.findall(r"<entry>(.*?)</entry>", texto, flags=re.DOTALL):
        tipo = re.search(r"<filing-type>(.*?)</filing-type>", entrada)
        fecha = re.search(r"<filing-date>(.*?)</filing-date>", entrada)
        enlace = re.search(r"<filing-href>(.*?)</filing-href>", entrada)
        if tipo and enlace and tipo.group(1).strip().startswith("NPORT-P"):
            reportes.append({"fecha": fecha.group(1).strip() if fecha else "", "url": enlace.group(1).strip()})
    return sorted(reportes, key=lambda r: r["fecha"], reverse=True)


def urlDocumentoPrincipal(urlIndice):
    """De la pagina indice del filing a su primary_doc.xml (misma carpeta)."""
    return urlIndice.rsplit("/", 1)[0] + "/primary_doc.xml"


# ---------------------------------------------------------------------------
# 3. NPORT-P -> tabla
# ---------------------------------------------------------------------------
def _local(etiqueta):
    return etiqueta.rsplit("}", 1)[-1]


def _hijo(elemento, nombre):
    for hijo in elemento:
        if _local(hijo.tag) == nombre:
            return hijo
    return None


def _texto(elemento, nombre):
    hijo = _hijo(elemento, nombre) if elemento is not None else None
    if hijo is None:
        return None
    valor = (hijo.text or "").strip() or hijo.attrib.get("value")
    return valor or None


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def parsearNport(contenido):
    """
    Convierte el XML de un NPORT-P en (tabla, meta). La tabla tiene una fila
    por posicion; las columnas de deuda quedan vacias en las que no son bonos.
    """
    fuente = BytesIO(contenido if isinstance(contenido, bytes) else contenido.encode("utf-8"))
    meta, filas = {}, []
    for _evento, elemento in ET.iterparse(fuente, events=("end",)):
        nombre = _local(elemento.tag)
        if nombre == "genInfo":
            meta.update({
                "registrante": _texto(elemento, "regName"), "serie": _texto(elemento, "seriesId"),
                "nombreSerie": _texto(elemento, "seriesName"),
                # repPdEnd = cierre del anio fiscal del fondo; repPdDate = fecha de las posiciones
                "finPeriodo": _texto(elemento, "repPdEnd"), "fechaReporte": _texto(elemento, "repPdDate"),
            })
        elif nombre == "fundInfo":
            meta["activosNetos"] = _numero(_texto(elemento, "netAssets"))
        elif nombre == "invstOrSec":
            deuda = _hijo(elemento, "debtSec")
            identificadores = _hijo(elemento, "identifiers")
            isin = None
            if identificadores is not None:
                nodoIsin = _hijo(identificadores, "isin")
                isin = nodoIsin.attrib.get("value") if nodoIsin is not None else None
            filas.append({
                "emisor": _texto(elemento, "name"), "titulo": _texto(elemento, "title"),
                "lei": _texto(elemento, "lei"), "cusip": _texto(elemento, "cusip"), "isin": isin,
                "nominal": _numero(_texto(elemento, "balance")), "unidades": _texto(elemento, "units"),
                "moneda": _texto(elemento, "curCd"), "valorUSD": _numero(_texto(elemento, "valUSD")),
                "pesoPct": _numero(_texto(elemento, "pctVal")), "categoriaActivo": _texto(elemento, "assetCat"),
                "tipoEmisor": _texto(elemento, "issuerCat"), "pais": _texto(elemento, "invCountry"),
                "vencimiento": _texto(deuda, "maturityDt"), "tipoCupon": _texto(deuda, "couponKind"),
                "cuponPct": _numero(_texto(deuda, "annualizedRt")),
                "enImpago": _texto(deuda, "isDefault") == "Y",
                "interesesAtrasados": _texto(deuda, "areIntrstPmntsInArrs") == "Y",
                "esDeuda": deuda is not None,
            })
            elemento.clear()
    if not filas:
        raise ErrorSec("El reporte N-PORT no trae posiciones.")
    tabla = pd.DataFrame(filas)
    tabla["vencimiento"] = pd.to_datetime(tabla["vencimiento"], errors="coerce")
    return tabla, meta


def descargarCartera(ticker, usarCache=True, serie=None):
    """
    Cartera completa del fondo segun su ultimo NPORT-P. Devuelve (tabla, meta).
    meta incluye 'origen' (descarga / cache / cache-vencida) y la fecha del reporte.
    serie permite fijar el ID de serie a mano si la SEC no lista el ticker.
    """
    archivo, archivoMeta = f"cartera_{nombreSeguro(ticker)}.csv", f"cartera_{nombreSeguro(ticker)}_meta.json"

    def desdeCache(origen):
        tabla, meta = leerTabla(archivo, columnaFecha=None), leerJson(archivoMeta)
        if tabla is None or tabla.empty or not meta:
            return None
        tabla["vencimiento"] = pd.to_datetime(tabla["vencimiento"], errors="coerce")
        for columna in ("cusip", "isin", "lei", "emisor", "titulo"):
            tabla[columna] = tabla[columna].astype("string")
        for columna in ("enImpago", "interesesAtrasados", "esDeuda"):
            tabla[columna] = tabla[columna].astype(str).str.lower().isin(["true", "1"])
        meta["origen"] = origen
        return tabla, meta

    if usarCache and cacheVigente(archivo, horas=NPORT_CACHE_DIAS * 24):
        guardado = desdeCache(ORIGEN_CACHE)
        if guardado:
            return guardado

    try:
        datosSerie = {"serie": serie} if serie else _resolverConRespaldo(ticker, usarCache)
        reportes = listarReportesNport(datosSerie["serie"])
        if not reportes:
            raise ErrorSec(f"La serie {datosSerie['serie']} no tiene reportes N-PORT públicos.")
        url = urlDocumentoPrincipal(reportes[0]["url"])
        tabla, meta = parsearNport(_get(url, timeout=180).content)
        meta.update({"ticker": ticker, "url": url, "fechaPresentacion": reportes[0]["fecha"], "origen": ORIGEN_DESCARGA})
        guardarTabla(tabla, archivo, conIndice=False)
        guardarJson(meta, archivoMeta)
        registrarEvento(f"Cartera N-PORT de {ticker}: {len(tabla)} posiciones al {meta.get('fechaReporte')}.")
        return tabla, meta
    except (requests.exceptions.RequestException, ErrorSec, ET.ParseError, KeyError) as error:
        registrarEvento(f"No se pudo obtener la cartera de {ticker}: {error}", "WARN")
        guardado = desdeCache(ORIGEN_RESPALDO)
        if guardado:
            return guardado
        raise ErrorSec(str(error)) from error


def describirMeta(meta):
    """Texto corto con la procedencia de la cartera, para la interfaz."""
    if not meta:
        return ""
    texto = f"Cartera al {meta.get('fechaReporte') or meta.get('finPeriodo') or 'N/D'} (formulario N-PORT de la SEC, presentado el {meta.get('fechaPresentacion') or 'N/D'})"
    if meta.get("nombreSerie"):
        texto += f" · {meta['nombreSerie']}"
    if meta.get("origen") == ORIGEN_RESPALDO:
        texto += " · copia guardada: no se pudo actualizar"
    return texto



def carteraEnCache(ticker):
    """True si la cartera del fondo ya esta guardada y vigente (no hace falta descargar)."""
    return cacheVigente(f"cartera_{nombreSeguro(ticker)}.csv", horas=NPORT_CACHE_DIAS * 24)

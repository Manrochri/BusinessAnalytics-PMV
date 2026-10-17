"""
utilidades.py
Funciones de apoyo: cache en disco, formatos y registro de eventos.
El proyecto es de actualizacion MANUAL, por eso todo se guarda en disco
y solo se vuelve a descargar cuando el usuario lo pide.

Cada tabla o ficha leida/descargada lleva su ORIGEN (descarga, cache vigente
o cache vencida usada como respaldo) para que la interfaz pueda avisar
cuando esta mostrando datos viejos.
"""

import json
import math
from datetime import datetime, timedelta

import pandas as pd

from config import CACHE_HORAS_VIGENCIA, RUTA_CACHE

ORIGEN_DESCARGA = "descarga"
ORIGEN_CACHE = "cache"
ORIGEN_RESPALDO = "cache-vencida"
ORIGEN_SIN_DATOS = "sin-datos"


def registrarEvento(mensaje, nivel="INFO"):
    """Imprime un mensaje con marca de tiempo (log simple del proyecto)."""
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{marca}] [{nivel}] {mensaje}")


def esNulo(valor):
    """True si el valor es None o NaN (incluye numpy y pandas)."""
    if valor is None:
        return True
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):
        return False


def valorODefecto(valor, defecto):
    """Devuelve 'defecto' si el valor es None o NaN (a diferencia de 'or', que deja pasar NaN)."""
    return defecto if esNulo(valor) else valor


def asegurarCarpeta(ruta):
    """Crea la carpeta si no existe."""
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def nombreSeguro(ticker):
    """Convierte un ticker en un nombre de archivo seguro (^GSPC -> idx_GSPC)."""
    return str(ticker).replace("^", "idx_").replace("/", "_").replace("=", "_")


def rutaCache(nombreArchivo):
    """Devuelve la ruta completa de un archivo dentro de la carpeta de cache."""
    return RUTA_CACHE / nombreArchivo


def cacheVigente(nombreArchivo, horas=None):
    """Indica si un archivo de cache existe y todavia esta vigente."""
    try:
        ruta = rutaCache(nombreArchivo)
        if not ruta.exists():
            return False
        horasVigencia = CACHE_HORAS_VIGENCIA if horas is None else horas
        modificado = datetime.fromtimestamp(ruta.stat().st_mtime)
        return datetime.now() - modificado < timedelta(hours=horasVigencia)
    except OSError as error:
        registrarEvento(f"No se pudo verificar el cache: {error}", "WARN")
        return False


def marcarOrigen(df, origen, fecha=None):
    """Anota en el DataFrame de donde vienen los datos (se lee con origenDe)."""
    if df is not None:
        df.attrs["origen"] = origen
        df.attrs["fechaCache"] = fecha
    return df


def origenDe(objeto):
    """Devuelve (origen, fecha) de una tabla o ficha."""
    if objeto is None:
        return ORIGEN_SIN_DATOS, None
    if isinstance(objeto, pd.DataFrame):
        return objeto.attrs.get("origen", ORIGEN_DESCARGA), objeto.attrs.get("fechaCache")
    if isinstance(objeto, dict):
        return objeto.get("_origen", ORIGEN_DESCARGA), objeto.get("_fechaCache")
    return ORIGEN_DESCARGA, None


def guardarTabla(df, nombreArchivo, conIndice=True):
    """Guarda un DataFrame en formato CSV dentro del cache."""
    try:
        if df is None or df.empty:
            return False
        asegurarCarpeta(RUTA_CACHE)
        df.to_csv(rutaCache(nombreArchivo), index=conIndice, encoding="utf-8")
        return True
    except OSError as error:
        registrarEvento(f"No se pudo guardar {nombreArchivo}: {error}", "WARN")
        return False


def leerTabla(nombreArchivo, columnaFecha="Date"):
    """
    Lee un DataFrame previamente guardado en el cache. Si columnaFecha es None
    se lee como tabla simple (sin indice de fechas). Las columnas de indice
    sin nombre que dejan versiones anteriores ('Unnamed: 0') se descartan.
    """
    try:
        ruta = rutaCache(nombreArchivo)
        if not ruta.exists():
            return None
        df = pd.read_csv(ruta, encoding="utf-8")
        df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed:")]]
        if columnaFecha and columnaFecha in df.columns:
            fechas = pd.to_datetime(df[columnaFecha], errors="coerce", utc=True)
            df[columnaFecha] = fechas.dt.tz_localize(None)
            df = df.dropna(subset=[columnaFecha]).set_index(columnaFecha).sort_index()
            df.index.name = columnaFecha
        return marcarOrigen(df, ORIGEN_CACHE, fechaArchivoCache(nombreArchivo))
    except (OSError, ValueError, pd.errors.ParserError) as error:
        registrarEvento(f"No se pudo leer {nombreArchivo}: {error}", "WARN")
        return None


def guardarJson(objeto, nombreArchivo):
    """Guarda un diccionario en formato JSON dentro del cache."""
    try:
        asegurarCarpeta(RUTA_CACHE)
        limpio = {k: v for k, v in objeto.items() if not str(k).startswith("_")}
        with open(rutaCache(nombreArchivo), "w", encoding="utf-8") as archivo:
            json.dump(limpio, archivo, ensure_ascii=False, indent=2, default=str)
        return True
    except (OSError, TypeError) as error:
        registrarEvento(f"No se pudo guardar {nombreArchivo}: {error}", "WARN")
        return False


def leerJson(nombreArchivo):
    """Lee un diccionario JSON del cache."""
    try:
        ruta = rutaCache(nombreArchivo)
        if not ruta.exists():
            return None
        with open(ruta, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        datos["_origen"] = ORIGEN_CACHE
        datos["_fechaCache"] = fechaArchivoCache(nombreArchivo)
        return datos
    except (OSError, ValueError) as error:
        registrarEvento(f"No se pudo leer {nombreArchivo}: {error}", "WARN")
        return None


def fechaArchivoCache(nombreArchivo):
    """Devuelve la fecha de la ultima actualizacion de un archivo de cache."""
    try:
        ruta = rutaCache(nombreArchivo)
        if not ruta.exists():
            return None
        return datetime.fromtimestamp(ruta.stat().st_mtime)
    except OSError:
        return None


def describirOrigen(nombre, objeto):
    """
    Devuelve un hallazgo de calidad ("ok"/"alerta", mensaje) segun el origen
    de los datos, o None si se descargaron recien.
    """
    origen, fecha = origenDe(objeto)
    textoFecha = f" del {fecha:%d/%m/%Y %H:%M}" if isinstance(fecha, datetime) else ""
    if origen == ORIGEN_RESPALDO:
        return ("alerta", f"{nombre}: no se pudo descargar; se muestra la copia guardada{textoFecha}.")
    if origen == ORIGEN_CACHE:
        return ("ok", f"{nombre}: leído desde la caché{textoFecha} (vigencia {CACHE_HORAS_VIGENCIA} h).")
    return None


def formatearMoneda(valor, simbolo="$"):
    """Convierte un numero a texto con formato de moneda."""
    if esNulo(valor):
        return "N/D"
    try:
        return f"{simbolo}{float(valor):,.2f}"
    except (TypeError, ValueError):
        return "N/D"


def formatearPorcentaje(valor, decimales=1, conSigno=False):
    """Convierte un numero decimal (0.184) a texto de porcentaje (+18.4%)."""
    if esNulo(valor):
        return "N/D"
    try:
        numero = float(valor) * 100
        signo = "+" if conSigno and numero > 0 else ""
        return f"{signo}{numero:.{decimales}f}%"
    except (TypeError, ValueError):
        return "N/D"


def formatearNumero(valor, decimales=2):
    """Convierte un numero a texto con decimales controlados."""
    if esNulo(valor):
        return "N/D"
    try:
        return f"{float(valor):,.{decimales}f}"
    except (TypeError, ValueError):
        return "N/D"


def numeroSeguro(valor, decimales=4):
    """Numero redondeado apto para JSON (None en lugar de NaN/inf)."""
    if esNulo(valor):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if math.isinf(numero):
        return None
    return round(numero, decimales)

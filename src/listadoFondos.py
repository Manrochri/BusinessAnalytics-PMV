"""
listadoFondos.py
Lista de fondos que el usuario puede elegir en «Analizar otro fondo».

- ETF que cotizan en EE.UU.: del listado oficial de Alpha Vantage
  (function=LISTING_STATUS, CSV; funciona incluso con la clave «demo»).
  Se guarda en la cache 7 dias: es una sola consulta por semana.
- Fondos mutuos: Alpha Vantage no los lista, asi que se agregan los mas
  conocidos (Vanguard, Fidelity, Schwab) con su nombre.
- Si Alpha Vantage no responde, se usa una lista de respaldo de ETF populares.

Cada fila: ticker, nombre (sencillo, en palabras) y tipo («ETF» o «Fondo mutuo»).
"""

import csv
import io

import pandas as pd
import requests

from config import ALPHA_VANTAGE_API_KEY, ALPHA_VANTAGE_URL
from src.utilidades import cacheVigente, registrarEvento, rutaCache

ARCHIVO_LISTADO = "listado_etf_alphavantage.csv"
HORAS_VIGENCIA_LISTADO = 24 * 7

# Fondos mutuos conocidos (Alpha Vantage solo lista lo que cotiza en bolsa)
FONDOS_MUTUOS_POPULARES = [
    ("VFIAX", "Vanguard 500 Index (acciones de las 500 mayores empresas de EE.UU.)"),
    ("VTSAX", "Vanguard Total Stock Market Index (todo el mercado de acciones de EE.UU.)"),
    ("VTIAX", "Vanguard Total International Stock Index (acciones fuera de EE.UU.)"),
    ("VBTLX", "Vanguard Total Bond Market Index (mercado total de bonos de EE.UU.)"),
    ("VIGAX", "Vanguard Growth Index (empresas de crecimiento de EE.UU.)"),
    ("VVIAX", "Vanguard Value Index (empresas de valor de EE.UU.)"),
    ("VWELX", "Vanguard Wellington (mixto: acciones y bonos)"),
    ("VWINX", "Vanguard Wellesley Income (mixto conservador)"),
    ("FXAIX", "Fidelity 500 Index (500 mayores empresas de EE.UU.)"),
    ("FSKAX", "Fidelity Total Market Index (todo el mercado de EE.UU.)"),
    ("FCNTX", "Fidelity Contrafund (acciones de crecimiento)"),
    ("SWPPX", "Schwab S&P 500 Index (500 mayores empresas de EE.UU.)"),
    ("SWTSX", "Schwab Total Stock Market Index (todo el mercado de EE.UU.)"),
]

# Respaldo si Alpha Vantage no responde: ETF muy conocidos
ETF_POPULARES = [
    ("VOO", "Vanguard S&P 500 ETF (500 mayores empresas de EE.UU.)"),
    ("SPY", "SPDR S&P 500 ETF Trust (500 mayores empresas de EE.UU.)"),
    ("IVV", "iShares Core S&P 500 ETF (500 mayores empresas de EE.UU.)"),
    ("VTI", "Vanguard Total Stock Market ETF (todo el mercado de EE.UU.)"),
    ("QQQ", "Invesco QQQ Trust (100 mayores tecnológicas del Nasdaq)"),
    ("VXUS", "Vanguard Total International Stock ETF (acciones fuera de EE.UU.)"),
    ("VEA", "Vanguard FTSE Developed Markets ETF (países desarrollados)"),
    ("VWO", "Vanguard FTSE Emerging Markets ETF (países emergentes)"),
    ("SCHD", "Schwab U.S. Dividend Equity ETF (empresas que pagan dividendos)"),
    ("VIG", "Vanguard Dividend Appreciation ETF (dividendos crecientes)"),
    ("VUG", "Vanguard Growth ETF (empresas de crecimiento)"),
    ("VTV", "Vanguard Value ETF (empresas de valor)"),
    ("IWM", "iShares Russell 2000 ETF (empresas pequeñas de EE.UU.)"),
    ("DIA", "SPDR Dow Jones Industrial Average ETF (30 grandes empresas)"),
    ("XLK", "Technology Select Sector SPDR (sector tecnología)"),
    ("XLF", "Financial Select Sector SPDR (sector financiero)"),
    ("XLV", "Health Care Select Sector SPDR (sector salud)"),
    ("XLE", "Energy Select Sector SPDR (sector energía)"),
    ("VNQ", "Vanguard Real Estate ETF (bienes raíces)"),
    ("GLD", "SPDR Gold Shares (oro)"),
    ("BND", "Vanguard Total Bond Market ETF (mercado total de bonos)"),
    ("AGG", "iShares Core U.S. Aggregate Bond ETF (mercado total de bonos)"),
    ("BNDX", "Vanguard Total International Bond ETF (bonos fuera de EE.UU.)"),
    ("LQD", "iShares iBoxx Investment Grade Corporate Bond ETF (bonos de empresas sólidas)"),
]
# Orden: primero los mas conocidos, luego el resto en orden alfabetico
PRIORIDAD = {t: i for i, (t, _) in enumerate(FONDOS_MUTUOS_POPULARES[:2] + ETF_POPULARES + FONDOS_MUTUOS_POPULARES[2:])}


def parsearListado(texto):
    """CSV de LISTING_STATUS -> tabla (ticker, nombre, tipo) solo con ETF activos."""
    filas = []
    for fila in csv.DictReader(io.StringIO(texto)):
        if str(fila.get("assetType", "")).upper() != "ETF" or str(fila.get("status", "Active")).lower() != "active":
            continue
        ticker = str(fila.get("symbol", "")).strip().upper()
        nombre = " ".join(str(fila.get("name", "")).split())
        if ticker and nombre and "-" not in ticker:
            filas.append({"ticker": ticker, "nombre": nombre, "tipo": "ETF"})
    if not filas:
        raise ValueError("el listado no trae ETF")
    return pd.DataFrame(filas).drop_duplicates("ticker")


def _descargarListado():
    clave = ALPHA_VANTAGE_API_KEY if ALPHA_VANTAGE_API_KEY not in (None, "", "tu_clave_aqui") else "demo"
    respuesta = requests.get(ALPHA_VANTAGE_URL, params={"function": "LISTING_STATUS", "apikey": clave}, timeout=30)
    respuesta.raise_for_status()
    return parsearListado(respuesta.text)


def listarFondos(usarCache=True):
    """
    Fondos disponibles para analizar: ETF del listado de Alpha Vantage (cache 7
    dias) + fondos mutuos conocidos. Nunca falla: si no hay red, usa el respaldo.
    Devuelve (tabla, origen) con origen 'Alpha Vantage', 'cache' o 'respaldo'.
    """
    etf, origen = None, "respaldo"
    ruta = rutaCache(ARCHIVO_LISTADO)
    if usarCache and cacheVigente(ARCHIVO_LISTADO, HORAS_VIGENCIA_LISTADO):
        try:
            etf, origen = pd.read_csv(ruta, dtype=str), "cache"
        except (OSError, ValueError):
            etf = None
    if etf is None:
        try:
            etf, origen = _descargarListado(), "Alpha Vantage"
            ruta.parent.mkdir(parents=True, exist_ok=True)
            etf.to_csv(ruta, index=False)
            registrarEvento(f"Listado de ETF de Alpha Vantage: {len(etf)} fondos.")
        except (requests.exceptions.RequestException, ValueError) as error:
            registrarEvento(f"No se pudo descargar el listado de ETF ({error}); se usa la lista de respaldo.", "WARN")
            if ruta.exists():  # copia vieja antes que la lista corta
                try:
                    etf, origen = pd.read_csv(ruta, dtype=str), "cache"
                except (OSError, ValueError):
                    etf = None
    respaldo = pd.DataFrame([{"ticker": t, "nombre": n, "tipo": "ETF"} for t, n in ETF_POPULARES])
    mutuos = pd.DataFrame([{"ticker": t, "nombre": n, "tipo": "Fondo mutuo"} for t, n in FONDOS_MUTUOS_POPULARES])
    # Los nombres explicados (populares) reemplazan al nombre comercial del listado
    tabla = pd.concat([respaldo, mutuos] + ([etf] if etf is not None else []), ignore_index=True).drop_duplicates("ticker")
    tabla["orden"] = tabla["ticker"].map(PRIORIDAD).fillna(len(PRIORIDAD))
    tabla = tabla.sort_values(["orden", "nombre"]).drop(columns="orden").reset_index(drop=True)
    return tabla, origen


def etiquetaFondo(fila):
    """'Invesco QQQ Trust (100 mayores tecnológicas del Nasdaq) · QQQ · ETF': nombre primero, símbolo al final."""
    return f"{fila['nombre']} · {fila['ticker']} · {fila['tipo']}"
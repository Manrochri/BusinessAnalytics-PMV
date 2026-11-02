"""
portafolio.py
Armado de un PORTAFOLIO con varios fondos (fondos mutuos y ETF del catalogo):
universo disponible, pesos sugeridos para el perfil, metricas de la mezcla
(con la correlacion real entre los fondos), aporte de cada fondo al riesgo,
costos y minimos, y la serie historica de la mezcla para proyectarla.

Todo es puro (sin Streamlit) para poder probarlo.
"""

import numpy as np
import pandas as pd

from config import RETORNO_ESPERADO_ACCIONES
from src.analisisBonos import retornosMensuales
from src.datosEstructurados import calcularMaximaCaida
from src.catalogoBonos import PARAMETROS_PERFIL, buscarBono, nombreFondo
from src.catalogoFondosMutuos import CLASE_ACCIONES, CLASE_BONOS, CLASE_MIXTO, buscarFondoMutuo, gastoAnualDeRespaldo
from src.utilidades import esNulo

MESES_ANIO = 12
MINIMO_MESES = 24
MAXIMO_FONDOS = 6
# Volatilidad anual maxima que se le permite a TODO el portafolio en cada perfil
VOLATILIDAD_PORTAFOLIO = {"Conservador": 0.07, "Moderado": 0.11, "Agresivo": 0.16}
# Clase (para la mezcla y el color) de los ETF de referencia que no estan en los catalogos
CLASE_ETF_EXTRA = {"VTI": CLASE_ACCIONES, "VOO": CLASE_ACCIONES, "VXUS": CLASE_ACCIONES, "VUG": CLASE_ACCIONES, "VTV": CLASE_ACCIONES,
                   "AOK": CLASE_MIXTO, "AOR": CLASE_MIXTO, "AOM": CLASE_MIXTO}
MEZCLA_ACCIONES_ETF = {"AOK": 0.30, "AOR": 0.60, "AOM": 0.40}
LIQUIDEZ = "LIQUIDEZ"


def claseDe(ticker):
    """'Acciones', 'Bonos' o 'Mixto' para cualquier fondo del universo."""
    ficha = buscarFondoMutuo(ticker)
    if ficha:
        return ficha["clase"]
    if buscarBono(ticker):
        return CLASE_BONOS
    return CLASE_ETF_EXTRA.get(ticker, CLASE_ACCIONES)


def fraccionAcciones(ticker):
    ficha = buscarFondoMutuo(ticker)
    if ficha:
        return {CLASE_ACCIONES: 1.0, CLASE_BONOS: 0.0}.get(ficha["clase"], ficha.get("mezclaAcciones", 0.5))
    if buscarBono(ticker):
        return 0.0
    return MEZCLA_ACCIONES_ETF.get(ticker, 1.0)


def universoPortafolio(datos, perfil):
    """
    Fondos disponibles para armar el portafolio: {ticker: {nombre, clase, tipo,
    historico, veredicto, motivo, rendimientoEsperado, gastoAnual, minimo}}.
    Veredicto y rendimiento salen de los rankings del perfil (ETF de bonos y fondos mutuos).
    """
    tablaBonos, _ = (datos.get("rankingsPorPerfil") or {}).get(perfil, (pd.DataFrame(), {}))
    tablaMutuos, _ = (datos.get("rankingsMutuosPorPerfil") or {}).get(perfil, (pd.DataFrame(), {}))
    filas = {}
    for tabla in (tablaBonos, tablaMutuos):
        if tabla is not None and not tabla.empty:
            for _, f in tabla.iterrows():
                filas[f["ticker"]] = f
    universo = {}
    fuentes = {**(datos.get("universoBonos") or {}), **(datos.get("universoMutuos") or {})}
    if datos.get("historico") is not None and datos.get("ticker"):
        fuentes.setdefault(datos["ticker"], {"historico": datos["historico"], "ficha": datos.get("ficha") or {}})
    for ticker, d in fuentes.items():
        historico = d.get("historico")
        if historico is None or historico.empty or len(retornosMensuales(historico)) < MINIMO_MESES:
            continue
        fila = filas.get(ticker)
        ficha = buscarFondoMutuo(ticker) or {}
        gasto = (fila["gastoAnual"] if fila is not None and "gastoAnual" in fila and not esNulo(fila.get("gastoAnual"))
                 else (fila["gasto"] if fila is not None and "gasto" in fila and not esNulo(fila.get("gasto")) else None))
        if gasto is None:
            gasto = (d.get("ficha") or {}).get("gastoAnual") or gastoAnualDeRespaldo(ticker)
        universo[ticker] = {
            "ticker": ticker, "nombre": nombreFondo(ticker, (d.get("ficha") or {}).get("nombre")), "clase": claseDe(ticker),
            "tipo": "Fondo mutuo" if ficha else "ETF", "historico": historico,
            "veredicto": fila["veredicto"] if fila is not None else "Sin veredicto",
            "motivo": fila["motivo"] if fila is not None else "No está en los catálogos de tu perfil.",
            "rendimientoEsperado": fila["rendimientoEsperado"] if fila is not None and "rendimientoEsperado" in fila else np.nan,
            "gastoAnual": gasto, "minimo": ficha.get("minimo", 0) if ficha else 0,
            "enPerfil": fila is not None,
        }
    return universo


def retornosConjuntos(universo, tickers):
    """Retornos mensuales alineados (meses comunes) de los fondos elegidos. Vacio si falta alguno."""
    series = {}
    for t in tickers:
        if t not in universo:
            return pd.DataFrame()
        series[t] = retornosMensuales(universo[t]["historico"])
    tabla = pd.concat(series, axis=1).dropna()
    return tabla if len(tabla) >= MINIMO_MESES else pd.DataFrame()


def retornoEsperadoFondo(info, tasaLibre):
    """
    Retorno anual esperado de un fondo, coherente con el resto de la app:
    bonos -> su rendimiento esperado (o la liquidez); acciones -> el supuesto
    central de acciones; mixtos -> la mezcla de ambos.
    """
    rendimiento = info.get("rendimientoEsperado")
    rendimientoBonos = float(rendimiento) if not esNulo(rendimiento) else float(tasaLibre)
    f = fraccionAcciones(info["ticker"])
    return f * RETORNO_ESPERADO_ACCIONES + (1 - f) * rendimientoBonos


def metricasMezcla(retornos, pesos, tasaLibre):
    """
    Metricas historicas de la mezcla (pesos por fondo; el resto es liquidez a
    la tasa libre): retorno anual, volatilidad, Sharpe, peor caida, serie
    mensual y aporte de cada fondo al riesgo total (en fraccion).
    """
    tickers = [t for t in retornos.columns if pesos.get(t, 0) > 0]
    if not tickers:
        return None
    w = np.array([pesos[t] for t in tickers], dtype=float)
    liquidez = max(1.0 - w.sum(), 0.0)
    r = retornos[tickers].to_numpy()
    tasaMensual = (1 + float(tasaLibre)) ** (1 / MESES_ANIO) - 1
    serie = pd.Series(r @ w + liquidez * tasaMensual, index=retornos.index)
    cov = np.cov(r, rowvar=False, ddof=1) if len(tickers) > 1 else np.array([[np.var(r[:, 0], ddof=1)]])
    varianza = float(w @ cov @ w)
    volatilidad = float(np.sqrt(max(varianza, 0) * MESES_ANIO))
    contribucion = (w * (cov @ w)) / varianza if varianza > 0 else np.full(len(w), 1 / len(w))
    nav = (1 + serie).cumprod() * 100
    anios = len(serie) / MESES_ANIO
    retornoAnual = float((nav.iloc[-1] / 100) ** (1 / anios) - 1) if anios > 0 else np.nan
    return {
        "retornoAnual": retornoAnual, "volatilidad": volatilidad,
        "sharpe": float((retornoAnual - tasaLibre) / volatilidad) if volatilidad > 0 else np.nan,
        "caidaMaxima": calcularMaximaCaida(nav), "serie": serie, "nav": nav, "meses": int(len(serie)),
        "contribucionRiesgo": {t: float(c) for t, c in zip(tickers, contribucion, strict=True)}, "liquidez": liquidez,
    }


PESO_MINIMO, PESO_MAXIMO = 0.05, 0.60   # ningun fondo sugerido pesa menos de 5% ni mas de 60%
DESVIO_CLASE = 0.15                      # la parte en acciones puede alejarse hasta 15 pp de la del perfil


def sugerirPesos(retornos, perfil, tasaLibre, muestras=6000, semilla=11):
    """
    Pesos sugeridos para el perfil, entre miles de mezclas al azar con la
    liquidez del perfil fija: la de mejor relacion retorno/riesgo que
      1) no supere la volatilidad del portafolio del perfil,
      2) tenga la parte en acciones cerca de la del perfil (±15 pp) y
      3) reparta de verdad (cada fondo entre 5% y 60%).
    Si ninguna cumple todo, se relajan las condiciones en ese orden. El retorno
    esperado de cada fondo es el mismo supuesto que usa el resto de la app (no
    el historico), para no premiar al que tuvo suerte en estos anios.
    Devuelve {ticker: peso} (suman 1 - liquidez).
    """
    tickers = list(retornos.columns)
    if not tickers:
        return {}
    p = PARAMETROS_PERFIL[perfil]
    liquidez, tope = p["liquidez"], VOLATILIDAD_PORTAFOLIO[perfil]
    r = retornos[tickers].to_numpy()
    esperados = np.array([fraccionAcciones(t) * RETORNO_ESPERADO_ACCIONES + (1 - fraccionAcciones(t)) * (r[:, i].mean() * MESES_ANIO)
                          for i, t in enumerate(tickers)])
    cov = np.cov(r, rowvar=False, ddof=1) * MESES_ANIO if len(tickers) > 1 else np.array([[np.var(r[:, 0], ddof=1) * MESES_ANIO]])
    acciones = np.array([fraccionAcciones(t) for t in tickers])
    generador = np.random.default_rng(semilla)
    candidatos = generador.dirichlet(np.full(len(tickers), 2.0), size=muestras) * (1 - liquidez)
    candidatos = np.vstack([candidatos, np.full(len(tickers), (1 - liquidez) / len(tickers))])
    retornosC = candidatos @ esperados + liquidez * tasaLibre
    volC = np.sqrt(np.einsum("ij,jk,ik->i", candidatos, cov, candidatos))
    sharpe = np.where(volC > 0, (retornosC - tasaLibre) / np.where(volC > 0, volC, 1), -np.inf)
    reparte = (candidatos >= PESO_MINIMO * (1 - liquidez) / 1.0).all(axis=1) & (candidatos <= PESO_MAXIMO).all(axis=1) if len(tickers) > 1 else np.ones(len(candidatos), bool)
    claseOk = np.abs(candidatos @ acciones - p["rentaVariable"]) <= DESVIO_CLASE
    cabe = volC <= tope
    for filtro in (cabe & claseOk & reparte, cabe & reparte, cabe, np.ones(len(candidatos), bool)):
        if filtro.any():
            elegido = int(np.argmax(np.where(filtro, sharpe, -np.inf))) if (filtro & cabe).any() else int(np.argmin(np.where(filtro, volC, np.inf)))
            break
    pesos = candidatos[elegido]
    pesos = np.round(pesos / pesos.sum() * (1 - liquidez), 2)  # redondeo a 1%
    return {t: float(w) for t, w in zip(tickers, pesos, strict=True)}


def mezclaPorClase(universo, pesos):
    """Fraccion del portafolio en acciones, bonos y liquidez (los mixtos se reparten)."""
    acciones = bonos = 0.0
    for t, w in pesos.items():
        if t not in universo or w <= 0:
            continue
        f = fraccionAcciones(t)
        acciones += w * f
        bonos += w * (1 - f)
    return {"Renta variable": acciones, "Renta fija": bonos, "Liquidez": max(1 - acciones - bonos, 0.0)}


def evaluarPortafolio(universo, pesos, perfil, tasaLibre):
    """
    Evaluacion completa de un portafolio {ticker: peso}. Devuelve dict con
    filas por fondo, metricas de la mezcla, retorno esperado, gasto ponderado,
    minimo total, mezcla por clase vs. la del perfil y avisos. None si no hay datos.
    """
    pesos = {t: float(w) for t, w in pesos.items() if t in universo and w > 0}
    if not pesos:
        return None
    total = sum(pesos.values())
    if total > 1.0001:
        return {"error": f"Los pesos suman {total:.0%}: deben sumar como máximo 100%."}
    retornos = retornosConjuntos(universo, list(pesos))
    if retornos.empty:
        return {"error": "Los fondos elegidos no comparten al menos 2 años de historia en común."}
    m = metricasMezcla(retornos, pesos, tasaLibre)
    p = PARAMETROS_PERFIL[perfil]
    filas, gasto, minimo, esperado = [], 0.0, 0.0, 0.0
    for t, w in pesos.items():
        info = universo[t]
        esperadoFondo = retornoEsperadoFondo(info, tasaLibre)
        esperado += w * esperadoFondo
        gasto += w * float(info["gastoAnual"] or 0)
        minimo += float(info["minimo"] or 0)
        filas.append({"ticker": t, "nombre": info["nombre"], "clase": info["clase"], "tipo": info["tipo"], "peso": w,
                      "veredicto": info["veredicto"], "motivo": info["motivo"], "aporteRiesgo": m["contribucionRiesgo"].get(t, np.nan),
                      "retornoEsperado": esperadoFondo, "gastoAnual": info["gastoAnual"], "minimo": info["minimo"]})
    liquidez = max(1 - total, 0.0)
    esperado += liquidez * float(tasaLibre)
    mezcla = mezclaPorClase(universo, pesos)
    base = {"Renta variable": p["rentaVariable"], "Renta fija": p["rentaFija"], "Liquidez": p["liquidez"]}
    tope = VOLATILIDAD_PORTAFOLIO[perfil]
    avisos = []
    if m["volatilidad"] > tope:
        avisos.append(("roja", f"La mezcla se mueve {m['volatilidad']:.0%} al año, más de lo que soporta un perfil {perfil} ({tope:.0%}). "
                               "Baja el peso de los fondos que más aportan al riesgo o usa «Sugerir pesos»."))
    noRecomendables = [f["nombre"] for f in filas if f["veredicto"] == "No recomendable"]
    if noRecomendables:
        avisos.append(("ambar", "No recomendables para tu perfil: " + "; ".join(noRecomendables) + "."))
    if abs(mezcla["Renta variable"] - base["Renta variable"]) > 0.15:
        avisos.append(("ambar", f"Tienes {mezcla['Renta variable']:.0%} en acciones; tu perfil sugiere {base['Renta variable']:.0%}."))
    if len(pesos) == 1:
        avisos.append(("ambar", "Un solo fondo no diversifica: agrega al menos uno de otra clase."))
    veredicto = ("No recomendable" if m["volatilidad"] > 1.25 * tope or any(f["veredicto"] == "No recomendable" and f["peso"] >= 0.25 for f in filas)
                 else "Aceptable" if avisos else "Recomendable")
    return {"filas": pd.DataFrame(filas), "pesos": pesos, "liquidez": liquidez, "metricas": m, "retornoEsperado": esperado,
            "gastoPonderado": gasto, "minimoTotal": minimo, "mezcla": mezcla, "mezclaPerfil": base, "avisos": avisos,
            "veredicto": veredicto, "volatilidadMaxima": tope,
            "historicoMezcla": pd.DataFrame({"nav": m["nav"].values}, index=m["nav"].index)}


def sugerenciaInicial(universo, perfil):
    """Portafolio de partida: el mejor fondo de acciones de EE.UU., uno internacional si lo hay y el mejor de bonos del perfil."""
    def mejor(filtro):
        candidatos = [u for u in universo.values() if u["enPerfil"] and filtro(u) and u["veredicto"] in ("Recomendable", "Aceptable")]
        candidatos.sort(key=lambda u: (u["veredicto"] != "Recomendable", u["tipo"] != "Fondo mutuo"))
        return candidatos[0]["ticker"] if candidatos else None
    p = PARAMETROS_PERFIL[perfil]
    acciones = mejor(lambda u: u["clase"] == CLASE_ACCIONES and u["ticker"] != "VTIAX")
    internacional = ("VTIAX" if "VTIAX" in universo and universo["VTIAX"]["enPerfil"]
                     and universo["VTIAX"]["veredicto"] in ("Recomendable", "Aceptable") else None)
    bonos = mejor(lambda u: u["clase"] == CLASE_BONOS)
    mixto = mejor(lambda u: u["clase"] == CLASE_MIXTO) if not acciones else None
    tickers = [t for t in (acciones or mixto, internacional, bonos) if t]
    pesos = {}
    rv = p["rentaVariable"]
    if acciones and internacional:
        pesos[acciones], pesos[internacional] = round(rv * 0.7, 2), round(rv * 0.3, 2)
    elif acciones or mixto:
        pesos[acciones or mixto] = rv
    if bonos:
        pesos[bonos] = p["rentaFija"]
    return tickers, pesos
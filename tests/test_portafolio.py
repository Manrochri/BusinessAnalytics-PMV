"""Portafolio con varios fondos: universo, pesos sugeridos, metricas de la mezcla y evaluacion."""

import numpy as np
import pandas as pd

from src.catalogoBonos import PARAMETROS_PERFIL
from src.datosEstructurados import construirTablaNav
from src.portafolio import (
    PESO_MAXIMO,
    PESO_MINIMO,
    VOLATILIDAD_PORTAFOLIO,
    evaluarPortafolio,
    metricasMezcla,
    mezclaPorClase,
    retornosConjuntos,
    sugerenciaInicial,
    sugerirPesos,
    universoPortafolio,
)


def _historico(mu, sigma, semilla, dias=1300):
    fechas = pd.bdate_range("2021-06-01", periods=dias)
    r = np.random.default_rng(semilla).normal(mu / 252, sigma / np.sqrt(252), dias)
    return construirTablaNav(pd.Series(100 * np.cumprod(1 + r), index=fechas))


def _datos():
    mutuos = {"VFIAX": (0.10, 0.16, 1), "VTIAX": (0.06, 0.15, 2), "VBTLX": (0.02, 0.06, 3), "VWINX": (0.05, 0.07, 4)}
    bonos = {"BND": (0.02, 0.06, 5), "VCIT": (0.03, 0.07, 6)}
    universoMutuos = {t: {"historico": _historico(*p), "ficha": {}} for t, p in mutuos.items()}
    universoBonos = {t: {"historico": _historico(*p), "ficha": {}} for t, p in bonos.items()}
    tablaMutuos = pd.DataFrame([
        {"ticker": "VFIAX", "veredicto": "Recomendable", "motivo": "ok", "rendimientoEsperado": np.nan, "gastoAnual": 0.0004},
        {"ticker": "VTIAX", "veredicto": "Aceptable", "motivo": "ok", "rendimientoEsperado": np.nan, "gastoAnual": 0.0009},
        {"ticker": "VBTLX", "veredicto": "Recomendable", "motivo": "ok", "rendimientoEsperado": 0.044, "gastoAnual": 0.0005},
        {"ticker": "VWINX", "veredicto": "No recomendable", "motivo": "x", "rendimientoEsperado": np.nan, "gastoAnual": 0.0023},
    ])
    tablaBonos = pd.DataFrame([
        {"ticker": "BND", "veredicto": "Aceptable", "motivo": "ok", "rendimientoEsperado": 0.042, "gasto": 0.0003},
        {"ticker": "VCIT", "veredicto": "Recomendable", "motivo": "ok", "rendimientoEsperado": 0.048, "gasto": 0.0003},
    ])
    return {"ticker": "VFIAX", "historico": universoMutuos["VFIAX"]["historico"], "ficha": {}, "tasaLibre": 0.039,
            "universoMutuos": universoMutuos, "universoBonos": universoBonos,
            "rankingsMutuosPorPerfil": {"Moderado": (tablaMutuos, {})}, "rankingsPorPerfil": {"Moderado": (tablaBonos, {})}}


def test_universo_y_sugerencia_inicial():
    u = universoPortafolio(_datos(), "Moderado")
    assert set(u) == {"VFIAX", "VTIAX", "VBTLX", "VWINX", "BND", "VCIT"}
    assert u["VFIAX"]["tipo"] == "Fondo mutuo" and u["BND"]["tipo"] == "ETF" and u["VBTLX"]["minimo"] == 3000
    assert u["VCIT"]["gastoAnual"] == 0.0003 and u["VFIAX"]["clase"] == "Acciones"
    tickers, pesos = sugerenciaInicial(u, "Moderado")
    assert tickers[0] == "VFIAX" and "VTIAX" in tickers and tickers[-1] in ("VBTLX", "VCIT")
    p = PARAMETROS_PERFIL["Moderado"]
    assert abs(sum(pesos.values()) - (p["rentaVariable"] + p["rentaFija"])) < 0.02


def test_metricas_de_la_mezcla_usan_la_correlacion():
    u = universoPortafolio(_datos(), "Moderado")
    retornos = retornosConjuntos(u, ["VFIAX", "VBTLX"])
    assert len(retornos) >= 24
    solo = metricasMezcla(retornos, {"VFIAX": 0.95}, 0.039)
    mezcla = metricasMezcla(retornos, {"VFIAX": 0.5, "VBTLX": 0.45}, 0.039)
    assert mezcla["volatilidad"] < solo["volatilidad"]  # dos fondos poco correlacionados se mueven menos que uno solo
    assert abs(sum(mezcla["contribucionRiesgo"].values()) - 1) < 1e-6
    assert mezcla["contribucionRiesgo"]["VFIAX"] > mezcla["contribucionRiesgo"]["VBTLX"]
    assert mezcla["caidaMaxima"] <= 0 and len(mezcla["nav"]) == mezcla["meses"]


def test_pesos_sugeridos_reparten_y_respetan_la_tolerancia():
    u = universoPortafolio(_datos(), "Moderado")
    retornos = retornosConjuntos(u, ["VFIAX", "VTIAX", "VBTLX"])
    pesos = sugerirPesos(retornos, "Moderado", 0.039)
    assert abs(sum(pesos.values()) - (1 - PARAMETROS_PERFIL["Moderado"]["liquidez"])) < 0.02
    assert all(PESO_MINIMO - 0.02 <= w <= PESO_MAXIMO + 0.01 for w in pesos.values())
    assert metricasMezcla(retornos, pesos, 0.039)["volatilidad"] <= VOLATILIDAD_PORTAFOLIO["Moderado"] + 1e-9


def test_evaluacion_del_portafolio():
    datos = _datos()
    u = universoPortafolio(datos, "Moderado")
    ev = evaluarPortafolio(u, {"VFIAX": 0.42, "VTIAX": 0.18, "VBTLX": 0.35}, "Moderado", 0.039)
    assert ev["veredicto"] in ("Recomendable", "Aceptable") and ev["liquidez"] > 0.04
    assert abs(ev["retornoEsperado"] - (0.6 * 0.07 + 0.35 * 0.044 + 0.05 * 0.039)) < 1e-6  # acciones al supuesto, bonos a su rendimiento
    assert ev["minimoTotal"] == 9000 and 0 < ev["gastoPonderado"] < 0.001
    assert abs(ev["mezcla"]["Renta variable"] - 0.6) < 1e-9 and list(ev["filas"]["ticker"]) == ["VFIAX", "VTIAX", "VBTLX"]
    assert "nav" in ev["historicoMezcla"]
    assert evaluarPortafolio(u, {"VFIAX": 0.7, "VBTLX": 0.5}, "Moderado", 0.039)["error"].startswith("Los pesos suman")
    pesado = evaluarPortafolio(u, {"VWINX": 0.9}, "Moderado", 0.039)
    assert pesado["veredicto"] == "No recomendable" and any("No recomendables" in a[1] for a in pesado["avisos"])
    assert mezclaPorClase(u, {"VWINX": 1.0})["Renta variable"] == 0.35
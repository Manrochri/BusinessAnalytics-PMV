"""Fondos mutuos: catalogo, veredicto por perfil, costos, rentabilidad tipo prospecto y aportes."""

import numpy as np
import pandas as pd

from src.analisisBonos import rendimientoAnualConAportes, valorFuturoAportes
from src.analisisFondosMutuos import evaluarFondoMutuo, puntuarRentaVariable, rankingFondosMutuos, veredictoParaPerfil
from src.catalogoBonos import PERFILES, benchmarkParaFondo, buscarBono, nombreFondo
from src.catalogoFondosMutuos import (
    CLASE_BONOS,
    FONDOS_MUTUOS,
    buscarFondoMutuo,
    condicionesDeCompra,
    costoAcumulado,
    fondosMutuosDelPerfil,
)
from src.datosEstructurados import (
    _normalizarGasto,
    construirTablaNav,
    mejorPeorTrimestre,
    rentabilidadPorAnio,
    retornoPromedioAnual,
)


def _historico(mu, sigma, dias=900, semilla=1):
    fechas = pd.bdate_range("2023-01-02", periods=dias)
    r = np.random.default_rng(semilla).normal(mu / 252, sigma / np.sqrt(252), dias)
    return construirTablaNav(pd.Series(100 * np.cumprod(1 + r), index=fechas))


def test_catalogo_de_fondos_mutuos_es_consistente():
    for f in FONDOS_MUTUOS:
        assert set(f["perfiles"]) <= set(PERFILES), f["ticker"]
        assert 0 <= f["gastoAnual"] < 0.02 and f["minimo"] >= 0
        if f["clase"] == CLASE_BONOS:
            assert buscarBono(f["gemelo"]) is not None, f"{f['ticker']} sin ETF gemelo en el ranking de bonos"
        assert f["benchmark"]
    assert all(fondosMutuosDelPerfil(p) for p in PERFILES)
    assert nombreFondo("VBTLX") == "Mercado total de bonos de EE.UU., Vanguard (VBTLX)"
    assert benchmarkParaFondo("VWINX", "Conservador", "^SP500TR") == "AOK"


def test_veredicto_de_fondo_de_acciones_segun_tolerancia_del_perfil():
    tranquilo = {"observaciones": 700, "volatilidad": 0.14, "caidaMaxima": -0.18, "sharpe": 0.8, "retorno6m": 0.05, "sobreMedia200": True}
    _, _, veredicto, _ = puntuarRentaVariable(tranquilo, "Moderado")
    assert veredicto == "Recomendable"
    _, _, veredicto, motivos = puntuarRentaVariable(tranquilo, "Conservador")  # 14% > 12% tolerado, pero < 1.25x
    assert veredicto == "Aceptable" and "Volatilidad" in motivos[0]
    salvaje = dict(tranquilo, volatilidad=0.30, caidaMaxima=-0.45)
    assert puntuarRentaVariable(salvaje, "Moderado")[2] == "No recomendable"
    assert puntuarRentaVariable(salvaje, "Agresivo")[2] == "Recomendable"
    malo = dict(tranquilo, sharpe=-0.6, retorno6m=-0.15, sobreMedia200=False)
    assert puntuarRentaVariable(malo, "Moderado")[2] == "No recomendable"
    assert puntuarRentaVariable(dict(tranquilo, observaciones=50), "Moderado")[2] == "Sin datos"


def test_fondo_mutuo_de_bonos_se_evalua_con_las_reglas_del_ranking_y_hereda_si_no_hay_historia():
    ficha = buscarFondoMutuo("VBTLX")
    historico = _historico(0.02, 0.06)
    fila = evaluarFondoMutuo(ficha, historico, {"rendimientoDistribucion": 0.045}, "Moderado", 0.039)
    assert fila["clase"] == "Bonos" and fila["fuenteVeredicto"] == "propio"
    assert abs(fila["rinde"] - (0.045 - buscarBono("BND")["perdidaCreditoEsperada"])) < 1e-9
    gemelo = pd.DataFrame([{"ticker": "BND", "puntaje": 70.0, "componentes": {}, "veredicto": "Recomendable", "motivo": "ok",
                            "rendimientoEsperado": 0.044, "prima": 0.005, "volatilidad": 0.06, "caidaMaxima": -0.1, "sharpe": 0.5}])
    heredada = evaluarFondoMutuo(ficha, pd.DataFrame(), {}, "Moderado", 0.039, gemelo)
    assert heredada["veredicto"] == "Recomendable" and heredada["fuenteVeredicto"] == "gemelo"


def test_ranking_de_fondos_mutuos_y_veredicto_para_la_conclusion():
    universo = {f["ticker"]: {"historico": _historico(0.08 if f["clase"] != "Bonos" else 0.02, 0.15 if f["clase"] != "Bonos" else 0.05, semilla=i),
                              "ficha": {"rendimientoDistribucion": 0.045}} for i, f in enumerate(FONDOS_MUTUOS)}
    tabla, resumen = rankingFondosMutuos(universo, "Moderado", 0.039)
    assert list(tabla["puesto"]) == list(range(1, len(tabla) + 1))
    assert set(tabla["veredicto"]) <= {"Recomendable", "Aceptable", "No recomendable", "Sin datos"}
    assert resumen["evaluados"] == len(tabla)
    datos = {"ticker": "VFIAX", "rankingsPorPerfil": {}, "rankingsMutuosPorPerfil": {"Moderado": (tabla, resumen)}}
    v = veredictoParaPerfil(datos, "Moderado")
    assert v["origen"] == "mutuos" and v["veredicto"] in ("Recomendable", "Aceptable", "No recomendable")
    if v["alternativa"]:
        assert buscarFondoMutuo(v["alternativa"])["clase"] == "Acciones"  # la alternativa es de la misma clase
    assert veredictoParaPerfil({"ticker": "ARKK", "rankingsPorPerfil": {}, "rankingsMutuosPorPerfil": {}}, "Moderado")["veredicto"] is None


def test_costos_y_condiciones():
    c = condicionesDeCompra("VFIAX", {"gastoAnual": None})
    assert c["esFondoMutuo"] and c["minimo"] == 3000 and c["gastoAnual"] == 0.0004 and "cierre" in c["comoSeCompra"]
    assert condicionesDeCompra("FXAIX")["minimo"] == 0
    etf = condicionesDeCompra("VCIT", {"gastoAnual": 0.0004})
    assert not etf["esFondoMutuo"] and etf["gastoAnual"] == 0.0004 and etf["gemelo"] == "VICSX"
    costos = costoAcumulado(0.0004)
    assert abs(costos[1] - 4.0) < 0.01 and costos[10] > costos[5] > costos[3] > costos[1]
    # Yahoo publica el gasto en porcentaje (0.04 = 0.04%)
    assert _normalizarGasto(0.04) == 0.0004 and _normalizarGasto(0.0945) == 0.000945 and _normalizarGasto(0.0004) == 0.0004


def test_rentabilidad_tipo_prospecto():
    h = _historico(0.06, 0.12, dias=1000)
    b = _historico(0.05, 0.12, dias=1000, semilla=2)
    anual = rentabilidadPorAnio(h, b)
    assert list(anual.columns) == ["anio", "fondo", "benchmark", "parcial"] and anual["parcial"].iloc[-1]
    assert anual["anio"].is_monotonic_increasing and anual["benchmark"].notna().all()
    t = mejorPeorTrimestre(h)
    assert t["mejor"] >= t["peor"] and t["mejorTrimestre"].startswith("T")
    promedios = retornoPromedioAnual(h, b)
    assert list(promedios["anios"]) == [1, 3] and promedios["fondo"].notna().all()  # ~4 anios de historia: 1 y 3


def test_aportes_mensuales():
    assert abs(valorFuturoAportes(100, 12, 0.0) - 1200) < 1e-9
    assert valorFuturoAportes(100, 12, 0.05) > 1200
    valor = 10000 * 1.05 ** 3 + valorFuturoAportes(100, 36, 0.05)
    assert abs(rendimientoAnualConAportes(valor, 10000, 100, 36) - 0.05) < 1e-6
    assert abs(rendimientoAnualConAportes(11576.25, 10000, 0, 36) - 0.05) < 1e-4
"""Fondo analizado segun el perfil: benchmark automatico, clase del fondo y ajuste tactico."""

import pandas as pd

from src.catalogoBonos import benchmarkParaFondo, bonosDelPerfil, perfilDelFondo
from src.datosNoticias import temaTonoPrensa
from src.motorPrescriptivo import claseDelFondo, construirAsignacion, construirPlanAccion


def _pesos(asignacion):
    return pd.DataFrame(asignacion["filas"]).groupby("clase")["peso"].sum()


def test_benchmark_por_perfil():
    assert benchmarkParaFondo("SGOV", "Conservador") == "BIL"
    assert benchmarkParaFondo("HYG", "Agresivo") == "AGG"
    assert benchmarkParaFondo("AGG", "Moderado") == "BND"  # nunca contra si mismo
    assert benchmarkParaFondo("VFIAX", "Moderado", "^SP500TR") == "^SP500TR"
    assert perfilDelFondo("ANGL") == "Agresivo" and perfilDelFondo("VFIAX") is None


def test_cada_fondo_del_catalogo_tiene_tema_de_prensa_propio():
    for perfil in ("Conservador", "Moderado", "Agresivo"):
        for bono in bonosDelPerfil(perfil):
            assert temaTonoPrensa(bono["ticker"]) != f'"{bono["ticker"]}"'


def test_clase_del_fondo():
    assert claseDelFondo("BND") == "Renta fija"
    assert claseDelFondo("VFIAX", {"categoria": "Large Blend"}) == "Renta variable"
    assert claseDelFondo("XYZ", {"categoria": "Intermediate Core Bond"}) == "Renta fija"


def test_ajuste_tactico_sobre_la_clase_del_fondo_analizado():
    ranking = pd.DataFrame([{"ticker": "HYG", "segmento": "Alto rendimiento", "veredicto": "Recomendable"}])
    base = _pesos(construirAsignacion("Agresivo", {"accion": "MANTENER"}, ranking, claseSenal="Renta fija"))
    compra = _pesos(construirAsignacion("Agresivo", {"accion": "COMPRAR"}, ranking, claseSenal="Renta fija"))
    reduce = _pesos(construirAsignacion("Agresivo", {"accion": "REDUCIR"}, ranking, claseSenal="Renta fija"))
    assert round(compra["Renta fija"] - base["Renta fija"], 4) == 0.05
    assert round(base["Renta variable"] - compra["Renta variable"], 4) == 0.05
    assert round(base["Renta fija"] - reduce["Renta fija"], 4) == 0.05
    assert round(reduce["Liquidez"] - base["Liquidez"], 4) == 0.05
    # Fondo de acciones: el ajuste sigue siendo sobre la renta variable
    rv = _pesos(construirAsignacion("Agresivo", {"accion": "COMPRAR"}, ranking))
    assert round(rv["Renta variable"] - base["Renta variable"], 4) == 0.05


def test_solo_liquidez_y_plan_de_fondo_de_bonos():
    ranking = pd.DataFrame([{"ticker": "BND", "segmento": "Agregado", "veredicto": "Recomendable"}])
    asignacion = construirAsignacion("Moderado", {"accion": "COMPRAR"}, ranking, fondoElegido="BND",
                                     claseSenal="Renta fija", soloLiquidez=True)
    pesos = _pesos(asignacion)
    assert "Renta fija" not in pesos and abs(pesos.sum() - 1) < 1e-9
    assert asignacion["rentaFijaObjetivo"] == 0.40
    asignacion = construirAsignacion("Moderado", {"accion": "COMPRAR"}, ranking, fondoElegido="BND", claseSenal="Renta fija")
    plan = construirPlanAccion({"accion": "COMPRAR"}, "BND", {"categoria": "Bajo"}, "Moderado", {}, asignacion,
                               capital=10000, fondoElegido="BND")
    assert plan[0]["accion"].startswith("Señal COMPRAR en BND")
    assert any("renta fija a 40%" in p["accion"] for p in plan)

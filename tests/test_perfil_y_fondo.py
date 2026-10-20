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


def test_cartera_completa_suma_partes_y_el_agresivo_espera_ganar_mas():
    import numpy as np

    from src.analisisBonos import proyectarCartera, proyectarInversion, rendimientoAnualizado
    from src.catalogoBonos import PARAMETROS_PERFIL

    def proyectar(perfil, capital=10000, meses=36):
        p = PARAMETROS_PERFIL[perfil]
        acciones = proyectarInversion(None, 0.07, capital * p["rentaVariable"], 0, meses, volatilidadRespaldo=0.16, centrarMediana=True)
        bonos = proyectarInversion(None, 0.045, capital * p["rentaFija"], 0, meses, volatilidadRespaldo=0.04)
        liquidez = capital * p["liquidez"] * 1.04 ** (meses / 12)
        return proyectarCartera([
            {"clase": "Renta variable", "nombre": "Acciones", "monto": capital * p["rentaVariable"], "valores": acciones["valores"]},
            {"clase": "Renta fija", "nombre": "Bonos", "monto": capital * p["rentaFija"], "valores": bonos["valores"]},
            {"clase": "Liquidez", "nombre": "Liquidez", "monto": capital * p["liquidez"], "valores": liquidez},
        ], meses)

    conservador, agresivo = proyectar("Conservador"), proyectar("Agresivo")
    assert abs(conservador["resumen"]["montoTotal"] - 10000) < 1e-6
    assert len(conservador["partes"]) == 3 and np.isclose(conservador["partes"]["monto"].sum(), 10000)
    # Mas acciones: mas ganancia esperada, pero tambien mas dispersion y mas probabilidad de perdida
    assert agresivo["resumen"]["gananciaMediana"] > conservador["resumen"]["gananciaMediana"]
    ancho = lambda r: r["gananciaOptimista"] - r["gananciaPesimista"]  # noqa: E731
    assert ancho(agresivo["resumen"]) > ancho(conservador["resumen"])
    assert agresivo["resumen"]["probabilidadPerdida"] >= conservador["resumen"]["probabilidadPerdida"]
    assert abs(rendimientoAnualizado(1157.625, 1000, 36) - 0.05) < 1e-9


def test_centrar_mediana_en_el_retorno_supuesto():
    from src.analisisBonos import proyectarInversion, rendimientoAnualizado

    r = proyectarInversion(None, 0.07, 1000, 0, 120, volatilidadRespaldo=0.16, centrarMediana=True)["resumen"]
    assert abs(rendimientoAnualizado(r["valorMediano"], 1000, 120) - 0.07) < 0.006

"""Pruebas de los modelos, la senal, los bonos y la validacion del LLM."""

import numpy as np
import pandas as pd
from conftest import serieSintetica

from src.analisisBonos import metricasBono, proyectarInversion, puntuarBono, rankingBonos
from src.backtest import backtestSenal
from src.catalogoBonos import bonosDelPerfil
from src.datosEstructurados import calcularMetricasDescriptivas, clasificarRiesgo
from src.datosNoticias import resumirSentimiento
from src.modeloClasificacionRiesgo import entrenarClasificadorRiesgo, etiquetarRiesgo
from src.modeloPredictivo import NOMBRE_MEDIA, entrenarYEvaluar, pronosticarHorizonte
from src.motorPrescriptivo import (
    calcularRetornoEsperado,
    construirAsignacion,
    generarSenal,
    validarCifrasInforme,
)
from src.preparacionDatos import construirCaracteristicas, unirNavYSentimiento

SIN_NOTICIAS = resumirSentimiento(pd.DataFrame())


def test_paseo_aleatorio_no_tiene_habilidad_y_pronostico_arranca_al_dia_siguiente():
    historico = serieSintetica(1000, deriva=0.0, semilla=3)
    tabla = construirCaracteristicas(unirNavYSentimiento(historico, None), horizonte=21)
    resultado = entrenarYEvaluar(tabla, 21)
    assert resultado["exito"]
    assert "RandomForest" in set(resultado["tabla"]["Modelo"])
    if not resultado["tieneHabilidad"]:
        assert resultado["nombrePredictor"] == NOMBRE_MEDIA
    pronostico = pronosticarHorizonte(resultado, tabla, float(historico["nav"].iloc[-1]), historico.index[-1], 21)
    assert pronostico.index[0] > historico.index[-1]
    assert len(pronostico) == 21
    assert (pronostico["bandaInferior"] <= pronostico["navEstimado"]).all()


def test_clasificador_de_riesgo_usa_etiquetas_futuras():
    # 600 dias tranquilos y luego una crisis: la etiqueta de los dias previos a la crisis debe ser Alto
    historico = serieSintetica(1200, volatilidad=0.07, tramos=[(600, 700, -0.6, 0.45)], semilla=5)
    tabla = construirCaracteristicas(unirNavYSentimiento(historico, None), 1)
    etiquetada = etiquetarRiesgo(tabla, historico)
    indiceCrisis = etiquetada.index.get_indexer([historico.index[600]], method="nearest")[0]
    assert etiquetada["categoriaFutura"].iloc[indiceCrisis - 5] == "Alto"
    assert etiquetada["categoriaPasada"].iloc[indiceCrisis - 5] != "Alto"
    assert etiquetada["categoriaFutura"].tail(63).isna().all()
    resultado = entrenarClasificadorRiesgo(etiquetada)
    assert resultado["modelo"] is not None
    assert type(resultado["modelo"]).__name__ == "RandomForestClassifier"


def test_senal_reduce_en_tendencia_bajista():
    historico = serieSintetica(700, tramos=[(450, 700, -0.35, 0.25)], semilla=7)
    metricas = calcularMetricasDescriptivas(historico, None, 0.04)
    senal = generarSenal(metricas, {"rentabilidadProyectada": np.nan}, clasificarRiesgo(metricas), SIN_NOTICIAS, 21)
    assert senal["accion"] == "REDUCIR"
    pronostico = next(f for f in senal["factores"] if f["factor"] == "Pronóstico del modelo")
    assert not pronostico["activo"]


def test_backtest_produce_reducir_en_crisis():
    historico = serieSintetica(1500, tramos=[(900, 1100, -0.4, 0.3)], semilla=11)
    tabla, resumen = backtestSenal(historico, None, 21, 0.04)
    assert resumen["vecesReducir"] > 0
    assert set(tabla["accion"]) <= {"COMPRAR", "MANTENER", "REDUCIR"}


def test_retorno_esperado_usa_el_horizonte_real():
    metricas = {"retornoAnual": 0.10}
    corto = calcularRetornoEsperado(metricas, {"rentabilidadProyectada": 0.01, "tieneHabilidad": True}, 5)
    largo = calcularRetornoEsperado(metricas, {"rentabilidadProyectada": 0.01, "tieneHabilidad": True}, 90)
    assert corto > largo
    assert calcularRetornoEsperado(metricas, {"rentabilidadProyectada": 0.5, "tieneHabilidad": False}, 30) == 0.10


def _universo(rendimiento, volatilidad=0.02, deriva=0.04):
    universo = {}
    for i, bono in enumerate(bonosDelPerfil("Moderado")):
        universo[bono["ticker"]] = {
            "historico": serieSintetica(1000, deriva=deriva, volatilidad=volatilidad, semilla=20 + i),
            "ficha": {"rendimientoDistribucion": rendimiento, "gastoAnual": 0.0005},
        }
    return universo


def test_ranking_no_recomienda_si_rinde_menos_que_la_liquidez():
    tabla, resumen = rankingBonos(_universo(0.02), "Moderado", tasaLibre=0.045)
    assert (tabla["veredicto"] == "No recomendable").all()
    assert resumen["invertir"] is False
    asignacion = construirAsignacion("Moderado", {"accion": "MANTENER"}, tabla)
    assert not [f for f in asignacion["filas"] if f["clase"] == "Renta fija"]
    assert abs(sum(f["peso"] for f in asignacion["filas"]) - 1) < 1e-6


def test_ranking_y_asignacion_con_bonos_validos():
    tabla, resumen = rankingBonos(_universo(0.055), "Moderado", tasaLibre=0.04)
    assert resumen["invertir"] is True
    assert tabla["puesto"].tolist() == list(range(1, len(tabla) + 1))
    asignacion = construirAsignacion("Moderado", {"accion": "COMPRAR"}, tabla)
    bonos = [f for f in asignacion["filas"] if f["clase"] == "Renta fija"]
    assert 1 <= len(bonos) <= 3
    assert abs(sum(f["peso"] for f in asignacion["filas"]) - 1) < 1e-6


def test_veto_por_caida_fuera_de_tolerancia():
    historico = serieSintetica(800, tramos=[(500, 560, -1.5, 0.2)], semilla=4)
    m = metricasBono(historico, {"rendimientoDistribucion": 0.06}, 0.04)
    _, _, veredicto, motivos = puntuarBono(m, "Conservador")
    assert veredicto == "No recomendable"
    assert any("Caída" in motivo or "Volatilidad" in motivo for motivo in motivos)


def test_proyeccion_sin_volatilidad_es_interes_compuesto():
    fechas = pd.bdate_range(end="2026-10-09", periods=800)
    historico = pd.DataFrame({"nav": np.linspace(100, 110, 800)}, index=fechas)
    resultado = proyectarInversion(historico, 0.05, 1000, 0, 12, simulaciones=200)
    assert abs(resultado["resumen"]["valorMediano"] - 1050) < 2
    conAporte = proyectarInversion(historico, 0.0, 0, 100, 12, simulaciones=200)
    assert abs(conAporte["resumen"]["totalAportado"] - 1200) < 1e-9


def test_validador_detecta_cifras_inventadas():
    contexto = {"indicadores": {"retornoAnualPct": 13.51, "varDiario95Pct": -1.63}}
    texto = "Rindió 13.5% al año; su VaR es -1.6% y podría caer 5% en un día."
    assert validarCifrasInforme(texto, contexto) == ["5%"]

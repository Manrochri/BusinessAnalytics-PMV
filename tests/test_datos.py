"""Pruebas de la capa de datos y preparacion."""

import numpy as np
import pandas as pd
from conftest import serieSintetica

import src.utilidades as utilidades
from src.datosEstructurados import (
    benchmarkEsRetornoTotal,
    calcularMetricasDescriptivas,
    clasificarRiesgo,
    compararConBenchmark,
)
from src.datosNoticias import asignarDiaBursatil, construirSerieSentimiento, resumirSentimiento
from src.preparacionDatos import construirCaracteristicas, dividirTemporal, filasEtiquetadas, unirNavYSentimiento


def test_valor_o_defecto_atrapa_nan():
    assert utilidades.valorODefecto(np.nan, 0.15) == 0.15
    assert utilidades.valorODefecto(None, 1) == 1
    assert utilidades.valorODefecto(0.0, 0.15) == 0.0  # 'or' habria devuelto 0.15


def test_leer_tabla_descarta_indice_sin_nombre(tmp_path, monkeypatch):
    monkeypatch.setattr(utilidades, "RUTA_CACHE", tmp_path)
    (tmp_path / "holdings_X.csv").write_text(",ticker,nombre,peso\n0,AAA,Uno,0.1\n", encoding="utf-8")
    tabla = utilidades.leerTabla("holdings_X.csv", columnaFecha=None)
    assert list(tabla.columns) == ["ticker", "nombre", "peso"]


def test_benchmark_retorno_total():
    assert benchmarkEsRetornoTotal("^SP500TR")
    assert benchmarkEsRetornoTotal("VOO")
    assert not benchmarkEsRetornoTotal("^GSPC")


def test_clasificar_riesgo_con_faltantes():
    riesgo = clasificarRiesgo({"volatilidadAnual": np.nan, "maxDrawdown": -0.2, "beta": None})
    assert not np.isnan(riesgo["puntaje"])
    assert set(riesgo["supuestos"]) == {"volatilidad", "beta"}


def test_comparar_con_benchmark_desde_fecha_comun():
    fondo = serieSintetica(400, semilla=1)
    benchmark = serieSintetica(300, semilla=2)  # empieza despues que el fondo
    comparativo = compararConBenchmark(fondo, benchmark)
    assert comparativo.iloc[0].tolist() == [100.0, 100.0]
    assert comparativo["benchmark"].notna().all()


def test_metricas_diferencial_cero_contra_si_mismo():
    fondo = serieSintetica(600)
    metricas = calcularMetricasDescriptivas(fondo, fondo, 0.04)
    assert abs(metricas["diferencialBenchmark"]) < 1e-12
    assert abs(metricas["beta"] - 1) < 1e-9
    assert metricas["sobreMedia200"] in (True, False)


def test_noticias_de_fin_de_semana_y_despues_del_cierre():
    dias = pd.bdate_range("2026-09-14", "2026-09-25")
    noticias = pd.DataFrame({
        "fecha": pd.to_datetime(["2026-09-19 10:00", "2026-09-15 17:30", "2026-09-16 09:00"]),
        "sentimiento": [0.4, -0.2, 0.1], "relevancia": [1.0, 1.0, 1.0],
    })
    asignadas = asignarDiaBursatil(noticias, dias)["diaBursatil"].dt.strftime("%Y-%m-%d").tolist()
    assert asignadas == ["2026-09-21", "2026-09-16", "2026-09-16"]
    serie = construirSerieSentimiento(noticias, dias)
    assert serie["cantidadNoticias"].sum() == 3  # ninguna se pierde


def test_resumen_sentimiento_exige_noticias_recientes():
    noticias = pd.DataFrame({"fecha": pd.date_range("2026-09-01", periods=5), "sentimiento": [0.3] * 5,
                             "relevancia": [1.0] * 5, "fuente": ["X"] * 5})
    assert not resumirSentimiento(noticias)["suficiente"]


def test_caracteristicas_conservan_el_ultimo_dia():
    historico = serieSintetica(500)
    tabla = construirCaracteristicas(unirNavYSentimiento(historico, None), horizonte=10)
    assert tabla.index[-1] == historico.index[-1]
    assert tabla["objetivo"].tail(10).isna().all()
    assert "nav" not in tabla.columns.difference(["nav"]).tolist()


def test_division_temporal_con_purga():
    historico = serieSintetica(800)
    tabla = filasEtiquetadas(construirCaracteristicas(unirNavYSentimiento(historico, None), horizonte=21))
    partes = dividirTemporal(tabla, 21)
    posicion = {f: i for i, f in enumerate(tabla.index)}
    assert posicion[partes["validacion"].index[0]] - posicion[partes["entrenamiento"].index[-1]] > 21
    assert posicion[partes["prueba"].index[0]] - posicion[partes["validacion"].index[-1]] > 21

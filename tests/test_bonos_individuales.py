"""Pruebas de la cartera N-PORT, la evaluacion bono por bono, el plan de compra y la historia de noticias."""

from pathlib import Path

import numpy as np
import pandas as pd

import src.utilidades as utilidades
from src.bonosIndividuales import (
    duracionModificada,
    evaluarBonos,
    evaluarSeleccion,
    planDeCompra,
    precioDesdeTir,
    proyectarBonos,
    resumirEmisores,
    tirDesdePrecio,
)
from src.datosSec import parsearNport, urlDocumentoPrincipal
from src.motorPrescriptivo import construirAsignacion, construirPlanAccion

DATOS = Path(__file__).parent / "datos"
CURVA = {0.25: 0.039, 5.0: 0.041, 10.0: 0.043, 30.0: 0.047}


def cartera():
    return parsearNport((DATOS / "nport_ejemplo.xml").read_bytes())


def test_parsear_nport():
    tabla, meta = cartera()
    assert meta["serie"] == "S000000001" and meta["fechaReporte"] == "2026-06-30"
    assert len(tabla) == 6 and tabla["esDeuda"].sum() == 5
    tesoro = tabla.iloc[0]
    assert tesoro["isin"] == "US91282CAA10" and tesoro["cuponPct"] == 4.0 and tesoro["tipoEmisor"] == "UST"
    assert bool(tabla.loc[tabla["emisor"] == "Quebrada Inc", "enImpago"].iloc[0])


def test_url_documento_principal():
    url = "https://www.sec.gov/Archives/edgar/data/36405/000175272425000001/0001752724-25-000001-index.htm"
    assert urlDocumentoPrincipal(url) == "https://www.sec.gov/Archives/edgar/data/36405/000175272425000001/primary_doc.xml"


def test_matematica_de_bonos():
    assert abs(precioDesdeTir(0.05, 10, 0.05) - 100) < 1e-9
    assert abs(precioDesdeTir(0.0, 10, 0.05) - 100 / 1.025 ** 20) < 1e-9
    assert abs(tirDesdePrecio(95, 0.04, 7.3) - 0.04956) < 1e-4
    assert abs(duracionModificada(0.05, 10, 0.05) - 7.79) < 0.01


def test_evaluacion_respeta_el_perfil():
    tabla, meta = cartera()
    conservador = evaluarBonos(tabla, "Conservador", CURVA, 0.039, meta["fechaReporte"], "2026-07-01").set_index("emisor")
    agresivo = evaluarBonos(tabla, "Agresivo", CURVA, 0.039, meta["fechaReporte"], "2026-07-01")
    # El corporativo largo (duracion ~10) no sirve a un conservador
    largo = conservador.loc[conservador["titulo"].str.contains("2045")].iloc[0]
    assert largo["veredicto"] == "No recomendable" and "Duración" in largo["motivo"]
    # El bono en impago nunca es recomendable
    assert (agresivo.loc[agresivo["emisor"] == "Quebrada Inc", "veredicto"] == "No recomendable").all()
    # El Tesoro se clasifica como tal y sin perdida esperada
    tesoro = agresivo.loc[agresivo["emisor"] == "United States Treasury"].iloc[0]
    assert tesoro["calidad"] == "Tesoro EE.UU." and tesoro["perdidaEsperada"] == 0
    # Mayor diferencial -> peor calidad implicita y mayor perdida esperada
    riesgosa = agresivo.loc[agresivo["emisor"] == "Riesgosa Corp"].iloc[0]
    assert riesgosa["calidad"] == "CCC o menor" and riesgosa["rendimientoEsperado"] < riesgosa["tir"]


def test_emisores_agrupan_por_lei():
    tabla, meta = cartera()
    emisores = resumirEmisores(evaluarBonos(tabla, "Agresivo", CURVA, 0.039, meta["fechaReporte"], "2026-07-01"))
    solida = emisores.loc[emisores["emisor"] == "Empresa Solida SA"].iloc[0]
    assert solida["bonos"] == 2 and abs(solida["pesoFondoPct"] - 29.8) < 1e-9


def test_plan_de_compra_usa_lotes_y_el_sobrante():
    seleccion = pd.DataFrame({
        "clave": ["a", "b", "c"], "emisor": ["T", "X", "Y"], "cusip": ["1", "2", "3"], "veredicto": ["Recomendable"] * 3,
        "precio": [103.0, 101.3, 101.7], "calidad": ["Tesoro EE.UU.", "BBB", "BBB"], "cupon": [0.04, 0.05, 0.05],
        "tir": [0.04, 0.05, 0.05], "rendimientoEsperado": [0.04, 0.049, 0.049], "plazoEfectivo": [2.0, 3.0, 4.0],
        "vencimiento": pd.to_datetime(["2028-10-01", "2029-10-01", "2030-10-01"]), "probImpago": [0.0, 0.0015, 0.0015],
        "duracion": [1.9, 2.8, 3.6],
    })
    plan, sobrante = planDeCompra(seleccion, 3000)
    assert (plan["lotes"] > 0).all()                    # el reparto exacto (1 000 c/u) no compraba ninguno de 1 013
    assert abs(plan["costo"].sum() + sobrante - 3000) < 1e-6
    assert plan.loc[plan["clave"] == "a", "lote"].iloc[0] == 100


def test_proyeccion_sin_riesgo_es_interes_compuesto():
    plan = pd.DataFrame([{"clave": "z", "nominalComprado": 1000.0, "cupon": 0.0, "plazo": 2.0, "probImpago": 0.0,
                          "tir": 0.05, "costo": 1000 / 1.025 ** 4}])
    sinCambios = np.zeros((10, 4))
    r = proyectarBonos(plan, 0.0, 24, 0.0, np.array([0.25, 5, 10, 30]), sinCambios, simulaciones=50)["resumen"]
    assert abs(r["valorMediano"] - 1000) < 1e-6 and r["probabilidadPerdida"] == 0


def test_seleccion_con_bono_no_recomendable_se_marca():
    tabla, meta = cartera()
    evaluados = evaluarBonos(tabla, "Conservador", CURVA, 0.039, meta["fechaReporte"], "2026-07-01")
    coherencia = evaluarSeleccion(evaluados.loc[evaluados["veredicto"] == "No recomendable"].head(1), "Conservador")
    assert coherencia["estado"] == "riesgo"
    asignacion = construirAsignacion("Conservador", {"accion": "MANTENER"}, None, evaluados.head(2), "XYZ", "VFIAX")
    assert abs(sum(f["peso"] for f in asignacion["filas"]) - 1) < 1e-6
    assert any(f["cusip"] for f in asignacion["filas"] if f["clase"] == "Renta fija")
    assert "VFIAX" in asignacion["filas"][0]["detalle"]
    plan = construirPlanAccion({"accion": "MANTENER"}, "VFIAX", {"categoria": "Moderado"}, "Conservador", {},
                               asignacion, coherencia=coherencia)
    assert any("reemplazar" in paso["accion"] for paso in plan)


def test_noticias_se_acumulan(tmp_path, monkeypatch):
    import src.datosNoticias as noticias

    monkeypatch.setattr(utilidades, "RUTA_CACHE", tmp_path)
    lote1 = pd.DataFrame({"fecha": pd.to_datetime(["2026-09-01 10:00", "2026-09-02 10:00"]), "titulo": ["a", "b"],
                          "fuente": ["X", "X"], "url": ["http://x/a", "http://x/b"], "resumen": ["", ""],
                          "sentimiento": [0.2, -0.1], "etiqueta": ["", ""], "relevancia": [1.0, 1.0]})
    lote2 = lote1.copy()
    lote2.loc[1, ["titulo", "url"]] = ["c", "http://x/c"]
    noticias._fusionarYGuardar(lote1, "noticias_TEST.csv")
    tabla, agregadas = noticias._fusionarYGuardar(lote2, "noticias_TEST.csv")
    assert len(tabla) == 3 and agregadas == 1

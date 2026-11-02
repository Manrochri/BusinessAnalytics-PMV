"""Informe estructurado del LLM: formato, coherencia con las reglas, registro, limite diario y costo."""

import json

import pandas as pd

import src.motorPrescriptivo as mp
import src.registroLlm as rl
from src.backtest import simularEstrategia
from src.modeloPredictivo import evaluarDeterioro


def _respuestaGemini(objeto, entrada=1200, salida=300):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(objeto, ensure_ascii=False)}]}}],
            "usageMetadata": {"promptTokenCount": entrada, "candidatesTokenCount": salida}}


INFORME = {"accion": "Invertir", "justificacion": "Puedes invertir el monto completo. Rinde 4.43% al año.",
           "comportamientoDelFondo": "Volatilidad 6%.", "bonosYAsignacion": "VICSX 35%.",
           "riesgos": ["Suben las tasas", "Crédito", "Inflación"], "nivelConfianza": "alta", "alternativas": ["Liquidez al 3.97%"]}


def test_parseo_y_validacion_del_informe():
    informe, problemas = mp.parsearInformeEstructurado("```json\n" + json.dumps(INFORME) + "\n```", {"decision": "Invertir"})
    assert informe["accion"] == "Invertir" and informe["accionCoincide"] and not problemas
    assert "### ¿Invertir o no? · Invertir" in mp.informeAMarkdown(informe) and "Alternativas" in mp.informeAMarkdown(informe)
    distinto, problemas = mp.parsearInformeEstructurado(json.dumps(dict(INFORME, accion="Esperar", nivelConfianza="segura")), {"decision": "Invertir"})
    assert distinto["accion"] == "Invertir" and distinto["accionDelLlm"] == "Esperar" and distinto["nivelConfianza"] == "media"
    assert any("no coincide" in p for p in problemas) and any("confianza" in p for p in problemas)
    incompleto, problemas = mp.parsearInformeEstructurado(json.dumps({"accion": "Invertir"}), {})
    assert incompleto is None and problemas
    assert mp.parsearInformeEstructurado("texto suelto", {})[0] is None


def test_informe_llm_valida_registra_y_respeta_el_limite(tmp_path, monkeypatch):
    monkeypatch.setattr(rl, "RUTA_SALIDAS", tmp_path)
    monkeypatch.setattr(mp, "GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(mp, "LLM_MAXIMO_LLAMADAS_DIA", 2)
    llamadas = []

    class Respuesta:
        def __init__(self, datos):
            self._datos = datos

        def raise_for_status(self):
            pass

        def json(self):
            return self._datos

    def postFalso(url, headers=None, json=None, timeout=None):
        llamadas.append(json)
        if len(llamadas) == 1:  # primera respuesta con formato invalido: debe reintentar
            return Respuesta({"candidates": [{"content": {"parts": [{"text": "no es json"}]}}]})
        return Respuesta(_respuestaGemini(INFORME))

    monkeypatch.setattr(mp.requests, "post", postFalso)
    contexto = {"fondo": {"ticker": "VICSX"}, "conclusion": {"decision": "Invertir"},
                "indicadores": {"rendimientoPct": 4.43, "volatilidadPct": 6.0, "tasaLibrePct": 3.97, "pesoPct": 35}}
    proveedor = ("gemini", {"disponible": True, "modeloListo": True, "mensaje": ""}, True)
    texto, usado, sospechosas, informe, detalle = mp.generarExplicacionLLM(contexto, "Moderado", proveedor)
    assert usado == "gemini" and informe["accion"] == "Invertir" and len(llamadas) == 2
    assert llamadas[1]["generationConfig"]["responseMimeType"] == "application/json"
    assert detalle["tokensEntrada"] == 1200 and abs(detalle["costoUsd"] - (1200 / 1e6 * 0.10 + 300 / 1e6 * 0.40)) < 1e-9
    registro = rl.leerRegistro()
    assert len(registro) == 1 and registro[0]["accion"] == "Invertir" and registro[0]["proveedor"] == "gemini"
    assert rl.llamadasHoy() == 1 and rl.resumenCostos()["informes"] == 1
    # Segunda consulta ok; la tercera supera el limite diario y cae al informe de reglas
    mp.generarExplicacionLLM(contexto, "Moderado", proveedor)
    texto, usado, sospechosas, informe, detalle = mp.generarExplicacionLLM(contexto, "Moderado", proveedor)
    assert texto is None and informe is None and detalle["limite"]
    assert mp.chatearConLLM([{"role": "user", "content": "hola"}], contexto, "Moderado", proveedor) == (None, "gemini")


def test_backtest_con_comisiones_y_deterioro():
    diario = pd.bdate_range("2024-01-01", periods=300)
    nav = pd.Series([100 * 1.0004 ** i for i in range(300)], index=diario)
    fechas = list(diario[4::5][:60])
    posicion = {f: i for i, f in enumerate(diario)}
    tabla = pd.DataFrame({"fecha": fechas, "accion": ["COMPRAR"] * 30 + ["REDUCIR"] * 30})
    r = simularEstrategia(nav, tabla, posicion, 0.04, 0.001)
    assert r["operaciones"] == 1 and r["retornoAcumuladoComprarMantener"] > r["retornoAcumuladoEstrategia"]
    assert r["caidaMaximaComprarMantener"] <= 0 and len(r["curvaEstrategia"]) == 60
    alertas = evaluarDeterioro({"exito": True, "habilidad": 0.0, "cobertura90": 70.0},
                               {"retornoAnualEstrategia": 0.01, "retornoAnualComprarMantener": 0.05}, {"modelo": object(), "superaPersistencia": False})
    assert len(alertas) == 4 and evaluarDeterioro({"exito": False}) == []
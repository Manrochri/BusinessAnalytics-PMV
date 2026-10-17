"""
predictivo.py
Dashboard 2 — ¿Qué podría pasar? Pronóstico directo del NAV con banda
calibrada, comparación honesta contra líneas base, y el RandomForestClassifier
de riesgo para los próximos 3 meses.
"""

import numpy as np
import pandas as pd
import streamlit as st

from src.estilos import abrirPanel
from src.graficos import graficarImportanciaVariables, graficarPronostico
from src.preparacionDatos import COBERTURA_MINIMA_SENTIMIENTO
from src.utilidades import formatearMoneda, formatearPorcentaje
from src.vistas.comunes import filaTarjetas, formatearFecha


def dibujarModelos(datos):
    modelo = datos["modelo"]
    with abrirPanel("Comparación de modelos (validación y prueba)"):
        tabla = modelo["tabla"].copy()
        for columna in ("MAE validación (pp)", "MAE prueba (pp)", "RMSE prueba (pp)"):
            tabla[columna] = tabla[columna].round(2)
        tabla["R² prueba"] = tabla["R² prueba"].round(3)
        tabla["Acierto dirección prueba %"] = tabla["Acierto dirección prueba %"].round(1)
        tabla["Habilidad vs línea base %"] = tabla["Habilidad vs línea base %"].round(1)
        st.dataframe(tabla, use_container_width=True, hide_index=True, key="predictivo_dataframe_1")
        periodos = modelo.get("periodos", {})
        textoPeriodos = " · ".join(
            f"{k}: {formatearFecha(v[0])} → {formatearFecha(v[1])}" for k, v in periodos.items()
        )
        st.caption(
            f"Objetivo: retorno a {modelo['horizonte']} días hábiles. El modelo se elige por el MAE de validación y se "
            "reporta en prueba, un tramo posterior que no participó en la elección. Habilidad = cuánto reduce el error "
            f"frente a la mejor línea base. Entre conjuntos se descartan {modelo['horizonte']} días para evitar fugas. "
            f"{textoPeriodos}."
        )


def dibujarImportancia(datos, modelo):
    """Importancia de las variables: del predictor usado o, si es la media historica, del mejor modelo de ML como referencia."""
    importancia = datos.get("importancia")
    if importancia is None or importancia.empty:
        st.info("No hay importancias que mostrar: ningún modelo de machine learning se pudo entrenar.")
        return
    if datos.get("importanciaEsReferencia"):
        st.caption(f"**Referencia:** variables en las que más se apoyó el mejor modelo de ML (**{modelo['mejorNombre']}**). "
                   "Como no superó a la línea base, el pronóstico usa la media histórica: estas variables no mueven el "
                   "resultado, pero muestran qué información intentó aprovechar el modelo.")
    else:
        st.caption(f"Variables del predictor usado (**{modelo['nombrePredictor']}**), que sí supera a la línea base.")
    st.plotly_chart(graficarImportanciaVariables(importancia), use_container_width=True, key="predictivo_plotly_chart_2")
    st.caption("Importancia relativa (suma 100%): reducción del error en los modelos de árboles y |coeficiente| "
               "estandarizado en Ridge; en el ensamble, el promedio de sus miembros.")


def dibujarEstadoSentimiento(datos, modelo):
    """Si el sentimiento entra al modelo y, si no, cuántos meses de tono de prensa faltan para que entre."""
    cobertura = modelo.get("coberturaSentimiento", 0.0) or 0.0
    if modelo.get("incluirSentimiento"):
        st.success(f"El sentimiento de la prensa participa como variable: {cobertura:.0%} de los días de entrenamiento tienen dato.")
        return
    inicio, fin = modelo.get("periodos", {}).get("entrenamiento", (None, None))
    inicioTono = datos.get("inicioTono")
    texto = (f"**El sentimiento no entra al modelo:** solo {cobertura:.0%} de los días de entrenamiento"
             + (f" ({inicio:%m/%Y} – {fin:%m/%Y})" if inicio is not None else "")
             + f" tienen dato, y el mínimo es {COBERTURA_MINIMA_SENTIMIENTO:.0%}.")
    if inicio is None or fin is None:
        st.warning(texto)
        return
    # El tono cubre desde su inicio hasta hoy: para llegar al minimo debe empezar antes de esta fecha
    fechaNecesaria = fin - (fin - inicio) * COBERTURA_MINIMA_SENTIMIENTO - pd.Timedelta(days=30)
    if inicioTono is None:
        texto += (f" Aún no hay historia del tono de prensa de {datos.get('temaTono', 'este fondo')}. Para incluirlo, completa "
                  f"la historia hasta {fechaNecesaria:%m/%Y}")
        meses = int(np.ceil((pd.Timestamp.today() - fechaNecesaria).days / 30.4))
    else:
        meses = max(int(np.ceil((inicioTono - fechaNecesaria).days / 30.4)), 3)
        texto += (f" El tono de prensa ({datos.get('temaTono', '')}) empieza el {inicioTono:%d/%m/%Y}. Para incluirlo, "
                  f"completa unos **{meses} meses** más (hasta {fechaNecesaria:%m/%Y})")
    st.warning(texto + " en la barra lateral → «Historia del tono de prensa» (≈ 5 s por cada 3 meses) y presiona "
                       "«Actualizar datos». Mientras tanto, el sentimiento sí participa en la señal del Prescriptivo "
                       "cuando hay 120 días de tono.")


def dibujarClasificador(datos):
    clasificador = datos.get("clasificadorRiesgo", {})
    with abrirPanel("Riesgo de los próximos 3 meses (RandomForestClassifier)"):
        if clasificador.get("modelo") is None:
            st.info(clasificador.get("mensaje") or "No hay suficiente historial para el clasificador de riesgo.")
            return
        supera = clasificador["superaPersistencia"]
        filaTarjetas([
            {"etiqueta": "Categoría predicha", "valor": str(clasificador["categoriaActual"]),
             "nota": "Próximos 63 días hábiles"},
            {"etiqueta": "Últimos 3 meses", "valor": str(clasificador.get("categoriaPasadaActual") or "N/D"),
             "nota": "Riesgo realizado (persistencia)"},
            {"etiqueta": "F1 macro (prueba)", "valor": f"{clasificador['f1Macro']:.2f}",
             "nota": f"Persistencia: {clasificador['f1Persistencia']:.2f}"},
            {"etiqueta": "Accuracy (prueba)", "valor": formatearPorcentaje(clasificador["accuracy"], 0),
             "nota": f"Persistencia: {formatearPorcentaje(clasificador['accuracyPersistencia'], 0)}"},
        ])
        (st.success if supera else st.warning)(
            "El clasificador supera a la línea base de persistencia en F1: su predicción se usa en las alertas de perfil."
            if supera else
            "El clasificador NO supera a la persistencia: se muestra como referencia y no se usa en las alertas."
        )
        columnas = st.columns([2, 3, 3])
        with columnas[0]:
            st.dataframe(pd.DataFrame({"Categoría": list(clasificador["probabilidades"].keys()),
                                       "Probabilidad": [f"{v:.0%}" for v in clasificador["probabilidades"].values()]}),
                         use_container_width=True, hide_index=True, key="predictivo_dataframe_3")
        with columnas[1]:
            st.caption("Matriz de confusión (tramo de prueba)")
            st.dataframe(clasificador["matrizConfusion"], use_container_width=True, key="predictivo_dataframe_4")
        with columnas[2]:
            st.plotly_chart(graficarImportanciaVariables(clasificador["importancia"].head(8)), use_container_width=True, key="predictivo_plotly_chart_5")
        st.caption(
            "Etiqueta = riesgo REALIZADO en los 63 días siguientes: Bajo si la volatilidad anualizada es < 12% y la peor "
            "caída > −5%; Alto si la volatilidad ≥ 20% o la caída ≤ −10%; Moderado en medio. Las variables solo usan "
            f"datos hasta cada fecha. Distribución histórica: {clasificador.get('distribucion', {})}."
        )


def dibujarDashboardPredictivo(datos):
    """Pestaña Predictivo."""
    modelo, resumen, riesgoFuturo = datos["modelo"], datos["resumenPronostico"], datos["riesgoFuturo"]
    if not modelo.get("exito") or datos["pronostico"].empty:
        st.warning(modelo.get("mensaje") or "No se pudo generar el pronóstico. Amplía el periodo histórico.")
        dibujarClasificador(datos)
        return

    if not modelo["tieneHabilidad"]:
        st.warning(
            f"Ningún modelo superó a las líneas base en el tramo de prueba (mejor: {modelo['mejorNombre']}, "
            f"habilidad {modelo['habilidad']:+.1%}). El pronóstico muestra la **media histórica** con su banda "
            "y la señal no lo usa. Es lo esperable en un fondo indexado (de acciones o de bonos): su precio es difícil de anticipar."
        )

    tono = "positivo" if (resumen["rentabilidadProyectada"] or 0) >= 0 else "negativo"
    filaTarjetas([
        {"etiqueta": f"Valor proyectado ({datos['diasPronostico']} días)", "valor": formatearMoneda(resumen["valorProyectado"]),
         "nota": f"Predictor: {modelo['nombrePredictor']}"},
        {"etiqueta": "Rentabilidad proyectada", "valor": formatearPorcentaje(resumen["rentabilidadProyectada"], 1, True), "tono": tono,
         "nota": f"Probabilidad de alza: {formatearPorcentaje(resumen['probabilidadAlza'], 0)}"},
        {"etiqueta": "Banda 90%", "valor": f"{formatearMoneda(resumen['bandaInferior'])} – {formatearMoneda(resumen['bandaSuperior'])}",
         "nota": f"Cobertura real en prueba: {modelo['cobertura90']:.0f}%"},
        {"etiqueta": "Habilidad vs línea base", "valor": formatearPorcentaje(modelo["habilidad"], 1, True),
         "tono": "positivo" if modelo["tieneHabilidad"] else "negativo", "nota": f"Mejor modelo: {modelo['mejorNombre']}"},
    ])
    st.write("")
    with abrirPanel(f"Pronóstico del NAV — {datos['diasPronostico']} días hábiles"):
        st.plotly_chart(graficarPronostico(datos["historico"], datos["pronostico"]), use_container_width=True, key="predictivo_plotly_chart_6")
        st.caption(
            f"Pronóstico directo del retorno a {datos['diasPronostico']} días desde el último dato "
            f"({formatearFecha(datos['fechaDatoFinal'])}). La banda sale de los errores de validación; en el tramo de "
            f"prueba contuvo al {modelo['cobertura90']:.0f}% de los resultados reales (ideal: ~90%)."
        )

    columnas = st.columns([3, 2])
    with columnas[0]:
        dibujarModelos(datos)
    with columnas[1], abrirPanel("Variables más influyentes"):
        dibujarImportancia(datos, modelo)
        dibujarEstadoSentimiento(datos, modelo)

    with abrirPanel("Riesgo prospectivo"):
        filaTarjetas([
            {"etiqueta": "Escenario adverso (P5)", "valor": formatearPorcentaje(riesgoFuturo.get("perdidaEsperadaPeor"), 1, True),
             "tono": "negativo", "nota": f"En {datos['diasPronostico']} días hábiles"},
            {"etiqueta": "Amplitud de la banda", "valor": formatearPorcentaje(riesgoFuturo.get("amplitudBanda"))},
            {"etiqueta": "Nivel de riesgo prospectivo", "valor": str(riesgoFuturo.get("nivel", "N/D")),
             "nota": f"Puntaje {riesgoFuturo.get('puntaje', 'N/D')}/10"},
        ])
        st.caption("Bajo si la pérdida en el escenario P5 es menor a 3%; Moderado hasta 8%; Alto por encima.")
    dibujarClasificador(datos)
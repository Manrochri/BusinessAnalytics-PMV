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
from src.utilidades import esNulo, formatearMoneda, formatearPorcentaje
from src.vistas.comunes import ANCHO, filaTarjetas, formatearFecha, tablaHtml


def dibujarModelos(datos):
    modelo = datos["modelo"]
    with st.container():
        tabla = modelo["tabla"].copy()
        for columna in ("MAE validación (pp)", "MAE prueba (pp)", "RMSE prueba (pp)"):
            tabla[columna] = tabla[columna].round(2)
        tabla["R² prueba"] = tabla["R² prueba"].round(3)
        tabla["Acierto dirección prueba %"] = tabla["Acierto dirección prueba %"].round(1)
        tabla["Habilidad vs línea base %"] = tabla["Habilidad vs línea base %"].round(1)
        tablaHtml(tabla)
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
    st.plotly_chart(graficarImportanciaVariables(importancia), **ANCHO, key="predictivo_plotly_chart_2")
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
    st.warning(texto + " en el menú lateral → «Historia de noticias» (≈ 5 s por cada 3 meses) y presiona "
                       "«Actualizar datos». Mientras tanto, el sentimiento sí participa en la señal del Prescriptivo "
                       "cuando hay 120 días de tono.")


def dibujarClasificador(datos):
    clasificador = datos.get("clasificadorRiesgo", {})
    with st.container():
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
            tablaHtml(pd.DataFrame({"Categoría": list(clasificador["probabilidades"].keys()),
                                    "Probabilidad": [f"{v:.0%}" for v in clasificador["probabilidades"].values()]}))
        with columnas[1]:
            st.caption("Matriz de confusión (tramo de prueba)")
            tablaHtml(clasificador["matrizConfusion"], mostrarIndice=True)
        with columnas[2]:
            st.plotly_chart(graficarImportanciaVariables(clasificador["importancia"].head(8)), **ANCHO, key="predictivo_plotly_chart_5")
        st.caption(
            "Etiqueta = riesgo REALIZADO en los 63 días siguientes: Bajo si la volatilidad anualizada es < 12% y la peor "
            "caída > −5%; Alto si la volatilidad ≥ 20% o la caída ≤ −10%; Moderado en medio. Las variables solo usan "
            f"datos hasta cada fecha. Distribución histórica: {clasificador.get('distribucion', {})}."
        )


def tablaMetricasInforme(datos):
    """
    Tabla «modelo del equipo vs. línea base» sobre datos de prueba (los que el
    modelo no vio): clasificador de riesgo, regresion del retorno y backtest
    de la señal con comisiones. Es la tabla F5 del cuestionario del curso.
    """
    modelo, c, r = datos.get("modelo") or {}, datos.get("clasificadorRiesgo") or {}, datos.get("resumenBacktest") or {}
    tabla = modelo.get("tabla")
    f = lambda v, d=2: "N/D" if esNulo(v) else f"{v:.{d}f}"  # noqa: E731
    p = lambda v, d=1: "N/D" if esNulo(v) else f"{v * 100:+.{d}f}%"  # noqa: E731
    q = lambda v, d=0: "N/D" if esNulo(v) else f"{v * 100:.{d}f}%"  # noqa: E731  (sin signo)
    pct = lambda v, d=1: "N/D" if esNulo(v) else f"{v:.{d}f}%"  # noqa: E731  (ya en porcentaje)
    regresion = {}
    if tabla is not None and not tabla.empty and modelo.get("mejorNombre"):
        porModelo = tabla.set_index("Modelo")
        mejor = porModelo.loc[modelo["mejorNombre"]]
        bases = porModelo.loc[porModelo["Tipo"] == "Línea base"]
        base = bases.sort_values("MAE prueba (pp)").iloc[0] if not bases.empty else None
        regresion = {"mae": (mejor["MAE prueba (pp)"], None if base is None else base["MAE prueba (pp)"]),
                     "rmse": (mejor["RMSE prueba (pp)"], None if base is None else base["RMSE prueba (pp)"]),
                     "direccion": (mejor["Acierto dirección prueba %"], None if base is None else base["Acierto dirección prueba %"]),
                     "nombreBase": None if base is None else base.name, "nombre": modelo["mejorNombre"]}
    filas = [
        {"Métrica": "Exactitud (accuracy) · clasificador de riesgo", "Modelo del equipo": q(c.get("accuracy")),
         "Línea base": q(c.get("accuracyPersistencia")) + " (persistencia)"},
        {"Métrica": "Precisión (macro) · clasificador", "Modelo del equipo": f(c.get("precisionMacro")), "Línea base": f(c.get("precisionPersistencia"))},
        {"Métrica": "Sensibilidad / recall (macro) · clasificador", "Modelo del equipo": f(c.get("recallMacro")), "Línea base": f(c.get("recallPersistencia"))},
        {"Métrica": "F1 macro · clasificador", "Modelo del equipo": f(c.get("f1Macro")), "Línea base": f(c.get("f1Persistencia"))},
        {"Métrica": "AUC-ROC (uno contra el resto) · clasificador", "Modelo del equipo": f(c.get("aucOvr")), "Línea base": "0.50 (azar)"},
        {"Métrica": f"MAE del retorno a {modelo.get('horizonte', datos.get('diasPronostico'))} días (pp) · {regresion.get('nombre', 'regresión')}",
         "Modelo del equipo": f(regresion.get("mae", (None,))[0]), "Línea base": f(regresion.get("mae", (None, None))[1]) + (f" ({regresion['nombreBase']})" if regresion.get("nombreBase") else "")},
        {"Métrica": "RMSE del retorno (pp) · regresión", "Modelo del equipo": f(regresion.get("rmse", (None,))[0]), "Línea base": f(regresion.get("rmse", (None, None))[1])},
        {"Métrica": "Acierto de dirección · regresión", "Modelo del equipo": pct(regresion.get("direccion", (None,))[0]), "Línea base": pct(regresion.get("direccion", (None, None))[1])},
        {"Métrica": f"Retorno simulado anual · señal con comisión de {r.get('comision', 0):.2%} por operación",
         "Modelo del equipo": p(r.get("retornoAnualEstrategia")), "Línea base": p(r.get("retornoAnualComprarMantener")) + " (comprar y mantener)"},
        {"Métrica": f"Retorno acumulado en {r.get('aniosSimulados', 0):.1f} años · {r.get('operaciones', 0)} operaciones",
         "Modelo del equipo": p(r.get("retornoAcumuladoEstrategia")), "Línea base": p(r.get("retornoAcumuladoComprarMantener"))},
        {"Métrica": "Caída máxima (max drawdown) · backtest", "Modelo del equipo": p(r.get("caidaMaximaEstrategia")), "Línea base": p(r.get("caidaMaximaComprarMantener"))},
    ]
    return pd.DataFrame(filas)


def exportarMetricas(datos):
    """
    Libro de Excel con todo lo que pide el informe: la tabla F5, el detalle por
    clase, la comparación de modelos, el backtest por señal y los avisos de
    deterioro. Devuelve los bytes del .xlsx (o None si no hay openpyxl).
    """
    import io

    c, modelo, r = datos.get("clasificadorRiesgo") or {}, datos.get("modelo") or {}, datos.get("resumenBacktest") or {}
    hojas = {"Métricas F5": tablaMetricasInforme(datos)}
    if c.get("porClase") is not None and not c["porClase"].empty:
        hojas["Clasificador por clase"] = c["porClase"]
    if c.get("matrizConfusion") is not None and not c["matrizConfusion"].empty:
        hojas["Matriz de confusión"] = c["matrizConfusion"].reset_index()
    if modelo.get("tabla") is not None and not modelo["tabla"].empty:
        hojas["Comparación de modelos"] = modelo["tabla"]
    if r.get("porAccion") is not None:
        hojas["Backtest por señal"] = r["porAccion"].reset_index()
    if r.get("curvaEstrategia") is not None:
        hojas["Curva del backtest"] = pd.DataFrame({"fecha": r["curvaEstrategia"].index, "señal (con comisiones)": r["curvaEstrategia"].values,
                                                    "comprar y mantener": r["curvaComprarMantener"].values})
    hojas["Deterioro y contexto"] = pd.DataFrame(
        [{"Concepto": "Fondo", "Valor": datos.get("ticker")}, {"Concepto": "Horizonte (días hábiles)", "Valor": datos.get("diasPronostico")},
         {"Concepto": "Modelo elegido", "Valor": modelo.get("mejorNombre")}, {"Concepto": "Habilidad vs línea base", "Valor": modelo.get("habilidad")},
         {"Concepto": "Cobertura banda 90 % (prueba)", "Valor": modelo.get("cobertura90")},
         {"Concepto": "Filas entrenamiento / validación / prueba", "Valor": str(modelo.get("filas"))},
         {"Concepto": "Comisión por operación", "Valor": r.get("comision")}, {"Concepto": "Operaciones en el backtest", "Valor": r.get("operaciones")},
         {"Concepto": "Modelo guardado en", "Valor": datos.get("rutaModelo")}, {"Concepto": "Duración del análisis (s)", "Valor": datos.get("duracionAnalisisSeg")}]
        + [{"Concepto": "Aviso de deterioro", "Valor": texto} for _, texto in (datos.get("deterioro") or [])])
    try:
        salida = io.BytesIO()
        with pd.ExcelWriter(salida, engine="openpyxl") as escritor:
            for nombre, tabla in hojas.items():
                tabla.to_excel(escritor, sheet_name=nombre[:31], index=False)
                hoja = escritor.sheets[nombre[:31]]
                for columna in hoja.columns:
                    ancho = max(len(str(celda.value)) if celda.value is not None else 0 for celda in columna)
                    hoja.column_dimensions[columna[0].column_letter].width = min(max(12, ancho + 2), 70)
        return salida.getvalue()
    except Exception:  # sin openpyxl: el CSV de la tabla F5 sigue disponible
        return None


def dibujarMetricasInforme(datos):
    tabla = tablaMetricasInforme(datos)
    tablaHtml(tabla)
    columnas = st.columns([1, 1, 2])
    excel = exportarMetricas(datos)
    if excel:
        columnas[0].download_button("Descargar métricas (Excel)", data=excel, key="descargarMetricasXlsx",
                                    file_name=f"metricas_{datos['ticker']}_{datos['diasPronostico']}d.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", **ANCHO)
    columnas[1].download_button("Descargar tabla (CSV)", data=tabla.to_csv(index=False).encode("utf-8-sig"), key="descargarMetricasCsv",
                                file_name=f"metricas_{datos['ticker']}_{datos['diasPronostico']}d.csv", mime="text/csv", **ANCHO)
    c = datos.get("clasificadorRiesgo") or {}
    st.caption(f"Todas las métricas se miden en el tramo de PRUEBA (posterior al entrenamiento, con purga). Clasificador: "
               f"{c.get('filasPrueba', 0)} días de prueba. Regresión: el mejor modelo en validación frente a la mejor línea base. "
               "Backtest: semana a semana, invertido salvo cuando la señal dice REDUCIR, descontando la comisión en cada entrada o salida.")
    porClase = c.get("porClase")
    if porClase is not None and not porClase.empty:
        vista = porClase.copy()
        vista["Precisión"] = vista["Precisión"].map(lambda v: f"{v:.2f}")
        vista["Sensibilidad"] = vista["Sensibilidad"].map(lambda v: f"{v:.2f}")
        tablaHtml(vista)
    for tono, texto in datos.get("deterioro") or []:
        (st.warning if tono == "ambar" else st.error)(texto)
    if datos.get("rutaModelo"):
        st.caption(f"Modelo entrenado guardado en `{datos['rutaModelo']}` (se reentrena con cada «Actualizar datos»). "
                   f"Entrenamiento y análisis: {datos.get('duracionAnalisisSeg', 0):.1f} s.")


def dibujarDashboardPredictivo(datos):
    """Pestaña Predictivo: lo esencial arriba (4 cifras y el gráfico); el detalle técnico, plegado."""
    modelo, resumen, riesgoFuturo = datos["modelo"], datos["resumenPronostico"], datos["riesgoFuturo"]
    if not modelo.get("exito") or datos["pronostico"].empty:
        st.warning(modelo.get("mensaje") or "No se pudo generar el pronóstico. Amplía el periodo histórico.")
        with st.expander("Riesgo de los próximos 3 meses (Random Forest)", expanded=True):
            dibujarClasificador(datos)
        return

    dias = datos["diasPronostico"]
    tono = "positivo" if (resumen["rentabilidadProyectada"] or 0) >= 0 else "negativo"
    filaTarjetas([
        {"etiqueta": f"Rentabilidad en {dias} días", "valor": formatearPorcentaje(resumen["rentabilidadProyectada"], 1, True), "tono": tono,
         "nota": f"Valor esperado {formatearMoneda(resumen['valorProyectado'])}"},
        {"etiqueta": "Rango probable (90%)", "valor": f"{formatearMoneda(resumen['bandaInferior'])} – {formatearMoneda(resumen['bandaSuperior'])}",
         "nota": f"Probabilidad de subir: {formatearPorcentaje(resumen['probabilidadAlza'], 0)}"},
        {"etiqueta": "Escenario adverso", "valor": formatearPorcentaje(riesgoFuturo.get("perdidaEsperadaPeor"), 1, True), "tono": "negativo",
         "nota": f"Riesgo {str(riesgoFuturo.get('nivel', 'N/D')).lower()} · 1 de cada 20 escenarios"},
        {"etiqueta": "Confiabilidad del modelo", "valor": "Útil" if modelo["tieneHabilidad"] else "Baja",
         "tono": "positivo" if modelo["tieneHabilidad"] else "negativo",
         "nota": f"{formatearPorcentaje(modelo['habilidad'], 1, True)} vs un pronóstico simple"},
    ])
    if not modelo["tieneHabilidad"]:
        st.caption("Ningún modelo superó a un pronóstico simple, así que se muestra el **promedio histórico** con su rango "
                   "y no se usa en la recomendación. Es lo normal en fondos indexados: su precio es difícil de anticipar.")
    with abrirPanel(f"Pronóstico a {dias} días hábiles"):
        st.plotly_chart(graficarPronostico(datos["historico"], datos["pronostico"]), **ANCHO, key="predictivo_plotly_chart_6")
        st.caption(f"Desde el {formatearFecha(datos['fechaDatoFinal'])}. En la prueba, el rango contuvo al "
                   f"{modelo['cobertura90']:.0f}% de los resultados reales (ideal: ~90%).")

    with st.expander("Riesgo de los próximos 3 meses (Random Forest)"):
        dibujarClasificador(datos)
    deterioro = datos.get("deterioro") or []
    if deterioro:
        with st.expander(f"Señales de deterioro del modelo ({len(deterioro)})", expanded=False):
            for _tono, texto in deterioro:
                st.warning(texto)
    with st.expander("Métricas para el informe: modelo del equipo vs. línea base"):
        dibujarMetricasInforme(datos)
    with st.expander("Detalle técnico: comparación de modelos"):
        dibujarModelos(datos)
    with st.expander("Detalle técnico: qué datos pesan más en el pronóstico"):
        dibujarImportancia(datos, modelo)
        dibujarEstadoSentimiento(datos, modelo)
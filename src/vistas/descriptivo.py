"""
descriptivo.py
Dashboard 1 — ¿Qué pasó? NAV, rentabilidad, benchmark, riesgo, sentimiento
y el RANKING DE BONOS del perfil elegido en la parte superior.
"""

import pandas as pd
import streamlit as st

from src.catalogoBonos import PARAMETROS_PERFIL, PERFILES, PESOS_RANKING, UMBRAL_ACEPTABLE, UMBRAL_RECOMENDABLE
from src.estilos import abrirPanel, insignia
from src.graficos import (
    graficarComparativoBenchmark,
    graficarDistribucionRetornos,
    graficarEvolucionNav,
    graficarRadarRiesgo,
    graficarRankingBonos,
    graficarRentabilidadPeriodos,
    graficarSentimiento,
)
from src.graficos import graficarMapaBonos
from src.utilidades import esNulo, formatearMoneda, formatearNumero, formatearPorcentaje
from src.vistas.bonos import (
    bonosEvaluados,
    botonCargarCartera,
    filtrarBonos,
    resumenFondoBonos,
    tablaEmisores,
    vistaBonos,
    vistaEmisores,
)
from src.vistas.comunes import filaTarjetas, formatearTablaPorcentajes, mostrarRecomendacion


def dibujarIndicadores(datos):
    metricas, riesgo = datos["metricas"], datos["riesgo"]
    filaTarjetas([
        {"etiqueta": "Valor actual", "valor": formatearMoneda(metricas["valorActual"])},
        {"etiqueta": "Retorno anual", "valor": formatearPorcentaje(metricas["retornoAnual"], 1, True),
         "tono": "positivo" if (metricas["retornoAnual"] or 0) >= 0 else "negativo", "nota": "Periodo completo"},
        {"etiqueta": "Retorno 12 meses", "valor": formatearPorcentaje(metricas["retorno12m"], 1, True),
         "tono": "positivo" if not esNulo(metricas["retorno12m"]) and metricas["retorno12m"] >= 0 else "negativo"},
        {"etiqueta": "Volatilidad anual", "valor": formatearPorcentaje(metricas["volatilidadAnual"])},
    ])
    st.write("")
    filaTarjetas([
        {"etiqueta": "Sharpe (12 meses)", "valor": formatearNumero(metricas["sharpe12m"]),
         "nota": f"Tasa libre {formatearPorcentaje(metricas['tasaLibre'], 2)}"},
        {"etiqueta": "Beta", "valor": formatearNumero(metricas["beta"]), "nota": f"vs {datos['benchmark']}"},
        {"etiqueta": "VaR 95% diario", "valor": formatearPorcentaje(metricas["varDiario95"], 1), "tono": "negativo"},
        {"etiqueta": "Máxima caída", "valor": formatearPorcentaje(metricas["maxDrawdown"], 1), "tono": "negativo",
         "nota": f"Riesgo {riesgo['categoria']} · {riesgo['puntaje']}/10"},
    ])


def dibujarBenchmark(datos):
    metricas = datos["metricas"]
    columnas = st.columns([3, 2])
    with columnas[0], abrirPanel(f"Rentabilidad acumulada vs {datos['benchmark']} (base 100)"):
        if datos["comparativo"].empty or "benchmark" not in datos["comparativo"]:
            st.info("No hay datos del benchmark para comparar.")
        else:
            st.plotly_chart(graficarComparativoBenchmark(datos["comparativo"], datos["ticker"], datos["benchmark"]),
                            use_container_width=True, key="descriptivo_plotly_chart_1")
            diferencial = metricas.get("diferencialBenchmark")
            if not esNulo(diferencial):
                texto = (f"El fondo {'supera' if diferencial >= 0 else 'queda por debajo de'} su benchmark en "
                         f"{formatearPorcentaje(abs(diferencial), 1)} acumulado desde la primera fecha común.")
                st.markdown(insignia(texto, "verde" if diferencial >= 0 else "roja"), unsafe_allow_html=True)
            if not datos.get("benchmarkComparable", True):
                st.warning(f"{datos['benchmark']} no incluye dividendos y el fondo sí: la diferencia está inflada. "
                           "Usa ^SP500TR o un ETF equivalente.")
    with columnas[1], abrirPanel("Rentabilidad por periodo"):
        st.plotly_chart(graficarRentabilidadPeriodos(datos["rentabilidadPeriodos"]), use_container_width=True, key="descriptivo_plotly_chart_2")

    columnas = st.columns(2)
    with columnas[0], abrirPanel("Distribución de retornos diarios"):
        st.plotly_chart(graficarDistribucionRetornos(datos["historico"]), use_container_width=True, key="descriptivo_plotly_chart_3")
    with columnas[1], abrirPanel("Composición del riesgo"):
        st.plotly_chart(graficarRadarRiesgo(datos["riesgo"].get("componentes", {})), use_container_width=True, key="descriptivo_plotly_chart_4")
        st.caption("Volatilidad 40% · caída máxima 35% · beta 25%. Sharpe y sentimiento entran por separado en la señal.")


def dibujarRankingBonos(datos, perfil):
    """Ranking de los bonos del perfil: cuáles conviene comprar y si conviene invertir o no."""
    tabla, resumen = datos.get("rankingsPorPerfil", {}).get(perfil, (pd.DataFrame(), {}))
    with abrirPanel(f"Fondos de bonos para el perfil {perfil}: ranking y bonos que contienen"):
        if datos.get("fechaCorte") is not None:
            st.caption("En la evaluación por semana, los precios de los bonos se recortan a esa fecha; "
                       "su rendimiento por distribuciones es el de hoy.")
        if tabla.empty:
            st.info("No hay datos de bonos. Presiona «Actualizar datos».")
            return
        mostrarRecomendacion(resumen.get("recomendacion", ""), resumen.get("tono"))
        if datos["ticker"] in set(tabla["ticker"]):
            fila = tabla.set_index("ticker").loc[datos["ticker"]]
            st.caption(f"El fondo analizado, **{datos['ticker']}**, ocupa el puesto **#{int(fila['puesto'])}** de {len(tabla)} "
                       f"en este perfil ({fila['veredicto'].lower()}). Cámbialo arriba, en «Fondo a analizar».")
        else:
            st.caption(f"El fondo analizado, **{datos['ticker']}**, no pertenece a este grupo de fondos de bonos: "
                       "se compara aquí con los fondos de bonos de tu perfil.")

        columnas = st.columns([2, 3])
        with columnas[0]:
            st.plotly_chart(graficarRankingBonos(tabla, UMBRAL_RECOMENDABLE, UMBRAL_ACEPTABLE), use_container_width=True, key="descriptivo_plotly_chart_5")
        with columnas[1]:
            vista = formatearTablaPorcentajes(
                tabla, ["rendimientoEsperado", "prima", "volatilidad", "caidaMaxima", "retorno6m"], decimales=2
            )
            vista.insert(0, "analizado", vista["ticker"].map(lambda t: "◀ analizado" if t == datos["ticker"] else ""))
            vista = vista[["analizado", "puesto", "ticker", "segmento", "veredicto", "puntaje", "rendimientoEsperado", "prima",
                           "volatilidad", "caidaMaxima", "retorno6m", "fondoMutuo", "motivo"]].rename(columns={
                "analizado": "", "puesto": "#", "ticker": "Fondo", "segmento": "Tipo de bonos", "veredicto": "Veredicto", "puntaje": "Puntaje",
                "rendimientoEsperado": "Rend. esperado", "prima": "Prima vs liquidez", "volatilidad": "Volatilidad 3a",
                "caidaMaxima": "Caída máx. 3a", "retorno6m": "Retorno 6m", "fondoMutuo": "Fondo mutuo equiv.",
                "motivo": "Motivo",
            })
            st.dataframe(vista, use_container_width=True, hide_index=True, key="descriptivo_dataframe_6")

        p = PARAMETROS_PERFIL[perfil]
        st.caption(
            f"Liquidez de referencia: {resumen.get('tasaLibre', 0):.2%} (letras del Tesoro). Rend. esperado = rendimiento "
            "por distribuciones menos la pérdida esperada por impagos. Tolerancias del perfil: volatilidad ≤ "
            f"{p['volatilidadMaxima']:.0%}, caída ≥ {p['caidaTolerada']:.0%}, prima ≥ {p['primaMinima']:+.2%}."
        )
        with st.expander("Cómo se calcula el puntaje y el veredicto"):
            st.markdown(
                "**Puntaje (0-100)**, con datos de los últimos 3 años: "
                + " · ".join(f"{k} {v:.0%}" for k, v in PESOS_RANKING.items())
                + f".\n\n**Veredicto:** Recomendable ≥ {UMBRAL_RECOMENDABLE} · Aceptable ≥ {UMBRAL_ACEPTABLE} · "
                "No recomendable por debajo, o si se activa un veto: rinde menos que la liquidez (menos la prima mínima "
                "del perfil), volatilidad mayor a 1.5 veces la tolerada, caída peor que la tolerada, o tendencia "
                "bajista (bajo su media de 200 días y −3% en 6 meses).\n\n"
                "Los fondos mutuos equivalentes son de referencia: verifica disponibilidad y montos mínimos con la gestora."
            )
        dibujarExploradorBonos(datos, perfil, tabla)
        with st.expander("Ver el resumen de los otros perfiles"):
            for otro in PERFILES:
                if otro == perfil:
                    continue
                _, resumenOtro = datos["rankingsPorPerfil"].get(otro, (None, {}))
                st.markdown(f"**{otro}:** {resumenOtro.get('recomendacion', 'Sin datos.')}")


def dibujarExploradorBonos(datos, perfil, tablaFondos):
    """Evaluacion individual de los bonos y emisores que componen un fondo del perfil."""
    st.markdown("**Dentro de cada fondo: bonos y emisores, uno por uno**")
    opciones = list(tablaFondos["ticker"])
    fondo = st.selectbox(
        "Fondo a explorar", opciones, key=f"explorarFondo_{perfil}_{datos['ticker']}",
        index=opciones.index(datos["ticker"]) if datos["ticker"] in opciones else 0,
        format_func=lambda t: f"{t} — {tablaFondos.set_index('ticker').loc[t, 'segmento']}",
    )
    if not botonCargarCartera(fondo, f"cargarCartera_desc_{fondo}"):
        return
    evaluados, meta, error = bonosEvaluados(datos, fondo, perfil)
    if error:
        st.info(error)
        return
    resumenFondoBonos(evaluados, meta)
    pestanas = st.tabs(["Por emisor (empresa / entidad)", "Por bono", "Mapa rendimiento / plazo"])
    with pestanas[0]:
        emisores = tablaEmisores(evaluados, f"{fondo}_{perfil}")
        st.dataframe(vistaEmisores(emisores), use_container_width=True, hide_index=True, key="descriptivo_dataframe_7")
        st.caption("Un emisor es Recomendable si tiene al menos un bono recomendable para tu perfil. "
                   "Calidad (peor) = la calidad implícita más baja entre sus bonos en el fondo.")
    with pestanas[1]:
        filtrados = filtrarBonos(evaluados, f"desc_{fondo}")
        st.dataframe(vistaBonos(filtrados), use_container_width=True, hide_index=True, key="descriptivo_dataframe_8")
    with pestanas[2]:
        st.plotly_chart(graficarMapaBonos(evaluados), use_container_width=True, key="descriptivo_plotly_chart_9")
    st.caption(
        "Cómo se evalúa cada bono: TIR calculada con su precio, cupón y vencimiento; diferencial sobre el Tesoro del mismo plazo; "
        "calidad crediticia implícita por ese diferencial (no es una calificación oficial); rendimiento esperado = TIR − pérdida "
        "esperada por impago. Veredicto con los límites del perfil (duración, calidad mínima, prima sobre la liquidez). "
        "Para elegir los bonos que comprarás y ver su proyección, ve al Prescriptivo (pasos 2 y 3)."
    )


def dibujarSentimiento(datos):
    """Tono de la prensa (GDELT) y titulares recientes (Yahoo Finance / Alpha Vantage)."""
    sentimiento, serie = datos["sentimiento"], datos["serieSentimiento"]
    with abrirPanel("Sentimiento de la prensa"):
        fuenteSerie = getattr(serie, "attrs", {}).get("fuente", "")
        participa = {"tono": "Participa en la señal (tono de prensa)", "titulares": "Participa en la señal (titulares)"}.get(
            sentimiento.get("fuenteSenal"), "No participa en la señal")
        filaTarjetas([
            {"etiqueta": "Tono de prensa · 30 días", "valor": formatearNumero(sentimiento.get("tonoReciente"), 2),
             "nota": f"Promedio del año: {formatearNumero(sentimiento.get('tonoAnual'), 2)}"},
            {"etiqueta": "Frente a su último año", "valor": (f"{sentimiento['zTono']:+.1f} desv." if not esNulo(sentimiento.get("zTono")) else "N/D"),
             "nota": participa},
            {"etiqueta": "Historia de tono", "valor": f"{sentimiento.get('diasTono', 0)} días",
             "nota": "Mínimo para la señal: 120"},
            {"etiqueta": "Titulares recientes", "valor": str(sentimiento.get("recientes", 0)),
             "nota": f"Promedio {formatearNumero(sentimiento.get('promedioReciente'), 2)} · {sentimiento.get('totalNoticias', 0)} acumulados"},
        ])
        st.write("")
        if not serie.empty:
            st.plotly_chart(graficarSentimiento(serie), use_container_width=True, key="descriptivo_plotly_chart_10")
        if fuenteSerie.startswith("Tono"):
            st.caption(
                f"Tono promedio diario de la prensa en inglés sobre {datos.get('temaTono', 'el tema del fondo')} según GDELT "
                "(escala de −100 a +100; en la práctica entre −10 y +10 y casi siempre negativa). Por eso se compara con su "
                "propio último año y no con cero. El tono de cada día se usa a partir del día de mercado siguiente. "
                "Completa la historia desde la barra lateral («Historia del tono de prensa»)."
            )
        else:
            st.caption("Sin historia de tono de prensa: el gráfico muestra el promedio de los titulares por día de mercado. "
                       "Completa la historia desde la barra lateral («Historia del tono de prensa»).")

        titulares = datos["titulares"]
        if titulares is not None and not titulares.empty:
            fuentes = datos.get("fuentesNoticias") or {}
            st.markdown(f"**Titulares recientes** de {datos.get('tickerNoticias')}"
                        + (f" y {datos['ticker']}" if datos.get("tickerNoticias") != datos["ticker"] else "")
                        + f" y del tema {datos.get('temaTono', '')}")
            if fuentes:
                st.caption("Fuentes de esta actualización: " + ", ".join(f"{k} ({v})" for k, v in fuentes.items()) + ".")
            tabla = titulares.copy()
            tabla["fecha"] = pd.to_datetime(tabla["fecha"]).dt.strftime("%d/%m/%Y")
            tabla["sentimiento"] = tabla["sentimiento"].round(3)
            tabla = tabla.rename(columns={"fecha": "Fecha", "titulo": "Titular", "fuente": "Fuente",
                                          "sentimiento": "Puntaje", "etiqueta": "Clasificación", "url": "Enlace"})
            st.dataframe(tabla, use_container_width=True, hide_index=True,
                         column_config={"Enlace": st.column_config.LinkColumn("Enlace", display_text="Abrir")}, key="descriptivo_dataframe_11")
            st.caption("Puntaje de los titulares: VADER (−1 a +1), un analizador general que no entiende jerga "
                       "financiera fina; por eso pesa menos que el tono de prensa.")
        elif datos.get("fechaCorte") is not None:
            st.info("No hay titulares guardados hasta esa fecha: las fuentes gratuitas solo entregan lo reciente, "
                    "así que la historia de titulares empieza el día de tu primera actualización y crece con cada una.")
        else:
            st.info("No llegaron titulares de ninguna fuente gratuita (Yahoo Finance, su RSS ni Google News). "
                    "Revisa tu conexión y presiona «Actualizar datos» con «Usar datos en caché» desactivado."
                    + (f"\n\nDetalle: {datos['motivoNoticias']}" if datos.get("motivoNoticias") else ""))


def dibujarDashboardDescriptivo(datos, perfil):
    """Pestaña Descriptivo."""
    dibujarIndicadores(datos)
    st.write("")
    with abrirPanel(f"Evolución del NAV — {datos['ficha'].get('nombre', datos['ticker'])}"):
        st.plotly_chart(graficarEvolucionNav(datos["historico"]), use_container_width=True, key="descriptivo_plotly_chart_12")
    dibujarBenchmark(datos)
    dibujarRankingBonos(datos, perfil)
    dibujarSentimiento(datos)
    posiciones = datos.get("posiciones")
    if posiciones is not None and not posiciones.empty:
        with abrirPanel("Principales posiciones del fondo"):
            tabla = posiciones.copy()
            tabla["peso"] = (tabla["peso"] * 100).round(2).astype(str) + "%"
            st.dataframe(tabla.rename(columns={"ticker": "Ticker", "nombre": "Nombre", "peso": "Peso"}),
                         use_container_width=True, hide_index=True, key="descriptivo_dataframe_13")
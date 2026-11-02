"""
descriptivo.py
Dashboard 1 — ¿Qué pasó? NAV, rentabilidad, benchmark, riesgo, sentimiento
y el RANKING DE BONOS del perfil elegido en la parte superior.
"""

import pandas as pd
import streamlit as st

from src.catalogoBonos import PARAMETROS_PERFIL, nombreFondo, PERFILES, PESOS_RANKING, UMBRAL_ACEPTABLE, UMBRAL_RECOMENDABLE
from src.estilos import abrirPanel, insignia
from src.graficos import (
    graficarComparativoBenchmark,
    graficarDistribucionRetornos,
    graficarEvolucionNav,
    graficarRadarRiesgo,
    graficarRankingBonos,
    graficarRentabilidadAnual,
    graficarRentabilidadPeriodos,
    graficarSentimiento,
)
from src.catalogoFondosMutuos import costoAcumulado
from src.graficos import graficarMapaBonos
from src.utilidades import esNulo, formatearMoneda, formatearNumero, formatearPorcentaje
from src.vistas.bonos import (
    bonosEvaluados,
    botonCargarCartera,
    filtrarBonos,
    resumenFondoBonos,
    explicarBonosVsFondo,
    tablaEmisores,
    vistaBonos,
    vistaEmisores,
)
from src.vistas.comunes import ANCHO, filaTarjetas, formatearTablaPorcentajes, mostrarRecomendacion, tablaDatos, tablaHtml


def dibujarIndicadores(datos):
    """Las 4 cifras clave arriba; el resto, plegado."""
    metricas, riesgo = datos["metricas"], datos["riesgo"]
    filaTarjetas([
        {"etiqueta": "Valor actual", "valor": formatearMoneda(metricas["valorActual"]),
         "nota": f"Último dato {datos['fechaDatoFinal']:%d/%m/%Y}"},
        {"etiqueta": "Retorno 12 meses", "valor": formatearPorcentaje(metricas["retorno12m"], 1, True),
         "tono": "positivo" if not esNulo(metricas["retorno12m"]) and metricas["retorno12m"] >= 0 else "negativo",
         "nota": f"Anual del periodo: {formatearPorcentaje(metricas['retornoAnual'], 1, True)}"},
        {"etiqueta": "Riesgo", "valor": riesgo["categoria"], "nota": f"Volatilidad {formatearPorcentaje(metricas['volatilidadAnual'])} anual"},
        {"etiqueta": "Peor caída", "valor": formatearPorcentaje(metricas["maxDrawdown"], 1), "tono": "negativo",
         "nota": "Desde un máximo"},
    ])
    with st.expander("Más indicadores (Sharpe, beta, VaR)"):
        filaTarjetas([
            {"etiqueta": "Sharpe 12 meses", "valor": formatearNumero(metricas["sharpe12m"]),
             "nota": f"Tasa libre {formatearPorcentaje(metricas['tasaLibre'], 2)}"},
            {"etiqueta": "Beta", "valor": formatearNumero(metricas["beta"]), "nota": f"vs {datos['benchmark']}"},
            {"etiqueta": "VaR 95% diario", "valor": formatearPorcentaje(metricas["varDiario95"], 1), "tono": "negativo"},
            {"etiqueta": "Puntaje de riesgo", "valor": f"{riesgo['puntaje']}/10", "nota": "Volatilidad, caída y beta"},
        ])


def dibujarCostosYCondiciones(datos):
    """Lo que el prospecto pide revisar antes de comprar: gasto anual, costo en el tiempo, minimo y como se compra."""
    c = datos.get("condiciones") or {}
    gasto = c.get("gastoAnual")
    costos = costoAcumulado(gasto)
    esMutuo = c.get("esFondoMutuo")
    with abrirPanel("Costos y condiciones de compra"):
        filaTarjetas([
            {"etiqueta": "Gasto anual del fondo", "valor": formatearPorcentaje(gasto, 2) if gasto is not None else "N/D",
             "nota": f"Según {c.get('fuenteGasto')}" if c.get("fuenteGasto") else "Sin dato; revisa el prospecto"},
            {"etiqueta": "Costo en 10 años por cada USD 10 000", "valor": formatearMoneda(costos.get(10)) if costos else "N/D",
             "nota": (f"1 año {formatearMoneda(costos[1])} · 3 años {formatearMoneda(costos[3])} · 5 años {formatearMoneda(costos[5])}"
                      if costos else "Supone 5% anual, como el prospecto")},
            {"etiqueta": "Monto mínimo de entrada", "valor": formatearMoneda(c.get("minimo")) if c.get("minimo") else "Sin mínimo",
             "nota": (f"Clase {c.get('claseParticipacion')} · {c.get('gestora')}" if esMutuo else "ETF: se compra por participación")},
            {"etiqueta": "Cargos de compra y venta", "valor": "Ninguno" if not (c.get("cargoCompra") or c.get("cargoVenta")) else
             f"{formatearPorcentaje(c.get('cargoCompra'), 2)} / {formatearPorcentaje(c.get('cargoVenta'), 2)}",
             "nota": "Sin comisión de entrada ni de salida (no-load)" if esMutuo else "Solo la comisión de tu bróker, si la cobra"},
        ])
        gemelo = c.get("gemelo")
        st.caption(f"**Cómo se compra:** {c.get('comoSeCompra', '')}"
                   + (f" **Misma cartera como {'ETF' if esMutuo else 'fondo mutuo'}:** {nombreFondo(gemelo)}." if gemelo else "")
                   + " Costos y mínimos según el prospecto más reciente conocido: verifícalos en la gestora antes de invertir. "
                   "El costo en el tiempo supone 5% anual bruto, como el ejemplo del prospecto.")


def dibujarRentabilidadProspecto(datos):
    """Rentabilidad ano a ano, mejor y peor trimestre y promedios a 1/3/5/10 anos frente a la referencia."""
    tabla, trimestres, promedios = datos.get("rentabilidadAnual"), datos.get("trimestres") or {}, datos.get("retornosPromedio")
    nombreRef = nombreFondo(datos["benchmark"], conTicker=False)
    with abrirPanel("Rentabilidad año a año (como en el prospecto)"):
        if tabla is None or tabla.empty:
            st.info("Sin historia suficiente para la rentabilidad por año.")
            return
        columnas = st.columns([3, 2])
        with columnas[0]:
            st.plotly_chart(graficarRentabilidadAnual(tabla, datos.get("nombreCorto") or datos["ticker"], nombreRef),
                            **ANCHO, key="descriptivo_plotly_chart_anual")
            st.caption("* año incompleto (en curso o primer año con datos). Con distribuciones reinvertidas.")
        with columnas[1]:
            if trimestres:
                filaTarjetas([
                    {"etiqueta": "Mejor trimestre", "valor": formatearPorcentaje(trimestres["mejor"], 1, True), "tono": "positivo",
                     "nota": trimestres["mejorTrimestre"]},
                    {"etiqueta": "Peor trimestre", "valor": formatearPorcentaje(trimestres["peor"], 1, True), "tono": "negativo",
                     "nota": trimestres["peorTrimestre"]},
                ])
            if promedios is not None and not promedios.empty:
                vista = pd.DataFrame({"Plazo": promedios["plazo"],
                                      "Fondo (anual)": promedios["fondo"].map(lambda v: formatearPorcentaje(v, 1, True)),
                                      nombreRef: promedios["benchmark"].map(lambda v: formatearPorcentaje(v, 1, True))})
                tablaHtml(vista)
                st.caption("Retorno anual promedio compuesto hasta el último dato.")


def dibujarRankingMutuos(datos, perfil):
    """Los fondos mutuos del perfil, del mejor al peor, con la fila del fondo analizado marcada."""
    tabla, resumen = (datos.get("rankingsMutuosPorPerfil") or {}).get(perfil, (pd.DataFrame(), {}))
    if tabla is None or tabla.empty:
        return
    with abrirPanel(f"Fondos mutuos comparables · perfil {perfil}"):
        vista = pd.DataFrame({
            "#": tabla["puesto"], "Fondo": tabla.apply(lambda f: ("▶ " if f["ticker"] == datos["ticker"] else "") + nombreFondo(f["ticker"]), axis=1),
            "Tipo": tabla["clase"], "Veredicto": tabla["veredicto"],
            "Rinde": tabla["rinde"].map(lambda v: formatearPorcentaje(v, 1, True)),
            "Volatilidad": tabla["volatilidad"].map(lambda v: formatearPorcentaje(v, 1)),
            "Peor caída": tabla["caidaMaxima"].map(lambda v: formatearPorcentaje(v, 1)),
            "Gasto": tabla["gastoAnual"].map(lambda v: formatearPorcentaje(v, 2)),
            "Mínimo": tabla["minimo"].map(lambda v: formatearMoneda(v) if v else "Sin mínimo"),
            "Por qué": tabla["motivo"],
        })
        tablaHtml(vista, destacar=lambda fila: str(fila["Fondo"]).startswith("▶"))
        st.caption(f"{resumen.get('recomendables', 0)} recomendable(s) y {resumen.get('aceptables', 0)} aceptable(s) de "
                   f"{resumen.get('evaluados', 0)} evaluados. «Rinde»: lo que paga al año (bonos) o el retorno anual de 3 años "
                   "(acciones y mixtos). Veredicto: riesgo de 3 años frente a la tolerancia de tu perfil y relación rendimiento/riesgo.")


def dibujarBenchmark(datos):
    metricas = datos["metricas"]
    columnas = st.columns([3, 2])
    with columnas[0], abrirPanel(f"Comparado con {nombreFondo(datos['benchmark'])}"):
        if datos["comparativo"].empty or "benchmark" not in datos["comparativo"]:
            st.info("No hay datos del benchmark para comparar.")
        else:
            st.plotly_chart(graficarComparativoBenchmark(datos["comparativo"], datos["ticker"], datos["benchmark"]),
                            **ANCHO, key="descriptivo_plotly_chart_1")
            diferencial = metricas.get("diferencialBenchmark")
            if not esNulo(diferencial):
                texto = (f"El fondo {'supera' if diferencial >= 0 else 'queda por debajo de'} su benchmark en "
                         f"{formatearPorcentaje(abs(diferencial), 1)} acumulado desde la primera fecha común.")
                st.markdown(insignia(texto, "verde" if diferencial >= 0 else "roja"), unsafe_allow_html=True)
            if not datos.get("benchmarkComparable", True):
                st.caption("Ojo: esta referencia no incluye dividendos y el fondo sí, así que la diferencia se ve mayor.")
    with columnas[1], abrirPanel("Rentabilidad por periodo"):
        st.plotly_chart(graficarRentabilidadPeriodos(datos["rentabilidadPeriodos"]), **ANCHO, key="descriptivo_plotly_chart_2")

    with st.expander("Distribución de retornos y composición del riesgo"):
        columnas = st.columns(2)
        with columnas[0]:
            st.plotly_chart(graficarDistribucionRetornos(datos["historico"]), **ANCHO, key="descriptivo_plotly_chart_3")
        with columnas[1]:
            st.plotly_chart(graficarRadarRiesgo(datos["riesgo"].get("componentes", {})), **ANCHO, key="descriptivo_plotly_chart_4")
            st.caption("Volatilidad 40% · caída máxima 35% · beta 25%.")


def dibujarRankingBonos(datos, perfil):
    """Ranking de los bonos del perfil: cuáles conviene comprar y si conviene invertir o no."""
    tabla, resumen = datos.get("rankingsPorPerfil", {}).get(perfil, (pd.DataFrame(), {}))
    with abrirPanel(f"Ranking de fondos de bonos · perfil {perfil}"):
        if datos.get("fechaCorte") is not None:
            st.caption("En la evaluación por semana, los precios de los bonos se recortan a esa fecha; "
                       "su rendimiento por distribuciones es el de hoy.")
        if tabla.empty:
            st.info("No hay datos de bonos. Presiona «Actualizar datos».")
            return
        mostrarRecomendacion(resumen.get("recomendacion", ""), resumen.get("tono"))

        columnas = st.columns([2, 3])
        with columnas[0]:
            st.plotly_chart(graficarRankingBonos(tabla, UMBRAL_RECOMENDABLE, UMBRAL_ACEPTABLE), **ANCHO, key="descriptivo_plotly_chart_5")
        with columnas[1]:
            vista = formatearTablaPorcentajes(
                tabla, ["rendimientoEsperado", "prima", "volatilidad", "caidaMaxima", "retorno6m"], decimales=2
            )
            vista["ticker"] = vista["ticker"].map(lambda t: ("▶ " if t == datos["ticker"] else "") + nombreFondo(t))
            columnasVista = {"ticker": "Fondo", "veredicto": "Veredicto", "rendimientoEsperado": "Rinde", "volatilidad": "Volatilidad",
                             "motivo": "Por qué"}
            tablaHtml(vista[list(columnasVista)].rename(columns=columnasVista),
                      destacar=lambda fila: str(fila["Fondo"]).startswith("▶"))
            st.caption("▶ = el fondo que estás viendo. «Rinde» = lo que se espera que pague al año.")

        p = PARAMETROS_PERFIL[perfil]
        with st.expander("Tabla completa y cómo se calcula el veredicto"):
            completa = formatearTablaPorcentajes(tabla, ["rendimientoEsperado", "prima", "volatilidad", "caidaMaxima", "retorno6m"], 2)
            completa = completa[["puesto", "ticker", "segmento", "veredicto", "puntaje", "rendimientoEsperado", "prima",
                                 "volatilidad", "caidaMaxima", "retorno6m", "fondoMutuo"]].rename(columns={
                "puesto": "#", "ticker": "Fondo", "segmento": "Tipo de bonos", "veredicto": "Veredicto", "puntaje": "Puntaje",
                "rendimientoEsperado": "Rend. esperado", "prima": "Prima vs liquidez", "volatilidad": "Volatilidad 3a",
                "caidaMaxima": "Caída máx. 3a", "retorno6m": "Retorno 6m", "fondoMutuo": "Fondo mutuo equiv."})
            tablaHtml(completa)
            st.caption(
                f"Liquidez de referencia: {resumen.get('tasaLibre', 0):.2%}. Rend. esperado = rendimiento por distribuciones menos "
                f"la pérdida esperada por impagos. Tolerancias del perfil: volatilidad ≤ {p['volatilidadMaxima']:.0%}, "
                f"caída ≥ {p['caidaTolerada']:.0%}, prima ≥ {p['primaMinima']:+.2%}."
            )
            st.markdown(
                "**Puntaje (0-100)**, con datos de los últimos 3 años: "
                + " · ".join(f"{k} {v:.0%}" for k, v in PESOS_RANKING.items())
                + f".\n\n**Veredicto:** Recomendable ≥ {UMBRAL_RECOMENDABLE} · Aceptable ≥ {UMBRAL_ACEPTABLE} · "
                "No recomendable por debajo, o si se activa un veto: rinde menos que la liquidez (menos la prima mínima "
                "del perfil), volatilidad mayor a 1.5 veces la tolerada, caída peor que la tolerada, o tendencia "
                "bajista (bajo su media de 200 días y −3% en 6 meses).\n\n"
                "Los fondos mutuos equivalentes son de referencia: verifica disponibilidad y montos mínimos con la gestora."
            )
        with st.expander("Bonos y emisores dentro de cada fondo"):
            dibujarExploradorBonos(datos, perfil, tabla)
        with st.expander("Los otros perfiles"):
            for otro in PERFILES:
                if otro == perfil:
                    continue
                _, resumenOtro = datos["rankingsPorPerfil"].get(otro, (None, {}))
                st.markdown(f"**{otro}:** {resumenOtro.get('recomendacion', 'Sin datos.')}")


def dibujarExploradorBonos(datos, perfil, tablaFondos):
    """Evaluacion individual de los bonos y emisores que componen un fondo del perfil."""
    opciones = list(tablaFondos["ticker"])
    fondo = st.selectbox(
        "Fondo a explorar", opciones, key=f"explorarFondo_{perfil}_{datos['ticker']}",
        index=opciones.index(datos["ticker"]) if datos["ticker"] in opciones else 0,
        format_func=nombreFondo,
    )
    if not botonCargarCartera(fondo, f"cargarCartera_desc_{fondo}"):
        return
    evaluados, meta, error = bonosEvaluados(datos, fondo, perfil)
    if error:
        st.info(error)
        return
    resumenFondoBonos(evaluados, meta)
    explicarBonosVsFondo(datos, fondo, perfil, evaluados)
    pestanas = st.tabs(["Por emisor (empresa / entidad)", "Por bono", "Mapa rendimiento / plazo"])
    with pestanas[0]:
        emisores = tablaEmisores(evaluados, f"{fondo}_{perfil}")
        tablaDatos(vistaEmisores(emisores), key="descriptivo_dataframe_7")
        st.caption("Un emisor es Recomendable si tiene al menos un bono recomendable para tu perfil. "
                   "Calidad (peor) = la calidad implícita más baja entre sus bonos en el fondo.")
    with pestanas[1]:
        filtrados = filtrarBonos(evaluados, f"desc_{fondo}")
        tablaDatos(vistaBonos(filtrados), key="descriptivo_dataframe_8")
    with pestanas[2]:
        st.plotly_chart(graficarMapaBonos(evaluados), **ANCHO, key="descriptivo_plotly_chart_9")
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
        z = sentimiento.get("zTono")
        filaTarjetas([
            {"etiqueta": "Tono de la prensa (30 días)",
             "valor": "Sin historia" if esNulo(z) else ("Más positivo" if z >= 1 else ("Más negativo" if z <= -1 else "Normal")),
             "nota": (f"{z:+.1f} desv. frente a su último año · " if not esNulo(z) else f"{sentimiento.get('diasTono', 0)} de 120 días · ")
                     + participa.lower()},
            {"etiqueta": "Titulares recientes", "valor": str(sentimiento.get("recientes", 0)),
             "nota": f"Promedio {formatearNumero(sentimiento.get('promedioReciente'), 2)} (−1 a +1)"},
        ])
        if not serie.empty:
            st.plotly_chart(graficarSentimiento(serie), **ANCHO, key="descriptivo_plotly_chart_10")
        st.caption(("Ánimo diario de la prensa internacional sobre este tipo de fondo; se compara con su propio último año."
                    if fuenteSerie.startswith("Tono") else "Ánimo promedio de los titulares de cada día.")
                   + (" Se descargan hasta 12 meses de historia al actualizar; para más, menú lateral → «Más historia de noticias»."
                      if fuenteSerie.startswith("Tono") else ""))
        motivoTono = getattr(serie, "attrs", {}).get("motivoHistoria") or datos.get("motivoTono")
        if motivoTono:
            st.caption(f"Historia del tono incompleta: {motivoTono}")

        titulares = datos["titulares"]
        if titulares is not None and not titulares.empty:
            fuentes = datos.get("fuentesNoticias") or {}
            with st.expander(f"Ver los {len(titulares)} titulares más recientes"):
                tabla = titulares.copy()
                tabla["fecha"] = pd.to_datetime(tabla["fecha"]).dt.strftime("%d/%m/%Y")
                tabla["sentimiento"] = tabla["sentimiento"].round(2)
                tabla = tabla[["fecha", "titulo", "sentimiento", "fuente", "url"]].rename(columns={
                    "fecha": "Fecha", "titulo": "Titular", "sentimiento": "Puntaje", "fuente": "Fuente", "url": "Enlace"})
                tablaDatos(tabla, column_config={"Enlace": st.column_config.LinkColumn("Enlace", display_text="Abrir")}, key="descriptivo_dataframe_11")
                st.caption("Puntaje de −1 (muy negativo) a +1 (muy positivo)."
                           + (" Fuentes: " + ", ".join(f"{k} ({v})" for k, v in fuentes.items()) + "." if fuentes else ""))
        elif datos.get("fechaCorte") is None:
            st.warning("**No llegaron titulares.** " + (datos.get("motivoNoticias") or "Las fuentes no respondieron.")
                       + " Puedes volver a intentarlo sin descargar todo lo demás.")
            st.button("Buscar titulares de nuevo", key="reintentarNoticias", type="primary",
                      on_click=lambda: st.session_state.__setitem__("reintentarNoticiasDe", datos["ticker"]))


def dibujarDashboardDescriptivo(datos, perfil):
    """Pestaña Descriptivo."""
    dibujarIndicadores(datos)
    with abrirPanel(f"Valor del fondo · {datos['ficha'].get('nombre', datos['ticker'])}"):
        st.plotly_chart(graficarEvolucionNav(datos["historico"]), **ANCHO, key="descriptivo_plotly_chart_12")
    dibujarCostosYCondiciones(datos)
    dibujarRentabilidadProspecto(datos)
    dibujarBenchmark(datos)
    dibujarRankingMutuos(datos, perfil)
    with st.expander(f"Ranking de los ETF de bonos · perfil {perfil}"):
        dibujarRankingBonos(datos, perfil)
    dibujarSentimiento(datos)
    posiciones = datos.get("posiciones")
    if posiciones is not None and not posiciones.empty:
        with st.expander("Principales posiciones del fondo"):
            tabla = posiciones.copy()
            tabla["peso"] = (tabla["peso"] * 100).round(2).astype(str) + "%"
            tablaDatos(tabla.rename(columns={"ticker": "Símbolo", "nombre": "Nombre", "peso": "Peso"})[["Nombre", "Peso", "Símbolo"]],
                       key="descriptivo_dataframe_13")
"""
graficos.py
Visualizaciones Plotly con la identidad visual de FundScope:
lineas azules, fondo blanco, rejilla punteada gris y sin marcos.
"""

import pandas as pd
import plotly.graph_objects as go

from src.estilos import COLORES
from src.utilidades import registrarEvento

TIPOGRAFIA = dict(family="Inter, sans-serif", size=14, color=COLORES["grisOscuro"])


def aplicarTema(figura, altura=340, mostrarLeyenda=False):
    """Aplica el tema visual comun a cualquier figura."""
    try:
        figura.update_layout(
            height=altura,
            font=TIPOGRAFIA,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=10, t=20, b=10),
            showlegend=mostrarLeyenda,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified",
            hoverlabel=dict(font_size=14, bgcolor="#FFFFFF", bordercolor=COLORES["borde"]),
        )
        figura.update_xaxes(showgrid=False, showline=False, zeroline=False, ticks="")
        figura.update_yaxes(
            showgrid=True,
            gridcolor=COLORES["borde"],
            griddash="dot",
            showline=False,
            zeroline=False,
            ticks="",
        )
        return figura
    except Exception as error:
        registrarEvento(f"Error al aplicar el tema del grafico: {error}", "WARN")
        return figura


def graficarEvolucionNav(historico, titulo=None):
    """Grafico de linea con la evolucion del NAV."""
    try:
        figura = go.Figure()
        figura.add_trace(
            go.Scatter(
                x=historico.index,
                y=historico["nav"],
                mode="lines",
                name="NAV",
                line=dict(color=COLORES["azul"], width=2.5),
                fill="tozeroy",
                fillcolor="rgba(51, 102, 204, 0.06)",
                hovertemplate="%{x|%d %b %Y}<br><b>$%{y:.2f}</b><extra></extra>",
            )
        )
        figura.update_yaxes(rangemode="normal")
        if titulo:
            figura.update_layout(title=titulo)
        return aplicarTema(figura)
    except Exception as error:
        registrarEvento(f"Error al graficar el NAV: {error}", "ERROR")
        return go.Figure()


def graficarComparativoBenchmark(comparativo, nombreFondo="Fondo", nombreBenchmark="Benchmark"):
    """Compara el fondo y su benchmark en base 100."""
    try:
        figura = go.Figure()
        figura.add_trace(
            go.Scatter(
                x=comparativo.index,
                y=comparativo["fondo"],
                mode="lines",
                name=nombreFondo,
                line=dict(color=COLORES["azul"], width=2.5),
                hovertemplate="%{x|%d %b %Y}<br>" + nombreFondo + ": <b>%{y:.1f}</b><extra></extra>",
            )
        )
        if "benchmark" in comparativo.columns:
            figura.add_trace(
                go.Scatter(
                    x=comparativo.index,
                    y=comparativo["benchmark"],
                    mode="lines",
                    name=nombreBenchmark,
                    line=dict(color=COLORES["grisMedio"], width=2, dash="dash"),
                    hovertemplate="%{x|%d %b %Y}<br>"
                    + nombreBenchmark
                    + ": <b>%{y:.1f}</b><extra></extra>",
                )
            )
        return aplicarTema(figura, mostrarLeyenda=True)
    except Exception as error:
        registrarEvento(f"Error al graficar el comparativo: {error}", "ERROR")
        return go.Figure()


def graficarSentimiento(serieSentimiento):
    """
    Sentimiento diario. Con muchos dias (tono de prensa) se dibuja como linea
    con su media de 30 dias y la media del periodo como referencia; con pocos
    (titulares) como barras positivas/negativas.
    """
    try:
        if serieSentimiento is None or serieSentimiento.empty:
            return go.Figure()
        valores = serieSentimiento["sentimientoDiario"]
        figura = go.Figure()
        if len(valores) > 60:
            figura.add_trace(go.Scatter(x=valores.index, y=valores, mode="lines", name="Tono diario",
                                        line=dict(color=COLORES["grisMedio"], width=1),
                                        hovertemplate="%{x|%d %b %Y}<br>Tono: <b>%{y:.2f}</b><extra></extra>"))
            figura.add_trace(go.Scatter(x=valores.index, y=valores.rolling(30, min_periods=10).mean(), mode="lines",
                                        name="Media de 30 días", line=dict(color=COLORES["azul"], width=2.5)))
            figura.add_hline(y=float(valores.mean()), line_width=1, line_dash="dash", line_color=COLORES["grisOscuro"],
                             annotation_text="Promedio del periodo", annotation_position="bottom right")
        else:
            figura.add_trace(go.Bar(x=valores.index, y=valores, name="Sentimiento diario",
                                    marker_color=[COLORES["verde"] if v >= 0 else COLORES["rojo"] for v in valores],
                                    hovertemplate="%{x|%d %b}<br>Sentimiento: <b>%{y:.3f}</b><extra></extra>"))
            if "mediaMovil3d" in serieSentimiento.columns:
                figura.add_trace(go.Scatter(x=serieSentimiento.index, y=serieSentimiento["mediaMovil3d"], mode="lines",
                                            name="Media móvil 3 días", line=dict(color=COLORES["azul"], width=2)))
            figura.add_hline(y=0, line_width=1, line_color=COLORES["grisMedio"])
        return aplicarTema(figura, altura=300, mostrarLeyenda=True)
    except Exception as error:
        registrarEvento(f"Error al graficar el sentimiento: {error}", "ERROR")
        return go.Figure()


def graficarPronostico(historico, pronostico, diasHistoria=90):
    """
    Historia en linea continua, pronostico en linea punteada desde el ultimo
    dato real y banda de confianza sombreada (el pronostico empieza el dia
    habil siguiente al ultimo dato).
    """
    try:
        if pronostico is None or pronostico.empty:
            return go.Figure()
        historiaReciente = historico.tail(diasHistoria)
        ultimo = historiaReciente["nav"].tail(1)
        figura = go.Figure()
        bandaX = list(ultimo.index) + list(pronostico.index)
        figura.add_trace(
            go.Scatter(
                x=bandaX + bandaX[::-1],
                y=list(ultimo.values) + list(pronostico["bandaSuperior"])
                + list(pronostico["bandaInferior"][::-1]) + list(ultimo.values),
                fill="toself", fillcolor="rgba(51, 102, 204, 0.10)", line=dict(color="rgba(0,0,0,0)"),
                name="Banda 90%", hoverinfo="skip",
            )
        )
        figura.add_trace(
            go.Scatter(
                x=historiaReciente.index, y=historiaReciente["nav"], mode="lines", name="Histórico",
                line=dict(color=COLORES["azul"], width=2.5),
                hovertemplate="%{x|%d %b}<br>NAV: <b>$%{y:.2f}</b><extra></extra>",
            )
        )
        puente = pd.concat([ultimo, pronostico["navEstimado"]])
        figura.add_trace(
            go.Scatter(
                x=puente.index, y=puente.values, mode="lines", name="Pronóstico",
                line=dict(color=COLORES["azul"], width=2.5, dash="dot"),
                hovertemplate="%{x|%d %b}<br>Proyectado: <b>$%{y:.2f}</b><extra></extra>",
            )
        )
        figura.add_vline(x=ultimo.index[-1], line_width=1, line_dash="dash", line_color=COLORES["grisMedio"])
        return aplicarTema(figura, altura=400, mostrarLeyenda=True)
    except Exception as error:
        registrarEvento(f"Error al graficar el pronostico: {error}", "ERROR")
        return go.Figure()


def graficarImportanciaVariables(tablaImportancia):
    """Barras horizontales con la importancia de las variables del modelo."""
    try:
        if tablaImportancia is None or tablaImportancia.empty:
            return go.Figure()

        from src.preparacionDatos import nombreVariable

        tabla = tablaImportancia.sort_values("importancia")
        figura = go.Figure(
            go.Bar(
                x=tabla["importancia"],
                y=tabla["variable"].map(nombreVariable),
                orientation="h",
                marker_color=COLORES["azul"],
                hovertemplate="%{y}: <b>%{x:.1%}</b><extra></extra>",
            )
        )
        figura.update_xaxes(tickformat=".0%")
        return aplicarTema(figura, altura=380)
    except Exception as error:
        registrarEvento(f"Error al graficar la importancia: {error}", "ERROR")
        return go.Figure()


def graficarDistribucionRetornos(historico):
    """Histograma de los retornos diarios con la marca del VaR 95%."""
    try:
        retornos = historico["retornoDiario"].dropna() * 100
        figura = go.Figure(
            go.Histogram(
                x=retornos,
                nbinsx=60,
                marker_color=COLORES["azul"],
                opacity=0.85,
                hovertemplate="Retorno: %{x:.2f}%<br>Días: <b>%{y}</b><extra></extra>",
            )
        )
        var95 = retornos.quantile(0.05)
        figura.add_vline(
            x=var95,
            line_width=2,
            line_dash="dash",
            line_color=COLORES["rojo"],
            annotation_text=f"VaR 95%: {var95:.2f}%",
            annotation_position="top left",
        )
        figura.update_xaxes(ticksuffix="%")
        return aplicarTema(figura, altura=320)
    except Exception as error:
        registrarEvento(f"Error al graficar la distribucion: {error}", "ERROR")
        return go.Figure()


def graficarRadarRiesgo(componentes):
    """Radar con los componentes del puntaje de riesgo."""
    try:
        if not componentes:
            return go.Figure()

        etiquetas = {
            "volatilidad": "Volatilidad",
            "maxDrawdown": "Caída máxima",
            "beta": "Beta",
            "sharpe": "Sharpe",
            "sentimiento": "Sentimiento",
        }
        nombres = [etiquetas.get(k, k) for k in componentes.keys()]
        valores = list(componentes.values())

        figura = go.Figure(
            go.Scatterpolar(
                r=valores + [valores[0]],
                theta=nombres + [nombres[0]],
                fill="toself",
                fillcolor="rgba(51, 102, 204, 0.18)",
                line=dict(color=COLORES["azul"], width=2),
                hovertemplate="%{theta}: <b>%{r}</b>/10<extra></extra>",
            )
        )
        figura.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 10], gridcolor=COLORES["borde"]),
                angularaxis=dict(gridcolor=COLORES["borde"]),
                bgcolor="rgba(0,0,0,0)",
            ),
            height=340,
            font=TIPOGRAFIA,
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=40, r=40, t=30, b=30),
            showlegend=False,
        )
        return figura
    except Exception as error:
        registrarEvento(f"Error al graficar el radar de riesgo: {error}", "ERROR")
        return go.Figure()


def graficarRentabilidadPeriodos(resumenPeriodos):
    """Barras con la rentabilidad del fondo por periodo."""
    try:
        if not resumenPeriodos:
            return go.Figure()

        etiquetas = list(resumenPeriodos.keys())
        valores = [v * 100 if v == v else 0 for v in resumenPeriodos.values()]
        colores = [COLORES["verde"] if v >= 0 else COLORES["rojo"] for v in valores]

        figura = go.Figure(
            go.Bar(
                x=etiquetas,
                y=valores,
                marker_color=colores,
                text=[f"{v:+.1f}%" for v in valores],
                textposition="outside",
                hovertemplate="%{x}: <b>%{y:.2f}%</b><extra></extra>",
            )
        )
        figura.update_yaxes(ticksuffix="%")
        return aplicarTema(figura, altura=300)
    except Exception as error:
        registrarEvento(f"Error al graficar la rentabilidad por periodo: {error}", "ERROR")
        return go.Figure()


COLOR_VEREDICTO = {
    "Recomendable": COLORES["verde"],
    "Aceptable": COLORES["ambar"],
    "No recomendable": COLORES["rojo"],
    "Sin datos": COLORES["grisMedio"],
}


def graficarRankingBonos(tablaRanking, umbralRecomendable=60, umbralAceptable=45):
    """Barras horizontales con el puntaje de cada bono, coloreadas por veredicto."""
    try:
        if tablaRanking is None or tablaRanking.empty:
            return go.Figure()
        tabla = tablaRanking.dropna(subset=["puntaje"]).iloc[::-1]
        figura = go.Figure(
            go.Bar(
                x=tabla["puntaje"], y=tabla["ticker"], orientation="h",
                marker_color=[COLOR_VEREDICTO.get(v, COLORES["grisMedio"]) for v in tabla["veredicto"]],
                text=[f"{p:.0f} · {v}" for p, v in zip(tabla["puntaje"], tabla["veredicto"], strict=True)],
                textposition="outside", customdata=tabla["segmento"],
                hovertemplate="<b>%{y}</b> · %{customdata}<br>Puntaje: %{x:.0f}/100<extra></extra>",
            )
        )
        for umbral, texto in ((umbralAceptable, "Aceptable"), (umbralRecomendable, "Recomendable")):
            figura.add_vline(x=umbral, line_width=1, line_dash="dot", line_color=COLORES["grisMedio"],
                             annotation_text=texto, annotation_position="top")
        figura.update_xaxes(range=[0, 110], title_text="Puntaje (0-100)")
        return aplicarTema(figura, altura=max(220, 56 * len(tabla) + 60))
    except Exception as error:
        registrarEvento(f"Error al graficar el ranking de bonos: {error}", "ERROR")
        return go.Figure()


def graficarProyeccionInversion(trayectoria, simbolo="$"):
    """Abanico de escenarios (P10-P90 y P25-P75), mediana, capital aportado y liquidez."""
    try:
        if trayectoria is None or trayectoria.empty:
            return go.Figure()
        x = trayectoria["mes"]
        figura = go.Figure()
        for bajo, alto, opacidad, nombre in (("p10", "p90", 0.10, "Escenarios P10-P90"), ("p25", "p75", 0.20, "Escenarios P25-P75")):
            figura.add_trace(
                go.Scatter(
                    x=list(x) + list(x[::-1]), y=list(trayectoria[alto]) + list(trayectoria[bajo][::-1]),
                    fill="toself", fillcolor=f"rgba(51, 102, 204, {opacidad})", line=dict(color="rgba(0,0,0,0)"),
                    name=nombre, hoverinfo="skip",
                )
            )
        figura.add_trace(
            go.Scatter(x=x, y=trayectoria["p50"], mode="lines", name="Escenario central (mediana)",
                       line=dict(color=COLORES["azul"], width=2.5),
                       hovertemplate="Mes %{x}<br>Mediana: <b>" + simbolo + "%{y:,.0f}</b><extra></extra>")
        )
        figura.add_trace(
            go.Scatter(x=x, y=trayectoria["aportado"], mode="lines", name="Capital aportado",
                       line=dict(color=COLORES["grisOscuro"], width=1.5),
                       hovertemplate="Mes %{x}<br>Aportado: <b>" + simbolo + "%{y:,.0f}</b><extra></extra>")
        )
        if "liquidez" in trayectoria:
            figura.add_trace(
                go.Scatter(x=x, y=trayectoria["liquidez"], mode="lines", name="Alternativa: liquidez",
                           line=dict(color=COLORES["grisMedio"], width=1.5, dash="dash"),
                           hovertemplate="Mes %{x}<br>Liquidez: <b>" + simbolo + "%{y:,.0f}</b><extra></extra>")
            )
        figura.update_xaxes(title_text="Meses")
        figura.update_yaxes(tickprefix=simbolo)
        return aplicarTema(figura, altura=380, mostrarLeyenda=True)
    except Exception as error:
        registrarEvento(f"Error al graficar la proyeccion: {error}", "ERROR")
        return go.Figure()


def graficarBacktest(tablaBacktest):
    """Retorno posterior de cada semana, coloreado por la senal emitida."""
    try:
        if tablaBacktest is None or tablaBacktest.empty:
            return go.Figure()
        colores = {"COMPRAR": COLORES["verde"], "MANTENER": COLORES["azul"], "REDUCIR": COLORES["rojo"]}
        figura = go.Figure()
        for accion, color in colores.items():
            tramo = tablaBacktest.loc[tablaBacktest["accion"] == accion]
            if tramo.empty:
                continue
            figura.add_trace(
                go.Scatter(
                    x=tramo["fecha"], y=tramo["retornoPosterior"] * 100, mode="markers", name=accion,
                    marker=dict(color=color, size=7, opacity=0.8),
                    hovertemplate="%{x|%d %b %Y}<br>" + accion + ": <b>%{y:+.1f}%</b> después<extra></extra>",
                )
            )
        figura.add_hline(y=0, line_width=1, line_color=COLORES["grisMedio"])
        figura.update_yaxes(ticksuffix="%", title_text="Retorno en el horizonte")
        return aplicarTema(figura, altura=320, mostrarLeyenda=True)
    except Exception as error:
        registrarEvento(f"Error al graficar el backtest: {error}", "ERROR")
        return go.Figure()


def graficarMapaBonos(evaluados, clavesSeleccionadas=None, maximo=1500):
    """
    Mapa de los bonos de un fondo: plazo (x) contra rendimiento esperado (y),
    color por veredicto y tamano por peso en el fondo. Los bonos elegidos se
    marcan con un anillo.
    """
    try:
        if evaluados is None or evaluados.empty:
            return go.Figure()
        tabla = evaluados.dropna(subset=["rendimientoEsperado"]).head(maximo)
        figura = go.Figure()
        for veredicto, color in COLOR_VEREDICTO.items():
            tramo = tabla.loc[tabla["veredicto"] == veredicto]
            if tramo.empty:
                continue
            figura.add_trace(
                go.Scatter(
                    x=tramo["plazo"], y=tramo["rendimientoEsperado"] * 100, mode="markers", name=veredicto,
                    marker=dict(color=color, size=(tramo["pesoPct"].fillna(0).clip(lower=0.05) ** 0.5 * 6).clip(4, 22),
                                opacity=0.65, line=dict(width=0)),
                    customdata=tramo[["emisor", "cupon", "calidad"]].assign(cupon=tramo["cupon"] * 100).to_numpy(),
                    text=tramo["vencimiento"].dt.strftime("%m/%Y"),
                    hovertemplate="<b>%{customdata[0]}</b><br>Cupón %{customdata[1]:.3f}% · vence %{text}"
                    "<br>Rend. esperado %{y:.2f}% · calidad %{customdata[2]}<extra></extra>",
                )
            )
        if clavesSeleccionadas:
            elegidos = tabla.loc[tabla["clave"].isin(clavesSeleccionadas)]
            figura.add_trace(
                go.Scatter(x=elegidos["plazo"], y=elegidos["rendimientoEsperado"] * 100, mode="markers",
                           name="Tu selección", marker=dict(size=18, color="rgba(0,0,0,0)",
                                                            line=dict(color=COLORES["texto"], width=2)),
                           hoverinfo="skip")
            )
        figura.update_xaxes(title_text="Años al vencimiento")
        figura.update_yaxes(title_text="Rendimiento esperado anual", ticksuffix="%")
        return aplicarTema(figura, altura=380, mostrarLeyenda=True)
    except Exception as error:
        registrarEvento(f"Error al graficar el mapa de bonos: {error}", "ERROR")
        return go.Figure()


def graficarAlternativas(alternativas, simbolo="$"):
    """
    Rango P10-P90 y mediana del valor final de cada alternativa (bonos
    elegidos, fondo completo, liquidez), con el monto invertido como referencia.
    alternativas: lista de dicts {nombre, p10, p50, p90, invertido}.
    """
    try:
        if not alternativas:
            return go.Figure()
        nombres = [a["nombre"] for a in alternativas][::-1]
        datos = alternativas[::-1]
        figura = go.Figure()
        figura.add_trace(
            go.Bar(
                y=nombres, x=[a["p90"] - a["p10"] for a in datos], base=[a["p10"] for a in datos], orientation="h",
                marker_color="rgba(51, 102, 204, 0.25)", name="Rango probable (P10-P90)",
                hovertemplate="%{y}<br>P10 " + simbolo + "%{base:,.0f}<extra></extra>",
            )
        )
        figura.add_trace(
            go.Scatter(
                y=nombres, x=[a["p50"] for a in datos], mode="markers+text", name="Escenario central",
                marker=dict(color=[COLORES["verde"] if a["nombre"].startswith("★") else COLORES["azul"] for a in datos], size=13),
                text=[f"{simbolo}{a['p50']:,.0f}" for a in datos],
                textposition="top center", hovertemplate="%{y}<br>Mediana: <b>" + simbolo + "%{x:,.0f}</b><extra></extra>",
            )
        )
        figura.add_vline(x=datos[0]["invertido"], line_width=1, line_dash="dash", line_color=COLORES["grisOscuro"],
                         annotation_text="Monto invertido", annotation_position="bottom")
        figura.update_xaxes(tickprefix=simbolo)
        return aplicarTema(figura, altura=90 * len(datos) + 90, mostrarLeyenda=True)
    except Exception as error:
        registrarEvento(f"Error al graficar las alternativas: {error}", "ERROR")
        return go.Figure()
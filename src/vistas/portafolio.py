"""
portafolio.py (vista)
Pestaña «Mi portafolio»: el usuario elige de 2 a 6 fondos del catalogo,
fija los pesos (o pide pesos sugeridos para su perfil), ve el riesgo y el
retorno de la mezcla real, el aporte de cada fondo al riesgo, costos y
minimos, la proyeccion con aportes y puede descargarlo.
"""

import pandas as pd
import streamlit as st

from config import RETORNO_ESPERADO_ACCIONES

from src.analisisBonos import proyectarInversion, rendimientoAnualConAportes
from src.catalogoBonos import PARAMETROS_PERFIL
from src.estilos import COLORES, abrirPanel, filaPeso, tituloSeccion
from src.graficos import graficarComposicion, graficarCrecimiento
from src.portafolio import (
    MAXIMO_FONDOS,
    evaluarPortafolio,
    metricasMezcla,
    retornosConjuntos,
    sugerenciaInicial,
    sugerirPesos,
    universoPortafolio,
)
from src.utilidades import esNulo, formatearMoneda, formatearPorcentaje
from src.vistas.comunes import ANCHO, filaTarjetas, tablaHtml

COLOR_CLASE = {"Acciones": COLORES["azul"], "Bonos": COLORES["verde"], "Mixto": COLORES["turquesa"]}
ICONO = {"Recomendable": "🟢", "Aceptable": "🟡", "No recomendable": "🔴"}


def _clavePesos(perfil):
    return f"portafolio_{perfil}"


def _estadoPortafolio(universo, perfil):
    """Fondos y pesos guardados en la sesion (o la sugerencia inicial la primera vez)."""
    clave = _clavePesos(perfil)
    if clave not in st.session_state:
        tickers, pesos = sugerenciaInicial(universo, perfil)
        st.session_state[clave] = {"fondos": tickers, "pesos": pesos}
    estado = st.session_state[clave]
    estado["fondos"] = [t for t in estado["fondos"] if t in universo]
    estado["pesos"] = {t: w for t, w in estado["pesos"].items() if t in estado["fondos"]}
    return estado


def _aplicarSugerencia(universo, perfil, tasaLibre):
    estado = st.session_state[_clavePesos(perfil)]
    retornos = retornosConjuntos(universo, estado["fondos"])
    if retornos.empty:
        return
    estado["pesos"] = sugerirPesos(retornos, perfil, tasaLibre)
    for t, w in estado["pesos"].items():
        st.session_state[f"peso_{perfil}_{t}"] = float(round(w * 100))


def _pesosIguales(perfil):
    estado = st.session_state[_clavePesos(perfil)]
    liquidez = PARAMETROS_PERFIL[perfil]["liquidez"]
    n = max(len(estado["fondos"]), 1)
    estado["pesos"] = {t: round((1 - liquidez) / n, 2) for t in estado["fondos"]}
    for t, w in estado["pesos"].items():
        st.session_state[f"peso_{perfil}_{t}"] = float(round(w * 100))


def _etiqueta(universo):
    return lambda t: f"{universo[t]['nombre']} · {universo[t]['clase']} · {ICONO.get(universo[t]['veredicto'], '⚪')}"


def dibujarPortafolio(datos, perfil):
    """Pestaña completa."""
    tasaLibre = datos["tasaLibre"]
    universo = universoPortafolio(datos, perfil)
    if not universo:
        st.info("Aún no hay fondos con historia suficiente. Presiona «Actualizar datos».")
        return None
    tituloSeccion("Arma tu portafolio", f"Elige de 2 a {MAXIMO_FONDOS} fondos y reparte tu dinero. Lo que no asignes queda en liquidez.")
    estado = _estadoPortafolio(universo, perfil)

    # --- 1. Fondos ------------------------------------------------------------
    opciones = sorted(universo, key=lambda t: (not universo[t]["enPerfil"], universo[t]["clase"], universo[t]["veredicto"] != "Recomendable", t))
    elegidos = st.multiselect("Fondos del portafolio", opciones, default=estado["fondos"], format_func=_etiqueta(universo),
                              max_selections=MAXIMO_FONDOS, key=f"fondosPortafolio_{perfil}",
                              placeholder="Escribe para buscar un fondo del catálogo")
    if elegidos != estado["fondos"]:
        nuevos = [t for t in elegidos if t not in estado["pesos"]]
        estado["fondos"] = list(elegidos)
        estado["pesos"] = {t: estado["pesos"].get(t, 0.0) for t in elegidos}
        if nuevos and not any(estado["pesos"].values()):
            _pesosIguales(perfil)
    if len(estado["fondos"]) < 2:
        st.info("Elige al menos dos fondos: uno de acciones (o mixto) y uno de bonos es un buen comienzo.")
        return None

    # --- 2. Pesos -------------------------------------------------------------
    columnas = st.columns([1, 1, 3])
    columnas[0].button("Sugerir pesos para mi perfil", key=f"sugerirPesos_{perfil}", type="primary", **ANCHO,
                       on_click=_aplicarSugerencia, args=(universo, perfil, tasaLibre),
                       help="Busca la mezcla con mejor relación retorno/riesgo que quepa en la tolerancia de tu perfil.")
    columnas[1].button("Partes iguales", key=f"pesosIguales_{perfil}", **ANCHO, on_click=_pesosIguales, args=(perfil,))
    filas = st.columns(min(len(estado["fondos"]), 3))
    pesos = {}
    for i, t in enumerate(estado["fondos"]):
        clave = f"peso_{perfil}_{t}"
        if clave not in st.session_state:
            st.session_state[clave] = float(round(estado["pesos"].get(t, 0.0) * 100))
        valor = filas[i % len(filas)].number_input(f"{universo[t]['nombre']} (%)", min_value=0.0, max_value=100.0, step=5.0, key=clave)
        pesos[t] = float(valor) / 100
    estado["pesos"] = pesos
    total = sum(pesos.values())
    liquidez = 1 - total
    if total > 1.0001:
        st.error(f"Los pesos suman {total:.0%}. Baja alguno hasta que sumen 100% o menos.")
        return None
    st.markdown("".join(filaPeso(universo[t]["nombre"], w, COLOR_CLASE.get(universo[t]["clase"])) for t, w in pesos.items() if w > 0)
                + filaPeso(f"Liquidez ({tasaLibre:.2%})", liquidez, COLORES["grisMedio"]), unsafe_allow_html=True)

    # --- 3. Evaluacion --------------------------------------------------------
    ev = evaluarPortafolio(universo, pesos, perfil, tasaLibre)
    if not ev:
        st.info("Asigna un peso mayor a 0% a por lo menos un fondo.")
        return None
    if ev.get("error"):
        st.error(ev["error"])
        return None
    m = ev["metricas"]
    tono = {"Recomendable": "verde", "Aceptable": "ambar", "No recomendable": "roja"}[ev["veredicto"]]
    filaTarjetas([
        {"etiqueta": "¿Encaja con tu perfil?", "valor": ev["veredicto"], "color": tono,
         "nota": f"Se mueve {m['volatilidad']:.0%} al año; tu perfil tolera hasta {ev['volatilidadMaxima']:.0%}"},
        {"etiqueta": "Retorno esperado", "valor": formatearPorcentaje(ev["retornoEsperado"], 1),
         "nota": f"Histórico de {m['meses'] // 12} años: {formatearPorcentaje(m['retornoAnual'], 1, True)} al año"},
        {"etiqueta": "Peor caída histórica", "valor": formatearPorcentaje(m["caidaMaxima"], 1), "tono": "negativo",
         "nota": "De la mezcla, con la correlación real entre fondos"},
        {"etiqueta": "Costo y mínimo", "valor": formatearPorcentaje(ev["gastoPonderado"], 2) + " al año",
         "nota": (f"Mínimos de entrada: {formatearMoneda(ev['minimoTotal'])} en total" if ev["minimoTotal"] else "Sin montos mínimos")},
    ])
    for tonoAviso, texto in ev["avisos"]:
        (st.error if tonoAviso == "roja" else st.warning)(texto)
    if not ev["avisos"]:
        st.success("Diversificado, dentro de la tolerancia de tu perfil y con fondos recomendables o aceptables.")

    columnas = st.columns([2, 3])
    with columnas[0], abrirPanel("Cómo queda repartido"):
        st.plotly_chart(graficarComposicion(ev["mezcla"]), **ANCHO, key=f"portafolio_mezcla_{perfil}")
        base = ev["mezclaPerfil"]
        st.caption(f"Tu perfil sugiere {base['Renta variable']:.0%} acciones · {base['Renta fija']:.0%} bonos · {base['Liquidez']:.0%} liquidez. "
                   "Los fondos mixtos se reparten entre acciones y bonos.")
    with columnas[1], abrirPanel("Cada fondo en el portafolio"):
        f = ev["filas"]
        vista = pd.DataFrame({
            "Fondo": f["nombre"], "Peso": f["peso"].map(lambda v: f"{v:.0%}"), "Veredicto": f["veredicto"],
            "Aporte al riesgo": f["aporteRiesgo"].map(lambda v: formatearPorcentaje(v, 0)),
            "Retorno esperado": f["retornoEsperado"].map(lambda v: formatearPorcentaje(v, 1)),
            "Gasto": f["gastoAnual"].map(lambda v: formatearPorcentaje(v, 2)),
            "Mínimo": f["minimo"].map(lambda v: formatearMoneda(v) if v else "Sin mínimo"),
        })
        tablaHtml(vista)
        st.caption("«Aporte al riesgo»: qué parte de las subidas y bajadas del portafolio viene de cada fondo. "
                   "Un fondo con 20% del dinero puede aportar 50% del riesgo.")

    # --- 4. Proyeccion --------------------------------------------------------
    with abrirPanel("Cuánto podría ganar este portafolio"):
        columnas = st.columns(3)
        capital = columnas[0].number_input("Capital inicial (USD)", min_value=0.0, value=10000.0, step=1000.0, key=f"capitalPortafolio_{perfil}")
        aporte = columnas[1].number_input("Aporte mensual (USD)", min_value=0.0, value=0.0, step=50.0, key=f"aportePortafolio_{perfil}")
        meses = columnas[2].slider("Plazo (meses)", 12, 120, 36, step=6, key=f"mesesPortafolio_{perfil}")
        if capital + aporte > 0:
            sim = proyectarInversion(ev["historicoMezcla"], ev["retornoEsperado"], capital, aporte, meses, simulaciones=3000,
                                     semilla=29, tasaLiquidez=tasaLibre, centrarMediana=True)
            r = sim["resumen"]
            total = capital + aporte * meses
            filaTarjetas([
                {"etiqueta": f"Ganancia esperada · {meses} meses", "valor": formatearMoneda(r["gananciaMediana"]),
                 "nota": f"{formatearPorcentaje(rendimientoAnualConAportes(r['valorMediano'], capital, aporte, meses), 2)} anual · "
                         f"terminas con {formatearMoneda(r['valorMediano'])} de {formatearMoneda(total)} aportados",
                 "tono": "positivo" if r["gananciaMediana"] >= 0 else "negativo"},
                {"etiqueta": "Rango probable", "valor": f"{formatearMoneda(r['gananciaPesimista'])} a {formatearMoneda(r['gananciaOptimista'])}",
                 "nota": "8 de cada 10 escenarios"},
                {"etiqueta": "Probabilidad de pérdida", "valor": formatearPorcentaje(r["probabilidadPerdida"], 1),
                 "nota": "Terminar con menos de lo aportado"},
                {"etiqueta": "Solo en liquidez", "valor": formatearMoneda(r["valorLiquidez"] - total) if not esNulo(r.get("valorLiquidez")) else "N/D",
                 "nota": f"Ganancia si todo quedara al {tasaLibre:.2%}"},
            ])
        st.caption("Simulación con los retornos mensuales históricos de la mezcla (correlación incluida), re-centrados en el retorno "
                   f"esperado: acciones al {formatearPorcentaje(RETORNO_ESPERADO_ACCIONES, 0)} anual supuesto, bonos a lo que "
                   "rinden hoy. Antes de impuestos; los gastos de los fondos ya están en sus precios.")

    # --- 5. Historia y descarga -------------------------------------------------
    with st.expander("Cómo le habría ido a este portafolio (crecimiento de USD 10 000)"):
        comparables = {"Tu portafolio": m["serie"]}
        tickers, pesosBase = sugerenciaInicial(universo, perfil)
        rb = retornosConjuntos(universo, tickers) if tickers else pd.DataFrame()
        if not rb.empty:
            mb = metricasMezcla(rb.loc[rb.index.isin(m["serie"].index)], pesosBase, tasaLibre)
            if mb:
                comparables["Portafolio sugerido del perfil"] = mb["serie"]
        st.plotly_chart(graficarCrecimiento(comparables), **ANCHO, key=f"portafolio_crecimiento_{perfil}")
        st.caption("Meses en que todos los fondos elegidos tienen datos. Rentabilidad pasada: no garantiza la futura.")
    csv = ev["filas"][["ticker", "nombre", "clase", "peso", "veredicto", "retornoEsperado", "gastoAnual", "minimo"]].to_csv(index=False).encode("utf-8")
    st.download_button("Descargar mi portafolio (CSV)", data=csv, file_name=f"portafolio_{perfil}.csv", mime="text/csv",
                       key=f"descargarPortafolio_{perfil}")
    return ev
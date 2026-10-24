"""
app.py
FundScope - Analitica de Fondos Mutuos con IA Generativa.

Flujo:  Perfil  ->  Fondo a analizar (del grupo de fondos de ese perfil)  ->
        Descriptivo, Predictivo, Prescriptivo y Asesor IA sobre ESE fondo.

El perfil y el fondo se eligen en la parte superior. El fondo por defecto es
el mejor del ranking del perfil; tambien se puede analizar cualquier otro
ticker. Los datos comunes (universo de fondos de bonos, curva del Tesoro,
tasa libre de riesgo) se descargan una vez al presionar «Comenzar»; cada
fondo se descarga (o se lee de la cache) la primera vez que se elige y su
analisis queda en memoria. «Actualizar datos» fuerza una nueva lectura.

Ejecucion:  streamlit run app.py
"""

from collections import OrderedDict

import pandas as pd
import streamlit as st

from config import (
    BENCHMARK_POR_DEFECTO,
    DIAS_PRONOSTICO,
    PERIODO_HISTORICO,
    SEMANAS_EN_MEMORIA,
    TICKER_NOTICIAS_POR_DEFECTO,
)
from src.analisis import descargarComun, descargarFondo, ejecutarAnalisis, rankingsComunes
from src.catalogoBonos import benchmarkParaFondo
from src.datosNoticias import completarHistoriaTono, sugerirTickerNoticias, temaTonoPrensa
from src.estilos import aplicarEstilos, flujoPasos, mostrarCabecera, tituloSeccion
from src.motorPrescriptivo import conclusionParaDatos, determinarProveedorActivo, proveedorListo
from src.preparacionDatos import listarFechasSemanales
from src.utilidades import formatearNumero, formatearPorcentaje
from src.vistas.asesor import dibujarChatAsesor
from src.vistas.comunes import filaTarjetas, formatearFecha, selectorFondo, selectorPerfil
from src.vistas.descriptivo import dibujarDashboardDescriptivo
from src.vistas.predictivo import dibujarDashboardPredictivo
from src.vistas.prescriptivo import dibujarDashboardPrescriptivo

st.set_page_config(page_title="FundScope | Analítica de Fondos Mutuos", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")

PERIODOS = ["1y", "2y", "5y", "10y", "max"]
NOMBRES_PERIODO = {"1y": "1 año", "2y": "2 años", "5y": "5 años", "10y": "10 años", "max": "Toda la historia"}
FONDOS_EN_MEMORIA = 6


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
def dibujarBarraLateral():
    """
    Controles avanzados. Devuelve (parametros, ejecutar, proveedorInfo,
    contenedores); los contenedores de «Semana evaluada» y del tono de prensa
    se llenan despues, cuando ya se sabe que fondo se analiza.
    """
    with st.sidebar:
        st.markdown("### Opciones")
        ejecutar = st.button("🔄 Actualizar datos", type="primary", use_container_width=True,
                             help="Vuelve a descargar los precios y las noticias más recientes.")
        contenedores = {"semana": st.container()}
        with st.expander("Opciones avanzadas"):
            parametros = {
                "periodo": st.selectbox("Años de historia a analizar", PERIODOS, format_func=NOMBRES_PERIODO.get,
                                        index=PERIODOS.index(PERIODO_HISTORICO) if PERIODO_HISTORICO in PERIODOS else 2),
                "dias": st.slider("Pronóstico a cuántos días hábiles", 5, 90, DIAS_PRONOSTICO, step=5),
                "benchmarkManual": st.text_input("Comparar contra (símbolo, opcional)", value="",
                                                 placeholder="Automático según tu perfil").strip().upper(),
                "tickerNoticias": TICKER_NOTICIAS_POR_DEFECTO.strip().upper() if TICKER_NOTICIAS_POR_DEFECTO else "",
            }
            parametros["usarCache"] = not st.checkbox("Descargar todo de nuevo (más lento)", value=False)
        contenedores["tono"] = st.container()

        st.divider()
        reverificar = st.button("Revisar asistente de IA", use_container_width=True)
        proveedorInfo = determinarProveedorActivo(forzarVerificacion=reverificar)
        _, estado, _ = proveedorInfo
        if proveedorListo(estado):
            st.success("✅ Asistente de IA activo")
        else:
            st.warning("Asistente de IA no disponible: el informe se arma con reglas y el chat queda desactivado.")
    return parametros, ejecutar, proveedorInfo, contenedores


def dibujarHistoriaTono(contenedor, ticker, tickerNoticias):
    """Expander para completar meses anteriores del tono de prensa del fondo analizado."""
    with contenedor, st.expander("Historia de noticias"):
        tema = temaTonoPrensa(ticker, tickerNoticias or sugerirTickerNoticias(ticker))
        st.caption("Descarga meses anteriores del ánimo de la prensa sobre este fondo. Con más historia, las noticias "
                   "pesan en la recomendación y en el pronóstico. Tarda unos 5 segundos por cada 3 meses.")
        meses = st.number_input("Meses a descargar", min_value=3, max_value=120, value=24, step=3, key="mesesTono")
        if st.button("Descargar historia", use_container_width=True):
            barra = st.progress(0.0, text="Descargando noticias…")
            r = completarHistoriaTono(tema, int(meses), lambda f, t: barra.progress(min(f, 1.0), text=t))
            textoDesde = f" desde el {r['desde']:%d/%m/%Y}" if r["desde"] is not None else ""
            (st.warning if r["mensaje"] else st.success)(
                f"Listo: {r['total']} días de noticias{textoDesde}. Presiona «Actualizar datos» para usarlos."
                if not r["mensaje"] else "No se pudo descargar todo. Intenta de nuevo en unos minutos."
            )


def dibujarSelectorSemana(contenedor, entrada):
    """«Semana evaluada»: recalcula todo hasta una fecha pasada, sin descargar."""
    with contenedor:
        fechas = listarFechasSemanales(entrada["base"]["historico"])
        seleccion = st.selectbox(
            "Ver cómo estaba en una fecha pasada", ["actual"] + [f"{f:%Y-%m-%d}" for f in fechas],
            format_func=lambda v: "Hoy" if v == "actual" else f"Semana del {pd.Timestamp(v):%d/%m/%Y}",
            key=f"semana_{entrada['base']['ticker']}",
            help="Muestra la recomendación como si fuera esa fecha y qué pasó después.",
        )
    return None if seleccion == "actual" else pd.Timestamp(seleccion)


# ---------------------------------------------------------------------------
# Datos y analisis (con memoria por fondo)
# ---------------------------------------------------------------------------
def cargarComun(usarCache):
    """Datos comunes a todos los fondos (universo de bonos, curva, tasa) y sus rankings por perfil."""
    with st.spinner("Descargando los fondos de bonos de los tres perfiles, la curva del Tesoro y la tasa libre de riesgo..."):
        comun = descargarComun(usarCache)
    st.session_state["comun"] = comun
    st.session_state["rankingsComunes"] = rankingsComunes(comun)
    st.session_state["analisisPorFondo"] = OrderedDict()


def obtenerAnalisis(ticker, benchmark, parametros, forzar=False):
    """Base y analisis del fondo; se reutilizan mientras no cambien el fondo ni los parametros."""
    memoria = st.session_state.setdefault("analisisPorFondo", OrderedDict())
    clave = (ticker, benchmark, parametros["tickerNoticias"], parametros["periodo"], parametros["dias"])
    if forzar or clave not in memoria:
        with st.spinner(f"Descargando y analizando {ticker}..."):
            base = descargarFondo(ticker, benchmark, parametros["periodo"], parametros["tickerNoticias"],
                                  parametros["usarCache"], comun=st.session_state["comun"])
            memoria[clave] = {"base": base, "resultado": ejecutarAnalisis(base, parametros["dias"]),
                              "evaluaciones": OrderedDict()}
        while len(memoria) > FONDOS_EN_MEMORIA:
            memoria.popitem(last=False)
    memoria.move_to_end(clave)
    return memoria[clave]


def obtenerEvaluacion(entrada, fechaCorte):
    """Analisis de la semana elegida (recalculado sin descargar; se guardan las ultimas N)."""
    resultado = entrada["resultado"]
    if fechaCorte is None:
        return resultado
    evaluaciones = entrada["evaluaciones"]
    clave = f"{fechaCorte:%Y-%m-%d}"
    if clave not in evaluaciones:
        with st.spinner(f"Recalculando el análisis al {fechaCorte:%d/%m/%Y}..."):
            evaluaciones[clave] = ejecutarAnalisis(entrada["base"], resultado["diasPronostico"], fechaCorte)
        while len(evaluaciones) > SEMANAS_EN_MEMORIA:
            evaluaciones.popitem(last=False)
    evaluaciones.move_to_end(clave)
    return evaluaciones[clave]


def dibujarGranularidad(datos):
    """Frecuencia, rango y cobertura reales de los datos usados."""
    info = datos.get("granularidad", {})
    filaTarjetas([
        {"etiqueta": "Precios diarios", "valor": formatearNumero(info.get("observacionesNav"), 0),
         "nota": f"{formatearFecha(info.get('desdeNav'))} → {formatearFecha(info.get('hastaNav'))}"},
        {"etiqueta": "Noticias", "valor": formatearNumero(info.get("totalNoticias"), 0),
         "nota": f"{formatearFecha(info.get('desdeNoticias'))} → {formatearFecha(info.get('hastaNoticias'))}"},
        {"etiqueta": "Días con noticias", "valor": formatearPorcentaje(info.get("coberturaNoticias"), 0),
         "nota": f"{info.get('diasConNoticias', 0)} días"},
    ])


def mostrarBienvenida(parametros):
    """Pantalla inicial: que hace la app y un unico boton grande."""
    tituloSeccion("Tres pasos", "Eliges tu perfil, eliges un fondo y te decimos si conviene invertir y cuánto podrías ganar.")
    st.markdown(flujoPasos([{"titulo": "Paso 1", "valor": "Tu perfil", "estado": "activo"},
                            {"titulo": "Paso 2", "valor": "El fondo", "estado": ""},
                            {"titulo": "Paso 3", "valor": "¿Invertir o no?", "estado": ""}]), unsafe_allow_html=True)
    _, centro, _ = st.columns([1, 2, 1])
    if centro.button("Comenzar", key="comenzar", type="primary", use_container_width=True):
        cargarComun(parametros["usarCache"])
        st.rerun()
    st.caption("La primera vez descarga los fondos de bonos de los tres perfiles (30-60 s). "
               "Los datos no se actualizan solos: se renuevan cuando lo pides.")


def principal():
    aplicarEstilos()
    mostrarCabecera("Proyecto académico · CRISP-ML(Q)")
    parametros, ejecutar, proveedorInfo, contenedores = dibujarBarraLateral()

    if ejecutar:
        cargarComun(parametros["usarCache"])
    if "comun" not in st.session_state:
        mostrarBienvenida(parametros)
        return

    # ---- Paso 1: perfil -------------------------------------------------------
    flujo = st.container()  # la barra de 3 pasos se dibuja al final, cuando ya se sabe que eligio el usuario
    tituloSeccion("1 · ¿Qué tipo de inversor eres?")
    perfil = selectorPerfil()

    # ---- Paso 2: fondo --------------------------------------------------------
    tablaPerfil, _ = st.session_state["rankingsComunes"].get(perfil, (pd.DataFrame(), {}))
    tituloSeccion("2 · ¿Qué fondo quieres analizar?", f"Fondos de bonos para el perfil {perfil}, del mejor al peor.")
    ticker = selectorFondo(perfil, tablaPerfil)
    if not ticker:
        with flujo:
            st.markdown(flujoPasos([{"titulo": "Perfil", "valor": perfil, "estado": "listo"},
                                    {"titulo": "Fondo", "valor": "Elige uno de la lista", "estado": "activo"},
                                    {"titulo": "Resultado", "valor": "—", "estado": ""}]), unsafe_allow_html=True)
        st.info("Busca el fondo en la lista y presiona «Analizar».")
        return
    benchmark = parametros["benchmarkManual"] or benchmarkParaFondo(ticker, perfil, BENCHMARK_POR_DEFECTO)
    entrada = obtenerAnalisis(ticker, benchmark, parametros, forzar=ejecutar)
    dibujarHistoriaTono(contenedores["tono"], ticker, parametros["tickerNoticias"])
    if not entrada["resultado"].get("exito"):
        st.error(entrada["resultado"].get("mensaje") or f"No se pudo completar el análisis de {ticker}. Revisa el ticker.")
        return
    fechaCorte = dibujarSelectorSemana(contenedores["semana"], entrada)

    datos = obtenerEvaluacion(entrada, fechaCorte)
    if not datos.get("exito"):
        st.error(datos.get("mensaje") or "No se pudo completar el análisis de esa semana.")
        return

    # ---- Paso 3: resultado ----------------------------------------------------
    tituloSeccion(f"3 · Resultado para {datos.get('nombreFondo') or ticker}")
    if datos.get("fechaCorte") is not None:
        st.info(f"**Evaluación retrospectiva al {datos['fechaCorte']:%d/%m/%Y}.** Precios y noticias solo hasta ese día.")

    pestanas = st.tabs(["🧭 ¿Qué hago?", "📊 ¿Qué pasó?", "🔮 ¿Qué podría pasar?", "💬 Asesor IA"])
    with pestanas[0]:
        decision = dibujarDashboardPrescriptivo(datos, perfil, proveedorInfo)
    with pestanas[1]:
        dibujarDashboardDescriptivo(datos, perfil)
    with pestanas[2]:
        dibujarDashboardPredictivo(datos)
    with pestanas[3]:
        dibujarChatAsesor(datos, perfil, proveedorInfo, decision)
    conclusion = (decision or {}).get("conclusion") or conclusionParaDatos(datos, perfil)
    with flujo:  # la barra de arriba muestra la conclusion final (sobre el fondo o sobre tus bonos)
        st.markdown(flujoPasos([{"titulo": "Perfil", "valor": perfil, "estado": "listo"},
                                {"titulo": "Fondo", "valor": datos.get("nombreCorto") or ticker, "estado": "listo"},
                                {"titulo": "Resultado", "valor": conclusion["decision"], "estado": "activo"}]), unsafe_allow_html=True)

    # Datos y calidad: al final, plegado (es informacion de respaldo, no de decision)
    st.write("")
    with st.expander(f"Datos usados · actualizados al {formatearFecha(datos['fechaDatoFinal'])}"):
        st.caption(f"Precios de Yahoo Finance descargados el {entrada['base']['fechaDescarga']:%d/%m/%Y a las %H:%M}. "
                   "Proyecto académico: no es asesoría financiera.")
        dibujarGranularidad(datos)


principal()
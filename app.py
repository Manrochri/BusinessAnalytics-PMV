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
from src.estilos import aplicarEstilos, mostrarCabecera
from src.modeloClasificacionRiesgo import COLUMNAS_PREDICTORAS_RIESGO
from src.motorPrescriptivo import determinarProveedorActivo, nombreProveedor, proveedorListo
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
        st.markdown("### Configuración del análisis")
        st.caption("El perfil y el fondo se eligen arriba, en la página.")
        parametros = {
            "benchmarkManual": st.text_input(
                "Benchmark (opcional)", value="", placeholder="Automático según el perfil",
                help="Vacío = automático: BIL (letras del Tesoro) en Conservador y AGG (mercado de bonos) en Moderado y "
                     f"Agresivo; {BENCHMARK_POR_DEFECTO} para fondos fuera del catálogo. Usa índices de retorno total o ETF.",
            ).strip().upper(),
            "tickerNoticias": st.text_input("Ticker para noticias (opcional)", value=TICKER_NOTICIAS_POR_DEFECTO,
                                            placeholder="Se detecta automáticamente si se deja vacío").strip().upper(),
            "periodo": st.selectbox("Periodo histórico", PERIODOS,
                                    index=PERIODOS.index(PERIODO_HISTORICO) if PERIODO_HISTORICO in PERIODOS else 2,
                                    help="Con 10 años el backtest y el clasificador de riesgo tienen más historia."),
            "dias": st.slider("Horizonte de pronóstico (días hábiles)", 5, 90, DIAS_PRONOSTICO, step=5),
        }
        contenedores = {"semana": st.container()}
        parametros["usarCache"] = st.checkbox("Usar datos en caché", value=True,
                                              help="Desactívalo para forzar una descarga nueva de precios, titulares y tono de prensa.")
        st.divider()
        ejecutar = st.button("Actualizar datos", type="primary", use_container_width=True,
                             help="Vuelve a leer los datos comunes y los del fondo elegido.")
        contenedores["tono"] = st.container()

        st.divider()
        st.markdown("### Proveedor de IA generativa")
        reverificar = st.button("Volver a verificar", use_container_width=True)
        proveedorInfo = determinarProveedorActivo(forzarVerificacion=reverificar)
        proveedor, estado, forzado = proveedorInfo
        etiqueta = nombreProveedor(proveedor) + (" · forzado en .env" if forzado else "")
        if proveedorListo(estado):
            st.success(f"**{etiqueta}**\n\n{estado['mensaje']}")
        elif estado.get("disponible"):
            st.warning(f"**{etiqueta}**\n\n{estado['mensaje']}")
        else:
            st.error(f"**{etiqueta}**\n\n{estado['mensaje']}")
            st.caption("Sin proveedor listo: el informe se arma con reglas y el chat no está disponible.")
    return parametros, ejecutar, proveedorInfo, contenedores


def dibujarHistoriaTono(contenedor, ticker, tickerNoticias):
    """Expander para completar meses anteriores del tono de prensa del fondo analizado."""
    with contenedor, st.expander("Historia del tono de prensa"):
        tema = temaTonoPrensa(ticker, tickerNoticias or sugerirTickerNoticias(ticker))
        st.caption(f"Tono diario de la prensa sobre {tema} (tema de {ticker}; GDELT, gratis y sin clave). Cada análisis suma "
                   "los últimos 3 meses; aquí puedes completar meses anteriores (una consulta cada ~5 s). Con ≥ 120 días "
                   "participa en la señal, y con historia suficiente entra al modelo.")
        meses = st.number_input("Meses a completar", min_value=3, max_value=120, value=24, step=3, key="mesesTono")
        if st.button("Completar historia del tono", use_container_width=True):
            barra = st.progress(0.0, text="Consultando GDELT...")
            r = completarHistoriaTono(tema, int(meses), lambda f, t: barra.progress(min(f, 1.0), text=t))
            textoDesde = f" desde el {r['desde']:%d/%m/%Y}" if r["desde"] is not None else ""
            (st.warning if r["mensaje"] else st.success)(
                f"{r['diasNuevos']} días nuevos en {r['consultas']} consulta(s); {r['total']} días acumulados{textoDesde}. "
                + (r["mensaje"] + " " if r["mensaje"] else "") + "Presiona «Actualizar datos» para usarlos."
            )


def dibujarSelectorSemana(contenedor, entrada):
    """«Semana evaluada»: recalcula todo hasta una fecha pasada, sin descargar."""
    with contenedor:
        fechas = listarFechasSemanales(entrada["base"]["historico"])
        seleccion = st.selectbox(
            "Semana evaluada", ["actual"] + [f"{f:%Y-%m-%d}" for f in fechas],
            format_func=lambda v: "Última disponible (hoy)" if v == "actual" else f"Semana al {pd.Timestamp(v):%d/%m/%Y}",
            key=f"semana_{entrada['base']['ticker']}",
            help="Recalcula todo con los datos disponibles hasta ese día, sin volver a descargar.",
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
        {"etiqueta": "Frecuencia del NAV", "valor": info.get("frecuenciaNav", "N/D")},
        {"etiqueta": "Observaciones del NAV", "valor": formatearNumero(info.get("observacionesNav"), 0),
         "nota": f"{formatearFecha(info.get('desdeNav'))} → {formatearFecha(info.get('hastaNav'))}"},
        {"etiqueta": "Noticias usadas", "valor": formatearNumero(info.get("totalNoticias"), 0),
         "nota": f"{formatearFecha(info.get('desdeNoticias'))} → {formatearFecha(info.get('hastaNoticias'))}"},
        {"etiqueta": "Historial con noticias", "valor": formatearPorcentaje(info.get("coberturaNoticias"), 1),
         "nota": f"{info.get('diasConNoticias', 0)} días distintos"},
    ])
    modelo = datos.get("modelo", {})
    if modelo.get("columnas"):
        st.caption(f"**Variables de los modelos de regresión ({len(modelo['columnas'])}):** " + ", ".join(modelo["columnas"]))
    st.caption(f"**Variables del clasificador de riesgo ({len(COLUMNAS_PREDICTORAS_RIESGO)}):** " + ", ".join(COLUMNAS_PREDICTORAS_RIESGO))
    st.caption("**Bonos:** precios diarios de los últimos 5 años; métricas del ranking en los últimos 3 años.")


def mostrarBienvenida(parametros):
    st.info("Elige tu **perfil** arriba y presiona **Comenzar**. Se descargan los fondos de bonos de los tres perfiles; "
            "luego eliges cuál analizar (por defecto, el mejor de tu perfil). La aplicación no se actualiza sola: "
            "los datos se renuevan cuando tú lo pides.")
    columnas = st.columns(4)
    for columna, (titulo, texto) in zip(columnas, [
        ("Descriptivo", "Qué pasó con el fondo elegido: NAV, rentabilidad, benchmark, riesgo, prensa y el ranking de su perfil."),
        ("Predictivo", "Qué podría pasar: pronóstico comparado con líneas base y riesgo de los próximos 3 meses."),
        ("Prescriptivo", "Qué hacer: fondo completo o bonos específicos de su cartera, y la proyección de tu ganancia."),
        ("Asesor IA", "Resuelve dudas puntuales conversando con Qwen3 o Gemini."),
    ], strict=True):
        columna.markdown(f'<div class="panel"><div class="panelTitulo">{titulo}</div>{texto}</div>', unsafe_allow_html=True)
    st.write("")
    _, centro, _ = st.columns([1, 2, 1])
    if centro.button("Comenzar", key="comenzar", type="primary", use_container_width=True):
        cargarComun(parametros["usarCache"])
        st.rerun()


def principal():
    aplicarEstilos()
    mostrarCabecera("Proyecto académico · CRISP-ML(Q)")
    parametros, ejecutar, proveedorInfo, contenedores = dibujarBarraLateral()
    perfil = selectorPerfil()

    if ejecutar:
        cargarComun(parametros["usarCache"])
    if "comun" not in st.session_state:
        mostrarBienvenida(parametros)
        return

    tablaPerfil, _ = st.session_state["rankingsComunes"].get(perfil, (pd.DataFrame(), {}))
    ticker = selectorFondo(perfil, tablaPerfil)
    if not ticker:
        st.info("Escribe el ticker del fondo que quieres analizar (p. ej. VFIAX), o elige uno de los fondos de tu perfil.")
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
    st.divider()
    for aviso in datos.get("avisos", []):
        st.caption(f"ℹ️ {aviso}")
    if datos.get("fechaCorte") is not None:
        st.info(f"**Evaluación retrospectiva al {datos['fechaCorte']:%d/%m/%Y}.** Precios y noticias solo hasta ese día.")

    st.caption(f"Análisis de **{datos['ticker']}** vs **{datos['benchmark']}** "
               f"(descargado {entrada['base']['fechaDescarga']:%d/%m/%Y %H:%M}) · último dato: **{formatearFecha(datos['fechaDatoFinal'])}**.")
    with st.expander("Calidad y disponibilidad de los datos"):
        for nivel, mensaje in datos["calidad"]:
            {"ok": st.success, "alerta": st.warning}.get(nivel, st.error)(mensaje)
    with st.expander("Datos utilizados y granularidad"):
        dibujarGranularidad(datos)

    pestanas = st.tabs(["📊 Descriptivo · ¿qué pasó?", "🔮 Predictivo · ¿qué podría pasar?", "🧭 Prescriptivo · ¿qué hago?", "💬 Asesor IA"])
    with pestanas[0]:
        dibujarDashboardDescriptivo(datos, perfil)
    with pestanas[1]:
        dibujarDashboardPredictivo(datos)
    with pestanas[2]:
        decision = dibujarDashboardPrescriptivo(datos, perfil, proveedorInfo)
    with pestanas[3]:
        dibujarChatAsesor(datos, perfil, proveedorInfo, decision)


principal()
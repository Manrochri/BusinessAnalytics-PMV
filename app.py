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

import time
from collections import OrderedDict

import pandas as pd
import streamlit as st

from config import (
    BENCHMARK_POR_DEFECTO,
    NOTICIAS_LIMITE,
    DIAS_PRONOSTICO,
    PERIODO_HISTORICO,
    SEMANAS_EN_MEMORIA,
    TICKER_NOTICIAS_POR_DEFECTO,
)
from src.analisis import (
    PASOS_DESCARGA_FONDO,
    descargarComun,
    descargarFondo,
    ejecutarAnalisis,
    pasosDescargaComun,
    rankingsComunes,
    rankingsMutuosComunes,
)
from src.catalogoBonos import benchmarkParaFondo, nombreFondo
from src.datosNoticias import completarHistoriaTono, descargarNoticias, descargarTonoPrensa, sugerirTickerNoticias, temaTonoPrensa
from src.estilos import ancla, aplicarEstilos, flujoPasos, mostrarCabecera, portada, tituloSeccion
from src.motorPrescriptivo import conclusionParaDatos, determinarProveedorActivo, llamadasHoy, proveedorListo
from src.preparacionDatos import listarFechasSemanales
from src.utilidades import formatearNumero, formatearPorcentaje
from src.vistas.asesor import dibujarChatAsesor
from src.vistas.comunes import ANCHO, filaTarjetas, formatearFecha, perfilActual, selectorFondo, selectorPerfil
from src.vistas.descriptivo import dibujarDashboardDescriptivo
from src.vistas.predictivo import dibujarDashboardPredictivo
from src.vistas.portafolio import dibujarPortafolio
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
        ejecutar = st.button("🔄 Actualizar datos", type="primary", **ANCHO,
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
        reverificar = st.button("Revisar asistente de IA", **ANCHO)
        proveedorInfo = determinarProveedorActivo(forzarVerificacion=reverificar)
        _, estado, _ = proveedorInfo
        if proveedorListo(estado):
            st.success("✅ Asistente de IA activo")
        else:
            st.warning("Asistente de IA no disponible: el informe se arma con reglas y el chat queda desactivado.")
    return parametros, ejecutar, proveedorInfo, contenedores


def dibujarHistoriaTono(contenedor, ticker, tickerNoticias):
    """
    Opcion avanzada: mas meses del tono de prensa. Los ultimos 12 meses ya se
    descargan solos con «Actualizar datos»; esto sirve para que el sentimiento
    cubra tambien el periodo de entrenamiento del modelo (anios atras).
    """
    with contenedor, st.expander("Más historia de noticias (opcional)"):
        tema = temaTonoPrensa(ticker, tickerNoticias or sugerirTickerNoticias(ticker))
        st.caption("Los últimos 12 meses del ánimo de la prensa se descargan solos. Con más años, las noticias también entran "
                   "al modelo predictivo. Tarda unos 5 segundos por cada 3 meses.")
        meses = st.number_input("Meses adicionales", min_value=3, max_value=120, value=24, step=3, key="mesesTono")
        if st.button("Descargar más historia", **ANCHO):
            barra = st.progress(0.0, text="Descargando noticias…")
            r = completarHistoriaTono(tema, int(meses), lambda f, t: barra.progress(min(f, 1.0), text=t))
            textoDesde = f" desde el {r['desde']:%d/%m/%Y}" if r["desde"] is not None else ""
            if r["mensaje"] and r["diasNuevos"] <= 0:
                st.error(f"No se pudo descargar: {r['mensaje']} Ya tenías {r['total']} días{textoDesde}.")
            elif r["mensaje"]:
                st.warning(f"Llegaron {r['diasNuevos']} días nuevos ({r['total']} en total{textoDesde}) y luego se cortó: "
                           f"{r['mensaje']} Vuelve a intentarlo en un minuto para seguir. Presiona «Actualizar datos» para usarlos.")
            else:
                st.success(f"Listo: {r['diasNuevos']} días nuevos, {r['total']} en total{textoDesde}. Presiona «Actualizar datos» para usarlos.")


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
def cargarComun(usarCache, lugar=None):
    """
    Datos comunes a todos los fondos (fondos mutuos, fondos de bonos, curva,
    tasa) y sus rankings por perfil. Muestra una barra de avance con lo que se
    esta descargando (unos 45 fondos: 1-2 minutos la primera vez).
    """
    total = pasosDescargaComun()
    lugar = lugar if lugar is not None else st.container()
    with lugar:
        estado = st.status("Preparando los fondos de los tres perfiles…", expanded=True)
    with estado:
        barra = st.progress(0.0, text="Conectando con Yahoo Finance…")
        detalle = st.empty()
        detalle.caption(f"Se descargan {total} series de precios. La primera vez tarda 1-2 minutos; después quedan guardadas.")
        contador = {"n": 0}

        def avanzar(texto):
            contador["n"] += 1
            fraccion = min(contador["n"] / total, 0.99)
            barra.progress(fraccion, text=f"{contador['n']} de {total} · {texto}")
            estado.update(label=f"Preparando los fondos de los tres perfiles… {fraccion:.0%}")

        inicio = time.time()
        comun = descargarComun(usarCache, progreso=avanzar)
        barra.progress(0.995, text="Calculando los rankings de cada perfil…")
        st.session_state["comun"] = comun
        st.session_state["rankingsComunes"] = rankingsComunes(comun)
        st.session_state["rankingsMutuos"] = rankingsMutuosComunes(comun, st.session_state["rankingsComunes"])
        st.session_state["analisisPorFondo"] = OrderedDict()
        st.session_state.setdefault("tiempos", {})["cargaInicial"] = round(time.time() - inicio, 1)
        barra.progress(1.0, text="Listo")
        estado.update(label="Datos listos", state="complete", expanded=False)


def obtenerAnalisis(ticker, benchmark, parametros, forzar=False):
    """Base y analisis del fondo; se reutilizan mientras no cambien el fondo ni los parametros."""
    memoria = st.session_state.setdefault("analisisPorFondo", OrderedDict())
    clave = (ticker, benchmark, parametros["tickerNoticias"], parametros["periodo"], parametros["dias"])
    if forzar or clave not in memoria:
        nombre = nombreFondo(ticker, conTicker=False)
        pasos = len(PASOS_DESCARGA_FONDO) + 1
        estado = st.status(f"Analizando {nombre}…", expanded=True)
        with estado:
            barra = st.progress(0.0, text="Empezando…")

            def avanzar(i, texto):
                barra.progress(i / pasos, text=f"Paso {i + 1} de {pasos} · {texto}")
                estado.update(label=f"Analizando {nombre}… {i / pasos:.0%}")

            inicio = time.time()
            base = descargarFondo(ticker, benchmark, parametros["periodo"], parametros["tickerNoticias"],
                                  parametros["usarCache"], comun=st.session_state["comun"], progreso=avanzar)
            barra.progress((pasos - 1) / pasos, text=f"Paso {pasos} de {pasos} · Entrenando los modelos y calculando la señal")
            estado.update(label=f"Analizando {nombre}… {(pasos - 1) / pasos:.0%}")
            memoria[clave] = {"base": base, "resultado": ejecutarAnalisis(base, parametros["dias"]),
                              "evaluaciones": OrderedDict()}
            st.session_state.setdefault("tiempos", {})[ticker] = round(time.time() - inicio, 1)
            barra.progress(1.0, text="Listo")
            estado.update(label=f"Análisis de {nombre} listo", state="complete", expanded=False)
        while len(memoria) > FONDOS_EN_MEMORIA:
            memoria.popitem(last=False)
    memoria.move_to_end(clave)
    return memoria[clave]


def refrescarNoticias(entrada):
    """Vuelve a descargar solo titulares y tono de prensa del fondo y recalcula el analisis (sin bajar precios)."""
    base = entrada["base"]
    with st.spinner("Buscando titulares y tono de prensa de nuevo…"):
        base["noticias"] = descargarNoticias(base["tickerNoticias"], NOTICIAS_LIMITE, usarCache=False,
                                            tickersExtra=(base["ticker"],) if base["ticker"] != base["tickerNoticias"] else (),
                                            tema=base.get("temaTono"))
        base["tono"] = descargarTonoPrensa(base["temaTono"], usarCache=False)
        entrada["resultado"] = ejecutarAnalisis(base, entrada["resultado"]["diasPronostico"])
        entrada["evaluaciones"].clear()


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
    """Portada: que hace la app, los pasos y un unico boton."""
    st.markdown(portada(
        "¿Conviene invertir en este fondo mutuo, <em>para alguien como tú</em>?",
        "Dinos qué tipo de inversor eres y qué fondo te interesa. FundScope revisa cómo le fue, qué podría pasar y te dice "
        "si conviene invertir, cuánto podrías ganar y qué fondos combinar en tu portafolio.",
        [("Tu perfil", "Conservador, moderado o agresivo: define cuánto riesgo cabe."),
         ("El fondo", "Fondos mutuos de acciones, mixtos y de bonos, con veredicto, costos y mínimos."),
         ("La decisión", "Invertir o no, cuánto podrías ganar y tu portafolio con varios fondos.")],
    ), unsafe_allow_html=True)
    columnas = st.columns([2, 3])
    lugar = st.container()  # aqui aparece la barra de avance al pulsar «Comenzar», justo debajo del boton
    if columnas[0].button("Comenzar", key="comenzar", type="primary", **ANCHO,
                          help="Descarga los fondos de los tres perfiles. Tarda 1-2 minutos la primera vez."):
        cargarComun(parametros["usarCache"], lugar)
        st.rerun()
    st.caption("La primera vez descarga los fondos de los tres perfiles (1-2 minutos). Los datos se renuevan solo cuando lo pides.")


def principal():
    aplicarEstilos()
    mostrarCabecera("Proyecto académico · CRISP-ML(Q)")
    parametros, ejecutar, proveedorInfo, contenedores = dibujarBarraLateral()

    if ejecutar:
        cargarComun(parametros["usarCache"])
    if "comun" not in st.session_state:
        mostrarBienvenida(parametros)
        return

    # ---- Pasos 1 y 2: perfil y fondo ------------------------------------------
    # Mientras no haya un resultado, los dos pasos van abiertos; despues se pliegan
    # y muestran la eleccion en su titulo, para que el resultado quede a la vista.
    # key="riel": Streamlit le pone la clase CSS st-key-riel al contenedor, y asi se fija arriba (estilos.py)
    flujo = st.container(key="riel")
    riel = flujo.empty()  # se dibuja YA (provisional) y se vuelve a dibujar al final con la conclusion
    listo = st.session_state.get("flujoListo", False)
    perfil = perfilActual()
    riel.markdown(flujoPasos([{"titulo": "Perfil", "valor": perfil, "estado": "listo"},
                              {"titulo": "Fondo", "valor": "Eligiendo…", "estado": "activo"},
                              {"titulo": "Resultado", "valor": "—", "estado": ""},
                              {"titulo": "Portafolio", "valor": "—", "estado": ""}]), unsafe_allow_html=True)
    ancla("paso-1")
    with st.expander(f"1 · Tu perfil: {perfil}" + ("  ·  cambiar" if listo else ""), expanded=not listo):
        st.caption("Define cuánto riesgo cabe en tu cartera y qué fondos se te proponen.")
        perfil = selectorPerfil()

    tablaPerfil, _ = st.session_state["rankingsComunes"].get(perfil, (pd.DataFrame(), {}))
    tablaMutuos, _ = st.session_state.get("rankingsMutuos", {}).get(perfil, (pd.DataFrame(), {}))
    elegido = st.session_state.get(f"fondoAnalizado_{perfil}")
    tituloFondo = (f"2 · Fondo: {nombreFondo(elegido, conTicker=False)}  ·  cambiar" if listo and elegido and elegido != "__otro__"
                   else "2 · ¿Qué fondo mutuo quieres analizar?")
    ancla("paso-2")
    with st.expander(tituloFondo, expanded=not listo):
        st.caption(f"Fondos mutuos de acciones, mixtos y de bonos para el perfil {perfil}, del mejor al peor.")
        ticker = selectorFondo(perfil, tablaPerfil, tablaMutuos)
    if not ticker:
        riel.markdown(flujoPasos([{"titulo": "Perfil", "valor": perfil, "estado": "listo"},
                                  {"titulo": "Fondo", "valor": "Elige uno de la lista", "estado": "activo"},
                                  {"titulo": "Resultado", "valor": "—", "estado": ""},
                                  {"titulo": "Portafolio", "valor": "—", "estado": ""}]), unsafe_allow_html=True)
        st.info("Busca el fondo en la lista y presiona «Analizar».")
        return
    riel.markdown(flujoPasos([{"titulo": "Perfil", "valor": perfil, "estado": "listo"},
                              {"titulo": "Fondo", "valor": nombreFondo(ticker, conTicker=False), "estado": "listo"},
                              {"titulo": "Resultado", "valor": "Calculando…", "estado": "activo"},
                              {"titulo": "Portafolio", "valor": "—", "estado": ""}]), unsafe_allow_html=True)
    benchmark = parametros["benchmarkManual"] or benchmarkParaFondo(ticker, perfil, BENCHMARK_POR_DEFECTO)
    entrada = obtenerAnalisis(ticker, benchmark, parametros, forzar=ejecutar)
    dibujarHistoriaTono(contenedores["tono"], ticker, parametros["tickerNoticias"])
    if not entrada["resultado"].get("exito"):
        st.error(entrada["resultado"].get("mensaje") or f"No se pudo completar el análisis de {ticker}. Revisa el ticker.")
        return
    if st.session_state.pop("reintentarNoticiasDe", None) == ticker:  # boton «Buscar titulares de nuevo»
        refrescarNoticias(entrada)
    fechaCorte = dibujarSelectorSemana(contenedores["semana"], entrada)

    datos = obtenerEvaluacion(entrada, fechaCorte)
    if not datos.get("exito"):
        st.error(datos.get("mensaje") or "No se pudo completar el análisis de esa semana.")
        return

    # ---- Paso 3: resultado ----------------------------------------------------
    tituloSeccion(f"3 · Resultado para {datos.get('nombreFondo') or ticker}", "Qué hacer, qué pasó, qué podría pasar y tu portafolio.", id="paso-3")
    if datos.get("fechaCorte") is not None:
        st.info(f"**Evaluación retrospectiva al {datos['fechaCorte']:%d/%m/%Y}.** Precios y noticias solo hasta ese día.")

    ancla("paso-4")  # el portafolio vive en su pestaña: el riel lleva hasta las pestañas
    pestanas = st.tabs(["¿Qué hago?", "¿Qué pasó?", "¿Qué podría pasar?", "Mi portafolio", "Asesor IA"])
    with pestanas[0]:
        decision = dibujarDashboardPrescriptivo(datos, perfil, proveedorInfo)
    with pestanas[1]:
        dibujarDashboardDescriptivo(datos, perfil)
    with pestanas[2]:
        dibujarDashboardPredictivo(datos)
    with pestanas[3]:
        portafolio = dibujarPortafolio(datos, perfil)
    with pestanas[4]:
        dibujarChatAsesor(datos, perfil, proveedorInfo, decision)
    conclusion = (decision or {}).get("conclusion") or conclusionParaDatos(datos, perfil)
    st.session_state["flujoListo"] = True  # desde aqui, los pasos 1 y 2 se pliegan
    textoPortafolio = (f"{len(portafolio['pesos'])} fondos · {portafolio['veredicto'].lower()}" if portafolio else "Ármalo en su pestaña")
    # El riel de arriba muestra la conclusion final (sobre el fondo o sobre tus bonos) y el portafolio
    riel.markdown(flujoPasos([{"titulo": "Perfil", "valor": perfil, "estado": "listo"},
                              {"titulo": "Fondo", "valor": datos.get("nombreCorto") or ticker, "estado": "listo"},
                              {"titulo": "Resultado", "valor": conclusion["decision"], "estado": "activo"},
                              {"titulo": "Portafolio", "valor": textoPortafolio, "estado": "listo" if portafolio else ""}]),
                  unsafe_allow_html=True)

    # Datos y calidad: al final, plegado (es informacion de respaldo, no de decision)
    st.write("")
    with st.expander(f"Datos usados · actualizados al {formatearFecha(datos['fechaDatoFinal'])}"):
        st.caption(f"Precios de Yahoo Finance descargados el {entrada['base']['fechaDescarga']:%d/%m/%Y a las %H:%M}. "
                   "Proyecto académico: no es asesoría financiera.")
        dibujarGranularidad(datos)
        tiempos = st.session_state.get("tiempos", {})
        st.caption(f"Tiempos medidos: carga inicial {tiempos.get('cargaInicial', 'N/D')} s · descarga y análisis de {ticker} "
                   f"{tiempos.get(ticker, 'N/D')} s (de ellos, modelos y señal {datos.get('duracionAnalisisSeg', 0)} s) · "
                   f"consultas a la IA hoy: {llamadasHoy()}.")
        for tono, texto in datos.get("calidad", []):
            if "descartados" in texto or "faltantes" in texto or "huecos" in texto:
                st.caption(("⚠ " if tono == "alerta" else "✓ ") + texto)


principal()
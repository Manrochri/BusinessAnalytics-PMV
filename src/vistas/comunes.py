"""
comunes.py
Piezas de interfaz compartidas por las vistas: selector de perfil,
tarjetas en fila, formatos de fecha y avisos.
"""

import pandas as pd
import streamlit as st

from config import FONDO_POR_DEFECTO, PERFIL_POR_DEFECTO
from src.catalogoBonos import PARAMETROS_PERFIL, PERFILES
from src.estilos import tarjetaMetrica

CLAVE_PERFIL = "perfil"
CLAVE_SELECTOR_PERFIL = "selectorPerfil"
CLAVE_TICKER_OTRO = "tickerOtro"
OTRO_FONDO = "__otro__"
ICONO_VEREDICTO = {"Recomendable": "🟢", "Aceptable": "🟡", "No recomendable": "🔴", "Sin datos": "⚪"}


def formatearFecha(fecha, conHora=False):
    """Fecha legible, o 'N/D' si no hay valor."""
    try:
        if fecha is None or pd.isna(fecha):
            return "N/D"
        return f"{fecha:%d/%m/%Y %H:%M}" if conHora else f"{fecha:%d/%m/%Y}"
    except (TypeError, ValueError):
        return "N/D"


def filaTarjetas(tarjetas):
    """Dibuja una fila de tarjetas. tarjetas = lista de dicts con los argumentos de tarjetaMetrica."""
    columnas = st.columns(len(tarjetas))
    for columna, tarjeta in zip(columnas, tarjetas, strict=True):
        columna.markdown(tarjetaMetrica(**tarjeta), unsafe_allow_html=True)


def perfilActual():
    """Perfil del inversor elegido en la parte superior (persistente en la sesion)."""
    if CLAVE_PERFIL not in st.session_state:
        st.session_state[CLAVE_PERFIL] = PERFIL_POR_DEFECTO if PERFIL_POR_DEFECTO in PERFILES else "Moderado"
    return st.session_state[CLAVE_PERFIL]


def selectorPerfil():
    """
    Selector del perfil en la PARTE SUPERIOR de la app. Usa un control
    segmentado (Streamlit >= 1.40) o, en versiones anteriores, un radio
    horizontal. Cambiar el perfil recalcula al instante el ranking de fondos de bonos, la
    evaluacion de cada bono,
    la asignacion y la proyeccion, sin volver a descargar datos.
    """
    actual = perfilActual()
    if CLAVE_SELECTOR_PERFIL not in st.session_state:
        st.session_state[CLAVE_SELECTOR_PERFIL] = actual

    columnaSelector, columnaTexto = st.columns([2, 3])
    with columnaSelector:
        if hasattr(st, "segmented_control"):
            valor = st.segmented_control(
                "Perfil del inversor", list(PERFILES), key=CLAVE_SELECTOR_PERFIL, selection_mode="single"
            )
        else:  # Streamlit < 1.40
            valor = st.radio("Perfil del inversor", list(PERFILES), key=CLAVE_SELECTOR_PERFIL, horizontal=True)
    if valor in PERFILES:
        st.session_state[CLAVE_PERFIL] = valor
    perfil = st.session_state[CLAVE_PERFIL]
    parametros = PARAMETROS_PERFIL[perfil]
    with columnaTexto:
        st.caption(
            f"**{perfil}** · {parametros['descripcion']} Bonos: {parametros['tipoBonos'].lower()} · "
            f"base {parametros['rentaVariable']:.0%} renta variable / {parametros['rentaFija']:.0%} renta fija / "
            f"{parametros['liquidez']:.0%} liquidez."
        )
    return perfil


def fondoInicial(tablaRanking):
    """Fondo con el que arranca un perfil: el del .env si es de ese grupo; si no, el primero del ranking."""
    tickers = list(tablaRanking["ticker"]) if tablaRanking is not None and not tablaRanking.empty else []
    if FONDO_POR_DEFECTO and FONDO_POR_DEFECTO.upper() in tickers:
        return FONDO_POR_DEFECTO.upper()
    return tickers[0] if tickers else OTRO_FONDO


def selectorFondo(perfil, tablaRanking):
    """
    Selector del FONDO A ANALIZAR, junto al perfil. Lista los fondos de bonos
    del grupo del perfil en el orden del ranking (el mejor primero, elegido
    por defecto) y la opcion «Otro ticker» para analizar cualquier fondo
    (p. ej. uno de acciones como VFIAX). Cada perfil recuerda su eleccion.
    Devuelve el ticker elegido (o None si «Otro» aun esta vacio).
    """
    tickers = list(tablaRanking["ticker"]) if tablaRanking is not None and not tablaRanking.empty else []
    opciones = tickers + [OTRO_FONDO]
    filas = tablaRanking.set_index("ticker") if tickers else None
    clave = f"fondoAnalizado_{perfil}"
    if clave not in st.session_state or st.session_state[clave] not in opciones:
        st.session_state[clave] = fondoInicial(tablaRanking)

    def etiqueta(ticker):
        if ticker == OTRO_FONDO:
            return "Otro ticker (fondo de acciones u otro)…"
        f = filas.loc[ticker]
        return f"#{int(f['puesto'])} {ticker} · {f['segmento']} · {ICONO_VEREDICTO.get(f['veredicto'], '')} {f['veredicto']}"

    columnaFondo, columnaDetalle = st.columns([2, 3])
    with columnaFondo:
        elegido = st.selectbox(
            "Fondo a analizar", opciones, format_func=etiqueta, key=clave,
            help=f"Fondos de bonos del perfil {perfil}, ordenados por el ranking (el mejor primero). "
                 "Todo el análisis —descriptivo, predictivo y prescriptivo— se hace sobre el fondo elegido.",
        )
    if elegido == OTRO_FONDO:
        with columnaDetalle:
            texto = st.text_input("Ticker", key=CLAVE_TICKER_OTRO, placeholder="p. ej. VFIAX, VTSAX, QQQ")
        ticker = str(texto or "").strip().upper()
        if ticker:
            st.caption(f"**{ticker}** no es parte del grupo de fondos de bonos del perfil {perfil}: se analiza como "
                       "fondo propio (renta variable si es de acciones) y la renta fija del Prescriptivo usa el mejor fondo de bonos del perfil.")
        return ticker or None
    f = filas.loc[elegido]
    with columnaDetalle:
        puntaje = "s/d" if pd.isna(f["puntaje"]) else f"{f['puntaje']:.0f}/100"
        st.caption(f"**{f['nombre']}** · {f['segmento']} · puntaje {puntaje} · "
                   f"fondo mutuo equivalente: {f['fondoMutuo']}. {f['motivo']}")
    return elegido


def mostrarRecomendacion(texto, tono):
    """Mensaje destacado segun el tono (verde / ambar / roja / azul)."""
    {"verde": st.success, "ambar": st.warning, "roja": st.error}.get(tono, st.info)(texto)


def formatearTablaPorcentajes(tabla, columnasPorcentaje, decimales=1):
    """Copia de la tabla con columnas de fraccion convertidas a texto de porcentaje."""
    salida = tabla.copy()
    for columna in columnasPorcentaje:
        if columna in salida:
            salida[columna] = salida[columna].map(
                lambda v: "N/D" if v is None or pd.isna(v) else f"{v * 100:.{decimales}f}%"
            )
    return salida

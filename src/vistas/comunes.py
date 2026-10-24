"""
comunes.py
Piezas de interfaz compartidas por las vistas: selector de perfil,
tarjetas en fila, formatos de fecha y avisos.
"""

import inspect
import re
from html import escape

import pandas as pd
import streamlit as st

from config import FONDO_POR_DEFECTO, PERFIL_POR_DEFECTO
from src.catalogoBonos import PARAMETROS_PERFIL, PERFILES
from src.catalogoBonos import nombreFondo
from src.estilos import tarjetaMetrica, tarjetaOpcion
from src.listadoFondos import etiquetaFondo, listarFondos

CLAVE_PERFIL = "perfil"
CLAVE_SELECTOR_PERFIL = "selectorPerfil"
CLAVE_FONDO_LISTA = "fondoDeLista"
OTRO_FONDO = "__otro__"
ICONO_VEREDICTO = {"Recomendable": "🟢", "Aceptable": "🟡", "No recomendable": "🔴", "Sin datos": "⚪"}


def _anchoCompleto():
    """Streamlit >= 1.49 reemplazo **ANCHO por width="stretch" (lo otro avisa que se retira)."""
    try:
        return {"width": "stretch"} if "width" in inspect.signature(st.button).parameters else {"use_container_width": True}
    except (TypeError, ValueError):
        return {"use_container_width": True}


ANCHO = _anchoCompleto()


def sinAtributos(df):
    """Copia ligera sin df.attrs (origen, fechaCache…): Streamlit no los puede serializar si traen fechas."""
    copia = df.copy(deep=False)
    copia.attrs = {}
    return copia


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


def _elegir(clave, valor):
    st.session_state[clave] = valor


def opcionesGrandes(opciones, clave, valorActual, prefijoBoton, textoBoton="Elegir", compactas=False):
    """
    Fila de tarjetas de opcion grandes con su boton debajo. opciones = lista de
    dicts {valor, titulo, subtitulo, chip, tonoChip}. Al pulsar un boton se
    guarda 'valor' en st.session_state[clave]. Devuelve el valor actual.
    """
    columnas = st.columns(len(opciones))
    for columna, opcion in zip(columnas, opciones, strict=True):
        elegida = opcion["valor"] == valorActual
        with columna:
            st.markdown(tarjetaOpcion(opcion["titulo"], opcion.get("subtitulo", ""), opcion.get("chip"),
                                      opcion.get("tonoChip", "gris"), elegida, compactas, opcion.get("dato")),
                        unsafe_allow_html=True)
            st.button("✓ Elegido" if elegida else textoBoton, key=f"{prefijoBoton}_{opcion['valor']}",
                      type="primary" if elegida else "secondary", **ANCHO,
                      on_click=_elegir, args=(clave, opcion["valor"]))
    return st.session_state.get(clave, valorActual)


def selectorPerfil():
    """
    Paso 1 del flujo: el perfil, como tres tarjetas grandes. Cambiarlo
    recalcula al instante el ranking, la evaluacion de bonos, la asignacion y
    la proyeccion, sin volver a descargar datos.
    """
    actual = perfilActual()
    opciones = []
    for perfil in PERFILES:
        p = PARAMETROS_PERFIL[perfil]
        opciones.append({"valor": perfil, "titulo": perfil, "subtitulo": p["descripcion"],
                         "chip": f"{p['rentaVariable']:.0%} acciones · {p['rentaFija']:.0%} bonos · {p['liquidez']:.0%} liquidez",
                         "tonoChip": {"Conservador": "verde", "Moderado": "ambar", "Agresivo": "roja"}[perfil]})
    return opcionesGrandes(opciones, CLAVE_PERFIL, actual, "btnPerfil")


def resumenPerfil(perfil):
    """Una linea corta con lo esencial del perfil."""
    p = PARAMETROS_PERFIL[perfil]
    return (f"**{perfil}:** {p['descripcion'].rstrip('.')} · {p['rentaVariable']:.0%} acciones · "
            f"{p['rentaFija']:.0%} bonos · {p['liquidez']:.0%} liquidez")


def fondoInicial(tablaRanking):
    """Fondo con el que arranca un perfil: el del .env si es de ese grupo; si no, el primero del ranking."""
    tickers = list(tablaRanking["ticker"]) if tablaRanking is not None and not tablaRanking.empty else []
    if FONDO_POR_DEFECTO and FONDO_POR_DEFECTO.upper() in tickers:
        return FONDO_POR_DEFECTO.upper()
    return tickers[0] if tickers else OTRO_FONDO


TONO_VEREDICTO_CHIP = {"Recomendable": "verde", "Aceptable": "ambar", "No recomendable": "roja", "Sin datos": "gris"}


def avisoRendimientoAproximado(tablaRanking):
    """
    Avisa cuando el «rinde» de algun fondo no es su rendimiento sino su retorno
    de 12 meses (pasa si Yahoo no entrega la ficha ni las distribuciones, algo
    frecuente en servidores en la nube): en un mal anio sale negativo y deja a
    todos los fondos como «no recomendables».
    """
    if tablaRanking is None or tablaRanking.empty or "fuenteRendimiento" not in tablaRanking:
        return
    aproximados = tablaRanking.loc[tablaRanking["fuenteRendimiento"].astype(str).str.startswith("Retorno"), "ticker"].tolist()
    if aproximados:
        st.warning(f"**Rendimiento aproximado en {', '.join(aproximados)}:** no se obtuvo lo que pagan al año, así que se usó su "
                   "retorno de 12 meses (puede ser negativo y volverlos «no recomendables»). Prueba «Actualizar datos» o, en el "
                   "menú lateral, «Descargar todo de nuevo».")


def selectorFondo(perfil, tablaRanking):
    """
    Paso 2 del flujo: el FONDO A ANALIZAR, como tarjetas grandes (una por
    fondo del perfil, en el orden del ranking, con su veredicto y rendimiento).
    Debajo, plegado, «Analizar otro ticker». Cada perfil recuerda su eleccion.
    Devuelve el ticker elegido (o None si «Otro» aun esta vacio).
    """
    tickers = list(tablaRanking["ticker"]) if tablaRanking is not None and not tablaRanking.empty else []
    clave = f"fondoAnalizado_{perfil}"
    if clave not in st.session_state or st.session_state[clave] not in tickers + [OTRO_FONDO]:
        st.session_state[clave] = fondoInicial(tablaRanking)
    actual = st.session_state[clave]

    if tickers:
        filas = tablaRanking.set_index("ticker")
        opciones = []
        for t in tickers:
            f = filas.loc[t]
            rinde = "" if pd.isna(f["rendimientoEsperado"]) else f" · rinde {f['rendimientoEsperado']:.1%} al año"
            opciones.append({"valor": t, "titulo": f"{int(f['puesto'])}. {nombreFondo(t, conTicker=False)}", "subtitulo": f"{t}{rinde}",
                             "chip": f"{ICONO_VEREDICTO.get(f['veredicto'], '')} {f['veredicto']}",
                             "tonoChip": TONO_VEREDICTO_CHIP.get(f["veredicto"], "gris")})
        opcionesGrandes(opciones, clave, actual, f"btnFondo_{perfil}", "Analizar", compactas=True)
        avisoRendimientoAproximado(tablaRanking)

    with st.expander("Analizar otro fondo (por ejemplo, uno de acciones)", expanded=actual == OTRO_FONDO):
        listado = listadoDeFondos()
        porTicker = listado.set_index("ticker")
        columnas = st.columns([4, 1])
        elegidoLista = columnas[0].selectbox(
            "Busca un fondo por su nombre o símbolo", list(listado["ticker"]), index=None, key=CLAVE_FONDO_LISTA,
            format_func=lambda t: etiquetaFondo({"ticker": t, **porTicker.loc[t].to_dict()}),
            placeholder="Escribe para buscar: S&P 500, Vanguard, tecnología, oro…")
        columnas[1].markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
        columnas[1].button("Analizar", key=f"btnOtro_{perfil}", **ANCHO, disabled=not elegidoLista,
                           type="primary" if actual == OTRO_FONDO else "secondary", on_click=_elegir, args=(clave, OTRO_FONDO))
        st.caption(f"{len(listado):,} fondos: ETF de EE.UU. y fondos mutuos conocidos.")
    actual = st.session_state[clave]
    if actual == OTRO_FONDO:
        return elegidoLista or None
    return actual


@st.cache_data(ttl=24 * 3600, show_spinner="Cargando la lista de fondos…")
def _listadoCacheado():
    return listarFondos()[0]


def listadoDeFondos():
    """Lista de fondos para «Analizar otro fondo» (Alpha Vantage + fondos mutuos conocidos), cacheada."""
    try:
        return _listadoCacheado()
    except Exception:  # sin red ni cache: la app sigue con la lista de respaldo
        return listarFondos(usarCache=False)[0]


def mostrarRecomendacion(texto, tono):
    """Mensaje destacado segun el tono (verde / ambar / roja / azul)."""
    {"verde": st.success, "ambar": st.warning, "roja": st.error}.get(tono, st.info)(texto)


# ---------------------------------------------------------------------------
# Tablas legibles
# ---------------------------------------------------------------------------
TONO_CELDA = {"Recomendable": "verde", "Aceptable": "ambar", "No recomendable": "roja",
              "Favorable": "verde", "Neutral": "ambar", "Desfavorable": "roja"}
_NUMERICO = re.compile(r"^[▶★\s]*[-+−]?(USD\s?|\$)?[-+−]?[\d.,]+\s?(%|pp|años|meses)?$")


def _esNumerica(serie):
    """True si la columna son cifras (se alinean a la derecha para compararlas de un vistazo)."""
    if pd.api.types.is_numeric_dtype(serie):
        return True
    valores = [str(v).strip() for v in serie.dropna() if str(v).strip() not in ("", "N/D", "—")]
    return bool(valores) and all(_NUMERICO.match(v) for v in valores)


def _celda(valor):
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return '<span class="tablaVacia">—</span>'
    if isinstance(valor, float):
        valor = f"{valor:,.2f}"
    texto = str(valor)
    # Veredictos y momentos como chips de color: se leen sin leer
    sinIcono = re.sub(r"^[^\wÁÉÍÓÚáéíóúÑñ]+", "", texto).strip()
    if sinIcono in TONO_CELDA:
        return f'<span class="celdaChip chip{TONO_CELDA[sinIcono].capitalize()}F">{escape(sinIcono)}</span>'
    return escape(texto)


def tablaHtml(df, mostrarIndice=False, alto=None, destacar=None):
    """
    Tabla en HTML para tablas CORTAS (planes, rankings, resumenes): letra del
    tamaño del texto, filas alternadas, cifras alineadas a la derecha,
    veredictos en color, encabezado fijo y desplazamiento horizontal en el
    celular. A diferencia de st.dataframe (dibujado en un lienzo), esta se
    adapta al tamaño de letra de la pagina y se puede copiar.
    destacar: funcion fila -> bool para resaltar filas (p. ej. el fondo analizado).
    """
    if df is None or df.empty:
        st.caption("Sin datos para mostrar.")
        return
    tabla = df.reset_index() if mostrarIndice else df
    numericas = {c for c in tabla.columns if _esNumerica(tabla[c])}
    cabecera = "".join(f'<th class="{"num" if c in numericas else ""}">{escape(str(c))}</th>' for c in tabla.columns)
    filas = []
    for _, fila in tabla.iterrows():
        clase = ' class="destacada"' if destacar and destacar(fila) else ""
        celdas = "".join(f'<td class="{"num" if c in numericas else ""}">{_celda(fila[c])}</td>' for c in tabla.columns)
        filas.append(f"<tr{clase}>{celdas}</tr>")
    estiloAlto = f' style="max-height:{alto}"' if alto else ""
    st.markdown(f'<div class="tablaFs"{estiloAlto}><table><thead><tr>{cabecera}</tr></thead>'
                f'<tbody>{"".join(filas)}</tbody></table></div>', unsafe_allow_html=True)


def _admiteAltoFila():
    """True si st.dataframe / st.data_editor aceptan row_height (Streamlit >= 1.43)."""
    try:
        return "row_height" in inspect.signature(st.dataframe).parameters and "row_height" in inspect.signature(st.data_editor).parameters
    except (TypeError, ValueError):
        return False


def tablaDatos(df, key, **opciones):
    """
    Tabla LARGA (cientos de filas: bonos, emisores, noticias) con st.dataframe,
    que permite ordenar, buscar y ampliar. Filas mas altas cuando la version
    de Streamlit lo permite; la letra la fija theme.baseFontSize.
    """
    opciones.update(ANCHO)
    opciones.setdefault("hide_index", True)
    if _admiteAltoFila():
        opciones.setdefault("row_height", 40)
    st.dataframe(sinAtributos(df), key=key, **opciones)


def formatearTablaPorcentajes(tabla, columnasPorcentaje, decimales=1):
    """Copia de la tabla con columnas de fraccion convertidas a texto de porcentaje."""
    salida = tabla.copy()
    for columna in columnasPorcentaje:
        if columna in salida:
            salida[columna] = salida[columna].map(
                lambda v: "N/D" if v is None or pd.isna(v) else f"{v * 100:.{decimales}f}%"
            )
    return salida
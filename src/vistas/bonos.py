"""
bonos.py
Componentes compartidos para explorar y elegir bonos individuales dentro de
un fondo: carga de la cartera (N-PORT), filtros, tablas por bono y por emisor.
"""

import pandas as pd
import streamlit as st

from src.bonosIndividuales import evaluarBonos, resumirEmisores, resumirEvaluacion
from src.catalogoBonos import buscarBono
from src.datosSec import ErrorSec, carteraEnCache, descargarCartera, describirMeta
from src.utilidades import esNulo

CLAVE_CARTERAS = "carterasNport"


def carteraDisponible(fondo):
    """True si la cartera del fondo ya esta en la sesion o en la cache de disco."""
    return fondo in st.session_state.get(CLAVE_CARTERAS, {}) or carteraEnCache(fondo)


def cargarCartera(fondo):
    """Cartera N-PORT del fondo (sesion -> disco -> SEC). Devuelve (tabla, meta, error)."""
    carteras = st.session_state.setdefault(CLAVE_CARTERAS, {})
    if fondo not in carteras:
        with st.spinner(f"Descargando la cartera bono por bono de {fondo} desde la SEC (formulario N-PORT)..."):
            try:
                carteras[fondo] = descargarCartera(fondo) + (None,)
            except ErrorSec as error:
                carteras[fondo] = (pd.DataFrame(), {}, str(error))
    return carteras[fondo]


def botonCargarCartera(fondo, clave):
    """Muestra el boton para descargar la cartera si aun no esta disponible. Devuelve True si ya se puede usar."""
    if carteraDisponible(fondo):
        return True
    st.info(f"Para ver los bonos individuales de {fondo} hay que descargar su cartera desde la SEC "
            "(una vez por semana; puede tardar 10-60 s en fondos con miles de bonos).")
    if st.button(f"Cargar los bonos de {fondo}", key=clave, type="primary"):
        cargarCartera(fondo)
        return True
    return False


def bonosEvaluados(datos, fondo, perfil):
    """Bonos del fondo evaluados para el perfil (se guarda en la sesion). Devuelve (evaluados, meta, error)."""
    tabla, meta, error = cargarCartera(fondo)
    if error or tabla.empty:
        return pd.DataFrame(), meta, f"No se pudo obtener la cartera de {fondo}: {error or 'la cartera no trae bonos.'}"
    fechaPosiciones = meta.get("fechaReporte") or meta.get("finPeriodo")
    clave = f"evaluados_{fondo}_{perfil}_{fechaPosiciones}_{datos['tasaLibre']:.4f}"
    if clave not in st.session_state:
        evaluados = evaluarBonos(tabla, perfil, datos.get("curva", {}), datos["tasaLibre"], fechaPosiciones)
        if not evaluados.empty:
            evaluados["fondo"] = fondo
        st.session_state[clave] = evaluados
    evaluados = st.session_state[clave]
    if evaluados.empty:
        return evaluados, meta, motivoSinBonosVigentes(fondo, tabla, fechaPosiciones)
    return evaluados, meta, None


def motivoSinBonosVigentes(fondo, cartera, fechaPosiciones):
    """
    Explica por que un fondo no tiene bonos que evaluar. Pasa en fondos de
    plazo ultra corto (p. ej. SGOV, letras de 0-3 meses): la SEC publica la
    cartera con unos 60 dias de retraso y, para hoy, todos esos bonos ya vencieron.
    """
    fecha = pd.to_datetime(fechaPosiciones, errors="coerce")
    texto = f" del {fecha:%d/%m/%Y}" if pd.notna(fecha) else ""
    deuda = cartera.loc[cartera["esDeuda"] & cartera["vencimiento"].notna()] if {"esDeuda", "vencimiento"} <= set(cartera.columns) else pd.DataFrame()
    if not deuda.empty and deuda["vencimiento"].max() <= pd.Timestamp.today().normalize():
        return (f"Todos los bonos de la última cartera publicada de {fondo}{texto} ya vencieron "
                f"(el último venció el {deuda['vencimiento'].max():%d/%m/%Y}). Es normal en fondos de plazo ultra corto: "
                "la SEC publica la cartera con ~60 días de retraso y el fondo la renueva cada semana. "
                f"Para este fondo conviene comprar el fondo {fondo} completo (o letras del Tesoro directamente en TreasuryDirect).")
    return (f"La cartera publicada de {fondo}{texto} no tiene bonos vigentes con precio y vencimiento que se puedan evaluar "
            f"(puede contener sobre todo efectivo, repos o derivados). Usa el fondo {fondo} completo.")


def describirFondo(fondo):
    """Nombre y segmento del fondo segun el catalogo."""
    ficha = buscarBono(fondo) or {}
    return f"{fondo} · {ficha.get('segmento', '')}"


def filtrarBonos(evaluados, prefijo):
    """Filtros de la tabla de bonos. Devuelve la tabla filtrada."""
    columnas = st.columns([2, 2, 2, 3])
    mostrar = columnas[0].selectbox("Mostrar", ["Recomendables y aceptables", "Solo recomendables", "Todos"], key=f"{prefijo}_mostrar")
    tipos = sorted(evaluados["tipoEmisorTexto"].dropna().unique())
    elegidosTipo = columnas[1].multiselect("Tipo de emisor", tipos, key=f"{prefijo}_tipo", placeholder="Todos")
    plazoMaximo = float(max(1.0, evaluados["plazo"].max()))
    hasta = columnas[2].slider("Vencimiento hasta (años)", 0.0, round(plazoMaximo + 0.5, 0), round(plazoMaximo + 0.5, 0),
                               step=0.5, key=f"{prefijo}_plazo")
    texto = columnas[3].text_input("Buscar emisor o CUSIP", key=f"{prefijo}_buscar", placeholder="p. ej. Apple, Treasury, 912828")

    tabla = evaluados
    if mostrar == "Solo recomendables":
        tabla = tabla.loc[tabla["veredicto"] == "Recomendable"]
    elif mostrar == "Recomendables y aceptables":
        tabla = tabla.loc[tabla["veredicto"].isin(["Recomendable", "Aceptable"])]
    if elegidosTipo:
        tabla = tabla.loc[tabla["tipoEmisorTexto"].isin(elegidosTipo)]
    tabla = tabla.loc[tabla["plazo"] <= hasta]
    if texto:
        patron = texto.strip().upper()
        tabla = tabla.loc[tabla["emisor"].str.upper().str.contains(patron, regex=False)
                          | tabla["cusip"].str.upper().str.contains(patron, regex=False)
                          | tabla["titulo"].str.upper().str.contains(patron, regex=False)]
    return tabla


def _pct(serie, decimales=2):
    return serie.map(lambda v: "N/D" if esNulo(v) else f"{v * 100:.{decimales}f}%")


def vistaBonos(tabla, maximo=300):
    """Tabla de bonos lista para mostrar."""
    if tabla is None or tabla.empty or "puesto" not in tabla:
        return pd.DataFrame(columns=["#", "Veredicto", "Emisor", "Tipo", "Cupón", "Vence", "Precio", "TIR", "Rend. esperado",
                                     "Dif. vs Tesoro", "Calidad implícita", "Duración", "% del fondo", "Puntaje", "Motivo",
                                     "Nota", "CUSIP"])
    t = tabla.head(maximo)
    return pd.DataFrame({
        "#": t["puesto"], "Veredicto": t["veredicto"], "Emisor": t["emisor"], "Tipo": t["tipoEmisorTexto"],
        "Cupón": _pct(t["cupon"], 3), "Vence": t["vencimiento"].dt.strftime("%d/%m/%Y"),
        "Precio": t["precio"].round(2), "TIR": _pct(t["tir"]), "Rend. esperado": _pct(t["rendimientoEsperado"]),
        "Dif. vs Tesoro": _pct(t["diferencial"]), "Calidad implícita": t["calidad"], "Duración": t["duracion"].round(1),
        "% del fondo": t["pesoPct"].round(3), "Puntaje": t["puntaje"], "Motivo": t["motivo"], "Nota": t["nota"],
        "CUSIP": t["cusip"],
    })


def vistaEmisores(emisores, maximo=300):
    """Tabla de emisores lista para mostrar."""
    if emisores is None or emisores.empty or "veredicto" not in emisores:
        return pd.DataFrame(columns=["Veredicto", "Emisor", "Tipo", "País", "Bonos", "% del fondo", "Rend. esperado",
                                     "Calidad (peor)", "Plazo prom. (años)", "Recomendables", "Mejor bono"])
    t = emisores.head(maximo)
    return pd.DataFrame({
        "Veredicto": t["veredicto"], "Emisor": t["emisor"], "Tipo": t["tipo"], "País": t["pais"], "Bonos": t["bonos"],
        "% del fondo": t["pesoFondoPct"].round(2), "Rend. esperado": _pct(t["rendimientoEsperado"]),
        "Calidad (peor)": t["calidad"], "Plazo prom. (años)": t["plazoPromedio"].round(1),
        "Recomendables": t["recomendables"], "Mejor bono": t["mejorBono"],
    })


def resumenFondoBonos(evaluados, meta):
    """Una linea con las cifras del fondo evaluado bono por bono y su procedencia."""
    r = resumirEvaluacion(evaluados)
    if not r:
        return
    st.caption(
        f"**{r['bonos']:,} bonos** de **{r['emisores']:,} emisores** · {r['recomendables']:,} recomendables, "
        f"{r['aceptables']:,} aceptables, {r['noRecomendables']:,} no recomendables, {r['sinDatos']:,} sin datos · "
        f"TIR ponderada {r['tirPonderada']:.2%}. {describirMeta(meta)}. Precios y pesos a esa fecha."
    )


def tablaEmisores(evaluados, claveCache):
    """Resumen por emisor, guardado en la sesion (puede haber miles de emisores)."""
    clave = f"emisores_{claveCache}"
    if clave not in st.session_state:
        st.session_state[clave] = resumirEmisores(evaluados)
    return st.session_state[clave]
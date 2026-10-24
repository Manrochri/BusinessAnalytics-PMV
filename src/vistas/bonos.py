"""
bonos.py
Componentes compartidos para explorar y elegir bonos individuales dentro de
un fondo: carga de la cartera (N-PORT), filtros, tablas por bono y por emisor.
"""

import pandas as pd
import streamlit as st

from src.bonosIndividuales import evaluarBonos, resumirEmisores, resumirEvaluacion
from src.catalogoBonos import buscarBono, nombreFondo
from src.datosSec import ErrorSec, carteraEnCache, descargarCartera
from src.utilidades import esNulo, nombreLegible, registrarEvento

CLAVE_CARTERAS = "carterasNport"


def carteraDisponible(fondo):
    """True si la cartera del fondo ya esta en la sesion o en la cache de disco."""
    return fondo in st.session_state.get(CLAVE_CARTERAS, {}) or carteraEnCache(fondo)


def cargarCartera(fondo):
    """Cartera N-PORT del fondo (sesion -> disco -> SEC). Devuelve (tabla, meta, error)."""
    carteras = st.session_state.setdefault(CLAVE_CARTERAS, {})
    if fondo not in carteras:
        with st.spinner(f"Descargando la lista de bonos de {fondo} desde el registro oficial de EE.UU.…"):
            try:
                carteras[fondo] = descargarCartera(fondo) + (None,)
            except ErrorSec as error:
                carteras[fondo] = (pd.DataFrame(), {}, str(error))
    return carteras[fondo]


def botonCargarCartera(fondo, clave):
    """Muestra el boton para descargar la cartera si aun no esta disponible. Devuelve True si ya se puede usar."""
    if carteraDisponible(fondo):
        return True
    st.caption("Primero hay que descargar la lista de bonos del fondo (puede tardar hasta un minuto).")
    if st.button(f"Ver los bonos de {fondo}", key=clave, type="primary"):
        cargarCartera(fondo)
        return True
    return False


def bonosEvaluados(datos, fondo, perfil):
    """Bonos del fondo evaluados para el perfil (se guarda en la sesion). Devuelve (evaluados, meta, error)."""
    tabla, meta, error = cargarCartera(fondo)
    if error or tabla.empty:
        if error:
            registrarEvento(f"Cartera de {fondo}: {error}", "WARN")  # el detalle tecnico va al registro, no a la pantalla
        return pd.DataFrame(), meta, f"No se pudo obtener la lista de bonos de {fondo} en este momento. Intenta más tarde."
    fechaPosiciones = meta.get("fechaReporte") or meta.get("finPeriodo")
    clave = f"evaluados_{fondo}_{perfil}_{fechaPosiciones}_{datos['tasaLibre']:.4f}"
    if clave not in st.session_state:
        evaluados = evaluarBonos(tabla, perfil, datos.get("curva", {}), datos["tasaLibre"], fechaPosiciones)
        if not evaluados.empty:
            evaluados["fondo"] = fondo
            evaluados["emisor"] = evaluados["emisor"].map(nombreLegible)  # 'PARAMOUNT GLOBAL' -> 'Paramount Global'
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
                f"(el último venció el {deuda['vencimiento'].max():%d/%m/%Y}). Es normal en fondos de plazo muy corto: la lista "
                "oficial se publica con unos 60 días de retraso y el fondo renueva sus bonos cada semana. "
                f"Para este fondo conviene comprar el fondo {fondo} completo.")
    return (f"La lista publicada de {fondo}{texto} no tiene bonos que se puedan evaluar uno por uno. Usa el fondo {fondo} completo.")


def describirFondo(fondo):
    """Nombre y segmento del fondo segun el catalogo."""
    ficha = buscarBono(fondo) or {}
    return f"{fondo} · {ficha.get('segmento', '')}"


def filtrarBonos(evaluados, prefijo):
    """Filtros de la tabla de bonos. Devuelve la tabla filtrada."""
    columnas = st.columns([2, 2, 2, 3])
    mostrar = columnas[0].selectbox("Mostrar", ["Recomendables y aceptables", "Solo recomendables", "Todos"], key=f"{prefijo}_mostrar")
    tipos = sorted(evaluados["tipoEmisorTexto"].dropna().unique())
    elegidosTipo = columnas[1].multiselect("Tipo", tipos, key=f"{prefijo}_tipo", placeholder="Todos")
    plazoMaximo = float(max(1.0, evaluados["plazo"].max()))
    hasta = columnas[2].slider("Vence en hasta (años)", 0.0, round(plazoMaximo + 0.5, 0), round(plazoMaximo + 0.5, 0),
                               step=0.5, key=f"{prefijo}_plazo")
    texto = columnas[3].text_input("Buscar empresa", key=f"{prefijo}_buscar", placeholder="p. ej. Apple, Treasury")

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


COLUMNAS_BONOS = ["Emisor", "Veredicto al vencer", "Rinde", "Vence", "Calidad", "Tipo", "Precio", "Por qué", "Código (CUSIP)"]


def vistaBonos(tabla, maximo=300):
    """Tabla de bonos en lenguaje sencillo (lo tecnico queda en la evaluacion, no en la pantalla)."""
    if tabla is None or tabla.empty or "puesto" not in tabla:
        return pd.DataFrame(columns=COLUMNAS_BONOS)
    t = tabla.head(maximo)
    return pd.DataFrame({
        "Emisor": t["emisor"], "Veredicto al vencer": t["veredicto"], "Rinde": _pct(t["rendimientoEsperado"]),
        "Vence": t["vencimiento"].dt.strftime("%m/%Y"), "Calidad": t["calidad"], "Tipo": t["tipoEmisorTexto"],
        "Precio": t["precio"].round(2), "Por qué": t["motivo"], "Código (CUSIP)": t["cusip"],
    })


def vistaEmisores(emisores, maximo=300):
    """Tabla de empresas o entidades emisoras en lenguaje sencillo."""
    columnas = ["Empresa o entidad", "Veredicto al vencer", "Bonos", "Rinde", "Calidad", "País", "Mejor bono"]
    if emisores is None or emisores.empty or "veredicto" not in emisores:
        return pd.DataFrame(columns=columnas)
    t = emisores.head(maximo)
    return pd.DataFrame({
        "Empresa o entidad": t["emisor"], "Veredicto al vencer": t["veredicto"], "Bonos": t["bonos"],
        "Rinde": _pct(t["rendimientoEsperado"]), "Calidad": t["calidad"], "País": t["pais"], "Mejor bono": t["mejorBono"],
    })


def veredictoFondoEnRanking(datos, fondo, perfil):
    """(veredicto, motivo) del fondo en el ranking del perfil, o (None, '') si no esta."""
    tabla, _ = (datos.get("rankingsPorPerfil") or {}).get(perfil, (pd.DataFrame(), {}))
    if tabla is None or tabla.empty or fondo not in set(tabla["ticker"]):
        return None, ""
    fila = tabla.set_index("ticker").loc[fondo]
    return fila.get("veredicto"), str(fila.get("motivo") or "")


def explicarBonosVsFondo(datos, fondo, perfil, evaluados):
    """
    Aclara, ANTES de la tabla, por que un fondo «No recomendable» (o «Aceptable»)
    puede tener adentro bonos «Recomendables»: son dos preguntas distintas.
    """
    veredicto, motivo = veredictoFondoEnRanking(datos, fondo, perfil)
    r = resumirEvaluacion(evaluados) or {}
    if veredicto in (None, "Recomendable") or not r.get("recomendables"):
        return
    nombre = nombreFondo(fondo)
    porque = f" ({motivo[0].lower() + motivo[1:].rstrip('.')})" if motivo else ""
    st.info(
        f"**¿Por qué el fondo {nombre} es {veredicto.lower()} y, aun así, hay bonos recomendables adentro?** "
        f"No se contradicen: son dos preguntas distintas.\n\n"
        f"- **El fondo** se juzga por cómo se mueve su *precio*{porque}. Un fondo nunca vence: si las tasas suben "
        "o la tendencia es bajista, su precio cae y tú pierdes al vender.\n"
        "- **Cada bono** de esta lista se juzga por sí mismo, **como si lo guardaras hasta que venza**: lo que paga al "
        "vencer, su calidad y su plazo. Si lo mantienes hasta el final, cobras lo pactado aunque su precio suba o baje en el camino.\n\n"
        f"Por eso la columna se llama «Veredicto al vencer». Si NO piensas guardar los bonos hasta su vencimiento, "
        f"guíate por el veredicto del fondo ({veredicto.lower()})."
    )


def resumenFondoBonos(evaluados, meta):
    """Una linea con las cifras del fondo evaluado bono por bono y su procedencia."""
    r = resumirEvaluacion(evaluados)
    if not r:
        return
    fecha = pd.to_datetime(meta.get("fechaReporte") or meta.get("finPeriodo"), errors="coerce") if meta else pd.NaT
    st.caption(
        f"**{r['bonos']:,} bonos** de **{r['emisores']:,} empresas o entidades** · {r['recomendables']:,} recomendables para tu perfil"
        + (f" · lista del {fecha:%d/%m/%Y}" if pd.notna(fecha) else "") + "."
    )


def tablaEmisores(evaluados, claveCache):
    """Resumen por emisor, guardado en la sesion (puede haber miles de emisores)."""
    clave = f"emisores_{claveCache}"
    if clave not in st.session_state:
        st.session_state[clave] = resumirEmisores(evaluados)
    return st.session_state[clave]
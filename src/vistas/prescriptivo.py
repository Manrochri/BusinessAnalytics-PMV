"""
prescriptivo.py
Dashboard 3 — ¿Qué hago con el fondo que elegí?

Diseño (de arriba hacia abajo, una decisión por paso):
  Resumen de tu decisión  <- se llena AL FINAL con lo que elijas abajo, así
                             cualquier cambio (modo, bonos, monto, plazo) se
                             refleja de inmediato arriba.
  Paso 1  Tu fondo y cómo invertir: fondo completo, bonos específicos o liquidez
  Paso 2  Marca «Comprar» en los bonos de la cartera del fondo (N-PORT)
  Paso 3  Monto y proyección: tu elección vs las alternativas
  Paso 4  Asignación de la cartera y plan de acción con CUSIP y lotes
  Detalles: por qué la señal, backtest, perfiles, validación, informe IA

El fondo analizado (elegido arriba, junto al perfil) es el vehículo de la
renta fija cuando pertenece al grupo de fondos del perfil; si es otro fondo
(p. ej. uno de acciones), la renta fija usa el mejor fondo del perfil.
"""

from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st

from config import RETORNO_ESPERADO_ACCIONES, VOLATILIDAD_ACCIONES_RESPALDO
from src.analisisBonos import proyectarCartera, proyectarInversion, rendimientoAnualizado
from src.bonosIndividuales import (
    cambiosHistoricosTasas,
    evaluarSeleccion,
    planDeCompra,
    proyectarBonos,
)
from src.estilos import COLOR_PERFIL, COLORES, abrirPanel, barraAsignacion, encabezadoPaso, insignia, recuadroEleccion
from src.graficos import graficarAlternativas, graficarBacktest, graficarMapaBonos
from src.motorPrescriptivo import (
    REGLAS_SENAL,
    calcularHorizonteOptimo,
    compararPerfiles,
    construirAsignacion,
    construirContexto,
    construirPlanAccion,
    evaluarAlertaPerfil,
    explicacionDeRespaldo,
    generarExplicacionLLM,
    nombreProveedor,
    proveedorListo,
)
from src.utilidades import esNulo, formatearMoneda, formatearPorcentaje
from src.vistas.bonos import (
    bonosEvaluados,
    botonCargarCartera,
    filtrarBonos,
    resumenFondoBonos,
    tablaEmisores,
    vistaBonos,
    vistaEmisores,
)
from src.vistas.comunes import (
    ICONO_VEREDICTO,
    filaTarjetas,
    formatearFecha,
    formatearTablaPorcentajes,
    mostrarRecomendacion,
)

COLOR_CLASE = {"Renta variable": COLORES["azul"], "Renta fija": COLORES["verde"], "Liquidez": COLORES["grisMedio"]}
MODO_FONDO, MODO_BONOS, MODO_LIQUIDEZ = "fondo", "bonos", "liquidez"
MAXIMO_FILAS_EDITOR = 300


# ---------------------------------------------------------------------------
# Paso 1: fondo y modo de inversion
# ---------------------------------------------------------------------------
def fondoDeRentaFija(datos, tablaFondos):
    """
    Fondo de bonos que se usa en la renta fija: el fondo analizado si es del
    grupo del perfil; si no, el mejor recomendable/aceptable del ranking.
    Devuelve (ticker o None, esElAnalizado).
    """
    if tablaFondos is None or tablaFondos.empty:
        return None, False
    if datos["ticker"] in set(tablaFondos["ticker"]):
        return datos["ticker"], True
    elegibles = tablaFondos.loc[tablaFondos["veredicto"].isin(["Recomendable", "Aceptable"])]
    return (elegibles.iloc[0]["ticker"] if not elegibles.empty else None), False


def mejorAlternativa(tablaFondos, fondo):
    """Mejor fondo recomendable/aceptable del perfil distinto de 'fondo' (fila o None)."""
    elegibles = tablaFondos.loc[tablaFondos["veredicto"].isin(["Recomendable", "Aceptable"]) & (tablaFondos["ticker"] != fondo)]
    return None if elegibles.empty else elegibles.iloc[0]


def pasoElegirModo(datos, perfil, tablaFondos, resumenFondos):
    """Fondo de la renta fija y como invertir en el. Devuelve (fondo o None, modo)."""
    encabezadoPaso(1, "Tu fondo y cómo invertir", "Decide si compras el fondo completo o eliges sus bonos uno por uno.")
    if tablaFondos is None or tablaFondos.empty:
        st.info("No hay datos de fondos de bonos. Presiona «Actualizar datos».")
        return None, MODO_LIQUIDEZ
    fondo, esAnalizado = fondoDeRentaFija(datos, tablaFondos)
    senal = datos["senal"]
    if not esAnalizado:
        texto = (f"**{datos['ticker']}** no es parte del grupo de fondos de bonos del perfil {perfil}"
                 + (" y es un fondo de renta variable: queda como la parte de acciones de tu cartera." if datos.get("claseFondo") == "Renta variable" else ".")
                 + (f" Para tu renta fija se usa **{fondo}**, el mejor fondo de bonos de tu perfil." if fondo
                    else " Ningún fondo de bonos de tu perfil califica hoy."))
        st.info(texto)
    if fondo is None:
        mostrarRecomendacion(resumenFondos.get("recomendacion", ""), resumenFondos.get("tono"))
        return None, MODO_LIQUIDEZ

    f = tablaFondos.set_index("ticker").loc[fondo]
    rendimiento = "s/d" if esNulo(f["rendimientoEsperado"]) else f"{f['rendimientoEsperado']:.2%}"
    columnas = st.columns([3, 2])
    with columnas[0]:
        filaTarjetas([
            {"etiqueta": f"Fondo de tu renta fija · #{int(f['puesto'])} de {len(tablaFondos)}", "valor": fondo,
             "nota": f"{f['segmento']} · {ICONO_VEREDICTO.get(f['veredicto'], '')} {f['veredicto']}"},
            {"etiqueta": "Rendimiento esperado", "valor": rendimiento,
             "nota": f"Liquidez {formatearPorcentaje(datos['tasaLibre'], 2)}"},
            {"etiqueta": f"Señal de {datos['ticker']}", "valor": senal["accion"], "destacada": senal["accion"] == "COMPRAR",
             "nota": f"Puntaje {senal['puntaje']:+.1f}"},
        ])
    with columnas[1]:
        st.caption(f"**{f['nombre']}** · fondo mutuo equivalente: {f['fondoMutuo']}. {f['motivo']}")
        if f["veredicto"] in ("No recomendable", "Sin datos"):
            alternativa = mejorAlternativa(tablaFondos, fondo)
            st.error(f"{fondo} es **{f['veredicto'].lower()}** para el perfil {perfil}."
                     + (f" El mejor de tu perfil hoy es **{alternativa['ticker']}** ({alternativa['veredicto'].lower()})." if alternativa is not None else ""))
            if alternativa is not None and esAnalizado:
                def cambiarFondo(nuevo=alternativa["ticker"]):
                    st.session_state[f"fondoAnalizado_{perfil}"] = nuevo
                st.button(f"Analizar {alternativa['ticker']} en su lugar", key=f"cambiarA_{perfil}_{alternativa['ticker']}",
                          on_click=cambiarFondo)

    opciones = [MODO_FONDO, MODO_BONOS, MODO_LIQUIDEZ]
    textos = {MODO_FONDO: f"Comprar el fondo {fondo} completo",
              MODO_BONOS: f"Elegir bonos específicos de la cartera de {fondo}",
              MODO_LIQUIDEZ: "No invertir en bonos por ahora (liquidez)"}
    modo = st.radio("¿Cómo quieres invertir tu renta fija?", opciones, format_func=textos.get, key=f"modoRf_{perfil}_{fondo}",
                    horizontal=True,
                    help="Fondo completo: una sola compra, miles de bonos y reinversión automática. Bonos específicos: tú eliges "
                         "emisor, plazo y calidad, y sabes cuánto recibes si los mantienes al vencimiento (lotes de USD 1 000).")
    return fondo, modo


# ---------------------------------------------------------------------------
# Paso 2: bonos especificos (casilla «Comprar» en la misma tabla)
# ---------------------------------------------------------------------------
def sugerirBonos(evaluados, cantidad=3):
    """Los mejores bonos recomendables (o aceptables) de emisores distintos."""
    candidatos = evaluados.loc[evaluados["veredicto"] == "Recomendable"]
    if candidatos.empty:
        candidatos = evaluados.loc[evaluados["veredicto"] == "Aceptable"]
    return list(candidatos.drop_duplicates("emisor").head(cantidad)["clave"])


def _aplicarEdicion(claveSeleccion, claveEditor, claves):
    """Callback del editor: pasa las casillas «Comprar» marcadas/desmarcadas a la selección."""
    cambios = (st.session_state.get(claveEditor) or {}).get("edited_rows", {})
    actual = list(st.session_state.get(claveSeleccion, []))
    for fila, valores in cambios.items():
        if "Comprar" not in valores or int(fila) >= len(claves):
            continue
        clave = claves[int(fila)]
        if valores["Comprar"] and clave not in actual:
            actual.append(clave)
        elif not valores["Comprar"] and clave in actual:
            actual.remove(clave)
    st.session_state[claveSeleccion] = actual
    _nuevaVersion(claveSeleccion)


def _nuevaVersion(claveSeleccion):
    """Cambia la clave de los editores para que se redibujen desde la selección actual."""
    st.session_state[f"version_{claveSeleccion}"] = st.session_state.get(f"version_{claveSeleccion}", 0) + 1


def tablaConCasillas(tabla, claveSeleccion, claveEditor, altura=None):
    """Tabla de bonos con la columna «Comprar» editable (el resto, solo lectura)."""
    vista = vistaBonos(tabla)
    claves = list(tabla["clave"].head(len(vista)))
    vista.insert(0, "Comprar", [c in st.session_state[claveSeleccion] for c in claves])
    argumentos = {"height": altura} if altura else {}
    st.data_editor(
        vista, key=claveEditor, hide_index=True, use_container_width=True,
        disabled=[c for c in vista.columns if c != "Comprar"],
        column_config={"Comprar": st.column_config.CheckboxColumn("Comprar", help="Marca para agregar el bono a tu compra", width="small")},
        on_change=_aplicarEdicion, args=(claveSeleccion, claveEditor, claves), **argumentos,
    )


def pasoElegirBonos(datos, fondo, perfil, modo):
    """Selección de bonos con casillas. Devuelve (seleccion, evaluados)."""
    encabezadoPaso(2, "Marca los bonos que quieres comprar",
                   "Cada bono del fondo evaluado para tu perfil. Marca la casilla «Comprar» y la proyección del paso 3 se actualiza al instante.")
    vacio = pd.DataFrame()
    if modo != MODO_BONOS or fondo is None:
        st.caption({MODO_FONDO: f"Elegiste comprar el fondo {fondo} completo: pasa al paso 3. Para elegir bonos uno por uno, "
                                "marca «Elegir bonos específicos» en el paso 1.",
                    MODO_LIQUIDEZ: "Elegiste mantener la renta fija en liquidez: no hay bonos que elegir."}.get(modo, ""))
        return vacio, vacio
    if not botonCargarCartera(fondo, f"cargarCartera_presc_{fondo}"):
        st.caption(f"Mientras tanto, la proyección usa el fondo {fondo} completo.")
        return vacio, vacio
    evaluados, meta, error = bonosEvaluados(datos, fondo, perfil)
    if error:
        st.warning(f"{error} Mientras tanto, la proyección usa el fondo {fondo} completo.")
        return vacio, vacio
    resumenFondoBonos(evaluados, meta)

    claveSeleccion = f"bonos_{perfil}_{fondo}"
    if claveSeleccion not in st.session_state:
        st.session_state[claveSeleccion] = sugerirBonos(evaluados)
    st.session_state[claveSeleccion] = [c for c in st.session_state[claveSeleccion] if c in set(evaluados["clave"])]
    version = st.session_state.get(f"version_{claveSeleccion}", 0)

    def usarSugerencia():
        st.session_state[claveSeleccion] = sugerirBonos(evaluados)
        _nuevaVersion(claveSeleccion)

    def limpiar():
        st.session_state[claveSeleccion] = []
        _nuevaVersion(claveSeleccion)

    # --- Tu seleccion (arriba: siempre visible) -------------------------------
    claves = st.session_state[claveSeleccion]
    seleccion = evaluados.set_index("clave").loc[claves].reset_index() if claves else evaluados.head(0)
    columnas = st.columns([5, 1, 1])
    columnas[0].markdown(f"**Tu compra: {len(seleccion)} bono(s)**" + (" — desmarca «Comprar» para quitar uno." if len(seleccion) else ""))
    columnas[1].button("Sugerencia", key=f"sugerir_{claveSeleccion}", on_click=usarSugerencia,
                       help="Los 3 mejores bonos de emisores distintos", use_container_width=True)
    columnas[2].button("Vaciar", key=f"limpiar_{claveSeleccion}", on_click=limpiar, use_container_width=True)
    if seleccion.empty:
        st.info("Aún no marcaste bonos. Usa «Sugerencia» o marca «Comprar» en la tabla de abajo.")
    else:
        tablaConCasillas(seleccion, claveSeleccion, f"editorSeleccion_{claveSeleccion}_{version}")
        if len(seleccion) > 10:
            st.warning(f"Con {len(seleccion)} bonos el monto por bono puede no alcanzar un lote mínimo: considera 3 a 8.")

    # --- Cartera completa con filtros ---------------------------------------
    st.markdown(f"**Cartera de {fondo}** · ordenada por puntaje para tu perfil")
    filtrados = filtrarBonos(evaluados, f"presc_{fondo}")
    huellaFiltro = abs(hash((len(filtrados), tuple(filtrados["clave"].head(MAXIMO_FILAS_EDITOR)))))
    st.caption(f"{len(filtrados):,} bonos con estos filtros" + (f"; se muestran los {MAXIMO_FILAS_EDITOR} mejores." if len(filtrados) > MAXIMO_FILAS_EDITOR else "."))
    tablaConCasillas(filtrados.head(MAXIMO_FILAS_EDITOR), claveSeleccion,
                     f"editorCartera_{claveSeleccion}_{version}_{huellaFiltro}", altura=420)

    with st.expander("Otras vistas: por emisor y mapa rendimiento / plazo"):
        pestanas = st.tabs(["Por emisor", "Mapa rendimiento / plazo"])
        with pestanas[0]:
            st.dataframe(vistaEmisores(tablaEmisores(evaluados, f"{fondo}_{perfil}")), use_container_width=True, hide_index=True, key="prescriptivo_dataframe_1")
            st.caption("Para comprar un bono de un emisor, búscalo por su nombre en «Buscar emisor o CUSIP» y marca «Comprar».")
        with pestanas[1]:
            st.plotly_chart(graficarMapaBonos(evaluados, claves), use_container_width=True, key="prescriptivo_plotly_chart_2")
            st.caption("Cada punto es un bono (tamaño = peso en el fondo). Los anillos son tu selección. "
                       "Arriba a la izquierda: más rendimiento con menos plazo.")
    return seleccion, evaluados


# ---------------------------------------------------------------------------
# Paso 3: monto y proyeccion
# ---------------------------------------------------------------------------
def cambiosTasasCacheados(datos, meses):
    clave = f"cambiosTasas_{meses}_{len(datos.get('curvaSeries', {}))}"
    if clave not in st.session_state:
        st.session_state[clave] = cambiosHistoricosTasas(datos.get("curvaSeries", {}), meses)
    return st.session_state[clave]


TONO_VEREDICTO = {"Recomendable": "verde", "Aceptable": "ambar", "No recomendable": "roja", "Sin datos": "roja"}


def nombreFondo(fondo, tablaFondos):
    """'ANGL — VanEck Fallen Angel High Yield Bond ETF' (o solo el ticker si no esta en la tabla)."""
    if fondo and tablaFondos is not None and not tablaFondos.empty and fondo in set(tablaFondos["ticker"]):
        return f"{fondo} — {tablaFondos.set_index('ticker').loc[fondo, 'nombre']}"
    return fondo or ""


def htmlEleccion(datos, fondo, modo, seleccion, tablaFondos, montoRf, meses):
    """Recuadro «Lo que estás proyectando»: fondo, bonos elegidos, monto y plazo."""
    plazo = f"{formatearMoneda(montoRf)} durante {meses} meses"
    if modo == MODO_LIQUIDEZ or not fondo:
        return recuadroEleccion("Lo que estás proyectando", f"Liquidez · letras del Tesoro al {datos['tasaLibre']:.2%}",
                                f"{plazo}. Sin bonos por ahora.")
    fila = tablaFondos.set_index("ticker").loc[fondo] if fondo in set(tablaFondos["ticker"]) else None
    detalleFondo = f"{fila['segmento']} · {fila['veredicto']} para tu perfil" if fila is not None else ""
    if modo == MODO_BONOS and not seleccion.empty:
        chips = []
        for _, b in seleccion.iterrows():
            texto = (f"<b>{escape(str(b['emisor'])[:40])}</b> · cupón {b['cupon']:.3%} · vence {b['vencimiento']:%m/%Y}"
                     f" · CUSIP {escape(str(b.get('cusip', '')))} · {escape(str(b['veredicto']))}")
            chips.append((texto, TONO_VEREDICTO.get(b["veredicto"], "")))
        return recuadroEleccion("Lo que estás proyectando", f"{len(seleccion)} bono(s) de {nombreFondo(fondo, tablaFondos)}",
                                f"{detalleFondo} · {plazo}", chips)
    extra = " · aún no marcaste bonos: se proyecta el fondo completo" if modo == MODO_BONOS else ""
    return recuadroEleccion("Lo que estás proyectando", f"Fondo completo: {nombreFondo(fondo, tablaFondos)}",
                            f"{detalleFondo} · {plazo}{extra}")


def pasoProyeccion(datos, perfil, fondo, modo, seleccion, tablaFondos, asignacion):
    """
    Monto, plan de compra y proyeccion. La proyeccion principal es la de TU
    eleccion (bonos marcados, fondo completo o liquidez); las otras se
    muestran como comparacion. Devuelve dict con capital, meses, plan y resumen.
    """
    queSeProyecta = {MODO_BONOS: "los bonos que marcaste", MODO_FONDO: f"el fondo {fondo} completo",
                     MODO_LIQUIDEZ: "la liquidez"}.get(modo, "tu renta fija")
    encabezadoPaso(3, "Define el monto y mira la proyección",
                   f"Primero tu renta fija ({queSeProyecta}) frente a las alternativas; después, toda tu cartera: acciones, bonos y liquidez.")
    columnas = st.columns([2, 2, 3])
    capital = columnas[0].number_input("Capital total de la cartera (USD)", min_value=0.0, value=10000.0, step=1000.0, key="capitalTotal")
    meses = columnas[1].slider("Horizonte (meses)", 12, 120, 36, step=6, key="horizonteMeses")
    pesoRf = sum(f["peso"] for f in asignacion["filas"] if f["clase"] == "Renta fija")
    if modo == MODO_LIQUIDEZ:  # se proyecta en liquidez el monto que el perfil destinaria a renta fija
        pesoRf = asignacion.get("rentaFijaObjetivo", pesoRf)
    montoRf = capital * pesoRf
    columnas[2].markdown(f"**Monto para renta fija:** {formatearMoneda(montoRf)} ({pesoRf:.0%} de tu cartera, perfil {perfil}"
                         + (f", señal {datos['senal']['accion']} de {datos['ticker']}" if asignacion.get("claseAjuste") == "Renta fija"
                            and asignacion.get("ajusteTactico") else "") + ").")

    st.markdown(htmlEleccion(datos, fondo, modo, seleccion, tablaFondos, montoRf, meses), unsafe_allow_html=True)

    resultado = {"capital": capital, "meses": meses, "montoRf": montoRf, "plan": pd.DataFrame(), "proyeccion": None, "cartera": None}
    if montoRf <= 0:
        st.info("Con la asignación actual no hay monto para renta fija.")
        resultado["cartera"] = proyeccionCarteraCompleta(datos, perfil, asignacion, capital, 0.0, meses, None) if capital else None
        return resultado

    tasa = datos["tasaLibre"]
    alternativas = []
    if modo == MODO_BONOS and seleccion.empty:
        st.info("Aún no marcaste bonos en el paso 2: mientras tanto se proyecta el fondo completo.")
    if not seleccion.empty:
        plan, sobrante = planDeCompra(seleccion, montoRf)
        plazos, cambios = cambiosTasasCacheados(datos, meses)
        proyeccion = proyectarBonos(plan, sobrante, meses, tasa, plazos, cambios)
        r = proyeccion["resumen"]
        resultado.update(plan=plan, proyeccion=r, valoresRf=proyeccion["valores"])
        alternativas.append({"nombre": f"★ Tus {len(seleccion)} bono(s) de {fondo}", "p10": r["valorPesimista"], "p50": r["valorMediano"],
                             "p90": r["valorOptimista"], "invertido": montoRf})
    if fondo:
        fila = tablaFondos.set_index("ticker").loc[fondo]
        historico = datos["universoBonos"].get(fondo, {}).get("historico")
        if not esNulo(fila["rendimientoEsperado"]):
            simulacionFondo = proyectarInversion(historico, fila["rendimientoEsperado"], montoRf, 0, meses, simulaciones=3000, tasaLiquidez=tasa)
            pf = dict(simulacionFondo["resumen"], montoTotal=montoRf)
            alternativas.append({"nombre": ("★ " if modo == MODO_FONDO or seleccion.empty and modo == MODO_BONOS else "")
                                 + f"Fondo {fondo} completo", "p10": pf["valorPesimista"], "p50": pf["valorMediano"],
                                 "p90": pf["valorOptimista"], "invertido": montoRf})
            if resultado["proyeccion"] is None and modo != MODO_LIQUIDEZ:
                resultado.update(proyeccion=pf, valoresRf=simulacionFondo["valores"])
    valorLiquidez = montoRf * (1 + tasa) ** (meses / 12)
    alternativas.append({"nombre": ("★ " if modo == MODO_LIQUIDEZ else "") + f"Liquidez ({tasa:.2%})", "p10": valorLiquidez, "p50": valorLiquidez, "p90": valorLiquidez, "invertido": montoRf})
    if resultado["proyeccion"] is None:
        resultado["proyeccion"] = {"valorMediano": valorLiquidez, "gananciaMediana": valorLiquidez - montoRf,
                                   "gananciaPesimista": valorLiquidez - montoRf, "gananciaOptimista": valorLiquidez - montoRf,
                                   "valorPesimista": valorLiquidez, "valorOptimista": valorLiquidez, "probabilidadPerdida": 0.0,
                                   "montoTotal": montoRf, "meses": meses}
        resultado["valoresRf"] = valorLiquidez

    r = resultado["proyeccion"]
    r["rendimientoAnual"] = rendimientoAnualizado(r["valorMediano"], montoRf, meses)
    st.markdown(f"##### Tu renta fija · {formatearMoneda(montoRf)}")
    filaTarjetas([
        {"etiqueta": "Monto en renta fija", "valor": formatearMoneda(montoRf),
         "nota": f"{len(seleccion)} bono(s) de {fondo}" if not seleccion.empty
                 else (f"Fondo {fondo} completo" if fondo and modo != MODO_LIQUIDEZ else "Liquidez")},
        {"etiqueta": f"Valor en {meses} meses (central)", "valor": formatearMoneda(r["valorMediano"]),
         "nota": f"Ganancia {formatearMoneda(r['gananciaMediana'])} · {formatearPorcentaje(r['rendimientoAnual'], 2)} anual",
         "tono": "positivo" if r["gananciaMediana"] >= 0 else "negativo"},
        {"etiqueta": "Rango probable de ganancia", "valor": f"{formatearMoneda(r['gananciaPesimista'])} a {formatearMoneda(r['gananciaOptimista'])}",
         "nota": "Escenarios P10 – P90"},
        {"etiqueta": "Probabilidad de pérdida", "valor": formatearPorcentaje(r["probabilidadPerdida"], 1),
         "nota": f"Liquidez: {formatearMoneda(valorLiquidez)}"},
    ])
    st.plotly_chart(graficarAlternativas(alternativas), use_container_width=True, key="prescriptivo_plotly_chart_3")
    st.caption("★ = tu elección. Las demás filas son la comparación: qué obtendrías con el mismo monto en otra alternativa.")

    resultado["cartera"] = proyeccionCarteraCompleta(datos, perfil, asignacion, capital, montoRf, meses, resultado.get("valoresRf"))

    if not resultado["plan"].empty:
        plan = resultado["plan"]
        vista = pd.DataFrame({
            "Bono": plan["bono"], "CUSIP": plan["cusip"], "Veredicto": plan["veredicto"], "Precio ref.": plan["precio"].round(2),
            "Lote mínimo (nominal)": plan["lote"].map(formatearMoneda), "Nominal a comprar": plan["nominalComprado"].map(formatearMoneda),
            "Costo aprox.": plan["costo"].map(formatearMoneda), "TIR": plan["tir"].map(lambda v: formatearPorcentaje(v, 2)),
            "Rend. esperado": plan["rendimientoEsperado"].map(lambda v: formatearPorcentaje(v, 2)),
            "Vence": plan["vencimiento"].dt.strftime("%d/%m/%Y"),
        })
        st.markdown("**Plan de compra**")
        st.dataframe(vista, use_container_width=True, hide_index=True, key="prescriptivo_dataframe_4")
        sinLote = plan.loc[plan["lotes"] == 0, "bono"].tolist()
        if sinLote:
            st.warning("El monto por bono no alcanza un lote mínimo en: " + "; ".join(sinLote) + ". Elige menos bonos o aumenta el capital.")
        st.caption(
            f"Partes iguales por bono; lo que no alcanza un lote queda en liquidez ({formatearMoneda(resultado['proyeccion']['sobrante'])}). "
            "El precio es el del último reporte del fondo: el de compra será el del mercado ese día. Lotes: USD 100 nominal en el "
            "Tesoro (TreasuryDirect) y USD 1 000 en el resto, vía un bróker."
        )
    st.caption(
        "Proyección de tus bonos: cupones reinvertidos en liquidez, impagos según la calidad implícita (recuperación 40%) y, si el "
        "bono vence después del horizonte, venta a la tasa actual más un cambio de tasas tomado de la historia del Tesoro. "
        "El fondo se proyecta con sus retornos mensuales históricos re-centrados en su rendimiento actual. Antes de impuestos y comisiones."
    )
    return resultado


def proyeccionCarteraCompleta(datos, perfil, asignacion, capital, montoRf, meses, valoresRf):
    """
    Proyecta TODA la cartera (acciones + renta fija elegida + liquidez) y la
    muestra con su ganancia en dólares y en % anual. Devuelve el resumen o None.
    """
    tasa = datos["tasaLibre"]
    pesoRv = sum(f["peso"] for f in asignacion["filas"] if f["clase"] == "Renta variable")
    montoRv = capital * pesoRv
    montoLiquidez = max(capital - montoRv - montoRf, 0.0)
    # Acciones: el fondo analizado si es de acciones; si no, el ETF de mercado amplio de referencia
    if datos.get("claseFondo") == "Renta variable":
        historicoRv, nombreRv = datos["historico"], f"Acciones ({datos['ticker']}, el fondo analizado)"
    else:
        historicoRv, nombreRv = datos.get("rentaVariableReferencia"), f"Acciones (referencia {datos.get('tickerRentaVariable', 'VTI')})"
    simulacionRv = proyectarInversion(historicoRv, RETORNO_ESPERADO_ACCIONES, montoRv, 0, meses, simulaciones=3000,
                                      semilla=23, volatilidadRespaldo=VOLATILIDAD_ACCIONES_RESPALDO, centrarMediana=True)
    componentes = [
        {"clase": "Renta variable", "nombre": nombreRv, "monto": montoRv, "valores": simulacionRv["valores"]},
        {"clase": "Renta fija", "nombre": "Tu renta fija (elección del paso 1-2)", "monto": montoRf,
         "valores": valoresRf if valoresRf is not None else montoRf * (1 + tasa) ** (meses / 12)},
        {"clase": "Liquidez", "nombre": f"Liquidez ({tasa:.2%})", "monto": montoLiquidez,
         "valores": montoLiquidez * (1 + tasa) ** (meses / 12)},
    ]
    cartera = proyectarCartera(componentes, meses)
    if cartera is None:
        return None
    r = cartera["resumen"]
    st.markdown(f"##### Toda tu cartera · {formatearMoneda(capital)} · perfil {perfil}")
    filaTarjetas([
        {"etiqueta": f"Valor de tu cartera en {meses} meses", "valor": formatearMoneda(r["valorMediano"]),
         "nota": "Escenario central (mediana)"},
        {"etiqueta": "Ganancia esperada de toda tu cartera", "valor": formatearMoneda(r["gananciaMediana"]),
         "nota": f"{formatearPorcentaje(r['rendimientoAnual'], 2)} anual", "tono": "positivo" if r["gananciaMediana"] >= 0 else "negativo",
         "destacada": True},
        {"etiqueta": "Rango probable de ganancia", "valor": f"{formatearMoneda(r['gananciaPesimista'])} a {formatearMoneda(r['gananciaOptimista'])}",
         "nota": "Escenarios P10 – P90"},
        {"etiqueta": "Probabilidad de pérdida", "valor": formatearPorcentaje(r["probabilidadPerdida"], 1),
         "nota": "De terminar con menos de lo invertido"},
    ])
    partes = cartera["partes"]
    vista = pd.DataFrame({
        "Parte de la cartera": partes["nombre"], "Monto": partes["monto"].map(formatearMoneda),
        "% de la cartera": (partes["monto"] / capital).map(lambda v: f"{v:.0%}") if capital else "",
        "Ganancia central": partes["gananciaMediana"].map(formatearMoneda),
        "Rendimiento anual": partes["rendimientoAnual"].map(lambda v: formatearPorcentaje(v, 2)),
    })
    st.dataframe(vista, use_container_width=True, hide_index=True, key="prescriptivo_dataframe_cartera")
    st.caption(
        f"Las acciones se simulan con su historia mensual, con un escenario central SUPUESTO de "
        f"{RETORNO_ESPERADO_ACCIONES:.0%} anual (RETORNO_ESPERADO_ACCIONES en el .env); por eso un perfil con más acciones "
        "espera ganar más, pero con un rango más ancho y más probabilidad de pérdida. Acciones y bonos se simulan por separado "
        "y se suman escenario por escenario. Antes de impuestos y comisiones."
    )
    return r


# ---------------------------------------------------------------------------
# Paso 4: asignacion y plan
# ---------------------------------------------------------------------------
def pasoAsignacionYPlan(datos, perfil, asignacion, plan, capital, coherencia, fondo, resumenFondos):
    encabezadoPaso(4, "Tu cartera y el plan de acción", "La asignación completa del perfil con tus elecciones, en porcentaje y en dólares.")
    columnas = st.columns(2)
    with columnas[0]:
        for fila in asignacion["filas"]:
            nombre = fila["detalle"] + (f" · {fila['ticker']}" if fila["clase"] == "Renta fija" and fila["ticker"] and fila["cusip"] else "")
            if fila["veredicto"] == "No recomendable":
                nombre = "⚠ " + nombre
            if capital:
                nombre += f" · {formatearMoneda(capital * fila['peso'])}"
            st.markdown(barraAsignacion(nombre, fila["peso"], COLOR_CLASE.get(fila["clase"])), unsafe_allow_html=True)
        st.caption(f"{asignacion['nota']} Ajuste por la señal {datos['senal']['accion']} de {datos['ticker']}: "
                   f"{asignacion['ajusteTactico'] * 100:+.0f} pp de {asignacion.get('claseAjuste', 'Renta variable').lower()}.")
    with columnas[1]:
        pasos = construirPlanAccion(datos["senal"], datos["ticker"], datos["riesgo"], perfil, resumenFondos, asignacion,
                                    plan, capital, coherencia, fondo)
        st.dataframe(pd.DataFrame(pasos)[["prioridad", "accion", "plazo"]].rename(
            columns={"prioridad": "#", "accion": "Acción", "plazo": "Plazo"}), use_container_width=True, hide_index=True, key="prescriptivo_dataframe_5")


# ---------------------------------------------------------------------------
# Resumen superior (se dibuja al final dentro del contenedor de arriba)
# ---------------------------------------------------------------------------
def tarjetaGanancia(proyeccion, cartera):
    """Ganancia de TODA la cartera, con la de la renta fija por separado (en $ y % anual)."""
    if not cartera:
        return {"etiqueta": "Ganancia esperada", "valor": "N/D", "nota": "Define el monto en el paso 3"}
    notaRf = (f"Solo renta fija: {formatearMoneda(proyeccion['gananciaMediana'])} "
              f"({formatearPorcentaje(proyeccion.get('rendimientoAnual'), 2)} anual)") if proyeccion else ""
    return {"etiqueta": f"Ganancia de toda tu cartera · {cartera['meses']} meses",
            "valor": formatearMoneda(cartera["gananciaMediana"]),
            "nota": f"{formatearPorcentaje(cartera['rendimientoAnual'], 2)} anual · {notaRf}",
            "tono": "positivo" if cartera["gananciaMediana"] >= 0 else "negativo"}


def dibujarResumen(datos, perfil, fondo, modo, seleccion, tablaFondos, asignacion, proyeccion, coherencia, cartera=None):
    senal, metricas = datos["senal"], datos["metricas"]
    st.markdown(insignia(f"Tu decisión · perfil {perfil} · fondo {datos['ticker']}",
                         COLOR_PERFIL.get(perfil, "azul")),
                unsafe_allow_html=True)
    st.write("")
    clase = asignacion.get("claseAjuste", "Renta variable")
    pesoClase = sum(f["peso"] for f in asignacion["filas"] if f["clase"] == clase)
    filaFondo = tablaFondos.set_index("ticker").loc[fondo] if fondo and not tablaFondos.empty else None
    if modo == MODO_BONOS and not seleccion.empty:
        rentaFija = f"{len(seleccion)} bono(s) de {fondo}"
        notaRf = f"{coherencia['emisores']} emisor(es) · calidad más baja: {coherencia['calidadMinima']}"
        rendimiento = coherencia["rendimientoEsperado"]
    elif fondo and modo != MODO_LIQUIDEZ:
        rentaFija = f"Fondo {fondo} completo"
        notaRf = f"{filaFondo['segmento']} · {filaFondo['veredicto']}"
        if modo == MODO_BONOS:
            notaRf += " · aún sin bonos marcados"
        rendimiento = filaFondo["rendimientoEsperado"]
    else:
        rentaFija, notaRf, rendimiento = "Liquidez", "Sin bonos por ahora", datos["tasaLibre"]
    filaTarjetas([
        {"etiqueta": f"Señal · {datos['ticker']}", "valor": senal["accion"], "destacada": senal["accion"] == "COMPRAR",
         "nota": f"Puntaje {senal['puntaje']:+.1f} · "
                 + ("renta fija en liquidez" if modo == MODO_LIQUIDEZ and clase == "Renta fija" else f"{pesoClase:.0%} en {clase.lower()}")
                 + " · horizonte "
                 f"{calcularHorizonteOptimo(metricas.get('volatilidadAnual'), perfil)}"},
        {"etiqueta": "Tu renta fija", "valor": rentaFija, "nota": notaRf},
        {"etiqueta": "Rendimiento esperado de tu renta fija", "valor": formatearPorcentaje(rendimiento, 2),
         "nota": f"Liquidez: {formatearPorcentaje(datos['tasaLibre'], 2)} anual",
         "tono": "positivo" if not esNulo(rendimiento) and rendimiento > datos["tasaLibre"] else "neutro"},
        tarjetaGanancia(proyeccion, cartera),
    ])
    if modo == MODO_BONOS and not seleccion.empty:
        {"coherente": st.success, "cautela": st.warning, "riesgo": st.error}.get(coherencia["estado"], st.info)(coherencia["mensaje"])
    elif filaFondo is not None and modo != MODO_LIQUIDEZ:
        (st.error if filaFondo["veredicto"] in ("No recomendable", "Sin datos") else st.info)(
            f"Renta fija en el fondo {fondo} completo ({filaFondo['veredicto'].lower()} para tu perfil). "
            + ("Marca bonos en el paso 2 para invertir directo en ellos." if modo == MODO_BONOS
               else "Si prefieres elegir sus bonos uno por uno, cámbialo en el paso 1."))
    alerta = evaluarAlertaPerfil(datos["riesgo"], senal, perfil, datos.get("clasificadorRiesgo"))
    if alerta:
        (st.warning if alerta[0] == "ambar" else st.info)(alerta[1])
    motivos = "; ".join((senal["motivos"] + senal["alertas"])[:3]) or "ningún factor fuerte a favor o en contra"
    st.caption(f"**Por qué {senal['accion']} en {datos['ticker']}:** {motivos}. Detalle en «Por qué esta señal», al final.")


# ---------------------------------------------------------------------------
# Detalles
# ---------------------------------------------------------------------------
def dibujarFactores(datos):
    senal = datos["senal"]
    tabla = pd.DataFrame(senal["factores"])
    tabla["Puntos"] = tabla.apply(lambda f: f"{f['puntos']:+.1f}" if f["activo"] else "no participa", axis=1)
    st.dataframe(tabla[["factor", "valor", "Puntos", "nota", "regla"]].rename(
        columns={"factor": "Factor", "valor": "Valor", "nota": "Nota", "regla": "Regla"}), use_container_width=True, hide_index=True, key="prescriptivo_dataframe_6")
    st.caption(f"Puntaje = suma de los puntos = **{senal['puntaje']:+.1f}** (rango −9.5 a +8.5). ≥ +3 COMPRAR · ≤ −3 REDUCIR · "
               f"en medio MANTENER. Retorno histórico anualizado de {datos['ticker']}: {formatearPorcentaje(datos['retornoEsperado'], 1, True)}.")


def dibujarBacktest(datos):
    tabla, resumen = datos.get("backtest", pd.DataFrame()), datos.get("resumenBacktest", {})
    if tabla is None or tabla.empty:
        st.info("Se necesita más historia para el backtest (al menos ~1.5 años). Prueba con el periodo de 10 años.")
        return
    st.plotly_chart(graficarBacktest(tabla), use_container_width=True, key="prescriptivo_plotly_chart_7")
    porAccion = resumen["porAccion"].reset_index().rename(columns={
        "accion": "Señal", "semanas": "Semanas", "retornoMedio": "Retorno medio posterior", "proporcionAlza": "% de veces que subió"})
    st.dataframe(formatearTablaPorcentajes(porAccion, ["Retorno medio posterior", "% de veces que subió"], 1),
                 use_container_width=True, hide_index=True, key="prescriptivo_dataframe_8")
    st.caption(f"{resumen['semanas']} cierres semanales entre {formatearFecha(resumen['desde'])} y {formatearFecha(resumen['hasta'])}, "
               f"retorno a {resumen['dias']} días hábiles; señal solo con reglas (sin pronóstico ni noticias). Ventanas solapadas: "
               "es un diagnóstico, no una rentabilidad realizable.")


def dibujarValidacionRetrospectiva(datos):
    validacion = datos.get("validacion")
    if not validacion:
        st.info("No hay datos posteriores a esa fecha para validar la recomendación.")
        return
    if not validacion["completo"]:
        st.warning(f"Solo hay {validacion['diasEvaluados']} de {validacion['diasSolicitados']} días hábiles posteriores.")
    filaTarjetas([
        {"etiqueta": "Señal emitida", "valor": validacion["accion"], "nota": f"Al {validacion['fechaCorte']:%d/%m/%Y}"},
        {"etiqueta": f"Retorno real ({validacion['diasEvaluados']} días)", "valor": formatearPorcentaje(validacion["retornoReal"], 1, True),
         "tono": "positivo" if validacion["retornoReal"] >= 0 else "negativo"},
        {"etiqueta": "Retorno proyectado", "valor": formatearPorcentaje(validacion["retornoProyectado"], 1, True),
         "nota": {True: "Dentro de la banda 90%", False: "Fuera de la banda 90%"}.get(validacion["dentroDeBanda"], "Banda no evaluable")},
        {"etiqueta": "Resultado", "valor": "Acierto" if validacion["acierto"] else "No acertó",
         "tono": "positivo" if validacion["acierto"] else "negativo",
         "nota": f"Benchmark: {formatearPorcentaje(validacion['retornoBenchmark'], 1, True)}"},
    ])


def dibujarExplicacionIa(datos, perfil, proveedorInfo, decision):
    proveedor, estado, _ = proveedorInfo
    if not proveedorListo(estado):
        st.warning(f"**{nombreProveedor(proveedor)}**: {estado['mensaje']}")
        st.markdown(explicacionDeRespaldo(datos, perfil))
        return
    seleccion = decision.get("seleccion")
    huella = "-".join(sorted(seleccion["clave"])) if seleccion is not None and not seleccion.empty else decision.get("fondo") or "liquidez"
    marca = f"{datos['fechaCorte']:%Y%m%d}" if datos.get("fechaCorte") is not None else "actual"
    clave = f"explicacion_{datos['ticker']}_{perfil}_{marca}_{abs(hash(huella))}"
    if st.button(f"Explicar mi decisión con {nombreProveedor(proveedor)}", type="primary"):
        with st.spinner(f"{nombreProveedor(proveedor)} está redactando el informe..."):
            texto, usado, sospechosas = generarExplicacionLLM(construirContexto(datos, perfil, decision), perfil, proveedorInfo)
            st.session_state[clave] = {"texto": texto or explicacionDeRespaldo(datos, perfil),
                                       "proveedor": usado if texto else None, "sospechosas": sospechosas}
    guardado = st.session_state.get(clave)
    if not guardado:
        st.caption("El informe explica la señal, el fondo y los bonos que elegiste, y tu proyección. Si cambias la selección, vuelve a generarlo.")
        return
    if guardado["proveedor"]:
        st.caption(f"Generado por **{nombreProveedor(guardado['proveedor'])}** a partir de los datos calculados.")
    if guardado["sospechosas"]:
        st.warning("Estas cifras del texto no aparecen en los datos del análisis; revísalas: " + ", ".join(guardado["sospechosas"]))
    st.markdown(guardado["texto"])
    st.download_button("Descargar informe", data=guardado["texto"],
                       file_name=f"informe_{datos['ticker']}_{perfil}_{datetime.now():%Y%m%d}.md", mime="text/markdown")


# ---------------------------------------------------------------------------
# Pestaña
# ---------------------------------------------------------------------------
def dibujarDashboardPrescriptivo(datos, perfil, proveedorInfo):
    """Pestaña Prescriptivo: resumen arriba, pasos 1-4 y detalles."""
    tablaFondos, resumenFondos = datos["rankingsPorPerfil"].get(perfil, (pd.DataFrame(), {}))
    resumenSuperior = st.container()  # se llena al final con las elecciones de abajo
    st.divider()

    fondo, modo = pasoElegirModo(datos, perfil, tablaFondos, resumenFondos)
    st.divider()
    seleccion, _ = pasoElegirBonos(datos, fondo, perfil, modo)
    st.divider()

    claseSenal = datos.get("claseFondo", "Renta variable")
    fondoAnalizado = datos["ticker"] if claseSenal == "Renta variable" else None
    asignacion = construirAsignacion(perfil, datos["senal"], tablaFondos, seleccion, fondo, fondoAnalizado,
                                     claseSenal=claseSenal, soloLiquidez=modo == MODO_LIQUIDEZ)
    coherencia = evaluarSeleccion(seleccion, perfil)
    resultado = pasoProyeccion(datos, perfil, fondo, modo, seleccion, tablaFondos, asignacion)
    st.divider()
    fondoPlan = fondo if modo != MODO_LIQUIDEZ else None
    pasoAsignacionYPlan(datos, perfil, asignacion, resultado["plan"], resultado["capital"], coherencia, fondoPlan,
                        resumenFondos if modo != MODO_LIQUIDEZ else dict(resumenFondos, invertir=False))

    with resumenSuperior:
        dibujarResumen(datos, perfil, fondo, modo, seleccion, tablaFondos, asignacion, resultado["proyeccion"], coherencia,
                       resultado.get("cartera"))

    decision = {"fondo": fondoPlan, "modo": modo, "seleccion": seleccion, "asignacion": asignacion, "coherencia": coherencia,
                "proyeccion": resultado["proyeccion"], "proyeccionCartera": resultado.get("cartera")}
    st.divider()
    st.markdown("#### Detalles del análisis")
    with st.expander(f"Por qué esta señal ({datos['senal']['accion']} en {datos['ticker']})"):
        dibujarFactores(datos)
        for nombre, regla in REGLAS_SENAL:
            st.markdown(f"- **{nombre}:** {regla}")
    with st.expander("Backtest de la señal: qué pasó después de cada recomendación"):
        dibujarBacktest(datos)
    with st.expander("Comparación entre perfiles"):
        st.dataframe(compararPerfiles(datos["senal"], datos["metricas"], datos["riesgo"], perfil, datos["rankingsPorPerfil"],
                                      datos.get("claseFondo", "Renta variable")),
                     use_container_width=True, hide_index=True, key="prescriptivo_dataframe_9")
        st.caption(f"Misma señal de {datos['ticker']}; cambian el horizonte, la mezcla y los fondos de bonos según el perfil.")
    if datos.get("fechaCorte") is not None:
        with st.expander("Validación retrospectiva: qué pasó después", expanded=True):
            dibujarValidacionRetrospectiva(datos)
    with abrirPanel("Explicación de tu decisión con IA"):
        dibujarExplicacionIa(datos, perfil, proveedorInfo, decision)
    st.caption("Proyecto con fines académicos. Las recomendaciones salen de un modelo estadístico y no constituyen asesoría financiera.")
    return decision


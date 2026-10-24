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

import numpy as np
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
from src.catalogoBonos import nombreFondo
from src.estilos import COLORES, abrirPanel, barraAsignacion, encabezadoPaso, recuadroEleccion
from src.graficos import graficarAlternativas, graficarBacktest, graficarMapaBonos
from src.motorPrescriptivo import (
    REGLAS_SENAL,
    calcularHorizonteOptimo,
    compararPerfiles,
    construirAsignacion,
    construirContexto,
    construirPlanAccion,
    evaluarAlertaPerfil,
    conclusionParaDatos,
    conclusionSeleccion,
    explicacionDeRespaldo,
    generarExplicacionLLM,
    proveedorListo,
)
from src.utilidades import esNulo, formatearMoneda, formatearPorcentaje
from src.vistas.bonos import (
    bonosEvaluados,
    botonCargarCartera,
    filtrarBonos,
    resumenFondoBonos,
    explicarBonosVsFondo,
    tablaEmisores,
    vistaBonos,
    vistaEmisores,
)
from src.vistas.comunes import (
    ICONO_VEREDICTO,
    opcionesGrandes,
    tablaDatos,
    _admiteAltoFila,
    tablaHtml,
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


def tarjetaConclusion(datos, conclusion):
    """Tarjeta principal: ¿invertir o no?, con sus dos razones (fondo y momento) o, si compras bonos, sobre ellos."""
    if conclusion.get("sobre") == "bonos":
        return {"etiqueta": "¿Invertir en tus bonos?", "valor": conclusion["decision"], "color": conclusion["tono"],
                "nota": f"Tus bonos: {conclusion['decision'].lower()} · el fondo completo: "
                        f"{str(conclusion.get('veredictoFondo') or 'sin ranking').lower()}"}
    fondoTxt = conclusion["veredicto"] or "fuera del ranking de tu perfil"
    return {"etiqueta": "¿Invertir en este fondo?", "valor": conclusion["decision"], "color": conclusion["tono"],
            "nota": f"Fondo: {fondoTxt.lower() if conclusion['veredicto'] else fondoTxt} · Momento: {conclusion['momento'].lower()}"
                    + (f" · Mejor opción: {nombreFondo(conclusion['alternativa'])}" if conclusion.get("alternativa") else "")}


def pasoElegirModo(datos, perfil, tablaFondos, resumenFondos, conclusion):
    """Fondo de la renta fija y como invertir en el. Devuelve (fondo o None, modo)."""
    encabezadoPaso(1, "¿Cómo inviertes tu renta fija?")
    if tablaFondos is None or tablaFondos.empty:
        st.info("No hay datos de fondos de bonos. Presiona «Actualizar datos».")
        return None, MODO_LIQUIDEZ
    fondo, esAnalizado = fondoDeRentaFija(datos, tablaFondos)
    if not esAnalizado:
        st.caption(f"{datos.get('nombreCorto') or datos['ticker']} va como tu parte de acciones; para la renta fija se usa "
                   + (f"**{fondo}**, el mejor fondo de bonos de tu perfil." if fondo else "liquidez (ningún fondo de tu perfil califica hoy)."))
    if fondo is None:
        mostrarRecomendacion(resumenFondos.get("recomendacion", ""), resumenFondos.get("tono"))
        return None, MODO_LIQUIDEZ

    f = tablaFondos.set_index("ticker").loc[fondo]
    rendimiento = "s/d" if esNulo(f["rendimientoEsperado"]) else f"{f['rendimientoEsperado']:.2%}"
    st.markdown(f"**{nombreFondo(fondo)}**  \n{ICONO_VEREDICTO.get(f['veredicto'], '')} {f['veredicto']} para tu perfil · "
                f"puesto {int(f['puesto'])} de {len(tablaFondos)} · rinde {rendimiento} al año (sin riesgo: "
                f"{formatearPorcentaje(datos['tasaLibre'], 2)})")
    if f["veredicto"] in ("No recomendable", "Sin datos") and esAnalizado:
        alternativa = mejorAlternativa(tablaFondos, fondo)
        if alternativa is not None:
            def cambiarFondo(nuevo=alternativa["ticker"]):
                st.session_state[f"fondoAnalizado_{perfil}"] = nuevo
            st.button(f"Ver «{nombreFondo(alternativa['ticker'], conTicker=False)}», el mejor de tu perfil →",
                      key=f"cambiarA_{perfil}_{alternativa['ticker']}",
                      on_click=cambiarFondo, type="primary")

    claveModo = f"modoRf_{perfil}_{fondo}"
    if claveModo not in st.session_state:
        # La opcion inicial sigue la conclusion: si dice «no invertir», arranca en liquidez
        invertir = conclusion["invertir"] if esAnalizado else f["veredicto"] in ("Recomendable", "Aceptable")
        st.session_state[claveModo] = MODO_FONDO if invertir else MODO_LIQUIDEZ
    modo = opcionesGrandes([
        {"valor": MODO_FONDO, "titulo": "El fondo completo", "subtitulo": "Una sola compra: miles de bonos y reinversión automática.",
         "chip": "Más simple", "tonoChip": "verde"},
        {"valor": MODO_BONOS, "titulo": "Bonos específicos", "subtitulo": "Eliges empresa, plazo y calidad dentro del fondo; sabes cuánto cobras al vencer.",
         "chip": "Lotes de USD 1 000", "tonoChip": "ambar"},
        {"valor": MODO_LIQUIDEZ, "titulo": "Nada por ahora", "subtitulo": "La parte de bonos se queda en liquidez (letras del Tesoro).",
         "chip": "Esperar", "tonoChip": "gris"},
    ], claveModo, st.session_state[claveModo], f"btnModo_{perfil}_{fondo}")
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
    if _admiteAltoFila():
        argumentos["row_height"] = 42
    st.data_editor(
        vista, key=claveEditor, hide_index=True, use_container_width=True,
        disabled=[c for c in vista.columns if c != "Comprar"],
        column_config={"Comprar": st.column_config.CheckboxColumn("Comprar", help="Marca para agregar el bono a tu compra", width="small"),
                       "Veredicto al vencer": st.column_config.TextColumn("Veredicto al vencer", help="Si guardas el bono hasta que venza")},
        on_change=_aplicarEdicion, args=(claveSeleccion, claveEditor, claves), **argumentos,
    )


def pasoElegirBonos(datos, fondo, perfil, modo):
    """Selección de bonos con casillas. Devuelve (seleccion, evaluados)."""
    vacio = pd.DataFrame()
    if modo != MODO_BONOS or fondo is None:  # el paso solo aparece si se eligen bonos especificos
        return vacio, vacio
    encabezadoPaso(2, "Marca los bonos que quieres comprar")
    if not botonCargarCartera(fondo, f"cargarCartera_presc_{fondo}"):
        st.caption(f"Mientras tanto, la proyección usa el fondo {fondo} completo.")
        return vacio, vacio
    evaluados, meta, error = bonosEvaluados(datos, fondo, perfil)
    if error:
        st.warning(f"{error} Mientras tanto, la proyección usa el fondo {fondo} completo.")
        return vacio, vacio
    resumenFondoBonos(evaluados, meta)
    explicarBonosVsFondo(datos, fondo, perfil, evaluados)

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
    if len(seleccion):
        costoMinimo = float((seleccion["precio"] / 100 * np.where(seleccion["calidad"].eq("Tesoro EE.UU."), 100, 1000)).sum())
        st.caption(f"Comprar un lote de cada uno cuesta ≈ {formatearMoneda(costoMinimo)}. En el paso 3 verás cuántos alcanzas "
                   "con el monto que tu perfil destina a renta fija.")
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
    st.markdown(f"**Todos los bonos de {fondo}** · los mejores para tu perfil primero")
    filtrados = filtrarBonos(evaluados, f"presc_{fondo}")
    huellaFiltro = abs(hash((len(filtrados), tuple(filtrados["clave"].head(MAXIMO_FILAS_EDITOR)))))
    st.caption(f"{len(filtrados):,} bonos con estos filtros" + (f"; se muestran los {MAXIMO_FILAS_EDITOR} mejores." if len(filtrados) > MAXIMO_FILAS_EDITOR else "."))
    tablaConCasillas(filtrados.head(MAXIMO_FILAS_EDITOR), claveSeleccion,
                     f"editorCartera_{claveSeleccion}_{version}_{huellaFiltro}", altura=420)

    with st.expander("Otras vistas: por emisor y mapa rendimiento / plazo"):
        pestanas = st.tabs(["Por emisor", "Mapa rendimiento / plazo"])
        with pestanas[0]:
            tablaDatos(vistaEmisores(tablaEmisores(evaluados, f"{fondo}_{perfil}")), key="prescriptivo_dataframe_1")
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
        return recuadroEleccion("Lo que estás proyectando", f"{len(seleccion)} bono(s) de {nombreFondo(fondo)}",
                                f"{detalleFondo} · {plazo}", chips)
    extra = " · aún no marcaste bonos: se proyecta el fondo completo" if modo == MODO_BONOS else ""
    return recuadroEleccion("Lo que estás proyectando", f"Fondo completo: {nombreFondo(fondo)}",
                            f"{detalleFondo} · {plazo}{extra}")


def avisoLotes(plan, seleccion, montoRf, capital, pesoRf):
    """
    Avisa, ANTES de la proyeccion, cuando el monto no alcanza para comprar todos
    los bonos marcados: los que no completan un lote quedan en liquidez, y eso
    cambia el riesgo y la ganancia que se proyectan.
    """
    sinLote = plan.loc[plan["lotes"] == 0]
    if sinLote.empty:
        return
    comprados = len(plan) - len(sinLote)
    costoMinimo = float((plan["precio"] / 100 * plan["lote"]).sum())  # un lote de cada bono marcado
    capitalNecesario = costoMinimo / pesoRf if pesoRf else np.nan
    enLiquidez = montoRf - float(plan["costo"].sum())
    texto = (f"**Con {formatearMoneda(montoRf)} solo alcanzas a comprar {comprados} de los {len(seleccion)} bonos.** "
             f"Cada bono se compra en lotes de USD 1 000; {formatearMoneda(enLiquidez)} quedan en liquidez y la proyección "
             f"es solo de {comprados} bono(s). Marca menos bonos o sube el capital a ~{formatearMoneda(capitalNecesario)}.")
    (st.error if comprados == 0 else st.warning)(texto)



def pasoProyeccion(datos, perfil, fondo, modo, seleccion, tablaFondos, asignacion, numero=3):
    """
    Monto, plan de compra y proyeccion. Primero lo que mas importa (toda tu
    cartera); el detalle de la renta fija y el plan de compra, en su pestaña.
    Devuelve dict con capital, meses, plan, proyeccion (renta fija) y cartera.
    """
    encabezadoPaso(numero, "¿Cuánto podrías ganar?", "Elige tu capital y el plazo.")
    columnas = st.columns(2)
    capital = columnas[0].number_input("Capital total (USD)", min_value=0.0, value=10000.0, step=1000.0, key="capitalTotal")
    meses = columnas[1].slider("Plazo (meses)", 12, 120, 36, step=6, key="horizonteMeses")
    pesoRf = sum(f["peso"] for f in asignacion["filas"] if f["clase"] == "Renta fija")
    if modo == MODO_LIQUIDEZ:  # se proyecta en liquidez el monto que el perfil destinaria a renta fija
        pesoRf = asignacion.get("rentaFijaObjetivo", pesoRf)
    montoRf = capital * pesoRf

    st.markdown(htmlEleccion(datos, fondo, modo, seleccion, tablaFondos, montoRf, meses), unsafe_allow_html=True)
    resultado = {"capital": capital, "meses": meses, "montoRf": montoRf, "plan": pd.DataFrame(), "proyeccion": None,
                 "cartera": None, "valoresRf": None}
    if capital <= 0:
        st.info("Ingresa un capital para ver la proyección.")
        return resultado

    # --- Calculo (sin dibujar) ----------------------------------------------
    tasa = datos["tasaLibre"]
    alternativas = []
    valorLiquidez = montoRf * (1 + tasa) ** (meses / 12)
    if montoRf > 0:
        if not seleccion.empty:
            plan, sobrante = planDeCompra(seleccion, montoRf)
            plazos, cambios = cambiosTasasCacheados(datos, meses)
            proyeccion = proyectarBonos(plan, sobrante, meses, tasa, plazos, cambios)
            r = proyeccion["resumen"]
            resultado.update(plan=plan, proyeccion=r, valoresRf=proyeccion["valores"])
            alternativas.append({"nombre": f"★ Tus {len(seleccion)} bono(s)", "p10": r["valorPesimista"], "p50": r["valorMediano"],
                                 "p90": r["valorOptimista"], "invertido": montoRf})
        if fondo:
            fila = tablaFondos.set_index("ticker").loc[fondo]
            historico = datos["universoBonos"].get(fondo, {}).get("historico")
            if not esNulo(fila["rendimientoEsperado"]):
                simulacionFondo = proyectarInversion(historico, fila["rendimientoEsperado"], montoRf, 0, meses, simulaciones=3000, tasaLiquidez=tasa)
                pf = dict(simulacionFondo["resumen"], montoTotal=montoRf)
                alternativas.append({"nombre": ("★ " if modo == MODO_FONDO or seleccion.empty and modo == MODO_BONOS else "")
                                     + f"Fondo {fondo}", "p10": pf["valorPesimista"], "p50": pf["valorMediano"],
                                     "p90": pf["valorOptimista"], "invertido": montoRf})
                if resultado["proyeccion"] is None and modo != MODO_LIQUIDEZ:
                    resultado.update(proyeccion=pf, valoresRf=simulacionFondo["valores"])
        alternativas.append({"nombre": ("★ " if modo == MODO_LIQUIDEZ else "") + f"Liquidez ({tasa:.2%})",
                             "p10": valorLiquidez, "p50": valorLiquidez, "p90": valorLiquidez, "invertido": montoRf})
        if resultado["proyeccion"] is None:
            resultado["proyeccion"] = {"valorMediano": valorLiquidez, "gananciaMediana": valorLiquidez - montoRf,
                                       "gananciaPesimista": valorLiquidez - montoRf, "gananciaOptimista": valorLiquidez - montoRf,
                                       "valorPesimista": valorLiquidez, "valorOptimista": valorLiquidez, "probabilidadPerdida": 0.0,
                                       "montoTotal": montoRf, "meses": meses}
            resultado["valoresRf"] = valorLiquidez
        resultado["proyeccion"]["rendimientoAnual"] = rendimientoAnualizado(resultado["proyeccion"]["valorMediano"], montoRf, meses)
    cartera, partes = calcularCarteraCompleta(datos, asignacion, capital, montoRf, meses, resultado["valoresRf"])
    resultado["cartera"] = cartera

    # --- Avisos que cambian lo que ves (solo si aplican) --------------------
    if modo == MODO_BONOS and seleccion.empty and montoRf > 0:
        st.info("Aún no marcaste bonos en el paso 2: mientras tanto se proyecta el fondo completo.")
    if not resultado["plan"].empty:
        avisoLotes(resultado["plan"], seleccion, montoRf, capital, pesoRf)

    # --- Resultado: primero toda la cartera, luego el detalle --------------
    pestanas = st.tabs([f"Toda tu cartera · {formatearMoneda(capital)}", f"Tu renta fija · {formatearMoneda(montoRf)}"])
    with pestanas[0]:
        dibujarCarteraCompleta(cartera, partes, capital, meses)
    with pestanas[1]:
        dibujarRentaFija(resultado, alternativas, seleccion, fondo, modo, montoRf, meses)
    with st.expander("¿Cómo se calcula esta proyección?"):
        st.markdown(
            f"- **Acciones:** su historia mensual con un escenario central **supuesto** de {RETORNO_ESPERADO_ACCIONES:.0%} anual "
            "para las acciones de EE.UU. Más acciones = más ganancia esperada, pero rango más ancho.\n"
            "- **Fondo de bonos:** sus retornos mensuales históricos, re-centrados en su rendimiento actual.\n"
            "- **Bonos específicos:** cupones reinvertidos, impagos según la calidad implícita (recuperación 40%) y, si vencen "
            "después del plazo, venta a la tasa actual más un cambio de tasas histórico.\n"
            "- **Liquidez:** tasa de las letras del Tesoro.\n"
            "- Acciones y bonos se simulan por separado y se suman escenario por escenario. Antes de impuestos y comisiones."
        )
    return resultado


def calcularCarteraCompleta(datos, asignacion, capital, montoRf, meses, valoresRf):
    """Proyeccion de TODA la cartera (acciones + renta fija elegida + liquidez). Devuelve (resumen, partes) o (None, None)."""
    tasa = datos["tasaLibre"]
    pesoRv = sum(f["peso"] for f in asignacion["filas"] if f["clase"] == "Renta variable")
    montoRv = capital * pesoRv
    montoLiquidez = max(capital - montoRv - montoRf, 0.0)
    # Acciones: el fondo analizado si es de acciones; si no, el ETF de mercado amplio de referencia
    if datos.get("claseFondo") == "Renta variable":
        historicoRv, nombreRv = datos["historico"], f"Acciones: {datos.get('nombreFondo') or datos['ticker']}"
    else:
        historicoRv, nombreRv = datos.get("rentaVariableReferencia"), "Acciones de EE.UU. (fondo indexado amplio)"
    simulacionRv = proyectarInversion(historicoRv, RETORNO_ESPERADO_ACCIONES, montoRv, 0, meses, simulaciones=3000,
                                      semilla=23, volatilidadRespaldo=VOLATILIDAD_ACCIONES_RESPALDO, centrarMediana=True)
    componentes = [
        {"clase": "Renta variable", "nombre": nombreRv, "monto": montoRv, "valores": simulacionRv["valores"]},
        {"clase": "Renta fija", "nombre": "Tu renta fija", "monto": montoRf,
         "valores": valoresRf if valoresRf is not None else montoRf * (1 + tasa) ** (meses / 12)},
        {"clase": "Liquidez", "nombre": f"Liquidez ({tasa:.2%})", "monto": montoLiquidez,
         "valores": montoLiquidez * (1 + tasa) ** (meses / 12)},
    ]
    cartera = proyectarCartera(componentes, meses)
    return (cartera["resumen"], cartera["partes"]) if cartera else (None, None)


def tarjetasProyeccion(r, meses):
    """Las 3 cifras de una proyeccion: ganancia central (con % anual), rango y probabilidad de perdida."""
    return [
        {"etiqueta": f"Ganancia esperada · {meses} meses", "valor": formatearMoneda(r["gananciaMediana"]),
         "nota": f"{formatearPorcentaje(r.get('rendimientoAnual'), 2)} anual · terminas con {formatearMoneda(r['valorMediano'])}",
         "tono": "positivo" if r["gananciaMediana"] >= 0 else "negativo"},
        {"etiqueta": "Rango probable", "valor": f"{formatearMoneda(r['gananciaPesimista'])} a {formatearMoneda(r['gananciaOptimista'])}",
         "nota": "8 de cada 10 escenarios"},
        {"etiqueta": "Probabilidad de pérdida", "valor": formatearPorcentaje(r["probabilidadPerdida"], 1),
         "nota": "Terminar con menos de lo invertido"},
    ]


def dibujarCarteraCompleta(cartera, partes, capital, meses):
    if not cartera:
        st.info("Sin datos para proyectar la cartera.")
        return
    filaTarjetas(tarjetasProyeccion(cartera, meses))
    vista = pd.DataFrame({
        "Parte": partes["nombre"], "Monto": partes["monto"].map(formatearMoneda),
        "%": (partes["monto"] / capital).map(lambda v: f"{v:.0%}"),
        "Ganancia": partes["gananciaMediana"].map(formatearMoneda),
        "Anual": partes["rendimientoAnual"].map(lambda v: formatearPorcentaje(v, 2)),
    })
    tablaHtml(vista)


def dibujarRentaFija(resultado, alternativas, seleccion, fondo, modo, montoRf, meses):
    r = resultado["proyeccion"]
    if not r:
        st.info("Con la asignación actual no hay monto para renta fija.")
        return
    filaTarjetas(tarjetasProyeccion(r, meses))
    if not resultado["plan"].empty:
        st.caption(f"En bonos {formatearMoneda(r['invertidoEnBonos'])} · en liquidez {formatearMoneda(r['sobrante'])} "
                   "(lo que no completa un lote).")
    st.plotly_chart(graficarAlternativas(alternativas), use_container_width=True, key="prescriptivo_plotly_chart_3")
    st.caption("★ = tu elección; las otras filas, qué obtendrías con el mismo monto en otra alternativa.")
    if not resultado["plan"].empty:
        plan = resultado["plan"]
        with st.expander(f"Plan de compra · {int((plan['lotes'] > 0).sum())} bono(s)", expanded=True):
            vista = pd.DataFrame({
                "Bono": plan["bono"], "CUSIP": plan["cusip"], "Nominal": plan["nominalComprado"].map(formatearMoneda),
                "Costo aprox.": plan["costo"].map(formatearMoneda), "Rend. esperado": plan["rendimientoEsperado"].map(lambda v: formatearPorcentaje(v, 2)),
                "Veredicto al vencer": plan["veredicto"], "Precio ref.": plan["precio"].round(2), "TIR": plan["tir"].map(lambda v: formatearPorcentaje(v, 2)),
                "Vence": plan["vencimiento"].dt.strftime("%d/%m/%Y"),
            })
            tablaHtml(vista)
            st.caption("Precio del último reporte del fondo (el de compra será el del mercado). Lotes: USD 100 nominal en el "
                       "Tesoro (TreasuryDirect) y USD 1 000 en el resto, vía un bróker.")


# ---------------------------------------------------------------------------
# Paso 4: asignacion y plan
# ---------------------------------------------------------------------------
def pasoAsignacionYPlan(datos, perfil, asignacion, plan, capital, coherencia, fondo, resumenFondos, conclusion=None, numero=4):
    encabezadoPaso(numero, "Tu plan")
    columnas = st.columns(2)
    with columnas[0]:
        for fila in asignacion["filas"]:
            nombre = fila["detalle"] + (f" · {fila['ticker']}" if fila["clase"] == "Renta fija" and fila["ticker"] and fila["cusip"] else "")
            if fila["veredicto"] == "No recomendable":
                nombre = "⚠ " + nombre
            if capital:
                nombre += f" · {formatearMoneda(capital * fila['peso'])}"
            st.markdown(barraAsignacion(nombre, fila["peso"], COLOR_CLASE.get(fila["clase"])), unsafe_allow_html=True)
        st.caption(asignacion["nota"])
    with columnas[1]:
        pasos = construirPlanAccion(datos["senal"], datos["ticker"], datos["riesgo"], perfil, resumenFondos, asignacion,
                                    plan, capital, coherencia, fondo, conclusion)
        tablaHtml(pd.DataFrame(pasos)[["prioridad", "accion", "plazo"]].rename(
            columns={"prioridad": "#", "accion": "Acción", "plazo": "Plazo"}))


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


def dibujarResumen(datos, perfil, fondo, modo, seleccion, tablaFondos, asignacion, proyeccion, coherencia, cartera=None,
                   conclusion=None):
    """
    Las primeras tarjetas del Prescriptivo, coherentes entre si:
    1) ¿Invertir o no? (conclusion)  2) en que (tu renta fija)  3) cuanto rinde  4) cuanto ganarias.
    Debajo, un solo mensaje que explica la conclusion y si tu eleccion la sigue o no.
    """
    senal = datos["senal"]
    conclusion = conclusion or conclusionParaDatos(datos, perfil)
    filaFondo = tablaFondos.set_index("ticker").loc[fondo] if fondo and not tablaFondos.empty else None
    if modo == MODO_BONOS and not seleccion.empty:
        rentaFija = f"{len(seleccion)} bono(s)"
        notaRf = f"de {nombreFondo(fondo)} · {coherencia['emisores']} empresa(s)"
        rendimiento = coherencia["rendimientoEsperado"]
    elif fondo and modo != MODO_LIQUIDEZ:
        rentaFija = "Fondo completo"
        notaRf = f"{nombreFondo(fondo)} · {filaFondo['veredicto']}" + (" · aún sin bonos marcados" if modo == MODO_BONOS else "")
        rendimiento = filaFondo["rendimientoEsperado"]
    else:
        rentaFija, notaRf, rendimiento = "Liquidez", "Letras del Tesoro / mercado monetario", datos["tasaLibre"]
    filaTarjetas([
        tarjetaConclusion(datos, conclusion),
        {"etiqueta": "Tu renta fija", "valor": rentaFija, "nota": notaRf},
        {"etiqueta": "Rendimiento esperado de tu renta fija", "valor": formatearPorcentaje(rendimiento, 2),
         "nota": f"Liquidez: {formatearPorcentaje(datos['tasaLibre'], 2)} anual",
         "tono": "positivo" if not esNulo(rendimiento) and rendimiento > datos["tasaLibre"] else "neutro"},
        tarjetaGanancia(proyeccion, cartera),
    ])

    # Un solo mensaje: la conclusion y si lo que elegiste abajo la sigue
    invierteEnElFondo = fondo == datos["ticker"] and modo != MODO_LIQUIDEZ
    enLiquidez = modo == MODO_LIQUIDEZ or not fondo
    eleccion = ("liquidez" if enLiquidez else (f"{len(seleccion)} bono(s) de {fondo}" if modo == MODO_BONOS and not seleccion.empty
                                                else f"el fondo {nombreFondo(fondo)} completo"))
    if conclusion.get("sobre") == "bonos":
        aviso = (f"{conclusion['como']}" + (f" El fondo completo es «{str(conclusion['veredictoFondo']).lower()}» porque su precio "
                 "sube y baja con las tasas y nunca vence; un bono que mantienes hasta su vencimiento sí te devuelve lo pactado."
                 if conclusion.get("veredictoFondo") in ("No recomendable", "Aceptable") else ""))
        {"verde": st.success, "ambar": st.warning}.get(conclusion["tono"], st.error)(aviso)
    elif conclusion["veredicto"] is not None and not conclusion["invertir"] and invierteEnElFondo:
        st.error(f"**La conclusión es «{conclusion['decision']}» pero elegiste invertir en {eleccion}.** {conclusion['como']} "
                 "Cámbialo en el paso 1 si quieres seguir la recomendación.")
    elif conclusion["veredicto"] is not None and conclusion["invertir"] and enLiquidez and fondo == datos["ticker"]:
        st.info(f"**La conclusión es «{conclusion['decision']}», pero elegiste mantener tu renta fija en liquidez.** "
                f"{conclusion['como']} Puedes cambiarlo en el paso 1.")
    elif fondo != datos["ticker"]:
        (st.success if conclusion["invertir"] else st.warning)(f"{conclusion['como']} Tu renta fija: {eleccion}.")
    else:
        (st.success if conclusion["invertir"] else st.warning)(f"{conclusion['como']} Tu elección: {eleccion}.")
    if modo == MODO_BONOS and not seleccion.empty and coherencia["estado"] == "riesgo":
        st.error(coherencia["mensaje"])
    alerta = evaluarAlertaPerfil(datos["riesgo"], senal, perfil, datos.get("clasificadorRiesgo"))
    if alerta:
        (st.warning if alerta[0] == "ambar" else st.info)(alerta[1])

    porqueFondo = (f"el fondo es **{conclusion['veredicto'].lower()}** para tu perfil"
                   + (f" ({filaFondo['motivo'].rstrip('.')})" if filaFondo is not None and fondo == datos["ticker"] else "")
                   if conclusion["veredicto"] else "es un fondo fuera del ranking de bonos de tu perfil")
    razones = "; ".join(r.rstrip(".") for r in conclusion["razonesMomento"]) or "sin señales fuertes a favor ni en contra"
    if conclusion.get("sobre") == "bonos":
        porqueFondo = (f"tus {coherencia['bonos']} bono(s) rinden {formatearPorcentaje(coherencia['rendimientoEsperado'], 2)} al año "
                       f"al vencimiento, calidad más baja {coherencia['calidadMinima']}; el fondo completo es "
                       f"**{str(conclusion.get('veredictoFondo') or 'sin ranking').lower()}**")
    st.caption(f"**Por qué:** {porqueFondo}; momento **{conclusion['momento'].lower()}** ({razones}). "
               f"Plazo sugerido: {calcularHorizonteOptimo(datos['metricas'].get('volatilidadAnual'), perfil)}.")


# ---------------------------------------------------------------------------
# Detalles
# ---------------------------------------------------------------------------
def dibujarFactores(datos):
    senal = datos["senal"]
    tabla = pd.DataFrame(senal["factores"])
    tabla["Puntos"] = tabla.apply(lambda f: f"{f['puntos']:+.1f}" if f["activo"] else "no participa", axis=1)
    tablaHtml(tabla[["factor", "valor", "Puntos", "nota", "regla"]].rename(
        columns={"factor": "Factor", "valor": "Valor", "nota": "Nota", "regla": "Regla"}))
    st.caption(f"Puntaje = suma de los puntos = **{senal['puntaje']:+.1f}** de un máximo de ±{senal.get('puntajeMaximo', 0):.1f} con los "
               f"{senal.get('factoresActivos', 0)} factores que participan (intensidad {senal.get('intensidad', 0):+.0%}). "
               f"COMPRAR (momento favorable) si llega a +{senal.get('umbralPuntos', 0):.1f}; REDUCIR (momento desfavorable) si llega a "
               f"−{senal.get('umbralPuntos', 0):.1f}; en medio MANTENER (neutral). El umbral es el 35% del máximo alcanzable, así no "
               "depende de cuántos factores tengan datos. La conclusión de arriba cruza este momento con el veredicto del ranking. "
               f"Retorno histórico anualizado de {datos['ticker']}: {formatearPorcentaje(datos['retornoEsperado'], 1, True)}.")


def dibujarBacktest(datos):
    tabla, resumen = datos.get("backtest", pd.DataFrame()), datos.get("resumenBacktest", {})
    if tabla is None or tabla.empty:
        st.info("Se necesita más historia para el backtest (al menos ~1.5 años). Prueba con el periodo de 10 años.")
        return
    st.plotly_chart(graficarBacktest(tabla), use_container_width=True, key="prescriptivo_plotly_chart_7")
    porAccion = resumen["porAccion"].reset_index().rename(columns={
        "accion": "Señal", "semanas": "Semanas", "retornoMedio": "Retorno medio posterior", "proporcionAlza": "% de veces que subió"})
    tablaHtml(formatearTablaPorcentajes(porAccion, ["Retorno medio posterior", "% de veces que subió"], 1))
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
    _, estado, _ = proveedorInfo
    if not proveedorListo(estado):
        st.caption("El asistente de IA no está disponible; este es el informe armado con las reglas de la app.")
        st.markdown(explicacionDeRespaldo(datos, perfil, decision.get("conclusion")))
        return
    seleccion = decision.get("seleccion")
    huella = "-".join(sorted(seleccion["clave"])) if seleccion is not None and not seleccion.empty else decision.get("fondo") or "liquidez"
    marca = f"{datos['fechaCorte']:%Y%m%d}" if datos.get("fechaCorte") is not None else "actual"
    clave = f"explicacion_{datos['ticker']}_{perfil}_{marca}_{abs(hash(huella))}"
    if st.button("Explicar mi decisión con IA", type="primary", key="botonInformeIa"):
        with st.spinner("La IA está redactando el informe…"):
            texto, usado, sospechosas = generarExplicacionLLM(construirContexto(datos, perfil, decision), perfil, proveedorInfo)
            st.session_state[clave] = {"texto": texto or explicacionDeRespaldo(datos, perfil, decision.get("conclusion")),
                                       "proveedor": usado if texto else None, "sospechosas": sospechosas}
    guardado = st.session_state.get(clave)
    if not guardado:
        st.caption("Un resumen en palabras de tu decisión, el fondo, los bonos que elegiste y cuánto podrías ganar.")
        return
    if guardado["sospechosas"]:
        st.warning("Revisa estas cifras: no coinciden con los datos del análisis: " + ", ".join(guardado["sospechosas"]))
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

    conclusion = conclusionParaDatos(datos, perfil)  # la misma que usan el Asesor IA y el informe
    fondo, modo = pasoElegirModo(datos, perfil, tablaFondos, resumenFondos, conclusion)
    st.divider()
    seleccion, _ = pasoElegirBonos(datos, fondo, perfil, modo)
    hayPasoBonos = modo == MODO_BONOS and fondo is not None
    if hayPasoBonos:
        st.divider()

    claseSenal = datos.get("claseFondo", "Renta variable")
    fondoAnalizado = datos["ticker"] if claseSenal == "Renta variable" else None
    asignacion = construirAsignacion(perfil, datos["senal"], tablaFondos, seleccion, fondo, fondoAnalizado,
                                     claseSenal=claseSenal, soloLiquidez=modo == MODO_LIQUIDEZ)
    coherencia = evaluarSeleccion(seleccion, perfil)
    if modo == MODO_BONOS and not seleccion.empty:  # se compran bonos, no el fondo: la conclusion es sobre ellos
        conclusion = conclusionSeleccion(conclusion, coherencia)
    resultado = pasoProyeccion(datos, perfil, fondo, modo, seleccion, tablaFondos, asignacion, numero=3 if hayPasoBonos else 2)
    st.divider()
    fondoPlan = fondo if modo != MODO_LIQUIDEZ else None
    pasoAsignacionYPlan(datos, perfil, asignacion, resultado["plan"], resultado["capital"], coherencia, fondoPlan,
                        resumenFondos if modo != MODO_LIQUIDEZ else dict(resumenFondos, invertir=False), conclusion,
                        numero=4 if hayPasoBonos else 3)

    with resumenSuperior:
        dibujarResumen(datos, perfil, fondo, modo, seleccion, tablaFondos, asignacion, resultado["proyeccion"], coherencia,
                       resultado.get("cartera"), conclusion)

    decision = {"fondo": fondoPlan, "modo": modo, "seleccion": seleccion, "asignacion": asignacion, "coherencia": coherencia,
                "proyeccion": resultado["proyeccion"], "proyeccionCartera": resultado.get("cartera"), "conclusion": conclusion}
    st.divider()
    with abrirPanel("Informe de tu decisión con IA"):
        dibujarExplicacionIa(datos, perfil, proveedorInfo, decision)
    st.markdown("##### Más detalle")
    with st.expander(f"Por qué el momento es {conclusion['momento'].lower()}"):
        dibujarFactores(datos)
        for nombre, regla in REGLAS_SENAL:
            st.markdown(f"- **{nombre}:** {regla}")
    with st.expander("Backtest: qué pasó después de cada señal"):
        dibujarBacktest(datos)
    with st.expander("Comparar perfiles"):
        tablaHtml(compararPerfiles(datos["senal"], datos["metricas"], datos["riesgo"], perfil, datos["rankingsPorPerfil"],
                                   datos.get("claseFondo", "Renta variable")),
                  destacar=lambda fila: str(fila.iloc[0]) == perfil)
        st.caption("El mismo fondo visto por cada perfil: cambian el plazo, la mezcla y los fondos de bonos.")
    if datos.get("fechaCorte") is not None:
        with st.expander("Validación retrospectiva: qué pasó después", expanded=True):
            dibujarValidacionRetrospectiva(datos)
    st.caption("Proyecto con fines académicos. Las recomendaciones salen de un modelo estadístico y no constituyen asesoría financiera.")
    return decision
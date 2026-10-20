"""
analisisBonos.py
Ranking de fondos de bonos por perfil y proyeccion de la ganancia esperada.

Ranking: cada bono del perfil recibe un puntaje de 0 a 100 con cinco
componentes (prima de rendimiento sobre la liquidez, Sharpe, volatilidad,
caida maxima y tendencia, en una ventana de 3 anios) y un veredicto:
Recomendable / Aceptable / No recomendable. Hay vetos explicitos (rinde menos
que la liquidez, volatilidad o caida fuera de la tolerancia del perfil,
tendencia bajista fuerte). Si ningun bono pasa, la recomendacion es NO
invertir en bonos de ese perfil por ahora y quedarse en liquidez.

Proyeccion: simulacion Monte Carlo con remuestreo por bloques de los
retornos MENSUALES reales del fondo, re-centrados en un retorno esperado
anclado al rendimiento actual del bono (el mejor estimador conocido del
retorno de un fondo de bonos a mediano plazo) menos la perdida esperada por
impagos. Asi la dispersion es la historica del propio bono y el centro es
su rendimiento de hoy, no el de un pasado con otras tasas.
"""

import numpy as np
import pandas as pd

from src.catalogoBonos import (
    PARAMETROS_PERFIL,
    PESOS_RANKING,
    UMBRAL_ACEPTABLE,
    UMBRAL_RECOMENDABLE,
    VENTANA_ANIOS_BONOS,
    bonosDelPerfil,
    todosLosTickersBonos,
)
from src.datosEstructurados import (
    calcularMaximaCaida,
    descargarHistorico,
    obtenerInfoFondo,
    retornoEnVentana,
    sharpeAnual,
)
from src.utilidades import esNulo, registrarEvento

DIAS_HABILES_ANIO = 252
VEREDICTOS = ("Recomendable", "Aceptable", "No recomendable", "Sin datos")


def descargarUniversoBonos(periodo="5y", usarCache=True, tickers=None):
    """Descarga historico y ficha de cada bono del catalogo. Devuelve {ticker: {historico, ficha}}."""
    universo = {}
    for ticker in tickers or todosLosTickersBonos():
        historico = descargarHistorico(ticker, periodo, usarCache)
        ficha = obtenerInfoFondo(ticker, usarCache)
        universo[ticker] = {"historico": historico, "ficha": ficha}
    registrarEvento(f"Universo de bonos: {sum(1 for v in universo.values() if not v['historico'].empty)} con datos.")
    return universo


def recortarUniverso(universo, fechaCorte):
    """Universo recortado a una fecha (para la evaluacion por semana)."""
    if fechaCorte is None or not universo:
        return universo
    fin = pd.Timestamp(fechaCorte).normalize() + pd.Timedelta(days=1)
    return {
        t: {"historico": d["historico"].loc[d["historico"].index < fin] if not d["historico"].empty else d["historico"],
            "ficha": d["ficha"]}
        for t, d in universo.items()
    }


def metricasBono(historico, ficha, tasaLibre, perdidaCredito=0.0, ventanaAnios=VENTANA_ANIOS_BONOS):
    """Metricas de un fondo de bonos en la ventana reciente (3 anios por defecto)."""
    m = {
        "observaciones": 0, "retornoAnual": np.nan, "volatilidad": np.nan, "sharpe": np.nan,
        "caidaMaxima": np.nan, "retorno6m": np.nan, "retorno12m": np.nan, "sobreMedia200": None,
        "rendimiento": np.nan, "fuenteRendimiento": "Sin dato", "rendimientoEsperado": np.nan,
        "prima": np.nan, "gasto": None, "valorActual": np.nan,
    }
    if historico is None or historico.empty:
        return m
    nav = historico["nav"].dropna()
    nav = nav.loc[nav.index >= nav.index[-1] - pd.DateOffset(years=ventanaAnios)]
    retornos = nav.pct_change().dropna()
    m["observaciones"] = int(len(retornos))
    m["valorActual"] = float(nav.iloc[-1])
    if len(retornos) >= 60:
        anios = len(retornos) / DIAS_HABILES_ANIO
        m["retornoAnual"] = float((nav.iloc[-1] / nav.iloc[0]) ** (1 / anios) - 1)
        m["volatilidad"] = float(retornos.std() * np.sqrt(DIAS_HABILES_ANIO))
        m["sharpe"] = sharpeAnual(retornos, tasaLibre)
        m["caidaMaxima"] = calcularMaximaCaida(nav)
    m["retorno6m"] = retornoEnVentana(nav, 126)
    m["retorno12m"] = retornoEnVentana(nav, DIAS_HABILES_ANIO)
    if len(nav) >= 200:
        m["sobreMedia200"] = bool(nav.iloc[-1] > nav.tail(200).mean())

    ficha = ficha or {}
    m["gasto"] = ficha.get("gastoAnual")
    rendimiento = ficha.get("rendimientoDistribucion")
    if not esNulo(rendimiento) and 0 < float(rendimiento) < 0.25:
        m["rendimiento"] = float(rendimiento)
        m["fuenteRendimiento"] = "Rendimiento por distribuciones (Yahoo)"
    elif not esNulo(m["retorno12m"]):
        m["rendimiento"] = float(m["retorno12m"])
        m["fuenteRendimiento"] = "Retorno de 12 meses (sin dato de rendimiento)"
    if not esNulo(m["rendimiento"]):
        m["rendimientoEsperado"] = m["rendimiento"] - float(perdidaCredito or 0)
        m["prima"] = m["rendimientoEsperado"] - tasaLibre
    return m


def _escala(valor, minimo, maximo):
    """Lleva un valor al rango 0-1 de forma lineal (con limites)."""
    if esNulo(valor):
        return np.nan
    return float(np.clip((valor - minimo) / (maximo - minimo), 0, 1))


def puntuarBono(metricas, perfil):
    """
    Puntaje 0-100, componentes y veredicto de un bono para un perfil.
    Devuelve (puntaje, componentes, veredicto, motivos).
    """
    p = PARAMETROS_PERFIL[perfil]
    if metricas["observaciones"] < 200 or esNulo(metricas["prima"]):
        return np.nan, {}, "Sin datos", ["Menos de un año de historia o sin rendimiento conocido."]

    tendenciaPrecio = _escala(metricas["retorno6m"], -0.03, 0.03)
    componentes = {
        "prima": _escala(metricas["prima"], -0.02, 0.03),
        "sharpe": _escala(metricas["sharpe"], -0.5, 1.0),
        "volatilidad": 1 - _escala(metricas["volatilidad"], 0, 2 * p["volatilidadMaxima"]),
        "caida": 1 - _escala(abs(metricas["caidaMaxima"]), 0, 2 * abs(p["caidaTolerada"])),
        "tendencia": 0.5 * (0.5 if esNulo(tendenciaPrecio) else tendenciaPrecio)
        + 0.5 * (1.0 if metricas["sobreMedia200"] else 0.0),
    }
    componentes = {k: (0.5 if esNulo(v) else v) for k, v in componentes.items()}
    puntaje = 100 * sum(componentes[k] * PESOS_RANKING[k] for k in PESOS_RANKING)

    motivos, vetos = [], []
    if metricas["prima"] < p["primaMinima"]:
        vetos.append(
            f"Rinde {metricas['prima']:+.2%} frente a la liquidez (mínimo para el perfil: {p['primaMinima']:+.2%})."
        )
    if not esNulo(metricas["volatilidad"]) and metricas["volatilidad"] > 1.5 * p["volatilidadMaxima"]:
        vetos.append(f"Volatilidad {metricas['volatilidad']:.1%}, alta para un perfil {perfil} (máx. {p['volatilidadMaxima']:.0%}).")
    if not esNulo(metricas["caidaMaxima"]) and metricas["caidaMaxima"] < p["caidaTolerada"]:
        vetos.append(f"Caída máxima {metricas['caidaMaxima']:.1%}, peor que la tolerada ({p['caidaTolerada']:.0%}).")
    if metricas["sobreMedia200"] is False and not esNulo(metricas["retorno6m"]) and metricas["retorno6m"] < -0.03:
        vetos.append(f"Tendencia bajista: {metricas['retorno6m']:+.1%} en 6 meses y bajo su media de 200 días.")

    if vetos:
        veredicto = "No recomendable"
        motivos = vetos
    elif puntaje >= UMBRAL_RECOMENDABLE:
        veredicto = "Recomendable"
        motivos = [f"Prima de {metricas['prima']:+.2%} sobre la liquidez con riesgo dentro de la tolerancia."]
    elif puntaje >= UMBRAL_ACEPTABLE:
        veredicto = "Aceptable"
        motivos = ["Cumple las tolerancias del perfil, pero su relación rendimiento/riesgo es intermedia."]
    else:
        veredicto = "No recomendable"
        motivos = ["Puntaje bajo: poca prima o mal desempeño reciente frente a su riesgo."]
    return round(float(puntaje), 1), {k: round(v * 100, 0) for k, v in componentes.items()}, veredicto, motivos


def rankingBonos(universo, perfil, tasaLibre):
    """
    Ranking de los bonos del perfil (mejor primero) y resumen general.
    Devuelve (tabla, resumen). tabla tiene una fila por bono.
    """
    filas = []
    for bono in bonosDelPerfil(perfil):
        datos = (universo or {}).get(bono["ticker"], {})
        m = metricasBono(datos.get("historico"), datos.get("ficha"), tasaLibre, bono["perdidaCreditoEsperada"])
        puntaje, componentes, veredicto, motivos = puntuarBono(m, perfil)
        filas.append(
            {
                "ticker": bono["ticker"], "nombre": bono["nombre"], "segmento": bono["segmento"],
                "fondoMutuo": bono["fondoMutuo"] or "—", "puntaje": puntaje, "veredicto": veredicto,
                "motivo": " ".join(motivos), "rendimiento": m["rendimiento"],
                "rendimientoEsperado": m["rendimientoEsperado"], "prima": m["prima"],
                "fuenteRendimiento": m["fuenteRendimiento"], "retornoAnual3a": m["retornoAnual"],
                "volatilidad": m["volatilidad"], "sharpe": m["sharpe"], "caidaMaxima": m["caidaMaxima"],
                "retorno6m": m["retorno6m"], "sobreMedia200": m["sobreMedia200"], "gasto": m["gasto"],
                "perdidaCredito": bono["perdidaCreditoEsperada"], "componentes": componentes,
            }
        )
    tabla = pd.DataFrame(filas)
    if tabla.empty:
        return tabla, {"recomendacion": "Sin bonos en el catálogo para este perfil.", "invertir": False}

    orden = {"Recomendable": 0, "Aceptable": 1, "No recomendable": 2, "Sin datos": 3}
    tabla["ordenVeredicto"] = tabla["veredicto"].map(orden)
    tabla = tabla.sort_values(["ordenVeredicto", "puntaje"], ascending=[True, False], na_position="last")
    tabla = tabla.drop(columns="ordenVeredicto").reset_index(drop=True)
    tabla.insert(0, "puesto", range(1, len(tabla) + 1))

    recomendables = tabla.loc[tabla["veredicto"] == "Recomendable"]
    aceptables = tabla.loc[tabla["veredicto"] == "Aceptable"]
    conDatos = tabla.loc[tabla["veredicto"] != "Sin datos"]
    resumen = {"perfil": perfil, "tasaLibre": tasaLibre, "recomendables": len(recomendables),
               "aceptables": len(aceptables), "evaluados": len(conDatos)}
    if conDatos.empty:
        resumen.update(invertir=None, tono="azul",
                       recomendacion="No hay datos de bonos para evaluar. Presiona «Actualizar datos».")
    elif len(recomendables):
        mejor = recomendables.iloc[0]
        resumen.update(invertir=True, tono="verde", mejor=mejor["ticker"],
                       recomendacion=(f"Sí es recomendable invertir en bonos de perfil {perfil}. La mejor opción es "
                                      f"{mejor['ticker']} ({mejor['segmento']}), con rendimiento esperado de "
                                      f"{mejor['rendimientoEsperado']:.2%} anual frente a {tasaLibre:.2%} de la liquidez."))
    elif len(aceptables):
        mejor = aceptables.iloc[0]
        resumen.update(invertir=True, tono="ambar", mejor=mejor["ticker"],
                       recomendacion=(f"Se puede invertir con cautela: ningún bono destaca, pero {mejor['ticker']} "
                                      f"({mejor['segmento']}) cumple las tolerancias del perfil {perfil}. "
                                      "Conviene entrar de forma escalonada."))
    else:
        resumen.update(invertir=False, tono="roja", mejor=None,
                       recomendacion=(f"No es recomendable invertir ahora en bonos de perfil {perfil}: ninguno compensa "
                                      f"su riesgo frente a la liquidez, que rinde {tasaLibre:.2%} (letras del Tesoro o "
                                      "un fondo de mercado monetario)."))
    return tabla, resumen


# ---------------------------------------------------------------------------
# Proyeccion de la ganancia
# ---------------------------------------------------------------------------
def retornosMensuales(historico):
    """Retornos mensuales (fin de mes) del NAV ajustado."""
    if historico is None or historico.empty:
        return pd.Series(dtype=float)
    nav = historico["nav"].dropna()
    try:
        mensual = nav.resample("ME").last()
    except ValueError:  # pandas < 2.2 usa 'M'
        mensual = nav.resample("M").last()
    return mensual.pct_change().dropna()


def proyectarInversion(historico, rendimientoEsperadoAnual, montoInicial, aporteMensual, meses,
                       simulaciones=3000, bloque=6, semilla=7, tasaLiquidez=None, volatilidadRespaldo=None,
                       centrarMediana=False):
    """
    Simula el valor de una inversion mes a mes.

    - Retornos: remuestreo por bloques de 'bloque' meses de los retornos
      mensuales historicos, re-centrados en el retorno esperado mensual.
    - Aportes: al inicio de cada mes (el primero es el monto inicial).
    - Sin historia suficiente: normal con volatilidadRespaldo (anual) si se da.
    - centrarMediana: el retorno esperado se interpreta como el del escenario
      CENTRAL (mediana), sumando la mitad de la varianza mensual; si no, con
      mucha volatilidad la mediana queda por debajo del retorno pedido.
    Devuelve dict con 'trayectoria' (percentiles por mes), 'resumen', 'metodo'
    y 'valores' (valor final de cada escenario, para combinar con otras partes).
    """
    meses = int(max(meses, 1))
    rm = retornosMensuales(historico)
    mu = (1 + float(rendimientoEsperadoAnual)) ** (1 / 12) - 1
    generador = np.random.default_rng(semilla)

    if len(rm) >= 24:
        desvios = (rm - rm.mean()).to_numpy()
        n = len(desvios)
        bloques = int(np.ceil(meses / bloque))
        inicios = generador.integers(0, n, size=(simulaciones, bloques))
        indices = (inicios[:, :, None] + np.arange(bloque)[None, None, :]) % n
        muestras = desvios[indices].reshape(simulaciones, -1)[:, :meses]
        metodo = f"Remuestreo por bloques de {bloque} meses de {n} retornos mensuales históricos"
    else:
        sigma = float(rm.std()) if len(rm) > 3 else (volatilidadRespaldo / np.sqrt(12) if volatilidadRespaldo else 0.01)
        muestras = generador.normal(0, sigma, size=(simulaciones, meses))
        metodo = "Distribución normal (historia mensual menor a 24 meses)"
    if centrarMediana:
        mu += float(np.var(muestras)) / 2
    retornos = mu + muestras

    aportes = np.full(meses, float(aporteMensual))
    aportes[0] += float(montoInicial)
    valor = np.zeros(simulaciones)
    trayectoria = np.zeros((simulaciones, meses))
    for mes in range(meses):
        valor = (valor + aportes[mes]) * (1 + retornos[:, mes])
        trayectoria[:, mes] = valor

    aportado = np.cumsum(aportes)
    percentiles = np.percentile(trayectoria, [5, 10, 25, 50, 75, 90, 95], axis=0)
    tabla = pd.DataFrame(
        {
            "mes": np.arange(1, meses + 1), "aportado": aportado,
            "p5": percentiles[0], "p10": percentiles[1], "p25": percentiles[2], "p50": percentiles[3],
            "p75": percentiles[4], "p90": percentiles[5], "p95": percentiles[6],
            "media": trayectoria.mean(axis=0),
        }
    )
    if tasaLiquidez is not None:
        muL = (1 + float(tasaLiquidez)) ** (1 / 12) - 1
        liquidez, acumulado = [], 0.0
        for mes in range(meses):
            acumulado = (acumulado + aportes[mes]) * (1 + muL)
            liquidez.append(acumulado)
        tabla["liquidez"] = liquidez

    final = trayectoria[:, -1]
    totalAportado = float(aportado[-1])
    resumen = {
        "totalAportado": totalAportado,
        "valorMediano": float(np.median(final)),
        "valorPesimista": float(np.percentile(final, 10)),
        "valorOptimista": float(np.percentile(final, 90)),
        "valorMedio": float(final.mean()),
        "gananciaMediana": float(np.median(final) - totalAportado),
        "gananciaPesimista": float(np.percentile(final, 10) - totalAportado),
        "gananciaOptimista": float(np.percentile(final, 90) - totalAportado),
        "probabilidadPerdida": float(np.mean(final < totalAportado)),
        "rendimientoEsperadoAnual": float(rendimientoEsperadoAnual),
        "valorLiquidez": float(tabla["liquidez"].iloc[-1]) if "liquidez" in tabla else np.nan,
        "probabilidadSuperarLiquidez": float(np.mean(final > tabla["liquidez"].iloc[-1])) if "liquidez" in tabla else np.nan,
        "meses": meses,
    }
    return {"trayectoria": tabla, "resumen": resumen, "metodo": metodo, "valores": final}


def rendimientoAnualizado(valorFinal, montoInicial, meses):
    """Rendimiento anual compuesto equivalente (fraccion); NaN si no hay monto."""
    if not montoInicial or montoInicial <= 0 or valorFinal is None or meses <= 0:
        return np.nan
    return float((valorFinal / montoInicial) ** (12 / meses) - 1)


def proyectarCartera(componentes, meses):
    """
    Proyeccion de la CARTERA COMPLETA sumando, escenario por escenario, el
    valor final de cada parte (acciones, renta fija, liquidez).

    componentes: lista de dicts {clase, nombre, monto, valores} donde 'valores'
    es el arreglo de valores finales simulados de esa parte (o un numero, para
    la liquidez). Las simulaciones de cada parte son independientes entre si
    (se supone correlacion baja entre acciones y bonos de calidad).
    Devuelve dict con 'resumen' (como proyectarInversion) y 'partes'.
    """
    partes = [c for c in componentes if c.get("monto", 0) > 0]
    if not partes:
        return None
    largo = max(len(np.atleast_1d(c["valores"])) for c in partes)
    total = np.zeros(largo)
    filas = []
    for c in partes:
        valores = np.atleast_1d(np.asarray(c["valores"], dtype=float))
        valores = np.resize(valores, largo) if len(valores) != largo else valores
        total += valores
        mediana = float(np.median(valores))
        filas.append({"clase": c["clase"], "nombre": c["nombre"], "monto": float(c["monto"]),
                      "valorMediano": mediana, "gananciaMediana": mediana - float(c["monto"]),
                      "rendimientoAnual": rendimientoAnualizado(mediana, float(c["monto"]), meses)})
    invertido = float(sum(c["monto"] for c in partes))
    mediano = float(np.median(total))
    resumen = {
        "montoTotal": invertido, "totalAportado": invertido, "meses": int(meses),
        "valorMediano": mediano, "valorPesimista": float(np.percentile(total, 10)),
        "valorOptimista": float(np.percentile(total, 90)),
        "gananciaMediana": mediano - invertido, "gananciaPesimista": float(np.percentile(total, 10)) - invertido,
        "gananciaOptimista": float(np.percentile(total, 90)) - invertido,
        "probabilidadPerdida": float(np.mean(total < invertido)),
        "rendimientoAnual": rendimientoAnualizado(mediano, invertido, meses),
    }
    return {"resumen": resumen, "partes": pd.DataFrame(filas), "valores": total}


def compararProyecciones(universo, tablaRanking, montoInicial, aporteMensual, meses, tasaLiquidez):
    """Proyeccion resumida de cada bono del ranking, para compararlos en una tabla."""
    filas = []
    for _, fila in tablaRanking.iterrows():
        if esNulo(fila["rendimientoEsperado"]):
            continue
        historico = (universo or {}).get(fila["ticker"], {}).get("historico")
        proyeccion = proyectarInversion(historico, fila["rendimientoEsperado"], montoInicial, aporteMensual,
                                        meses, simulaciones=1500, tasaLiquidez=tasaLiquidez)
        r = proyeccion["resumen"]
        filas.append(
            {
                "Fondo": fila["ticker"], "Veredicto": fila["veredicto"],
                "Rend. esperado anual": r["rendimientoEsperadoAnual"],
                "Ganancia mediana": r["gananciaMediana"], "Escenario pesimista (P10)": r["gananciaPesimista"],
                "Escenario optimista (P90)": r["gananciaOptimista"], "Prob. de pérdida": r["probabilidadPerdida"],
                "Prob. de superar la liquidez": r["probabilidadSuperarLiquidez"],
            }
        )
    return pd.DataFrame(filas)

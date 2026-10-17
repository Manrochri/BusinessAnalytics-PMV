"""
bonosIndividuales.py
Evaluacion de cada bono (y de cada emisor) dentro de un fondo de bonos.

Por cada bono de la cartera N-PORT se calcula:
  - Precio (valor de mercado / nominal) y rendimiento al vencimiento (TIR)
  - Duracion modificada (sensibilidad del precio a las tasas)
  - Diferencial sobre el Tesoro del mismo plazo (curva ^IRX, ^FVX, ^TNX, ^TYX)
  - Calidad crediticia IMPLICITA por ese diferencial y perdida esperada
  - Rendimiento esperado = TIR - perdida esperada por impago
  - Puntaje 0-100 y veredicto segun el perfil, con vetos explicitos

Tambien: agregacion por emisor (empresa o entidad), plan de compra con
lotes minimos y proyeccion Monte Carlo de comprar y mantener los bonos
elegidos (cupones, impagos y cambios de tasas historicos).
"""

import numpy as np
import pandas as pd

from src.catalogoBonos import (
    CALIDAD_MUNICIPAL,
    CORTES_DIFERENCIAL,
    NIVELES_CALIDAD,
    NOMINAL_MINIMO,
    PARAMETROS_PERFIL,
    PERDIDA_EN_IMPAGO,
    PROBABILIDAD_IMPAGO_ANUAL,
    UMBRAL_ACEPTABLE,
    UMBRAL_RECOMENDABLE,
    VIDA_ESTIMADA_MBS,
)
from src.utilidades import esNulo

# Plazos (anios) de las tasas del Tesoro publicadas por Yahoo Finance (en %)
TICKERS_CURVA = {"^IRX": 0.25, "^FVX": 5.0, "^TNX": 10.0, "^TYX": 30.0}
RECUPERACION = 1 - PERDIDA_EN_IMPAGO


# ---------------------------------------------------------------------------
# Curva del Tesoro
# ---------------------------------------------------------------------------
def _nivelTasa(valor):
    """Yahoo publica las tasas en %; algunos historicos antiguos de ^TNX venian x10."""
    valor = float(valor)
    return valor / 1000 if valor > 25 else valor / 100


def construirCurva(seriesCurva):
    """{plazoAnios: tasa} con el ultimo dato de cada serie (fraccion)."""
    curva = {}
    for ticker, plazo in TICKERS_CURVA.items():
        serie = (seriesCurva or {}).get(ticker)
        if serie is not None and not serie.empty:
            curva[plazo] = _nivelTasa(serie["nav"].dropna().iloc[-1])
    return dict(sorted(curva.items()))


def tasaTesoro(curva, plazos):
    """Tasa del Tesoro interpolada linealmente para cada plazo (extremos planos)."""
    if not curva:
        return np.full(np.shape(plazos), np.nan)
    x, y = np.array(list(curva.keys())), np.array(list(curva.values()))
    return np.interp(np.asarray(plazos, dtype=float), x, y)


def cambiosHistoricosTasas(seriesCurva, meses):
    """
    Cambios historicos de cada tasa en ventanas de 'meses' (en fraccion), para
    simular a que tasa se podria vender un bono antes de su vencimiento.
    Devuelve (plazos, matriz n_ventanas x n_plazos) con fechas comunes.
    """
    columnas = {}
    for ticker, plazo in TICKERS_CURVA.items():
        serie = (seriesCurva or {}).get(ticker)
        if serie is not None and not serie.empty:
            columnas[plazo] = serie["nav"].dropna().map(_nivelTasa)
    if not columnas:
        return np.array([]), np.empty((0, 0))
    tabla = pd.DataFrame(columnas).dropna().sort_index(axis=1)
    pasos = int(round(meses * 21))
    if len(tabla) < 300:
        return np.array(tabla.columns, dtype=float), np.zeros((1, tabla.shape[1]))
    # Si la historia no alcanza para ventanas del largo pedido (p. ej. 10 anios con
    # 10 anios de datos), se usa la ventana mas larga posible y se escala por la
    # raiz del tiempo (como un paseo aleatorio), dejando al menos 250 ventanas.
    pasosEfectivos = min(pasos, len(tabla) - 250)
    cambios = (tabla.shift(-pasosEfectivos) - tabla).dropna().to_numpy()
    if pasosEfectivos < pasos:
        cambios = cambios * np.sqrt(pasos / pasosEfectivos)
    return np.array(tabla.columns, dtype=float), cambios


# ---------------------------------------------------------------------------
# Matematica de bonos (vectorizada)
# ---------------------------------------------------------------------------
def precioDesdeTir(cupon, plazo, tir):
    """
    Precio por 100 de nominal con cupones semestrales: el ultimo pago es al
    vencimiento y los anteriores cada 0.5 anios hacia atras.
    """
    cupon, plazo, tir = (np.asarray(v, dtype=float) for v in (cupon, plazo, tir))
    pagos = np.ceil(plazo * 2 - 1e-9).clip(min=1)
    v = 1 / (1 + tir / 2)
    descuentoFinal = v ** (2 * plazo)
    with np.errstate(divide="ignore", invalid="ignore"):
        suma = np.where(np.abs(v - 1) < 1e-12, pagos, (v ** (-pagos) - 1) / (1 / v - 1))
    return cupon * 100 / 2 * descuentoFinal * suma + 100 * descuentoFinal


def tirDesdePrecio(precio, cupon, plazo, iteraciones=70):
    """TIR por biseccion (vectorizada) entre -5% y 100%."""
    precio, cupon, plazo = (np.asarray(v, dtype=float) for v in (precio, cupon, plazo))
    bajo, alto = np.full(precio.shape, -0.05), np.full(precio.shape, 1.0)
    for _ in range(iteraciones):
        medio = (bajo + alto) / 2
        caro = precioDesdeTir(cupon, plazo, medio) > precio  # precio teorico mayor -> la TIR debe subir
        bajo = np.where(caro, medio, bajo)
        alto = np.where(caro, alto, medio)
    return (bajo + alto) / 2


def duracionModificada(cupon, plazo, tir, paso=0.0001):
    """Duracion modificada numerica: -dP/dy / P."""
    arriba = precioDesdeTir(cupon, plazo, np.asarray(tir) + paso)
    abajo = precioDesdeTir(cupon, plazo, np.asarray(tir) - paso)
    centro = precioDesdeTir(cupon, plazo, tir)
    return (abajo - arriba) / (2 * paso * centro)


def calidadPorDiferencial(diferencial):
    """Nivel de calidad inferido del diferencial sobre el Tesoro (fraccion)."""
    if esNulo(diferencial):
        return None
    for tope, nivel in CORTES_DIFERENCIAL:
        if diferencial < tope:
            return nivel
    return "CCC o menor"


def _escala(valor, minimo, maximo):
    return np.clip((np.asarray(valor, dtype=float) - minimo) / (maximo - minimo), 0, 1)


# ---------------------------------------------------------------------------
# Evaluacion bono por bono
# ---------------------------------------------------------------------------
def evaluarBonos(cartera, perfil, curva, tasaLibre, fechaValoracion=None, vencimientoMinimo=None):
    """
    Evalua cada bono de la cartera para el perfil. Devuelve una tabla
    ordenada (mejor primero) con metricas, puntaje, veredicto y motivo.
    fechaValoracion = fecha de los precios (la de las posiciones del reporte);
    se descartan las posiciones que no son bonos y los bonos que ya vencieron.
    """
    if cartera is None or cartera.empty:
        return pd.DataFrame()
    p = PARAMETROS_PERFIL[perfil]
    fecha = pd.Timestamp(fechaValoracion or pd.Timestamp.today()).normalize()
    # Solo bonos que todavia se pueden comprar: vencen despues de hoy (y de la fecha del reporte)
    minimo = max(fecha, pd.Timestamp(vencimientoMinimo or pd.Timestamp.today()).normalize())
    t = cartera.loc[cartera["esDeuda"] & cartera["vencimiento"].notna() & (cartera["vencimiento"] > minimo)].copy()
    t = t.loc[(t["nominal"] > 0) & (t["valorUSD"] > 0)]
    if t.empty:
        return pd.DataFrame()

    t["cusip"] = t["cusip"].fillna("").astype(str)
    t["titulo"] = t["titulo"].fillna(t["emisor"]).astype(str)
    t["emisor"] = t["emisor"].fillna("Sin nombre").astype(str)
    texto = (t["titulo"] + " " + t["emisor"]).str.upper()
    t["esMbs"] = t["categoriaActivo"].fillna("").str.startswith("ABS-MBS")
    t["esTips"] = texto.str.contains("INFLATION|TIPS|TREASURY INFL", regex=True)
    t["esFlotante"] = t["tipoCupon"].fillna("").str.lower().eq("floating")
    t["esUsd"] = t["moneda"].fillna("USD").eq("USD") & t["unidades"].fillna("PA").eq("PA")
    t["plazo"] = (t["vencimiento"] - fecha).dt.days / 365.25
    t["plazoEfectivo"] = np.where(t["esMbs"], np.minimum(t["plazo"], VIDA_ESTIMADA_MBS), t["plazo"])
    t["cupon"] = t["cuponPct"].fillna(0.0) / 100
    t["precio"] = np.where(t["esUsd"], t["valorUSD"] / t["nominal"] * 100, np.nan)
    precioValido = t["precio"].between(1, 250)

    t["tir"] = np.where(precioValido, tirDesdePrecio(t["precio"].fillna(100), t["cupon"], t["plazoEfectivo"]), np.nan)
    fueraDeRango = (t["tir"] < -0.02) | (t["tir"] > 0.60)  # precio con intereses corridos o dato atipico
    t.loc[fueraDeRango, "tir"] = np.nan
    precioValido = precioValido & ~fueraDeRango
    t["duracion"] = np.where(precioValido, duracionModificada(t["cupon"], t["plazoEfectivo"], t["tir"].fillna(0.04)), np.nan)
    t.loc[t["esFlotante"], "duracion"] = 0.25  # el cupon se ajusta con las tasas
    t["tesoro"] = tasaTesoro(curva, t["plazoEfectivo"])
    # TIPS: el valor incluye la inflacion acumulada y la TIR calculada no es
    # comparable; se usa la tasa nominal del Tesoro del mismo plazo como aproximacion
    t.loc[t["esTips"], "tir"] = t.loc[t["esTips"], "tesoro"]
    t["diferencial"] = t["tir"] - t["tesoro"]

    tipo = t["tipoEmisor"].fillna("OTHER")
    calidad = t["diferencial"].map(calidadPorDiferencial)
    calidad = np.where(tipo.eq("UST"), "Tesoro EE.UU.", calidad)
    calidad = np.where(tipo.isin(["USGA", "USGSE"]) | t["esMbs"] & tipo.isin(["USGA", "USGSE"]), "Agencia EE.UU.", calidad)
    calidad = np.where(tipo.eq("MUN"), CALIDAD_MUNICIPAL, calidad)
    t["calidad"] = calidad
    t["nivelCalidad"] = t["calidad"].map({c: i for i, c in enumerate(NIVELES_CALIDAD)})
    t["probImpago"] = t["calidad"].map(PROBABILIDAD_IMPAGO_ANUAL)
    t["perdidaEsperada"] = t["probImpago"] * PERDIDA_EN_IMPAGO
    t["rendimientoEsperado"] = t["tir"] - t["perdidaEsperada"]
    t["prima"] = t["rendimientoEsperado"] - tasaLibre

    nivelMinimo = NIVELES_CALIDAD.index(p["calidadMinima"])
    puntaje = 100 * (
        0.45 * _escala(t["prima"], -0.02, 0.04)
        + 0.30 * (1 - t["nivelCalidad"].fillna(6) / 6)
        + 0.25 * (1 - _escala(t["duracion"], 0, 2 * p["duracionMaxima"]))
    )
    t["puntaje"] = np.round(puntaje, 1)

    veredictos, motivos = [], []
    for fila in t.itertuples():
        vetos = []
        if fila.enImpago or fila.interesesAtrasados:
            veredictos.append("No recomendable")
            motivos.append("En impago o con intereses atrasados según el último reporte del fondo.")
            continue
        if esNulo(fila.tir) or not fila.esUsd:
            veredictos.append("Sin datos")
            motivos.append("Sin precio en USD por nominal: no se puede calcular su rendimiento.")
            continue
        if fila.duracion > p["duracionMaxima"]:
            vetos.append(f"Duración {fila.duracion:.1f}: más sensible a las tasas de lo que tolera el perfil (máx. {p['duracionMaxima']:.1f}).")
        if not esNulo(fila.nivelCalidad) and fila.nivelCalidad > nivelMinimo:
            vetos.append(f"Calidad implícita {fila.calidad}, por debajo de la mínima del perfil ({p['calidadMinima']}).")
        if fila.prima < p["primaMinima"]:
            vetos.append(f"Rinde {fila.prima:+.2%} frente a la liquidez.")
        if vetos:
            veredictos.append("No recomendable")
            motivos.append(" ".join(vetos))
        elif fila.puntaje >= UMBRAL_RECOMENDABLE:
            veredictos.append("Recomendable")
            motivos.append(f"Rinde {fila.rendimientoEsperado:.2%} esperado ({fila.prima:+.2%} sobre la liquidez); calidad: {fila.calidad}")
        elif fila.puntaje >= UMBRAL_ACEPTABLE:
            veredictos.append("Aceptable")
            motivos.append("Dentro de los límites del perfil, con una relación rendimiento/riesgo intermedia.")
        else:
            veredictos.append("No recomendable")
            motivos.append("Puntaje bajo: poca prima para su riesgo.")
    t["veredicto"], t["motivo"] = veredictos, motivos

    notas = np.where(t["esTips"], "TIPS: rendimiento nominal aproximado. ", "")
    notas = notas + np.where(t["esMbs"], f"Hipotecario: vida estimada ≤ {VIDA_ESTIMADA_MBS:.0f} años. ", "")
    notas = notas + np.where(t["esFlotante"], "Cupón flotante. ", "")
    notas = notas + np.where(tipo.eq("MUN"), "Municipal: rendimiento exento de impuesto federal en EE.UU. ", "")
    t["nota"] = pd.Series(notas, index=t.index).str.strip()
    t["tipoEmisorTexto"] = tipo.map(lambda c: {
        "UST": "Tesoro de EE.UU.", "USGA": "Agencia de EE.UU.", "USGSE": "Agencia patrocinada (GSE)", "MUN": "Municipal",
        "CORP": "Corporativo", "NUSS": "Soberano extranjero"}.get(c, "Otro"))

    orden = {"Recomendable": 0, "Aceptable": 1, "No recomendable": 2, "Sin datos": 3}
    t = t.assign(_orden=t["veredicto"].map(orden)).sort_values(["_orden", "puntaje"], ascending=[True, False]).drop(columns="_orden")
    t["clave"] = np.where(t["cusip"].str.len() > 3, t["cusip"], t["titulo"].str[:30]) + "·" + t["vencimiento"].dt.strftime("%Y%m%d")
    t = t.drop_duplicates("clave").reset_index(drop=True)
    t.insert(0, "puesto", range(1, len(t) + 1))
    return t


def describirBono(fila):
    """Etiqueta corta de un bono: emisor, cupon y vencimiento."""
    return f"{str(fila['emisor'])[:38]} · {fila['cupon']:.3%} · vence {fila['vencimiento']:%m/%Y}"


def resumirEmisores(evaluados):
    """
    Una fila por emisor (empresa o entidad): cuantos bonos tiene en el fondo,
    su peso, rendimiento ponderado, calidad, plazo y su mejor bono.
    """
    if evaluados is None or evaluados.empty:
        return pd.DataFrame()
    t = evaluados.copy()
    t["claveEmisor"] = t["lei"].fillna("").astype(str)
    t.loc[t["claveEmisor"].str.len() < 5, "claveEmisor"] = t["emisor"].str.upper().str.strip()
    t["peso"] = t["pesoPct"].fillna(0)
    t["rendPond"] = t["rendimientoEsperado"] * t["peso"]
    t["plazoPond"] = t["plazo"] * t["peso"]
    filas = []
    for _, grupo in t.groupby("claveEmisor", sort=False):
        peso = grupo["peso"].sum()
        mejor = grupo.sort_values("puntaje", ascending=False).iloc[0]
        cuenta = grupo["veredicto"].value_counts()
        filas.append({
            "emisor": grupo["emisor"].mode().iloc[0], "tipo": grupo["tipoEmisorTexto"].iloc[0],
            "pais": grupo["pais"].mode().iloc[0] if grupo["pais"].notna().any() else "",
            "bonos": len(grupo), "pesoFondoPct": peso,
            "rendimientoEsperado": grupo["rendPond"].sum() / peso if peso else grupo["rendimientoEsperado"].mean(),
            "calidad": NIVELES_CALIDAD[int(grupo["nivelCalidad"].max())] if grupo["nivelCalidad"].notna().any() else "N/D",
            "plazoPromedio": grupo["plazoPond"].sum() / peso if peso else grupo["plazo"].mean(),
            "recomendables": int(cuenta.get("Recomendable", 0)), "aceptables": int(cuenta.get("Aceptable", 0)),
            "mejorBono": describirBono(mejor), "mejorPuntaje": mejor["puntaje"],
        })
    tabla = pd.DataFrame(filas)
    tabla["veredicto"] = np.where(tabla["recomendables"] > 0, "Recomendable",
                                  np.where(tabla["aceptables"] > 0, "Aceptable", "No recomendable"))
    orden = {"Recomendable": 0, "Aceptable": 1, "No recomendable": 2}
    return (tabla.assign(_o=tabla["veredicto"].map(orden))
            .sort_values(["_o", "mejorPuntaje", "pesoFondoPct"], ascending=[True, False, False])
            .drop(columns="_o").reset_index(drop=True))


def resumirEvaluacion(evaluados):
    """Cifras de resumen de un fondo evaluado bono por bono."""
    if evaluados is None or evaluados.empty:
        return {}
    cuenta = evaluados["veredicto"].value_counts()
    peso = evaluados["pesoPct"].fillna(0)
    return {
        "bonos": len(evaluados), "emisores": evaluados["emisor"].nunique(),
        "recomendables": int(cuenta.get("Recomendable", 0)), "aceptables": int(cuenta.get("Aceptable", 0)),
        "noRecomendables": int(cuenta.get("No recomendable", 0)), "sinDatos": int(cuenta.get("Sin datos", 0)),
        "pesoRecomendables": float(peso[evaluados["veredicto"] == "Recomendable"].sum()),
        "tirPonderada": float((evaluados["tir"] * peso).sum() / peso.sum()) if peso.sum() else np.nan,
    }


# ---------------------------------------------------------------------------
# Plan de compra y proyeccion
# ---------------------------------------------------------------------------
def planDeCompra(seleccion, monto):
    """
    Convierte el monto en lotes comprables de los bonos elegidos (nominal
    minimo: USD 100 en el Tesoro via TreasuryDirect, USD 1 000 en el resto).
    Reparte en partes iguales y luego usa el sobrante para completar lotes,
    bono por bono, mientras alcance. Lo que no completa un lote queda en liquidez.
    """
    if seleccion is None or seleccion.empty or monto <= 0:
        return pd.DataFrame(), float(monto)
    bonos = seleccion.reset_index(drop=True)
    lotes = np.where(bonos["calidad"].eq("Tesoro EE.UU."), NOMINAL_MINIMO["Tesoro EE.UU."], NOMINAL_MINIMO["otros"]).astype(float)
    costoLote = bonos["precio"].to_numpy(dtype=float) / 100 * lotes
    objetivo = monto / len(bonos)
    cantidad = np.floor(objetivo / costoLote).astype(int)
    restante = monto - float((cantidad * costoLote).sum())
    # Completar con el sobrante: primero los bonos que quedaron mas lejos de su objetivo
    while True:
        faltante = objetivo - cantidad * costoLote
        candidatos = [i for i in np.argsort(-faltante) if costoLote[i] <= restante + 1e-9]
        if not candidatos:
            break
        i = candidatos[0]
        cantidad[i] += 1
        restante -= costoLote[i]

    filas = []
    for i, bono in bonos.iterrows():
        filas.append({
            "clave": bono["clave"], "bono": describirBono(bono), "cusip": bono["cusip"], "emisor": bono["emisor"],
            "veredicto": bono["veredicto"], "precio": bono["precio"], "lote": lotes[i], "lotes": int(cantidad[i]),
            "nominalComprado": cantidad[i] * lotes[i], "costo": cantidad[i] * costoLote[i], "tir": bono["tir"],
            "rendimientoEsperado": bono["rendimientoEsperado"], "cupon": bono["cupon"], "plazo": bono["plazoEfectivo"],
            "vencimiento": bono["vencimiento"], "probImpago": bono["probImpago"], "calidad": bono["calidad"],
            "duracion": bono["duracion"],
        })
    plan = pd.DataFrame(filas)
    return plan, float(monto - plan["costo"].sum())


def proyectarBonos(plan, sobrante, meses, tasaLiquidez, plazosCurva, cambiosTasas, simulaciones=3000, semilla=11):
    """
    Monte Carlo de comprar y mantener los bonos del plan durante 'meses':
      - Cupones semestrales reinvertidos en liquidez (tasa simulada).
      - Impago con la probabilidad anual de su calidad (recupera 40% del nominal).
      - Si vence antes del horizonte, el principal se reinvierte en liquidez.
      - Si vence despues, se vende al horizonte a la TIR actual mas un cambio de
        tasas tomado de la historia (mismo escenario para todos los bonos).
    Devuelve dict con 'valores' (finales por escenario), 'resumen' y 'detalle'.
    """
    horizonte = meses / 12
    rng = np.random.default_rng(semilla)
    invertido = float(plan["costo"].sum()) if plan is not None and not plan.empty else 0.0
    if len(cambiosTasas):
        escenarios = cambiosTasas[rng.integers(0, len(cambiosTasas), simulaciones)]
    else:
        escenarios = np.zeros((simulaciones, max(len(plazosCurva), 1)))
    # Lo que se cobra antes del horizonte (cupones, vencimientos) se reinvierte en
    # liquidez a una tasa que tambien cambia: la de hoy mas la mitad del cambio
    # historico de la tasa corta en el escenario (cambio promedio del periodo).
    tasaReinversion = np.maximum(tasaLiquidez + 0.5 * escenarios[:, 0], 0.0)
    crecer = lambda t: (1 + tasaReinversion) ** np.maximum(horizonte - t, 0)  # noqa: E731
    total = sobrante * crecer(0.0)
    detalle = []
    for _, bono in (plan.iterrows() if plan is not None else []):
        if bono["nominalComprado"] <= 0:
            continue
        nominal, cupon, plazo = bono["nominalComprado"], bono["cupon"], bono["plazo"]
        tasaImpago = -np.log(1 - min(bono["probImpago"], 0.99)) if bono["probImpago"] > 0 else 0.0
        tiempoImpago = rng.exponential(1 / tasaImpago, simulaciones) if tasaImpago > 0 else np.full(simulaciones, np.inf)
        fechasPago = plazo - 0.5 * np.arange(int(np.ceil(plazo * 2 - 1e-9)))
        fechasPago = np.sort(fechasPago[(fechasPago > 0) & (fechasPago <= horizonte)])
        valor = np.zeros(simulaciones)
        for fechaPago in fechasPago:  # cupones antes del horizonte (si no hubo impago)
            valor += np.where(tiempoImpago > fechaPago, nominal * cupon / 2 * crecer(fechaPago), 0.0)
        impagoAntes = tiempoImpago < min(plazo, horizonte)
        valor += np.where(impagoAntes, nominal * RECUPERACION * crecer(np.minimum(tiempoImpago, horizonte)), 0.0)
        if plazo <= horizonte:
            valor += np.where(~impagoAntes, nominal * crecer(plazo), 0.0)
        else:
            restante = plazo - horizonte
            columna = int(np.argmin(np.abs(np.asarray(plazosCurva) - restante))) if len(plazosCurva) else 0
            tirFutura = np.maximum(bono["tir"] + escenarios[:, columna], -0.01)
            precioVenta = precioDesdeTir(cupon, restante, tirFutura)
            valor += np.where(~impagoAntes, nominal * precioVenta / 100, 0.0)
        total += valor
        detalle.append({"clave": bono["clave"], "valorMediano": float(np.median(valor)), "costo": bono["costo"],
                        "venceAntes": plazo <= horizonte})

    montoTotal = invertido + sobrante
    liquidez = montoTotal * (1 + tasaLiquidez) ** horizonte
    resumen = {
        "montoTotal": montoTotal, "invertidoEnBonos": invertido, "sobrante": sobrante,
        "valorMediano": float(np.median(total)), "valorPesimista": float(np.percentile(total, 10)),
        "valorOptimista": float(np.percentile(total, 90)),
        "gananciaMediana": float(np.median(total) - montoTotal),
        "gananciaPesimista": float(np.percentile(total, 10) - montoTotal),
        "gananciaOptimista": float(np.percentile(total, 90) - montoTotal),
        "probabilidadPerdida": float(np.mean(total < montoTotal)),
        "valorLiquidez": float(liquidez), "probabilidadSuperarLiquidez": float(np.mean(total > liquidez)),
        "rendimientoAnualMediano": float((np.median(total) / montoTotal) ** (1 / horizonte) - 1) if montoTotal else np.nan,
        "meses": int(meses),
    }
    return {"valores": total, "resumen": resumen, "detalle": pd.DataFrame(detalle)}


def evaluarSeleccion(seleccion, perfil):
    """
    Coherencia de la seleccion con el perfil: cuantos bonos no recomendables
    incluye, calidad mas baja, duracion maxima y rendimiento esperado promedio.
    """
    if seleccion is None or seleccion.empty:
        return {"bonos": 0, "estado": "vacia", "mensaje": "Aún no elegiste bonos."}
    noRecomendables = seleccion.loc[seleccion["veredicto"].isin(["No recomendable", "Sin datos"])]
    aceptables = seleccion.loc[seleccion["veredicto"] == "Aceptable"]
    resultado = {
        "bonos": len(seleccion), "emisores": seleccion["emisor"].nunique(),
        "noRecomendables": len(noRecomendables), "aceptables": len(aceptables),
        "rendimientoEsperado": float(seleccion["rendimientoEsperado"].mean()),
        "tir": float(seleccion["tir"].mean()), "duracionMaxima": float(seleccion["duracion"].max()),
        "calidadMinima": NIVELES_CALIDAD[int(seleccion["nivelCalidad"].max())] if seleccion["nivelCalidad"].notna().any() else "N/D",
    }
    if len(noRecomendables):
        nombres = ", ".join(noRecomendables["emisor"].astype(str).str[:28].head(3))
        resultado.update(estado="riesgo", mensaje=(
            f"Tu selección incluye {len(noRecomendables)} bono(s) NO recomendable(s) para el perfil {perfil} ({nombres}). "
            "Revisa el motivo en la tabla o reemplázalos."))
    elif len(aceptables):
        resultado.update(estado="cautela", mensaje=f"Selección dentro del perfil {perfil}; {len(aceptables)} bono(s) son solo aceptables.")
    else:
        resultado.update(estado="coherente", mensaje=f"Todos los bonos elegidos son recomendables para el perfil {perfil}.")
    if resultado["emisores"] == 1 and len(seleccion) > 1:
        resultado["mensaje"] += " Todos son del mismo emisor: considera diversificar."
    return resultado

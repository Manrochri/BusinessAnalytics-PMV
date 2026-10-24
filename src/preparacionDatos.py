"""
preparacionDatos.py
Fase "Comprension y preparacion de datos" de CRISP-ML(Q).

Une la serie de NAV con la serie de sentimiento y construye la tabla de
caracteristicas (features) que alimenta a los modelos predictivos.

Principios:
  - Solo variables estacionarias (retornos, distancias relativas, volatilidad):
    los niveles de precio no se usan porque los arboles no extrapolan.
  - La ULTIMA fila (el dia de hoy) se conserva aunque su objetivo aun no se
    conozca: es la fila desde la que se pronostica.
  - Las divisiones temporales dejan un hueco de 'horizonte' dias entre
    conjuntos, porque los objetivos de varios dias se solapan.
"""

import re

import numpy as np
import pandas as pd

from src.utilidades import describirOrigen, registrarEvento

VENTANAS = (5, 10, 21, 63)
REZAGOS = (1, 2, 3, 5, 10)
COLUMNAS_SENTIMIENTO = ["sentimiento", "noticiasDia", "sentimientoMedia5"]
COLUMNAS_NO_PREDICTORAS = {"objetivo", "nav", "volumen", "distribucion", "retornoAcumulado"}
# Proporcion minima de filas de entrenamiento con noticias para que el
# sentimiento entre al modelo (con menos, la columna es casi toda cero).
COBERTURA_MINIMA_SENTIMIENTO = 0.30


def calcularRsi(serie, ventana=14):
    """Indice de fuerza relativa (RSI) de la serie de NAV."""
    diferencia = serie.diff()
    ganancia = diferencia.clip(lower=0).rolling(ventana, min_periods=1).mean()
    perdida = (-diferencia.clip(upper=0)).rolling(ventana, min_periods=1).mean()
    fuerza = ganancia / perdida.replace(0, np.nan)
    return (100 - (100 / (1 + fuerza))).fillna(50)


def unirNavYSentimiento(historicoFondo, serieSentimiento):
    """
    Une el historico de NAV con la serie diaria de sentimiento (ya alineada a
    dias bursatiles). Los dias sin noticias quedan con sentimiento 0 y
    noticiasDia 0; no se arrastra el ultimo valor indefinidamente.
    """
    tabla = historicoFondo.copy()
    if serieSentimiento is not None and not serieSentimiento.empty:
        sentimiento = serieSentimiento.reindex(tabla.index)
        tabla["sentimiento"] = sentimiento["sentimientoDiario"].fillna(0.0)
        tabla["noticiasDia"] = sentimiento["cantidadNoticias"].fillna(0.0)
    else:
        tabla["sentimiento"] = 0.0
        tabla["noticiasDia"] = 0.0
    return tabla


def construirCaracteristicas(tablaUnida, horizonte=1):
    """
    Tabla de caracteristicas. La variable objetivo es el retorno del NAV a
    'horizonte' dias habiles: nav[t+h] / nav[t] - 1. Las ultimas 'horizonte'
    filas quedan con objetivo NaN (se usan para pronosticar, no para entrenar).
    """
    if tablaUnida is None or tablaUnida.empty:
        return pd.DataFrame()

    datos = tablaUnida.copy()
    nav = datos["nav"]
    retorno = nav.pct_change()
    datos["retornoDiario"] = retorno

    for rezago in REZAGOS:
        datos[f"retornoRezago{rezago}"] = retorno.shift(rezago)
    for ventana in VENTANAS:
        datos[f"distanciaMedia{ventana}"] = nav / nav.rolling(ventana, min_periods=ventana).mean() - 1
        datos[f"volatilidad{ventana}"] = retorno.rolling(ventana, min_periods=ventana).std()
        datos[f"momento{ventana}"] = nav.pct_change(ventana)
    datos["caida126"] = nav / nav.rolling(126, min_periods=21).max() - 1
    datos["rsi14"] = calcularRsi(nav)
    if "sentimiento" not in datos:
        datos["sentimiento"] = 0.0
        datos["noticiasDia"] = 0.0
    datos["sentimientoMedia5"] = datos["sentimiento"].rolling(5, min_periods=1).mean()

    datos["objetivo"] = nav.shift(-horizonte) / nav - 1

    columnas = listarColumnasPredictoras(datos)
    datos = datos.replace([np.inf, -np.inf], np.nan).dropna(subset=columnas)
    registrarEvento(
        f"Tabla de caracteristicas: {datos.shape[0]} filas ({int(datos['objetivo'].notna().sum())} con objetivo), "
        f"{len(columnas)} variables, horizonte {horizonte} dias."
    )
    return datos


NOMBRES_VARIABLES = {
    "retornoDiario": "Retorno del día", "caida126": "Caída desde el máximo de 6 meses", "rsi14": "RSI de 14 días",
    "sentimiento": "Sentimiento del día", "noticiasDia": "Cantidad de noticias del día",
    "sentimientoMedia5": "Sentimiento promedio de 5 días",
}
PATRONES_VARIABLES = [
    (r"retornoRezago(\d+)", "Retorno de hace {} día(s)"), (r"distanciaMedia(\d+)", "Distancia a la media de {} días"),
    (r"volatilidad(\d+)", "Volatilidad de {} días"), (r"momento(\d+)", "Retorno acumulado de {} días"),
]


def nombreVariable(columna):
    """Nombre legible de una variable del modelo (p. ej. 'volatilidad21' -> 'Volatilidad de 21 días')."""
    if columna in NOMBRES_VARIABLES:
        return NOMBRES_VARIABLES[columna]
    for patron, plantilla in PATRONES_VARIABLES:
        coincidencia = re.fullmatch(patron, str(columna))
        if coincidencia:
            return plantilla.format(coincidencia.group(1))
    return str(columna)


def listarColumnasPredictoras(tablaCaracteristicas, incluirSentimiento=True):
    """Columnas que se usan como predictoras (sin niveles de precio ni el objetivo)."""
    if tablaCaracteristicas is None or tablaCaracteristicas.empty:
        return []
    columnas = [c for c in tablaCaracteristicas.columns if c not in COLUMNAS_NO_PREDICTORAS]
    if not incluirSentimiento:
        columnas = [c for c in columnas if c not in COLUMNAS_SENTIMIENTO]
    return columnas


def coberturaSentimiento(tabla):
    """Proporcion de filas que tienen al menos una noticia."""
    if tabla is None or tabla.empty or "noticiasDia" not in tabla:
        return 0.0
    return float((tabla["noticiasDia"] > 0).mean())


def filasEtiquetadas(tablaCaracteristicas):
    """Filas con objetivo conocido (aptas para entrenar y evaluar)."""
    return tablaCaracteristicas.loc[tablaCaracteristicas["objetivo"].notna()]


def dividirTemporal(tablaEtiquetada, horizonte=1, proporcionValidacion=0.2, proporcionPrueba=0.2):
    """
    Division cronologica en entrenamiento / validacion / prueba, sin barajar.
    Entre conjuntos se descartan 'horizonte' filas (purga): el objetivo de la
    ultima fila de entrenamiento usa precios que caen dentro de validacion.

    Devuelve un dict con tres DataFrames: entrenamiento, validacion, prueba.
    """
    n = len(tablaEtiquetada)
    hueco = max(int(horizonte), 0)
    nPrueba = int(n * proporcionPrueba)
    nValidacion = int(n * proporcionValidacion)
    finEntrena = n - nPrueba - nValidacion - 2 * hueco
    if finEntrena < 60:
        registrarEvento("Muy pocos datos para dividir en entrenamiento/validacion/prueba.", "WARN")
    inicioValidacion = finEntrena + hueco
    inicioPrueba = inicioValidacion + nValidacion + hueco
    return {
        "entrenamiento": tablaEtiquetada.iloc[: max(finEntrena, 0)],
        "validacion": tablaEtiquetada.iloc[inicioValidacion: inicioValidacion + nValidacion],
        "prueba": tablaEtiquetada.iloc[inicioPrueba:],
    }


def recortarHastaFecha(historico, historicoBenchmark, noticias, fechaCorte):
    """
    Devuelve los tres conjuntos recortados a la fecha de corte, para evaluar
    el analisis "como si hoy fuera esa fecha": ni el NAV, ni el benchmark, ni
    las noticias posteriores llegan a los modelos ni a las reglas.
    Si fechaCorte es None se devuelven los datos completos.
    """
    if fechaCorte is None:
        return historico, historicoBenchmark, noticias

    finDelDia = pd.Timestamp(fechaCorte).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    historicoRecortado = historico.loc[historico.index <= finDelDia] if historico is not None else historico
    benchmarkRecortado = historicoBenchmark
    if historicoBenchmark is not None and not historicoBenchmark.empty:
        benchmarkRecortado = historicoBenchmark.loc[historicoBenchmark.index <= finDelDia]
    noticiasRecortadas = noticias
    if noticias is not None and not noticias.empty:
        fechas = pd.to_datetime(noticias["fecha"], errors="coerce")
        noticiasRecortadas = noticias.loc[fechas <= finDelDia].reset_index(drop=True)
    return historicoRecortado, benchmarkRecortado, noticiasRecortadas


def listarFechasSemanales(historico, cantidad=26, minimoObservaciones=300):
    """
    Ultimo dia habil de cada semana (mas reciente primero) usable como fecha de
    corte. Se excluye la semana en curso y las fechas con poco historial.
    """
    if historico is None or historico.empty:
        return []
    fechas = historico.index.to_series()
    ultimaFecha = fechas.iloc[-1]
    ultimoPorSemana = fechas.groupby(fechas.index.to_period("W")).max()
    salida = []
    for fecha in sorted(ultimoPorSemana.values, reverse=True):
        fecha = pd.Timestamp(fecha)
        if fecha >= ultimaFecha:
            continue
        if int((historico.index <= fecha).sum()) < minimoObservaciones:
            continue
        salida.append(fecha)
        if len(salida) >= cantidad:
            break
    return salida


def describirGranularidad(historico, noticias):
    """Frecuencia, rango y cobertura reales de los datos usados (calculados, no asumidos)."""
    info = {
        "frecuenciaNav": "No disponible", "observacionesNav": 0, "desdeNav": None, "hastaNav": None,
        "pasoMaximoDias": None, "totalNoticias": 0, "desdeNoticias": None, "hastaNoticias": None,
        "diasConNoticias": 0, "coberturaNoticias": 0.0,
    }
    if historico is not None and not historico.empty:
        pasos = historico.index.to_series().diff().dt.days.dropna()
        mediana = float(pasos.median()) if len(pasos) else float("nan")
        if mediana <= 1:
            info["frecuenciaNav"] = "Diaria (un dato por día bursátil)"
        elif mediana <= 8:
            info["frecuenciaNav"] = "Semanal"
        else:
            info["frecuenciaNav"] = f"Cada ~{mediana:.0f} días"
        info["observacionesNav"] = int(len(historico))
        info["desdeNav"] = historico.index.min()
        info["hastaNav"] = historico.index.max()
        info["pasoMaximoDias"] = int(pasos.max()) if len(pasos) else None

    if noticias is not None and not noticias.empty:
        fechas = pd.to_datetime(noticias["fecha"], errors="coerce").dropna()
        if len(fechas):
            info["totalNoticias"] = int(len(fechas))
            info["desdeNoticias"] = fechas.min()
            info["hastaNoticias"] = fechas.max()
            info["diasConNoticias"] = int(fechas.dt.normalize().nunique())
            if historico is not None and not historico.empty:
                enRango = (historico.index >= fechas.min().normalize()) & (historico.index <= fechas.max())
                info["coberturaNoticias"] = float(enRango.sum() / len(historico))
    return info


def verificarCalidadDatos(historicoFondo, noticias, historicoBenchmark=None, benchmark=None,
                          benchmarkComparable=True):
    """
    Monitoreo de calidad y disponibilidad de datos (CRISP-ML(Q)).
    Devuelve una lista de hallazgos (nivel, mensaje) para la aplicacion.
    """
    hallazgos = []
    if historicoFondo is None or historicoFondo.empty:
        return [("error", "No hay histórico de NAV disponible.")]

    hallazgos.append(("ok", f"Registros de NAV cargados: {len(historicoFondo)}."))
    faltantes = int(historicoFondo["nav"].isna().sum())
    if faltantes:
        hallazgos.append(("alerta", f"Valores de NAV faltantes: {faltantes}."))
    huecos = int((historicoFondo.index.to_series().diff().dt.days > 5).sum())
    if huecos:
        hallazgos.append(("alerta", f"Se detectaron {huecos} huecos mayores a 5 días en el NAV."))
    ultimaFecha = historicoFondo.index.max()
    hallazgos.append(("ok", f"Último dato de mercado: {ultimaFecha:%d/%m/%Y}."))
    for nombre, objeto in (("Histórico del fondo", historicoFondo), ("Benchmark", historicoBenchmark), ("Noticias", noticias)):
        if objeto is not None and not getattr(objeto, "empty", True):
            hallazgo = describirOrigen(nombre, objeto)
            if hallazgo:
                hallazgos.append(hallazgo)

    if benchmark and not benchmarkComparable:
        hallazgos.append(
            (
                "alerta",
                f"El benchmark {benchmark} es un índice de solo precio (sin dividendos) y el NAV del fondo sí "
                "los incluye: la comparación favorece al fondo en ~1-2% al año. No se usa en la señal. "
                "Usa ^SP500TR o un ETF equivalente para una comparación justa.",
            )
        )

    if noticias is None or noticias.empty:
        motivo = getattr(noticias, "attrs", {}).get("motivo") if noticias is not None else None
        texto = "Sin titulares recientes (Yahoo Finance / Alpha Vantage)."
        hallazgos.append(("alerta", f"{texto} ({motivo})" if motivo else texto))
    else:
        hallazgos.append(("ok", f"Noticias cargadas: {len(noticias)}."))
        if int((noticias["relevancia"].fillna(0) == 0).sum()) > len(noticias) * 0.5:
            hallazgos.append(("alerta", "Más de la mitad de las noticias no tienen relevancia asignada."))
    return hallazgos
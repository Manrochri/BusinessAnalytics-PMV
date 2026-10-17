"""
modeloClasificacionRiesgo.py
Componente de Machine Learning supervisado por CLASIFICACION (fase
"Modelado" de CRISP-ML(Q)): un RandomForestClassifier que predice la
categoria de riesgo (Bajo / Moderado / Alto) que el fondo va a TENER en los
proximos 63 dias habiles (~3 meses).

Por que asi: la version anterior aprendia una etiqueta calculada con sus
propias variables de entrada en la misma fecha, y su accuracy solo medía
que reproducia la formula. Ahora:
  - Las variables describen el pasado hasta la fecha t (volatilidad, caida,
    beta, momento, RSI...).
  - La etiqueta describe el futuro t+1..t+63: volatilidad REALIZADA y peor
    caida dentro de esa ventana. Nadie la conoce en t.
  - Se compara contra la linea base de "persistencia": suponer que los
    proximos 3 meses tendran el mismo nivel de riesgo que los ultimos 3.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score

from src.preparacionDatos import dividirTemporal
from src.utilidades import registrarEvento

VENTANA_RIESGO = 63  # aprox. 3 meses bursatiles
DIAS_HABILES_ANIO = 252
CATEGORIAS_RIESGO = ("Bajo", "Moderado", "Alto")
# Cortes absolutos del riesgo realizado en una ventana de 3 meses
CORTES_VOLATILIDAD = (0.12, 0.20)   # anualizada: < 12% Bajo, < 20% Moderado, si no Alto
CORTES_CAIDA = (-0.05, -0.10)       # peor caida: > -5% Bajo, > -10% Moderado, si no Alto

COLUMNAS_PREDICTORAS_RIESGO = [
    "volatilidad21", "volatilidad63", "caida126", "betaMovil", "momento21", "momento63",
    "distanciaMedia63", "rsi14", "retornoRezago1", "retornoRezago5",
]


def nivelPorCortes(valor, cortes, menorEsMejor=True):
    """0 = Bajo, 1 = Moderado, 2 = Alto (NaN si falta el dato)."""
    if pd.isna(valor):
        return np.nan
    if menorEsMejor:
        return 0 if valor < cortes[0] else (1 if valor < cortes[1] else 2)
    return 0 if valor > cortes[0] else (1 if valor > cortes[1] else 2)


def riesgoRealizado(nav, inicio, fin):
    """Volatilidad anualizada y peor caida de nav[inicio..fin] (posiciones, ambos incluidos)."""
    tramo = nav[inicio: fin + 1]
    if len(tramo) < 10:
        return np.nan, np.nan
    retornos = np.diff(tramo) / tramo[:-1]
    volatilidad = float(np.std(retornos, ddof=1) * np.sqrt(DIAS_HABILES_ANIO))
    caida = float(np.min(tramo / np.maximum.accumulate(tramo) - 1))
    return volatilidad, caida


def categoriaDeRiesgo(volatilidad, caida):
    """Categoria = el peor de los dos niveles (volatilidad y caida)."""
    niveles = [nivelPorCortes(volatilidad, CORTES_VOLATILIDAD), nivelPorCortes(caida, CORTES_CAIDA, False)]
    if any(pd.isna(n) for n in niveles):
        return None
    return CATEGORIAS_RIESGO[int(max(niveles))]


def calcularBetaMovil(retornosFondo, retornosBenchmark, ventana=VENTANA_RIESGO):
    """Beta movil del fondo frente al benchmark, recalculado en cada fecha."""
    alineados = pd.concat([retornosFondo, retornosBenchmark], axis=1, join="inner")
    alineados.columns = ["fondo", "benchmark"]
    minimo = int(ventana * 0.8)
    covarianza = alineados["fondo"].rolling(ventana, min_periods=minimo).cov(alineados["benchmark"])
    varianza = alineados["benchmark"].rolling(ventana, min_periods=minimo).var()
    return (covarianza / varianza.replace(0, np.nan)).reindex(retornosFondo.index)


def etiquetarRiesgo(tablaCaracteristicas, historicoBenchmark=None, ventana=VENTANA_RIESGO):
    """
    Agrega a la tabla de caracteristicas: betaMovil, volatilidad anualizada,
    'categoriaPasada' (riesgo realizado en los ultimos 63 dias, para la linea
    base) y 'categoriaFutura' (riesgo realizado en los proximos 63 dias: la
    etiqueta; vacia en los ultimos 63 dias, que son los que se pronostican).
    """
    if tablaCaracteristicas is None or tablaCaracteristicas.empty:
        return pd.DataFrame()

    tabla = tablaCaracteristicas.copy()
    nav = tabla["nav"].to_numpy(dtype=float)
    n = len(nav)

    if historicoBenchmark is not None and not historicoBenchmark.empty:
        tabla["betaMovil"] = calcularBetaMovil(tabla["retornoDiario"], historicoBenchmark["nav"].pct_change(), ventana)
    else:
        tabla["betaMovil"] = 1.0
    tabla["betaMovil"] = tabla["betaMovil"].fillna(tabla["betaMovil"].median()).fillna(1.0)
    for columna in ("volatilidad21", "volatilidad63"):
        tabla[columna + "Anual"] = tabla[columna] * np.sqrt(DIAS_HABILES_ANIO)

    futuras, pasadas = [], []
    for i in range(n):
        if i + ventana < n:
            futuras.append(categoriaDeRiesgo(*riesgoRealizado(nav, i, i + ventana)))
        else:
            futuras.append(None)
        pasadas.append(categoriaDeRiesgo(*riesgoRealizado(nav, i - ventana, i)) if i >= ventana else None)
    tabla["categoriaFutura"] = futuras
    tabla["categoriaPasada"] = pasadas
    registrarEvento(f"Etiquetas de riesgo futuro: {int(tabla['categoriaFutura'].notna().sum())} filas.")
    return tabla


def entrenarClasificadorRiesgo(tablaEtiquetada, semilla=42):
    """
    Entrena el RandomForestClassifier, lo evalua en un tramo de prueba
    posterior (con purga de 63 dias) frente a la linea base de persistencia y
    lo reentrena con todo el historial etiquetado para la prediccion actual.
    """
    resultado = {
        "modelo": None, "accuracy": np.nan, "f1Macro": np.nan, "accuracyPersistencia": np.nan,
        "f1Persistencia": np.nan, "superaPersistencia": False, "matrizConfusion": pd.DataFrame(),
        "categoriaActual": None, "probabilidades": {}, "categoriaPasadaActual": None,
        "distribucion": {}, "importancia": pd.DataFrame(), "mensaje": "",
    }
    if tablaEtiquetada is None or tablaEtiquetada.empty:
        resultado["mensaje"] = "Sin datos para el clasificador de riesgo."
        return resultado

    columnas = [c for c in COLUMNAS_PREDICTORAS_RIESGO if c in tablaEtiquetada.columns]
    etiquetadas = tablaEtiquetada.dropna(subset=columnas + ["categoriaFutura"])
    etiquetadas = etiquetadas.loc[etiquetadas["categoriaPasada"].notna()]
    resultado["distribucion"] = etiquetadas["categoriaFutura"].value_counts().to_dict()
    if len(etiquetadas) < 250 or etiquetadas["categoriaFutura"].nunique() < 2:
        resultado["mensaje"] = "Historial insuficiente o con una sola categoría de riesgo: no se entrena el clasificador."
        return resultado

    partes = dividirTemporal(etiquetadas, VENTANA_RIESGO, proporcionValidacion=0.0, proporcionPrueba=0.25)
    entrena, prueba = partes["entrenamiento"], partes["prueba"]
    if len(entrena) < 100 or len(prueba) < 30 or entrena["categoriaFutura"].nunique() < 2:
        resultado["mensaje"] = "Muy pocos datos para evaluar el clasificador tras la purga."
        return resultado

    def crear():
        return RandomForestClassifier(
            n_estimators=300, max_depth=6, min_samples_leaf=10, class_weight="balanced",
            random_state=semilla, n_jobs=-1,
        )

    modelo = crear().fit(entrena[columnas], entrena["categoriaFutura"])
    prediccion = modelo.predict(prueba[columnas])
    reales = prueba["categoriaFutura"].to_numpy()
    persistencia = prueba["categoriaPasada"].to_numpy()

    resultado["accuracy"] = float(accuracy_score(reales, prediccion))
    resultado["f1Macro"] = float(f1_score(reales, prediccion, average="macro", zero_division=0))
    resultado["accuracyPersistencia"] = float(accuracy_score(reales, persistencia))
    resultado["f1Persistencia"] = float(f1_score(reales, persistencia, average="macro", zero_division=0))
    resultado["superaPersistencia"] = resultado["f1Macro"] > resultado["f1Persistencia"]

    etiquetas = [c for c in CATEGORIAS_RIESGO if c in set(reales) | set(prediccion)]
    resultado["matrizConfusion"] = pd.crosstab(
        pd.Series(reales, name="Real"), pd.Series(prediccion, name="Predicho")
    ).reindex(index=etiquetas, columns=etiquetas, fill_value=0)

    # Modelo final con todo lo etiquetado y prediccion para la fila mas reciente
    final = crear().fit(etiquetadas[columnas], etiquetadas["categoriaFutura"])
    filaActual = tablaEtiquetada[columnas].dropna().iloc[[-1]]
    resultado["modelo"] = final
    resultado["categoriaActual"] = str(final.predict(filaActual)[0])
    resultado["probabilidades"] = {str(c): float(p) for c, p in zip(final.classes_, final.predict_proba(filaActual)[0], strict=True)}
    resultado["categoriaPasadaActual"] = tablaEtiquetada["categoriaPasada"].dropna().iloc[-1] if tablaEtiquetada["categoriaPasada"].notna().any() else None
    resultado["importancia"] = (
        pd.DataFrame({"variable": columnas, "importancia": final.feature_importances_})
        .sort_values("importancia", ascending=False).reset_index(drop=True)
    )
    resultado["periodoPrueba"] = (prueba.index.min(), prueba.index.max())
    registrarEvento(
        f"Clasificador de riesgo: accuracy {resultado['accuracy']:.2f} / F1 {resultado['f1Macro']:.2f} "
        f"vs persistencia {resultado['accuracyPersistencia']:.2f} / {resultado['f1Persistencia']:.2f}."
    )
    return resultado

"""
modeloPredictivo.py
Fases "Modelado" y "Evaluacion" de CRISP-ML(Q).

Pronostico DIRECTO del retorno del NAV a 'horizonte' dias habiles (no
recursivo de 1 dia): cada modelo aprende nav[t+h]/nav[t]-1.

Evaluacion honesta:
  - Division cronologica entrenamiento / validacion / prueba con purga.
  - El modelo se ELIGE con validacion y se REPORTA con prueba.
  - Siempre se compara contra dos lineas base: "paseo aleatorio" (retorno 0)
    y "media historica" (el retorno promedio de entrenamiento). Si ningun
    modelo las supera en prueba, el pronostico usa la media historica y la
    senal no usa el pronostico.
  - La banda del 90% sale de los residuos de validacion y su cobertura real
    se mide en prueba.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.preparacionDatos import (
    COBERTURA_MINIMA_SENTIMIENTO,
    coberturaSentimiento,
    dividirTemporal,
    filasEtiquetadas,
    listarColumnasPredictoras,
)
from src.utilidades import esNulo, registrarEvento

DIAS_HABILES_ANIO = 252
NOMBRE_PASEO = "Línea base: paseo aleatorio"
NOMBRE_MEDIA = "Línea base: media histórica"
# Mejora minima del MAE frente a la mejor linea base para considerar que hay habilidad
HABILIDAD_MINIMA = 0.02

try:
    from xgboost import XGBRegressor

    XGBOOST_DISPONIBLE = True
except ImportError:
    XGBOOST_DISPONIBLE = False


class LineaBase:
    """Predictor constante: 0 (paseo aleatorio) o la media del objetivo (media historica)."""

    def __init__(self, tipo="media"):
        self.tipo = tipo
        self.valor = 0.0

    def fit(self, X, y):
        self.valor = 0.0 if self.tipo == "paseo" else float(np.mean(y))
        return self

    def predict(self, X):
        return np.full(len(X), self.valor, dtype=float)


class Ensamble:
    """Promedio de las predicciones de varios modelos ya entrenados."""

    def __init__(self, modelos):
        self.modelos = list(modelos)

    def predict(self, X):
        return np.mean([m.predict(X) for m in self.modelos], axis=0)


def crearModelos(semilla=42):
    """Catalogo de modelos que se comparan (Random Forest se conserva siempre)."""
    modelos = {
        "Ridge": Pipeline([("escalador", StandardScaler()), ("modelo", Ridge(alpha=10.0))]),
        "RandomForest": RandomForestRegressor(
            n_estimators=300, max_depth=6, min_samples_leaf=20, random_state=semilla, n_jobs=-1
        ),
        "GradientBoosting": GradientBoostingRegressor(
            n_estimators=200, max_depth=2, learning_rate=0.03, subsample=0.8, random_state=semilla
        ),
    }
    if XGBOOST_DISPONIBLE:
        modelos["XGBoost"] = XGBRegressor(
            n_estimators=300, max_depth=3, learning_rate=0.03, subsample=0.8,
            colsample_bytree=0.8, random_state=semilla, verbosity=0,
        )
    return modelos


def calcularMetricas(reales, estimados):
    """MAE, RMSE, R2 fuera de muestra y acierto de direccion."""
    reales = np.asarray(reales, dtype=float)
    estimados = np.asarray(estimados, dtype=float)
    if len(reales) == 0:
        return {"mae": np.nan, "rmse": np.nan, "r2": np.nan, "aciertoDireccion": np.nan}
    return {
        "mae": float(mean_absolute_error(reales, estimados)),
        "rmse": float(np.sqrt(mean_squared_error(reales, estimados))),
        "r2": float(r2_score(reales, estimados)) if len(reales) > 1 else np.nan,
        "aciertoDireccion": float(np.mean(np.sign(reales) == np.sign(estimados)) * 100),
    }


def _ajustar(modelo, X, y):
    return modelo.fit(X, y)


def _clonar(nombre, semilla=42):
    if nombre == NOMBRE_PASEO:
        return LineaBase("paseo")
    if nombre == NOMBRE_MEDIA:
        return LineaBase("media")
    return crearModelos(semilla)[nombre]


def entrenarYEvaluar(tablaCaracteristicas, horizonte=21, incluirSentimiento=None, semilla=42):
    """
    Entrena, selecciona y evalua los modelos. Devuelve un dict con:
      tabla           comparacion (validacion y prueba) incluidas las lineas base
      mejorNombre     modelo elegido por MAE de validacion
      tieneHabilidad  True si el elegido supera a ambas lineas base en prueba
      habilidad       1 - MAE(elegido)/MAE(mejor linea base), en prueba
      predictor       objeto con .predict() entrenado con TODAS las filas
                      (el elegido si tiene habilidad; si no, la media historica)
      nombrePredictor nombre del predictor efectivamente usado
      residuos        residuos de validacion del predictor usado (para bandas)
      cobertura90     % de resultados de prueba dentro de la banda del 90%
      columnas, incluirSentimiento, coberturaSentimiento, filas (por conjunto)
    """
    resultado = {"exito": False, "mensaje": "", "tabla": pd.DataFrame(), "avisos": []}
    etiquetadas = filasEtiquetadas(tablaCaracteristicas)
    if len(etiquetadas) < 250:
        resultado["mensaje"] = "Historial insuficiente para entrenar (se necesitan al menos 250 días con objetivo)."
        return resultado

    partes = dividirTemporal(etiquetadas, horizonte)
    entrena, valida, prueba = partes["entrenamiento"], partes["validacion"], partes["prueba"]
    if min(len(entrena), len(valida), len(prueba)) < 30:
        resultado["mensaje"] = "Muy pocos datos por conjunto tras la purga; amplía el periodo histórico."
        return resultado

    cobertura = coberturaSentimiento(entrena)
    if incluirSentimiento is None:
        incluirSentimiento = cobertura >= COBERTURA_MINIMA_SENTIMIENTO
    if not incluirSentimiento:
        resultado["avisos"].append(
            f"El sentimiento se excluyó del modelo: solo {cobertura:.0%} de los días de entrenamiento tienen dato de sentimiento "
            f"(mínimo {COBERTURA_MINIMA_SENTIMIENTO:.0%}). Completa la historia del tono de prensa desde la barra lateral."
        )
    columnas = listarColumnasPredictoras(tablaCaracteristicas, incluirSentimiento)

    def xy(tabla):
        return tabla[columnas], tabla["objetivo"].to_numpy()

    xE, yE = xy(entrena)
    xV, yV = xy(valida)
    xP, yP = xy(prueba)
    entrenaValida = pd.concat([entrena, valida])
    xEV, yEV = xy(entrenaValida)

    nombresMl = list(crearModelos(semilla).keys())
    filas, predVal, predPrueba, ajustadosE, ajustadosEV = [], {}, {}, {}, {}

    for nombre in nombresMl + [NOMBRE_PASEO, NOMBRE_MEDIA]:
        try:
            modeloE = _ajustar(_clonar(nombre, semilla), xE, yE)
            modeloEV = _ajustar(_clonar(nombre, semilla), xEV, yEV)
            predVal[nombre] = modeloE.predict(xV)
            predPrueba[nombre] = modeloEV.predict(xP)
            ajustadosE[nombre], ajustadosEV[nombre] = modeloE, modeloEV
        except Exception as error:  # un modelo que falla no detiene el resto
            registrarEvento(f"No se pudo entrenar {nombre}: {error}", "ERROR")
            resultado["avisos"].append(f"{nombre} no se pudo entrenar: {error}")

    entrenadosMl = [n for n in nombresMl if n in ajustadosE]
    if len(entrenadosMl) >= 2:
        predVal["Ensamble"] = Ensamble([ajustadosE[n] for n in entrenadosMl]).predict(xV)
        predPrueba["Ensamble"] = Ensamble([ajustadosEV[n] for n in entrenadosMl]).predict(xP)

    for nombre in predVal:
        mVal = calcularMetricas(yV, predVal[nombre])
        mPrueba = calcularMetricas(yP, predPrueba[nombre])
        if nombre == NOMBRE_PASEO:  # predice 0: no tiene direccion
            mPrueba["aciertoDireccion"] = np.nan
        filas.append(
            {
                "Modelo": nombre,
                "Tipo": "Línea base" if nombre.startswith("Línea base") else "Modelo",
                "MAE validación (pp)": mVal["mae"] * 100,
                "MAE prueba (pp)": mPrueba["mae"] * 100,
                "RMSE prueba (pp)": mPrueba["rmse"] * 100,
                "R² prueba": mPrueba["r2"],
                "Acierto dirección prueba %": mPrueba["aciertoDireccion"],
            }
        )
    tabla = pd.DataFrame(filas)
    if tabla.empty:
        resultado["mensaje"] = "Ningún modelo se pudo entrenar."
        return resultado

    candidatos = tabla.loc[tabla["Tipo"] == "Modelo"].sort_values("MAE validación (pp)")
    mejorNombre = candidatos["Modelo"].iloc[0] if not candidatos.empty else NOMBRE_MEDIA
    maePrueba = tabla.set_index("Modelo")["MAE prueba (pp)"]
    mejorBase = min(maePrueba.get(NOMBRE_PASEO, np.inf), maePrueba.get(NOMBRE_MEDIA, np.inf))
    habilidad = float(1 - maePrueba[mejorNombre] / mejorBase) if mejorBase and np.isfinite(mejorBase) else np.nan
    tieneHabilidad = (not esNulo(habilidad)) and habilidad > HABILIDAD_MINIMA

    tabla["Habilidad vs línea base %"] = (1 - tabla["MAE prueba (pp)"] / mejorBase) * 100
    tabla["Elegido"] = np.where(tabla["Modelo"] == mejorNombre, "✓", "")
    tabla = tabla.sort_values(["Tipo", "MAE validación (pp)"], ascending=[False, True]).reset_index(drop=True)

    # Predictor final: el elegido (si tiene habilidad) o la media historica
    nombrePredictor = mejorNombre if tieneHabilidad else NOMBRE_MEDIA
    xTodo, yTodo = xy(etiquetadas)
    if nombrePredictor == "Ensamble":
        predictor = Ensamble([_ajustar(_clonar(n, semilla), xTodo, yTodo) for n in entrenadosMl])
    else:
        predictor = _ajustar(_clonar(nombrePredictor, semilla), xTodo, yTodo)

    # Banda: cuantiles de residuos de validacion; cobertura medida en prueba
    residuosVal = yV - predVal[nombrePredictor]
    q05, q95 = np.quantile(residuosVal, [0.05, 0.95])
    dentro = (yP >= predPrueba[nombrePredictor] + q05) & (yP <= predPrueba[nombrePredictor] + q95)

    if not tieneHabilidad:
        resultado["avisos"].append(
            f"Ningún modelo superó a las líneas base en prueba (mejor: {mejorNombre}, habilidad {habilidad:+.1%}). "
            "El pronóstico usa la media histórica y la señal no usa el pronóstico."
        )

    resultado.update(
        {
            "exito": True,
            "tabla": tabla,
            "mejorNombre": mejorNombre,
            "nombrePredictor": nombrePredictor,
            "predictor": predictor,
            # Mejor modelo de ML (entrenado con entrenamiento + validacion), aunque no supere a la linea base:
            # sirve para mostrar QUE variables intento usar, como referencia
            "modeloReferencia": (Ensamble([ajustadosEV[n] for n in entrenadosMl]) if mejorNombre == "Ensamble"
                                 else ajustadosEV.get(mejorNombre)),
            "tieneHabilidad": bool(tieneHabilidad),
            "habilidad": habilidad,
            "residuos": residuosVal,
            "cuantilesResiduo": (float(q05), float(q95)),
            "cobertura90": float(np.mean(dentro) * 100),
            "columnas": columnas,
            "incluirSentimiento": bool(incluirSentimiento),
            "coberturaSentimiento": cobertura,
            "horizonte": int(horizonte),
            "filas": {"entrenamiento": len(entrena), "validacion": len(valida), "prueba": len(prueba)},
            "periodos": {k: (v.index.min(), v.index.max()) for k, v in partes.items()},
        }
    )
    registrarEvento(
        f"Modelo elegido {mejorNombre}; habilidad en prueba {habilidad:+.1%}; "
        f"cobertura de la banda 90%: {resultado['cobertura90']:.0f}%."
    )
    return resultado


def pronosticarHorizonte(resultadoModelo, tablaCaracteristicas, navActual, fechaUltima, horizonte):
    """
    Pronostico directo desde la ULTIMA fila disponible (el dia de hoy).
    El camino intermedio interpola de forma geometrica hasta el valor final, y
    la banda crece con la raiz del tiempo hasta los cuantiles 5%-95% de los
    residuos de validacion. Las fechas empiezan el dia habil SIGUIENTE.
    """
    if not resultadoModelo.get("exito") or tablaCaracteristicas is None or tablaCaracteristicas.empty:
        return pd.DataFrame()

    filaActual = tablaCaracteristicas[resultadoModelo["columnas"]].iloc[[-1]]
    retorno = float(resultadoModelo["predictor"].predict(filaActual)[0])
    q05, q95 = resultadoModelo["cuantilesResiduo"]

    fechas = pd.bdate_range(start=pd.Timestamp(fechaUltima) + pd.offsets.BDay(1), periods=horizonte)
    fraccion = np.arange(1, horizonte + 1) / horizonte
    central = navActual * (1 + retorno) ** fraccion
    inferior = navActual * np.maximum(1 + retorno * fraccion + q05 * np.sqrt(fraccion), 0.01)
    superior = navActual * (1 + retorno * fraccion + q95 * np.sqrt(fraccion))

    pronostico = pd.DataFrame(
        {"navEstimado": central, "bandaInferior": inferior, "bandaSuperior": superior}, index=fechas
    )
    pronostico.index.name = "Date"
    pronostico.attrs["retornoCentral"] = retorno
    return pronostico


def resumirPronostico(pronostico, navActual, resultadoModelo=None):
    """Indicadores del dashboard predictivo, incluida la probabilidad empirica de alza."""
    resumen = {
        "valorProyectado": np.nan, "rentabilidadProyectada": np.nan, "bandaInferior": np.nan,
        "bandaSuperior": np.nan, "probabilidadAlza": np.nan, "tieneHabilidad": False,
    }
    if pronostico is None or pronostico.empty:
        return resumen
    resumen["valorProyectado"] = float(pronostico["navEstimado"].iloc[-1])
    resumen["rentabilidadProyectada"] = resumen["valorProyectado"] / float(navActual) - 1
    resumen["bandaInferior"] = float(pronostico["bandaInferior"].iloc[-1])
    resumen["bandaSuperior"] = float(pronostico["bandaSuperior"].iloc[-1])
    if resultadoModelo:
        resumen["tieneHabilidad"] = bool(resultadoModelo.get("tieneHabilidad"))
        residuos = np.asarray(resultadoModelo.get("residuos", []), dtype=float)
        if len(residuos):
            # Proporcion de escenarios (prediccion + error historico) que terminan en alza
            resumen["probabilidadAlza"] = float(np.mean(resumen["rentabilidadProyectada"] + residuos > 0))
    return resumen


def evaluarRiesgoFuturo(pronostico, navActual):
    """Riesgo prospectivo a partir de la banda: amplitud y perdida en el escenario P5."""
    evaluacion = {"amplitudBanda": np.nan, "perdidaEsperadaPeor": np.nan, "nivel": "No disponible", "puntaje": np.nan}
    if pronostico is None or pronostico.empty:
        return evaluacion
    final = pronostico.iloc[-1]
    evaluacion["amplitudBanda"] = float((final["bandaSuperior"] - final["bandaInferior"]) / navActual)
    evaluacion["perdidaEsperadaPeor"] = float(final["bandaInferior"] / navActual - 1)
    perdida = max(-evaluacion["perdidaEsperadaPeor"], 0.0)
    evaluacion["puntaje"] = round(float(np.clip(perdida / 0.15 * 10, 0, 10)), 1)
    evaluacion["nivel"] = "Bajo" if perdida < 0.03 else ("Moderado" if perdida < 0.08 else "Alto")
    return evaluacion


def obtenerImportanciaVariables(modelo, columnas, cantidad=10):
    """Importancia normalizada de las variables del modelo usado (vacio para lineas base)."""
    if modelo is None or isinstance(modelo, LineaBase):
        return pd.DataFrame()
    miembros = modelo.modelos if isinstance(modelo, Ensamble) else [modelo]
    valores = []
    for miembro in miembros:
        if hasattr(miembro, "feature_importances_"):
            valores.append(np.asarray(miembro.feature_importances_, dtype=float))
        elif hasattr(miembro, "named_steps") and hasattr(miembro.named_steps.get("modelo"), "coef_"):
            valores.append(np.abs(miembro.named_steps["modelo"].coef_))
    if not valores:
        return pd.DataFrame()
    normalizados = [v / v.sum() if v.sum() else v for v in valores]
    tabla = pd.DataFrame({"variable": columnas, "importancia": np.mean(normalizados, axis=0)})
    return tabla.sort_values("importancia", ascending=False).head(cantidad).reset_index(drop=True)
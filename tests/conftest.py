"""Configuracion comun de las pruebas: raiz del proyecto en el path y datos sinteticos."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.datosEstructurados import construirTablaNav


def serieSintetica(dias=1300, deriva=0.08, volatilidad=0.15, semilla=1, fin="2026-10-09", tramos=None):
    """
    Historico sintetico con la estructura de descargarHistorico.
    tramos: lista de (inicio, fin, deriva, volatilidad) para simular crisis.
    """
    fechas = pd.bdate_range(end=fin, periods=dias)
    rng = np.random.default_rng(semilla)
    mu = np.full(dias, deriva / 252)
    sigma = np.full(dias, volatilidad / np.sqrt(252))
    for inicio, final, d, v in tramos or []:
        mu[inicio:final], sigma[inicio:final] = d / 252, v / np.sqrt(252)
    retornos = rng.normal(mu, sigma)
    return construirTablaNav(pd.Series(100 * np.cumprod(1 + retornos), index=fechas))

"""
catalogoBonos.py
Catalogo de fondos de bonos (ETF con su fondo mutuo equivalente) segmentado
por perfil de inversor, y los parametros de cada perfil.

Se usan ETF porque Yahoo Finance publica su precio diario ajustado y su
rendimiento por distribuciones; el fondo mutuo equivalente de Vanguard se
muestra como referencia para quien prefiera invertir via fondo mutuo
(verificar disponibilidad y montos minimos con la gestora).

Todos los supuestos numericos estan aqui, en un solo lugar, para poder
revisarlos o calibrarlos sin tocar la logica.
"""

PERFILES = ("Conservador", "Moderado", "Agresivo")

PARAMETROS_PERFIL = {
    "Conservador": {
        "descripcion": "Prioriza no perder capital: bonos de corto plazo y alta calidad crediticia.",
        "tipoBonos": "Corto plazo y alta calidad",
        # Asignacion estrategica base (suma 1)
        "rentaVariable": 0.35, "rentaFija": 0.55, "liquidez": 0.10,
        # Tolerancias para el ranking de bonos (ventana de 3 anios)
        "volatilidadMaxima": 0.04, "caidaTolerada": -0.06,
        # Prima minima del rendimiento sobre la liquidez (puede ser negativa:
        # un bono de Tesoro corto plazo rinde casi lo mismo que la liquidez)
        "primaMinima": -0.0075,
        # Limites para elegir bonos INDIVIDUALES dentro de los fondos
        "duracionMaxima": 3.5, "calidadMinima": "AA–A",
    },
    "Moderado": {
        "descripcion": "Busca equilibrio entre ingreso y estabilidad: bonos de plazo intermedio y grado de inversión.",
        "tipoBonos": "Plazo intermedio y grado de inversión",
        "rentaVariable": 0.60, "rentaFija": 0.35, "liquidez": 0.05,
        "volatilidadMaxima": 0.08, "caidaTolerada": -0.18,
        "primaMinima": -0.0025,
        "duracionMaxima": 8.0, "calidadMinima": "BBB",
    },
    "Agresivo": {
        "descripcion": "Acepta más volatilidad a cambio de más rendimiento: crédito de alto rendimiento, emergentes y largo plazo.",
        "tipoBonos": "Alto rendimiento, emergentes y largo plazo",
        "rentaVariable": 0.80, "rentaFija": 0.17, "liquidez": 0.03,
        "volatilidadMaxima": 0.15, "caidaTolerada": -0.35,
        "primaMinima": 0.0075,
        "duracionMaxima": 20.0, "calidadMinima": "B",
    },
}

# ---------------------------------------------------------------------------
# Bonos individuales: calidad crediticia
# ---------------------------------------------------------------------------
# Sin acceso gratuito a calificaciones, la calidad se INFIERE del diferencial
# de rendimiento sobre un bono del Tesoro del mismo plazo (lo que el mercado
# cobra por el riesgo de credito). Probabilidad de impago anual: promedios de
# largo plazo aproximados de los estudios anuales de impago de S&P Global por
# calificacion. Perdida en caso de impago: 60% (recuperacion de 40%).
NIVELES_CALIDAD = ["Tesoro EE.UU.", "Agencia EE.UU.", "AA–A", "BBB", "BB", "B", "CCC o menor"]
PROBABILIDAD_IMPAGO_ANUAL = {
    "Tesoro EE.UU.": 0.0, "Agencia EE.UU.": 0.0001, "AA–A": 0.0005, "BBB": 0.0015,
    "BB": 0.006, "B": 0.03, "CCC o menor": 0.25,
}
PERDIDA_EN_IMPAGO = 0.60
# Diferencial maximo (en fraccion) para cada nivel inferido
CORTES_DIFERENCIAL = [(0.006, "AA–A"), (0.016, "BBB"), (0.035, "BB"), (0.06, "B")]
# Calidad asignada a bonos municipales (su rendimiento esta exento de impuesto
# federal y suele ser MENOR al del Tesoro, por lo que el diferencial no sirve)
CALIDAD_MUNICIPAL = "AA–A"
# Vida promedio estimada de los hipotecarios (MBS): se prepagan antes del vencimiento
VIDA_ESTIMADA_MBS = 7.0
# Lote minimo de compra por bono (valor nominal)
NOMINAL_MINIMO = {"Tesoro EE.UU.": 100, "otros": 1000}

# perdidaCreditoEsperada: descuento anual al rendimiento ofrecido por impagos
# esperados (supuesto prudente; el rendimiento de un bono de alto riesgo
# incluye la compensacion por impagos que, en promedio, si ocurren).
CATALOGO_BONOS = [
    # --- Conservador -------------------------------------------------------
    {"ticker": "SGOV", "nombre": "iShares 0-3 Month Treasury Bond ETF", "perfil": "Conservador",
     "segmento": "Tesoro ultra corto (0-3 meses)", "fondoMutuo": "VUSXX", "perdidaCreditoEsperada": 0.0},
    {"ticker": "SHY", "nombre": "iShares 1-3 Year Treasury Bond ETF", "perfil": "Conservador",
     "segmento": "Tesoro corto plazo (1-3 años)", "fondoMutuo": "VSBSX", "perdidaCreditoEsperada": 0.0},
    {"ticker": "VGSH", "nombre": "Vanguard Short-Term Treasury ETF", "perfil": "Conservador",
     "segmento": "Tesoro corto plazo (1-3 años)", "fondoMutuo": "VSBSX", "perdidaCreditoEsperada": 0.0},
    {"ticker": "VTIP", "nombre": "Vanguard Short-Term Inflation-Protected Securities ETF", "perfil": "Conservador",
     "segmento": "Protegidos contra inflación (corto plazo)", "fondoMutuo": "VTAPX", "perdidaCreditoEsperada": 0.0},
    {"ticker": "VCSH", "nombre": "Vanguard Short-Term Corporate Bond ETF", "perfil": "Conservador",
     "segmento": "Corporativos grado de inversión (corto plazo)", "fondoMutuo": "VSCSX", "perdidaCreditoEsperada": 0.001},
    # --- Moderado ----------------------------------------------------------
    {"ticker": "BND", "nombre": "Vanguard Total Bond Market ETF", "perfil": "Moderado",
     "segmento": "Mercado agregado de EE.UU.", "fondoMutuo": "VBTLX", "perdidaCreditoEsperada": 0.0005},
    {"ticker": "AGG", "nombre": "iShares Core U.S. Aggregate Bond ETF", "perfil": "Moderado",
     "segmento": "Mercado agregado de EE.UU.", "fondoMutuo": "VBTLX", "perdidaCreditoEsperada": 0.0005},
    {"ticker": "VCIT", "nombre": "Vanguard Intermediate-Term Corporate Bond ETF", "perfil": "Moderado",
     "segmento": "Corporativos grado de inversión (intermedio)", "fondoMutuo": "VICSX", "perdidaCreditoEsperada": 0.002},
    {"ticker": "IEF", "nombre": "iShares 7-10 Year Treasury Bond ETF", "perfil": "Moderado",
     "segmento": "Tesoro intermedio (7-10 años)", "fondoMutuo": "VSIGX", "perdidaCreditoEsperada": 0.0},
    {"ticker": "MUB", "nombre": "iShares National Muni Bond ETF", "perfil": "Moderado",
     "segmento": "Municipales (exentos de impuesto federal en EE.UU.)", "fondoMutuo": "VTEAX", "perdidaCreditoEsperada": 0.0005},
    # --- Agresivo ----------------------------------------------------------
    {"ticker": "HYG", "nombre": "iShares iBoxx $ High Yield Corporate Bond ETF", "perfil": "Agresivo",
     "segmento": "Alto rendimiento (high yield)", "fondoMutuo": "VWEAX", "perdidaCreditoEsperada": 0.015},
    {"ticker": "JNK", "nombre": "SPDR Bloomberg High Yield Bond ETF", "perfil": "Agresivo",
     "segmento": "Alto rendimiento (high yield)", "fondoMutuo": "VWEAX", "perdidaCreditoEsperada": 0.015},
    {"ticker": "ANGL", "nombre": "VanEck Fallen Angel High Yield Bond ETF", "perfil": "Agresivo",
     "segmento": "Ángeles caídos (ex grado de inversión)", "fondoMutuo": None, "perdidaCreditoEsperada": 0.01},
    {"ticker": "EMB", "nombre": "iShares J.P. Morgan USD Emerging Markets Bond ETF", "perfil": "Agresivo",
     "segmento": "Mercados emergentes en USD", "fondoMutuo": "VEGBX", "perdidaCreditoEsperada": 0.01},
    {"ticker": "TLT", "nombre": "iShares 20+ Year Treasury Bond ETF", "perfil": "Agresivo",
     "segmento": "Tesoro largo plazo (20+ años)", "fondoMutuo": "VLGSX", "perdidaCreditoEsperada": 0.0},
]

# Peso de cada componente en el puntaje del ranking (suma 1)
PESOS_RANKING = {"prima": 0.35, "sharpe": 0.20, "volatilidad": 0.15, "caida": 0.15, "tendencia": 0.15}
UMBRAL_RECOMENDABLE = 60
UMBRAL_ACEPTABLE = 45
VENTANA_ANIOS_BONOS = 3


def bonosDelPerfil(perfil):
    """Lista de bonos del catalogo para un perfil."""
    return [b for b in CATALOGO_BONOS if b["perfil"] == perfil]


def todosLosTickersBonos():
    """Tickers unicos del catalogo (para descargarlos una sola vez)."""
    return list(dict.fromkeys(b["ticker"] for b in CATALOGO_BONOS))


def buscarBono(ticker):
    """Ficha del catalogo para un ticker (o None)."""
    return next((b for b in CATALOGO_BONOS if b["ticker"] == ticker), None)


# ---------------------------------------------------------------------------
# Fondo analizado: benchmark y tema de prensa segun el perfil y el fondo
# ---------------------------------------------------------------------------
# Benchmark de retorno total (ETF) contra el que se compara cada fondo:
# Conservador -> letras del Tesoro (BIL): ¿paga el plazo/credito extra?
# Moderado y Agresivo -> mercado agregado de bonos de EE.UU. (AGG)
BENCHMARK_PERFIL = {"Conservador": "BIL", "Moderado": "AGG", "Agresivo": "AGG"}
BENCHMARK_ALTERNATIVO = "BND"  # si el fondo analizado es el propio benchmark


def benchmarkParaFondo(ticker, perfil, otro=None):
    """Benchmark del fondo analizado: el del perfil (o el alternativo si coincide); 'otro' si no es un fondo del catalogo."""
    if buscarBono(ticker) is None:
        return otro
    elegido = BENCHMARK_PERFIL.get(perfil, "AGG")
    return BENCHMARK_ALTERNATIVO if elegido == ticker else elegido


def perfilDelFondo(ticker):
    """Perfil al que pertenece un fondo del catalogo (o None)."""
    bono = buscarBono(ticker)
    return bono["perfil"] if bono else None

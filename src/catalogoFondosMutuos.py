"""
catalogoFondosMutuos.py
Catalogo de FONDOS MUTUOS (acciones, bonos y mixtos) por perfil, con lo que
un inversor en fondos mutuos necesita y Yahoo no siempre entrega: gasto anual,
monto minimo de entrada, clase de participacion, como se compra, el ETF
gemelo (misma cartera, sirve para heredar el ranking de bonos y como
referencia de comparacion) y las tolerancias de riesgo por perfil para los
fondos de acciones y mixtos.

Los costos y minimos son los del prospecto mas reciente conocido (2025) y se
usan solo cuando la ficha de Yahoo no los trae; la pantalla siempre pide
verificarlos con la gestora. Todos los supuestos estan aqui, en un solo lugar.
"""

from src.catalogoBonos import buscarBono

CLASE_ACCIONES, CLASE_BONOS, CLASE_MIXTO = "Acciones", "Bonos", "Mixto"

# Cargos: estos fondos indexados y de Vanguard/Fidelity/Schwab no cobran comision
# de compra ni de venta (sin "load"); los minimos son por cuenta en la gestora.
FONDOS_MUTUOS = [
    # --- Acciones ------------------------------------------------------------
    {"ticker": "VFIAX", "nombreSimple": "Las 500 mayores empresas de EE.UU., Vanguard", "clase": CLASE_ACCIONES,
     "categoria": "Acciones de EE.UU. (grandes empresas)", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0004, "minimo": 3000, "gemelo": "VOO", "benchmark": "VOO", "perfiles": ("Moderado", "Agresivo")},
    {"ticker": "VTSAX", "nombreSimple": "Todo el mercado de acciones de EE.UU., Vanguard", "clase": CLASE_ACCIONES,
     "categoria": "Acciones de EE.UU. (todo el mercado)", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0004, "minimo": 3000, "gemelo": "VTI", "benchmark": "VTI", "perfiles": ("Moderado", "Agresivo")},
    {"ticker": "FXAIX", "nombreSimple": "Las 500 mayores empresas de EE.UU., Fidelity", "clase": CLASE_ACCIONES,
     "categoria": "Acciones de EE.UU. (grandes empresas)", "gestora": "Fidelity", "claseParticipacion": "Única",
     "gastoAnual": 0.00015, "minimo": 0, "gemelo": "VOO", "benchmark": "VOO", "perfiles": ("Moderado", "Agresivo")},
    {"ticker": "SWPPX", "nombreSimple": "Las 500 mayores empresas de EE.UU., Schwab", "clase": CLASE_ACCIONES,
     "categoria": "Acciones de EE.UU. (grandes empresas)", "gestora": "Schwab", "claseParticipacion": "Única",
     "gastoAnual": 0.0002, "minimo": 0, "gemelo": "VOO", "benchmark": "VOO", "perfiles": ("Moderado", "Agresivo")},
    {"ticker": "VVIAX", "nombreSimple": "Empresas de valor de EE.UU., Vanguard", "clase": CLASE_ACCIONES,
     "categoria": "Acciones de EE.UU. (valor)", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0005, "minimo": 3000, "gemelo": "VTV", "benchmark": "VTV", "perfiles": ("Moderado", "Agresivo")},
    {"ticker": "VIGAX", "nombreSimple": "Empresas de crecimiento de EE.UU., Vanguard", "clase": CLASE_ACCIONES,
     "categoria": "Acciones de EE.UU. (crecimiento)", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0005, "minimo": 3000, "gemelo": "VUG", "benchmark": "VUG", "perfiles": ("Agresivo",)},
    {"ticker": "VTIAX", "nombreSimple": "Acciones de todo el mundo fuera de EE.UU., Vanguard", "clase": CLASE_ACCIONES,
     "categoria": "Acciones internacionales", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0009, "minimo": 3000, "gemelo": "VXUS", "benchmark": "VXUS", "perfiles": ("Moderado", "Agresivo")},
    # --- Mixtos (acciones + bonos en un solo fondo) ----------------------------
    {"ticker": "VWINX", "nombreSimple": "Mixto conservador Wellesley (1/3 acciones, 2/3 bonos)", "clase": CLASE_MIXTO,
     "categoria": "Mixto conservador", "gestora": "Vanguard", "claseParticipacion": "Investor", "mezclaAcciones": 0.35,
     "gastoAnual": 0.0023, "minimo": 3000, "gemelo": None, "benchmark": "AOK", "perfiles": ("Conservador", "Moderado")},
    {"ticker": "VBIAX", "nombreSimple": "Mixto 60/40 indexado, Vanguard", "clase": CLASE_MIXTO,
     "categoria": "Mixto moderado", "gestora": "Vanguard", "claseParticipacion": "Admiral", "mezclaAcciones": 0.60,
     "gastoAnual": 0.0007, "minimo": 3000, "gemelo": None, "benchmark": "AOR", "perfiles": ("Moderado",)},
    {"ticker": "VWELX", "nombreSimple": "Mixto Wellington (2/3 acciones, 1/3 bonos)", "clase": CLASE_MIXTO,
     "categoria": "Mixto moderado", "gestora": "Vanguard", "claseParticipacion": "Investor", "mezclaAcciones": 0.65,
     "gastoAnual": 0.0026, "minimo": 3000, "gemelo": None, "benchmark": "AOR", "perfiles": ("Moderado", "Agresivo")},
    # --- Bonos (fondo mutuo gemelo de cada ETF del ranking) --------------------
    {"ticker": "VSBSX", "nombreSimple": "Bonos del Tesoro de EE.UU. a 1-3 años, Vanguard", "clase": CLASE_BONOS,
     "categoria": "Bonos del Tesoro, corto plazo", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0007, "minimo": 3000, "gemelo": "VGSH", "benchmark": "VGSH", "perfiles": ("Conservador",)},
    {"ticker": "VTAPX", "nombreSimple": "Bonos protegidos contra la inflación, corto plazo, Vanguard", "clase": CLASE_BONOS,
     "categoria": "Bonos protegidos contra inflación", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0006, "minimo": 3000, "gemelo": "VTIP", "benchmark": "VTIP", "perfiles": ("Conservador",)},
    {"ticker": "VSCSX", "nombreSimple": "Bonos de empresas sólidas, corto plazo, Vanguard", "clase": CLASE_BONOS,
     "categoria": "Bonos corporativos, corto plazo", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0007, "minimo": 3000, "gemelo": "VCSH", "benchmark": "VCSH", "perfiles": ("Conservador",)},
    {"ticker": "VBTLX", "nombreSimple": "Mercado total de bonos de EE.UU., Vanguard", "clase": CLASE_BONOS,
     "categoria": "Bonos de EE.UU. (mercado total)", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0005, "minimo": 3000, "gemelo": "BND", "benchmark": "BND", "perfiles": ("Moderado",)},
    {"ticker": "FXNAX", "nombreSimple": "Mercado total de bonos de EE.UU., Fidelity", "clase": CLASE_BONOS,
     "categoria": "Bonos de EE.UU. (mercado total)", "gestora": "Fidelity", "claseParticipacion": "Única",
     "gastoAnual": 0.00025, "minimo": 0, "gemelo": "AGG", "benchmark": "AGG", "perfiles": ("Moderado",)},
    {"ticker": "VICSX", "nombreSimple": "Bonos de empresas sólidas, plazo intermedio, Vanguard", "clase": CLASE_BONOS,
     "categoria": "Bonos corporativos, plazo intermedio", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0007, "minimo": 3000, "gemelo": "VCIT", "benchmark": "VCIT", "perfiles": ("Moderado",)},
    {"ticker": "VSIGX", "nombreSimple": "Bonos del Tesoro de EE.UU. a 3-10 años, Vanguard", "clase": CLASE_BONOS,
     "categoria": "Bonos del Tesoro, plazo intermedio", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0007, "minimo": 3000, "gemelo": "IEF", "benchmark": "IEF", "perfiles": ("Moderado",)},
    {"ticker": "VTEAX", "nombreSimple": "Bonos municipales de EE.UU., Vanguard", "clase": CLASE_BONOS,
     "categoria": "Bonos municipales", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0009, "minimo": 3000, "gemelo": "MUB", "benchmark": "MUB", "perfiles": ("Moderado",)},
    {"ticker": "VWEHX", "nombreSimple": "Bonos de alto rendimiento, Vanguard", "clase": CLASE_BONOS,
     "categoria": "Bonos de alto rendimiento", "gestora": "Vanguard", "claseParticipacion": "Investor",
     "gastoAnual": 0.0022, "minimo": 3000, "gemelo": "HYG", "benchmark": "HYG", "perfiles": ("Agresivo",)},
    {"ticker": "VEMBX", "nombreSimple": "Bonos de países emergentes, Vanguard", "clase": CLASE_BONOS,
     "categoria": "Bonos de mercados emergentes", "gestora": "Vanguard", "claseParticipacion": "Investor",
     "gastoAnual": 0.0055, "minimo": 3000, "gemelo": "EMB", "benchmark": "EMB", "perfiles": ("Agresivo",)},
    {"ticker": "VLGSX", "nombreSimple": "Bonos del Tesoro de EE.UU. a largo plazo, Vanguard", "clase": CLASE_BONOS,
     "categoria": "Bonos del Tesoro, largo plazo", "gestora": "Vanguard", "claseParticipacion": "Admiral",
     "gastoAnual": 0.0007, "minimo": 3000, "gemelo": "TLT", "benchmark": "TLT", "perfiles": ("Agresivo",)},
]

# Gasto anual de respaldo de los ETF del ranking y de referencia (si Yahoo no lo entrega)
GASTO_ANUAL_ETF = {
    "SGOV": 0.0009, "SHY": 0.0015, "VGSH": 0.0003, "VTIP": 0.0003, "VCSH": 0.0003, "BND": 0.0003, "AGG": 0.0003,
    "VCIT": 0.0003, "IEF": 0.0015, "MUB": 0.0005, "HYG": 0.0049, "JNK": 0.0040, "ANGL": 0.0025, "EMB": 0.0039,
    "TLT": 0.0015, "BIL": 0.0014, "VTI": 0.0003, "VOO": 0.0003, "VXUS": 0.0005, "VUG": 0.0004, "VTV": 0.0004,
    "AOK": 0.0015, "AOR": 0.0015,
}

# Tolerancias de riesgo de cada perfil para fondos de ACCIONES y MIXTOS
# (ventana de 3 anios). Mas alla de 1.25x la tolerancia, «No recomendable».
TOLERANCIAS_RENTA_VARIABLE = {
    "Conservador": {"volatilidadMaxima": 0.12, "caidaTolerada": -0.25},
    "Moderado": {"volatilidadMaxima": 0.20, "caidaTolerada": -0.40},
    "Agresivo": {"volatilidadMaxima": 0.35, "caidaTolerada": -0.60},
}
SHARPE_RECOMENDABLE = 0.30  # Sharpe de 3 anios a partir del cual un fondo de acciones destaca
RETORNO_SUPUESTO_PROSPECTO = 0.05  # el ejemplo de costos del prospecto supone 5% anual

# Nombres sencillos de referencias que no estan en el catalogo de bonos
NOMBRES_REFERENCIA_EXTRA = {
    "VUG": "Empresas de crecimiento de EE.UU. (ETF)", "VTV": "Empresas de valor de EE.UU. (ETF)",
    "VXUS": "Acciones de todo el mundo fuera de EE.UU. (ETF)", "AOK": "Cartera mixta conservadora 30/70, iShares",
    "AOR": "Cartera mixta 60/40, iShares", "AOM": "Cartera mixta 40/60, iShares",
}


def buscarFondoMutuo(ticker):
    """Ficha del catalogo de fondos mutuos para un ticker (o None)."""
    return next((f for f in FONDOS_MUTUOS if f["ticker"] == str(ticker or "").upper()), None)


def esFondoMutuo(ticker):
    return buscarFondoMutuo(ticker) is not None


def fondosMutuosDelPerfil(perfil):
    """Fondos mutuos del catalogo para un perfil, en el orden del catalogo (acciones, mixtos, bonos)."""
    return [f for f in FONDOS_MUTUOS if perfil in f["perfiles"]]


def todosLosTickersMutuos():
    return [f["ticker"] for f in FONDOS_MUTUOS]


def tickersReferencia():
    """Referencias (benchmarks) de los fondos mutuos que no son ETF del ranking de bonos."""
    return list(dict.fromkeys(f["benchmark"] for f in FONDOS_MUTUOS if f["benchmark"] and buscarBono(f["benchmark"]) is None))


def gemeloEtf(ticker):
    """ETF con la misma cartera que el fondo mutuo (o None)."""
    ficha = buscarFondoMutuo(ticker)
    return ficha["gemelo"] if ficha else None


def fondoMutuoGemelo(ticker):
    """Fondo mutuo del catalogo con la misma cartera que un ETF del ranking (o None)."""
    return next((f["ticker"] for f in FONDOS_MUTUOS if f["gemelo"] == ticker), None)


def claseFondoMutuo(ticker):
    """'Acciones', 'Bonos', 'Mixto' o None si no esta en el catalogo."""
    ficha = buscarFondoMutuo(ticker)
    return ficha["clase"] if ficha else None


def gastoAnualDeRespaldo(ticker):
    """Gasto anual del catalogo (fondo mutuo o ETF), o None."""
    ficha = buscarFondoMutuo(ticker)
    if ficha:
        return ficha["gastoAnual"]
    return GASTO_ANUAL_ETF.get(str(ticker or "").upper())


def condicionesDeCompra(ticker, fichaYahoo=None):
    """
    Costos y condiciones para la pantalla: gasto anual (Yahoo o catalogo),
    minimo, clase, cargos, como se compra y a que precio. Nunca falla.
    """
    ficha = buscarFondoMutuo(ticker) or {}
    gastoYahoo = (fichaYahoo or {}).get("gastoAnual")
    gasto = gastoYahoo if gastoYahoo is not None and 0 <= float(gastoYahoo) < 0.05 else gastoAnualDeRespaldo(ticker)
    esMutuo = bool(ficha)
    return {
        "esFondoMutuo": esMutuo,
        "gastoAnual": gasto,
        "fuenteGasto": "ficha de Yahoo" if gastoYahoo is not None and gasto == gastoYahoo else ("prospecto (catálogo)" if gasto is not None else None),
        "minimo": ficha.get("minimo") if esMutuo else 0,
        "claseParticipacion": ficha.get("claseParticipacion") if esMutuo else "ETF",
        "cargoCompra": 0.0, "cargoVenta": 0.0,
        "gestora": ficha.get("gestora") if esMutuo else None,
        "comoSeCompra": ("Directo en la gestora o en un bróker; se compra y se vende una vez al día al precio de cierre (NAV)."
                         if esMutuo else "En cualquier bróker, como una acción: precio de mercado durante el día."),
        "gemelo": ficha.get("gemelo") if esMutuo else fondoMutuoGemelo(ticker),
    }


def costoAcumulado(gastoAnual, monto=10000, anios=(1, 3, 5, 10), retorno=RETORNO_SUPUESTO_PROSPECTO):
    """
    Ejemplo de costos como en el prospecto: cuanto se paga en gastos sobre
    'monto' si el fondo rinde 'retorno' anual bruto. Devuelve {anios: costo}.
    """
    if gastoAnual is None:
        return {}
    g = float(gastoAnual)
    salida = {}
    for n in anios:
        valorBruto = monto * (1 + retorno) ** n
        valorNeto = monto * (1 + retorno - g) ** n
        salida[n] = float(valorBruto - valorNeto)
    return salida


def perfilesDelFondoMutuo(ticker):
    ficha = buscarFondoMutuo(ticker)
    return tuple(ficha["perfiles"]) if ficha else ()
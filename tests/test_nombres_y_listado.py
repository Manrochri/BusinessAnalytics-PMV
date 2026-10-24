"""Nombres sencillos para el usuario y lista de fondos de «Analizar otro fondo»."""

import requests

import src.listadoFondos as lf
from src.catalogoBonos import CATALOGO_BONOS, nombreFondo
from src.utilidades import nombreLegible

CSV_AV = """symbol,name,exchange,assetType,ipoDate,delistingDate,status
QQQ,Invesco QQQ Trust Series 1,NASDAQ,ETF,1999-03-10,null,Active
AAPL,Apple Inc,NASDAQ,Stock,1980-12-12,null,Active
ZZZ-W,Something Warrant,NYSE,ETF,2020-01-01,null,Active
SCHD,Schwab U.S. Dividend Equity ETF,NYSE ARCA,ETF,2011-10-20,null,Active
NEWX,Brand New Thematic ETF,NYSE ARCA,ETF,2025-01-01,null,Active
"""


def test_nombre_sencillo_con_simbolo_al_final():
    assert nombreFondo("VCIT") == "Bonos de empresas sólidas, plazo intermedio (VCIT)"
    assert nombreFondo("VCIT", conTicker=False) == "Bonos de empresas sólidas, plazo intermedio"
    assert nombreFondo("VFIAX", "Vanguard 500 Index Fund Admiral Shares") == "Vanguard 500 Index Fund Admiral Shares (VFIAX)"
    assert nombreFondo("XYZ") == "XYZ"
    assert all(b.get("nombreSimple") for b in CATALOGO_BONOS)  # todo el catalogo tiene nombre en palabras


def test_nombre_legible_de_emisores():
    assert nombreLegible("PARAMOUNT GLOBAL") == "Paramount Global"
    assert nombreLegible("JPMORGAN CHASE & CO") == "JPMorgan Chase & Co"
    assert nombreLegible("AT&T INC") == "AT&T Inc"
    assert nombreLegible("Apple Inc") == "Apple Inc"


def test_listado_alpha_vantage_solo_etf_activos():
    tabla = lf.parsearListado(CSV_AV)
    assert set(tabla["ticker"]) == {"QQQ", "SCHD", "NEWX"}  # sin acciones ni warrants
    assert (tabla["tipo"] == "ETF").all()


def test_listado_completo_y_respaldo_sin_red(tmp_path, monkeypatch):
    import src.utilidades as utilidades

    monkeypatch.setattr(utilidades, "RUTA_CACHE", tmp_path)

    class Respuesta:
        text = CSV_AV

        def raise_for_status(self):
            pass

    monkeypatch.setattr(lf.requests, "get", lambda *a, **k: Respuesta())
    tabla, origen = lf.listarFondos(usarCache=False)
    assert origen == "Alpha Vantage" and {"NEWX", "VFIAX", "VOO"} <= set(tabla["ticker"])
    assert tabla.iloc[0]["ticker"] in ("VFIAX", "VTSAX", "VOO")  # los conocidos primero
    fila = tabla.set_index("ticker").loc["QQQ"]
    assert "Nasdaq" in fila["nombre"]  # el nombre explicado reemplaza al comercial
    assert lf.etiquetaFondo({"ticker": "QQQ", **fila.to_dict()}).endswith("· QQQ · ETF")

    def sinRed(*a, **k):
        raise requests.exceptions.ConnectionError("sin red")

    monkeypatch.setattr(lf.requests, "get", sinRed)
    (tmp_path / lf.ARCHIVO_LISTADO).unlink()
    tabla, origen = lf.listarFondos(usarCache=False)
    assert origen == "respaldo" and "VOO" in set(tabla["ticker"]) and "VFIAX" in set(tabla["ticker"])
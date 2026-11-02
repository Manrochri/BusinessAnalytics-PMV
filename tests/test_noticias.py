"""Pruebas de las fuentes gratuitas de noticias: Yahoo Finance (titulares) y GDELT (tono diario)."""

import numpy as np
import pandas as pd

import src.datosNoticias as dn
from src.datosEstructurados import clasificarRiesgo
from src.motorPrescriptivo import generarSenal


class AnalizadorFalso:
    def polarity_scores(self, texto):
        texto = texto.lower()
        return {"compound": 0.6 if "surge" in texto else (-0.6 if "plunge" in texto else 0.0)}


def test_yahoo_formato_actual_y_anterior(monkeypatch):
    monkeypatch.setattr(dn, "_ANALIZADOR", AnalizadorFalso())
    items = [
        {"id": "1", "content": {"title": "Stocks surge on earnings", "summary": "Big day", "pubDate": "2026-09-18T21:30:00Z",
                                "provider": {"displayName": "Reuters"}, "canonicalUrl": {"url": "https://x/1"}}},
        {"title": "Index futures plunge", "publisher": "AP", "link": "https://x/2", "providerPublishTime": 1758200000},
        {"content": {"title": None}},
    ]
    tabla = dn.parsearNoticiasYahoo(items)
    assert len(tabla) == 2
    primera = tabla.iloc[0]
    assert primera["fuente"] == "Reuters" and primera["url"] == "https://x/1" and primera["sentimiento"] > 0
    assert primera["fecha"] == pd.Timestamp("2026-09-18 17:30")  # 21:30 UTC = 17:30 en Nueva York (horario de verano)
    assert tabla.iloc[1]["sentimiento"] < 0 and tabla.iloc[1]["fuente"] == "AP"


def test_parsear_tono_gdelt():
    contenido = {"timeline": [{"series": "Average Tone", "data": [
        {"date": "20260901T000000Z", "value": -1.5}, {"date": "20260902T000000Z", "value": -0.5}]}]}
    tabla = dn.parsearTonoGdelt(contenido)
    assert list(tabla["tono"]) == [-1.5, -0.5] and tabla["fecha"].iloc[0] == pd.Timestamp("2026-09-01")
    assert dn.parsearTonoGdelt({}).empty


def test_tono_se_usa_desde_el_dia_de_mercado_siguiente():
    dias = pd.bdate_range("2026-09-14", "2026-09-25")
    tono = pd.DataFrame({"tono": [-1.0, -2.0, -3.0]}, index=pd.to_datetime(["2026-09-18", "2026-09-19", "2026-09-20"]))
    serie = dn.alinearTonoADiasBursatiles(tono, dias)
    # viernes, sabado y domingo -> lunes 21 (promediados); nunca el mismo viernes
    assert list(serie.index) == [pd.Timestamp("2026-09-21")]
    assert serie["sentimientoDiario"].iloc[0] == -2.0 and serie["cantidadNoticias"].iloc[0] == 3


def _tonoSintetico(dias=400, ultimo=0.0):
    fechas = pd.date_range(end="2026-10-08", periods=dias, freq="D")
    valores = np.random.default_rng(3).normal(-1.0, 0.3, dias)
    valores[-30:] += ultimo
    return pd.DataFrame({"tono": valores}, index=fechas)


def test_resumen_y_senal_usan_el_tono_contra_su_historia():
    sentimiento = dn.resumirSentimiento(pd.DataFrame(), "2026-10-09", _tonoSintetico(ultimo=+1.0))
    assert sentimiento["fuenteSenal"] == "tono" and sentimiento["zTono"] > 1
    metricas = {"volatilidadAnual": 0.15, "maxDrawdown": -0.1, "beta": 1.0}
    senal = generarSenal(metricas, {"rentabilidadProyectada": np.nan}, clasificarRiesgo(metricas), sentimiento, 21)
    factor = next(f for f in senal["factores"] if f["factor"] == "Sentimiento de noticias")
    assert factor["activo"] and factor["puntos"] == 1
    corto = dn.resumirSentimiento(pd.DataFrame(), "2026-10-09", _tonoSintetico(dias=60))
    assert corto["fuenteSenal"] is None


def test_tono_acumulado_sin_duplicados(tmp_path, monkeypatch):
    import src.utilidades as utilidades

    monkeypatch.setattr(utilidades, "RUTA_CACHE", tmp_path)
    a = pd.DataFrame({"fecha": pd.to_datetime(["2026-09-01", "2026-09-02"]), "tono": [-1.0, -2.0]})
    b = pd.DataFrame({"fecha": pd.to_datetime(["2026-08-31", "2026-09-01"]), "tono": [-3.0, -9.0]})
    dn._fusionarTono(a, '"S&P 500"')
    tabla = dn._fusionarTono(b, '"S&P 500"')
    assert len(tabla) == 3 and tabla.loc["2026-09-01", "tono"] == -9.0  # gana la descarga mas nueva (el dia puede haber estado incompleto)


GOOGLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Google News</title>
<item><title>High-yield bonds surge as spreads tighten - Reuters</title><link>https://news.google.com/rss/articles/abc</link>
<pubDate>Thu, 15 Oct 2026 14:00:00 GMT</pubDate><description>&lt;a href="x"&gt;High-yield bonds surge as spreads tighten&lt;/a&gt;</description>
<source url="https://www.reuters.com">Reuters</source></item>
<item><title>Junk bond funds plunge - Bloomberg</title><link>https://news.google.com/rss/articles/def</link>
<pubDate>Wed, 14 Oct 2026 20:30:00 GMT</pubDate><source url="https://www.bloomberg.com">Bloomberg</source></item>
</channel></rss>"""

YAHOO_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Yahoo! Finance: HYG News</title>
<item><title>High-Yield Bonds Surge As Spreads Tighten</title><link>https://finance.yahoo.com/news/hyg-1.html</link>
<pubDate>Thu, 15 Oct 2026 13:00:00 +0000</pubDate><description>Credit markets rally.</description></item>
</channel></rss>"""


def test_parsear_rss_google_y_yahoo(monkeypatch):
    monkeypatch.setattr(dn, "_ANALIZADOR", AnalizadorFalso())
    google = dn.parsearRss(GOOGLE_RSS, "Google News")
    assert list(google["fuente"]) == ["Reuters", "Bloomberg"]
    assert google.iloc[0]["titulo"] == "High-yield bonds surge as spreads tighten"  # sin " - Reuters"
    assert google.iloc[0]["resumen"] == "" and google.iloc[0]["sentimiento"] > 0 > google.iloc[1]["sentimiento"]
    assert google.iloc[0]["fecha"] == pd.Timestamp("2026-10-15 10:00")  # 14:00 UTC -> Nueva York
    yahoo = dn.parsearRss(YAHOO_RSS, "Yahoo Finance RSS")
    assert yahoo.iloc[0]["fuente"] == "Yahoo Finance RSS" and yahoo.iloc[0]["resumen"] == "Credit markets rally."
    try:
        dn.parsearRss(b"<html>no es rss", "X")
        raise AssertionError("debio fallar")
    except ValueError:
        pass


def test_noticias_combinan_fuentes_aunque_yahoo_falle(tmp_path, monkeypatch):
    import src.utilidades as utilidades

    monkeypatch.setattr(utilidades, "RUTA_CACHE", tmp_path)
    monkeypatch.setattr(dn, "_ANALIZADOR", AnalizadorFalso())
    monkeypatch.setattr(dn, "_consultarYahoo", lambda tickers, cantidad: (None, "Yahoo Finance no devolvió noticias."))

    class Respuesta:
        def __init__(self, contenido):
            self.content = contenido

        def raise_for_status(self):
            pass

    pedidas = []

    def getFalso(url, params=None, headers=None, timeout=None):
        pedidas.append((url, params))
        return Respuesta(YAHOO_RSS if url == dn.URL_YAHOO_RSS else GOOGLE_RSS)

    monkeypatch.setattr(dn.requests, "get", getFalso)
    tabla = dn.descargarNoticias("HYG", 50, usarCache=False, tema='"high-yield bonds"')
    # La nota de Yahoo RSS y la de Google son la misma (mismo titulo): queda una sola (Google va primero)
    assert len(tabla) == 2 and set(tabla["origenNoticia"]) == {"Google News"}
    assert tabla.attrs["fuentes"] == {"Google News": 2, "Yahoo Finance RSS": 1}
    assert "Yahoo Finance no devolvió" in tabla.attrs["motivo"]
    consultasGoogle = [p["q"] for u, p in pedidas if u == dn.URL_GOOGLE_NEWS_RSS]
    # Busca de mas a menos especifica hasta reunir un minimo util (sin comillas en el tema, que Google no necesita)
    assert consultasGoogle[0] == 'high-yield bonds OR "HYG ETF" when:30d' and consultasGoogle[1] == "high-yield bonds when:30d"
    assert len(consultasGoogle) == 3 and "stock market" in consultasGoogle[2]
    # Medios reconocidos pesan 1.0; los demas, menos
    assert dn.relevanciaDelMedio("Reuters") == 1.0 and dn.relevanciaDelMedio("Blog de Juan") == dn.RELEVANCIA_OTROS_MEDIOS
    assert dn.temaTonoPrensa("VWINX", "AOK") == dn.MAPEO_TEMAS_TONO["AOK"] and dn.temaTonoPrensa("ZZZZ") == dn.TEMA_GENERAL


def test_gdelt_lee_el_limite_como_texto_y_completa_12_meses_solo(tmp_path, monkeypatch):
    """GDELT avisa el limite como texto (a veces con estado 200); al actualizar se completan 12 meses sin pedirlo."""
    import json

    import src.utilidades as utilidades

    monkeypatch.setattr(utilidades, "RUTA_CACHE", tmp_path)
    monkeypatch.setattr(dn.time, "sleep", lambda s: None)
    monkeypatch.setattr(dn, "GDELT_PAUSA_SEGUNDOS", 0)
    llamadas = []

    class Respuesta:
        def __init__(self, texto, codigo=200):
            self.text, self.status_code, self.headers = texto, codigo, {}

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self.text)

    def getFalso(url, params=None, headers=None, timeout=None):
        llamadas.append(params)
        if len(llamadas) == 1:  # primera vez: GDELT pide esperar, con estado 200 y texto plano
            return Respuesta("Please limit requests to one every 5 seconds.")
        inicio, fin = pd.to_datetime(params["startdatetime"]), pd.to_datetime(params["enddatetime"])
        datos = [{"date": d.strftime("%Y%m%dT000000Z"), "value": -1.0} for d in pd.date_range(inicio, fin, freq="D")]
        return Respuesta(json.dumps({"timeline": [{"series": "Average Tone", "data": datos}]}))

    monkeypatch.setattr(dn.requests, "get", getFalso)
    tono = dn.descargarTonoPrensa('("bond market" OR "Treasury yields")', usarCache=False)
    hoy = pd.Timestamp.now().normalize()
    assert len(tono) >= 360 and tono.index.min() <= hoy - pd.DateOffset(months=11)
    assert len(llamadas) == 5  # 1 rechazada + 3 meses recientes + 3 ventanas de 3 meses hacia atras
    assert not tono.attrs.get("motivoHistoria")

    def getRechaza(url, params=None, headers=None, timeout=None):
        return Respuesta("Please limit requests to one every 5 seconds.")

    monkeypatch.setattr(dn.requests, "get", getRechaza)
    _, error = dn._consultarGdelt("x", "2026-01-01", "2026-03-01", reintentos=0)
    assert "esperar" in error
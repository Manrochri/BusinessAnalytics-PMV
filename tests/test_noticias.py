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
    # La nota de Yahoo RSS y la de Google son la misma (mismo titulo): queda una sola
    assert len(tabla) == 2 and set(tabla["origenNoticia"]) == {"Yahoo Finance RSS", "Google News"}
    assert tabla.attrs["fuentes"] == {"Yahoo Finance RSS": 1, "Google News": 2}
    assert "Yahoo Finance no devolvió" in tabla.attrs["motivo"]
    consultaGoogle = next(p for u, p in pedidas if u == dn.URL_GOOGLE_NEWS_RSS)["q"]
    assert consultaGoogle == '"high-yield bonds" OR "HYG ETF" when:30d'
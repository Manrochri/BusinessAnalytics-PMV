"""
config.py
Carga la configuracion del proyecto. Ninguna credencial se escribe en el codigo.

Puente de configuracion: el mismo codigo funciona en local y en Streamlit
Community Cloud, sin borrar ni renombrar nada. Cada variable se busca en este
orden y gana la primera que tenga valor:

  1. Variables de entorno del sistema (las que define el servidor o la terminal).
  2. Archivo .env de la raiz del proyecto (desarrollo local; no se sube a Git).
  3. Secretos de Streamlit (st.secrets):
       - en Community Cloud, los que pegas en Settings -> Secrets;
       - en local, .streamlit/secrets.toml (opcional).
     Se aceptan en el nivel raiz (CLAVE = "valor") o dentro de cualquier
     seccion ([fundscope] CLAVE = "valor"); el nivel raiz tiene prioridad.
  4. El valor por defecto escrito en este archivo.

Asi, en tu computadora sigue mandando el .env, y en la nube (donde el .env no
existe porque esta en .gitignore) mandan los secretos de Streamlit.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv

# Carpetas base del proyecto
RUTA_BASE = Path(__file__).resolve().parent
RUTA_DATOS = RUTA_BASE / "data"
RUTA_CACHE = RUTA_DATOS / "cache"
RUTA_SALIDAS = RUTA_DATOS / "salidas"

# 1 y 2: variables del sistema y .env. override=False: lo que ya define el sistema
# (o la nube) no se pisa con el .env. Sin crear carpetas al importar: eso lo hace
# utilidades.asegurarCarpeta() justo antes de escribir.
ARCHIVO_ENV = RUTA_BASE / ".env"
load_dotenv(ARCHIVO_ENV, override=False)

_SECRETOS = None  # se leen una sola vez, la primera vez que se necesitan


def _secretosStreamlit():
    """
    Secretos de Streamlit aplanados en {CLAVE: "valor"}. Devuelve {} si
    Streamlit no esta instalado, si no hay secrets.toml (notebook, pruebas,
    local sin secretos) o si el archivo no se puede leer: nunca detiene la app.
    """
    global _SECRETOS
    if _SECRETOS is not None:
        return _SECRETOS
    _SECRETOS = {}
    try:
        import streamlit as st

        secretos = st.secrets
        # Comprueba si existe algun secrets.toml SIN mostrar errores en la pagina
        if hasattr(secretos, "load_if_toml_exists") and not secretos.load_if_toml_exists():
            return _SECRETOS
        raiz, secciones = {}, {}
        for clave, valor in secretos.items():
            if isinstance(valor, Mapping):
                for subclave, subvalor in valor.items():
                    if not isinstance(subvalor, Mapping):
                        secciones.setdefault(str(subclave), subvalor)
            else:
                raiz[str(clave)] = valor
        _SECRETOS = {k: str(v) for k, v in {**secciones, **raiz}.items() if v is not None}
    except Exception:  # sin streamlit, sin archivo o TOML invalido: se ignoran los secretos
        _SECRETOS = {}
    return _SECRETOS


def origenVariable(nombre):
    """De donde sale una variable: 'entorno o .env', 'secretos de Streamlit' o 'valor por defecto'."""
    if str(os.getenv(nombre) or "").strip():
        return "entorno o .env"
    if str(_secretosStreamlit().get(nombre) or "").strip():
        return "secretos de Streamlit"
    return "valor por defecto"


def describirFuentesConfiguracion():
    """Texto corto con las fuentes de configuracion activas (para la barra lateral)."""
    fuentes = []
    if ARCHIVO_ENV.exists():
        fuentes.append(".env")
    if _secretosStreamlit():
        fuentes.append("secretos de Streamlit")
    return " + ".join(fuentes) if fuentes else "valores por defecto (sin .env ni secretos)"


def leerVariable(nombre, valorPorDefecto=None):
    """Lee una variable: entorno/.env, luego secretos de Streamlit, luego el valor por defecto."""
    valor = os.getenv(nombre)
    if valor is None or str(valor).strip() == "":
        valor = _secretosStreamlit().get(nombre)
    if valor is None or str(valor).strip() == "":
        return valorPorDefecto
    return str(valor).strip()


def leerEntero(nombre, valorPorDefecto):
    """Lee una variable de entorno numerica de forma segura."""
    try:
        return int(leerVariable(nombre, valorPorDefecto))
    except (TypeError, ValueError):
        return valorPorDefecto


def leerDecimal(nombre, valorPorDefecto):
    """Lee una variable de entorno decimal de forma segura."""
    try:
        return float(leerVariable(nombre, valorPorDefecto))
    except (TypeError, ValueError):
        return valorPorDefecto


# ---------------------------------------------------------------------------
# Credenciales y parametros externos
# ---------------------------------------------------------------------------
ALPHA_VANTAGE_API_KEY = leerVariable("ALPHA_VANTAGE_API_KEY", "demo")
ALPHA_VANTAGE_URL = leerVariable("ALPHA_VANTAGE_URL", "https://www.alphavantage.co/query")

OLLAMA_HOST = leerVariable("OLLAMA_HOST", "http://localhost")
OLLAMA_PUERTO = leerEntero("OLLAMA_PUERTO", 11434)
OLLAMA_MODELO = leerVariable("OLLAMA_MODELO", "qwen3:8b")
OLLAMA_TIMEOUT = leerEntero("OLLAMA_TIMEOUT", 180)
OLLAMA_TEMPERATURA = leerDecimal("OLLAMA_TEMPERATURA", 0.3)

# Gemini se usa SOLO como respaldo cuando Qwen3 (Ollama) no esta disponible.
# Clave gratuita: https://aistudio.google.com/apikey
GEMINI_API_KEY = leerVariable("GEMINI_API_KEY", "")
GEMINI_MODELO = leerVariable("GEMINI_MODELO", "gemini-3.6-flash")
GEMINI_URL = leerVariable("GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta/models")
GEMINI_TIMEOUT = leerEntero("GEMINI_TIMEOUT", 60)
GEMINI_TEMPERATURA = leerDecimal("GEMINI_TEMPERATURA", 0.3)

# Override manual del proveedor de IA generativa, SOLO para pruebas.
# Valores validos: "qwen3" o "gemini". Vacio = Qwen3 primero, Gemini de respaldo.
PROVEEDOR_LLM_FORZADO = (leerVariable("PROVEEDOR_LLM_FORZADO", "") or "").lower()

# Segundos que se reutiliza la verificacion del proveedor de IA antes de
# volver a consultarlo (evita esperar a Ollama/Gemini en cada clic).
PROVEEDOR_LLM_TTL = leerEntero("PROVEEDOR_LLM_TTL", 120)

# ---------------------------------------------------------------------------
# Parametros de negocio y de modelado
# ---------------------------------------------------------------------------
# Fondo inicial a analizar. Vacio = el mejor fondo del ranking del perfil elegido.
# Si se indica un ticker del catalogo, se usa cuando pertenece al perfil.
FONDO_POR_DEFECTO = leerVariable("FONDO_POR_DEFECTO", "")
# Benchmark para fondos FUERA del catalogo de bonos (los del catalogo usan el
# del perfil: BIL o AGG). ^SP500TR = S&P 500 con dividendos reinvertidos.
BENCHMARK_POR_DEFECTO = leerVariable("BENCHMARK_POR_DEFECTO", "^SP500TR")
# Ticker alterno para buscar noticias cuando el fondo no tiene cobertura en
# Alpha Vantage. Vacio = se detecta un equivalente automaticamente.
TICKER_NOTICIAS_POR_DEFECTO = leerVariable("TICKER_NOTICIAS", "")
PERIODO_HISTORICO = leerVariable("PERIODO_HISTORICO", "5y")
# Tasa libre de riesgo de respaldo. La app intenta leer la tasa vigente de
# las letras del Tesoro a 13 semanas (^IRX) y usa este valor si no puede.
TASA_LIBRE_RIESGO = leerDecimal("TASA_LIBRE_RIESGO", 0.045)
DIAS_PRONOSTICO = leerEntero("DIAS_PRONOSTICO", 30)
NOTICIAS_LIMITE = leerEntero("NOTICIAS_LIMITE", 50)
PERFIL_POR_DEFECTO = leerVariable("PERFIL_POR_DEFECTO", "Moderado")

# Proyeccion de la CARTERA COMPLETA (acciones + bonos + liquidez) en el Prescriptivo.
# La parte de acciones se simula con la historia mensual de este ETF de mercado amplio
# (o con la del fondo analizado, si es de acciones), re-centrada en un retorno esperado
# anual SUPUESTO. 7% es una referencia prudente de largo plazo para acciones de EE.UU.
# (el promedio historico del S&P 500 con dividendos ronda 10%); ajustalo a tu criterio.
TICKER_RENTA_VARIABLE = leerVariable("TICKER_RENTA_VARIABLE", "VTI")
RETORNO_ESPERADO_ACCIONES = leerDecimal("RETORNO_ESPERADO_ACCIONES", 0.07)
# Volatilidad anual de respaldo si no se pudo descargar la historia de acciones
VOLATILIDAD_ACCIONES_RESPALDO = leerDecimal("VOLATILIDAD_ACCIONES_RESPALDO", 0.16)

# Puerto de la aplicacion Streamlit
APP_PUERTO = leerEntero("APP_PUERTO", 8501)

# Vigencia del cache en horas (el proyecto es manual, no de tiempo real)
CACHE_HORAS_VIGENCIA = leerEntero("CACHE_HORAS_VIGENCIA", 24)

# Cantidad maxima de semanas pasadas que se guardan recalculadas en memoria
SEMANAS_EN_MEMORIA = leerEntero("SEMANAS_EN_MEMORIA", 8)

# ---------------------------------------------------------------------------
# Carteras bono por bono (formulario N-PORT de la SEC)
# ---------------------------------------------------------------------------
# La SEC exige identificarse con nombre y correo en cada consulta automatizada:
# https://www.sec.gov/os/accessing-edgar-data
SEC_USER_AGENT = leerVariable("SEC_USER_AGENT", "FundScope proyecto-academico contacto@ejemplo.com")
# Las carteras N-PORT se publican cada trimestre: se guardan una semana
NPORT_CACHE_DIAS = leerEntero("NPORT_CACHE_DIAS", 7)

# ---------------------------------------------------------------------------
# Historia de noticias
# ---------------------------------------------------------------------------
# Maximo de noticias que se conservan acumuladas por ticker
NOTICIAS_MAXIMO_ACUMULADO = leerEntero("NOTICIAS_MAXIMO_ACUMULADO", 5000)
# Titulares: por defecto se combinan TRES fuentes gratuitas sin clave (Yahoo Finance,
# su RSS y Google News). "alphavantage" la agrega primero (requiere clave; su plan
# gratuito no permite pedir fechas pasadas). Con clave, Alpha Vantage es el ultimo respaldo.
NOTICIAS_FUENTE = (leerVariable("NOTICIAS_FUENTE", "gratuitas") or "gratuitas").lower()
# Tono diario de la prensa (GDELT, gratis y sin clave). Tema de busqueda: vacio =
# se deduce del fondo (p. ej. VFIAX/VOO -> "S&P 500").
TEMA_TONO_PRENSA = leerVariable("TEMA_TONO_PRENSA", "")
# GDELT pide no hacer mas de una consulta cada 5 segundos
GDELT_PAUSA_SEGUNDOS = leerDecimal("GDELT_PAUSA_SEGUNDOS", 5.5)
"""
config.py
Carga la configuracion del proyecto desde el archivo .env.
Ninguna credencial debe escribirse directamente en el codigo.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Carpetas base del proyecto
RUTA_BASE = Path(__file__).resolve().parent
RUTA_DATOS = RUTA_BASE / "data"
RUTA_CACHE = RUTA_DATOS / "cache"
RUTA_SALIDAS = RUTA_DATOS / "salidas"

# Carga de variables de entorno (sin crear carpetas al importar: eso lo hace
# utilidades.asegurarCarpeta() justo antes de escribir)
load_dotenv(RUTA_BASE / ".env")


def leerVariable(nombre, valorPorDefecto=None):
    """Lee una variable de entorno y devuelve un valor por defecto si no existe."""
    valor = os.getenv(nombre)
    if valor is None or str(valor).strip() == "":
        return valorPorDefecto
    return valor.strip()


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
# FundScope: imagen para correr la app de Streamlit en cualquier servidor.
#   construir:  docker build -t fundscope .
#   ejecutar:   docker run -p 8501:8501 --env-file .env fundscope
#   abrir:      http://localhost:8501
FROM python:3.12-slim

# Sin archivos .pyc y salida sin buffer (los registros se ven al instante)
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# Primero las dependencias (se reutiliza la capa si no cambian)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Despues el codigo
COPY . .

# Carpetas de cache y salidas (pueden montarse como volumen para conservarlas)
RUN mkdir -p data/cache data/salidas
VOLUME ["/app/data"]

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]

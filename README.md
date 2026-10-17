# FundScope — Analítica de Fondos Mutuos con IA Generativa
*NUeva versión*
Aplicación web que analiza un fondo mutuo o ETF combinando **datos de mercado** (Yahoo Finance) con **noticias financieras** gratuitas (titulares de Yahoo Finance y tono diario de la prensa de GDELT), y que recomienda **qué hacer según el perfil del inversor**, incluidos los **bonos** que le convienen y **cuánto podría ganar** con ellos.

Las recomendaciones se calculan con reglas auditables y modelos de machine learning evaluados contra líneas base. **Qwen3 en Ollama** (local) las explica en lenguaje natural; Gemini es un respaldo opcional.

> **Flujo:** eliges tu **perfil** → eliges el **fondo a analizar** dentro del grupo de fondos de ese perfil (por defecto, el mejor del ranking) → todo el análisis se hace sobre ese fondo → en el Prescriptivo decides si compras el **fondo completo** o **bonos específicos** de su cartera, y ves la proyección.
>
> La actualización es **manual**: nada se descarga hasta que presionas «Comenzar» o «Actualizar datos».

---

## 1. Qué hace cada pestaña

En la **parte superior** de la app se eligen el **perfil del inversor** (Conservador, Moderado o Agresivo) y el **fondo a analizar**. La lista de fondos es la del grupo del perfil, ordenada por el ranking (🟢 recomendable, 🟡 aceptable, 🔴 no recomendable), y el primero se elige por defecto; con «Otro ticker…» se puede analizar cualquier fondo (p. ej. VFIAX). El benchmark se elige solo: BIL (letras del Tesoro) para Conservador, AGG (mercado de bonos) para Moderado y Agresivo, y `^SP500TR` para fondos fuera del catálogo.

| Pestaña | Pregunta | Contenido |
| --- | --- | --- |
| **Descriptivo** | ¿Qué pasó? | NAV, rentabilidad vs benchmark de retorno total, Sharpe, beta, VaR, caída máxima, riesgo, sentimiento de noticias, el **ranking de fondos de bonos del perfil** (o la indicación de **no invertir** en bonos por ahora) y el **explorador de bonos y emisores** que contiene cada fondo |
| **Predictivo** | ¿Qué podría pasar? | Pronóstico directo del NAV con banda del 90% calibrada, comparación de modelos contra líneas base, y **riesgo de los próximos 3 meses** con un RandomForestClassifier |
| **Prescriptivo** | ¿Qué hago? | **Resumen de tu decisión** arriba (se actualiza con lo que elijas) y cuatro pasos: 1) **cómo invertir** en tu fondo: completo, bonos específicos o liquidez, 2) casilla **«Comprar»** en la tabla de bonos de su cartera, 3) monto y **proyección de la ganancia** de tu elección (★) frente a las alternativas, 4) asignación y plan de acción con CUSIP y lotes. Al final: por qué la señal, backtest, perfiles e informe con IA |
| **Asesor IA** | Dudas puntuales | Chat sobre los datos del análisis y el perfil elegido |

---

## 2. Requisitos

- **Python 3.11 o superior** (probado en 3.13)
- **Ollama** ([ollama.com/download](https://ollama.com/download)) — opcional, para el informe y el chat
- Ninguna clave de API obligatoria: Yahoo Finance, GDELT y la SEC son gratuitos. Alpha Vantage es opcional.

## 3. Instalación

```bash
cd FundScope
python -m venv .venv
# Windows: .venv\Scripts\activate    ·    macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
pip freeze > requirements.lock          # guarda las versiones exactas que quedaron instaladas
cp .env.example .env                    # pon tu nombre y correo en SEC_USER_AGENT
```

Qwen3 (en otra terminal):

```bash
ollama serve
ollama pull qwen3:8b        # ~5 GB; con poca memoria usa qwen3:1.7b y cámbialo en OLLAMA_MODELO
```

La app verifica que el modelo **exacto** configurado esté descargado. Si no hay Ollama y configuras `GEMINI_API_KEY`, usa Gemini (en ese caso los datos del análisis se envían a la API de Google). Sin ninguno, el informe se arma con reglas.

```bash
streamlit run app.py        # http://localhost:8501
```

Pruebas y notebook:

```bash
pip install -r requirements-dev.txt
pytest
jupyter notebook notebooks/FundScope_CRISP_ML_Q.ipynb
```

---

## 4. Cómo usar la aplicación

1. Elige el **perfil** en la parte superior y presiona **Comenzar**: se descargan los 15 fondos de bonos de los tres perfiles, la curva del Tesoro y la tasa libre de riesgo (30-60 s la primera vez).
2. En **Fondo a analizar** queda elegido el mejor fondo de tu perfil. Puedes cambiarlo por otro del grupo o escribir **otro ticker**. Cada fondo se analiza la primera vez que lo eliges (5-15 s) y queda en memoria: volver a él es instantáneo.
3. **Descriptivo**: cómo se comportó el fondo, su puesto en el ranking del perfil (marcado «◀ analizado») y sus bonos y emisores.
4. **Prescriptivo**:
   - Paso 1: elige **cómo invertir**: el fondo completo, **bonos específicos** de su cartera o mantener la renta fija en liquidez. Si el fondo no es recomendable para tu perfil, un botón te lleva al mejor.
   - Paso 2 (bonos específicos): presiona «Cargar los bonos» y **marca la casilla «Comprar»** en los bonos que quieras (o usa «Sugerencia»). Arriba ves «Tu compra»; desmarca para quitar. Los filtros (veredicto, tipo de emisor, plazo, búsqueda por emisor o CUSIP) no borran tu selección.
   - Paso 3: define capital y horizonte; la proyección se actualiza con cada casilla que marcas. ★ marca tu elección.
5. En la barra lateral: periodo, horizonte de pronóstico, benchmark manual (opcional) y **Semana evaluada**, que recalcula todo como si hoy fuera una semana pasada y muestra qué ocurrió después.

«Actualizar datos» vuelve a leer los datos comunes y los del fondo elegido. La casilla «Usar datos en caché» reutiliza lo descargado en las últimas 24 h; si se usa una copia vieja por un error de red, el panel de calidad lo avisa.

---

## 5. Estructura del proyecto

```
FundScope/
├── app.py                         # Perfil y fondo arriba, barra lateral, memoria por fondo y pestañas
├── config.py                      # Lectura del .env
├── requirements.txt / requirements-dev.txt / .env.example
├── src/
│   ├── analisis.py                # Orquestación: datos comunes, datos del fondo y análisis completo (app y notebook)
│   ├── datosEstructurados.py      # Yahoo Finance, métricas, riesgo, tasa libre (^IRX)
│   ├── datosNoticias.py           # Titulares (Yahoo Finance / Alpha Vantage), tono de prensa (GDELT), alineación a días bursátiles
│   ├── preparacionDatos.py        # Variables, división temporal con purga, calidad
│   ├── modeloPredictivo.py        # Ridge, Random Forest, Gradient Boosting, XGBoost, ensamble y líneas base
│   ├── modeloClasificacionRiesgo.py  # RandomForestClassifier del riesgo de los próximos 3 meses
│   ├── catalogoBonos.py           # Bonos por perfil y parámetros de cada perfil
│   ├── analisisBonos.py           # Ranking de fondos de bonos y proyección del fondo
│   ├── datosSec.py                # Cartera bono por bono (formulario N-PORT de la SEC)
│   ├── bonosIndividuales.py       # TIR, duración, calidad implícita, emisores, plan de compra y proyección
│   ├── motorPrescriptivo.py       # Señal, asignación, plan, IA generativa y validación de cifras
│   ├── backtest.py                # Prueba histórica semanal de la señal
│   ├── graficos.py / estilos.py / utilidades.py
│   └── vistas/                    # descriptivo, predictivo, prescriptivo, asesor, bonos, comunes
├── tests/                         # 39 pruebas sin red (datos sintéticos y un N-PORT de ejemplo)
├── notebooks/FundScope_CRISP_ML_Q.ipynb
└── data/cache, data/salidas
```

---

## 6. Cómo funciona por dentro

### Bonos por perfil

| Perfil | Tipo de bonos | Catálogo (ETF → fondo mutuo equivalente) | Base RV / RF / liquidez |
| --- | --- | --- | --- |
| Conservador | Corto plazo, alta calidad | SGOV, SHY, VGSH, VTIP, VCSH | 35 / 55 / 10 |
| Moderado | Intermedio, grado de inversión | BND, AGG, VCIT, IEF, MUB | 60 / 35 / 5 |
| Agresivo | Alto rendimiento, emergentes, largo plazo | HYG, JNK, ANGL, EMB, TLT | 80 / 17 / 3 |

**Ranking (0-100, últimos 3 años):** prima del rendimiento sobre la liquidez 35% · Sharpe 20% · volatilidad 15% · caída máxima 15% · tendencia 15%. Recomendable ≥ 60, Aceptable ≥ 45. **Vetos:** rinde menos que la liquidez (menos la prima mínima del perfil), volatilidad > 1.5 × la tolerada, caída peor que la tolerada, o tendencia bajista. Si ningún bono pasa, la recomendación es **no invertir en bonos de ese perfil por ahora** y la renta fija queda en liquidez.

**Rendimiento esperado** = rendimiento por distribuciones del ETF − pérdida esperada por impagos (0% Tesoro, 1-1.5% alto rendimiento). Todos los supuestos están en `src/catalogoBonos.py`.

**Proyección de ganancia:** 3 000 escenarios Monte Carlo con remuestreo por bloques de 6 meses de los retornos mensuales reales del bono, re-centrados en el rendimiento esperado. Muestra escenario central, rango P10-P90, probabilidad de pérdida y comparación con la liquidez. Admite monto inicial, aporte mensual y un rendimiento editable.

### Noticias y sentimiento (fuentes gratuitas)

| Capa | Fuente | Para qué |
| --- | --- | --- |
| Titulares recientes | Yahoo Finance (por defecto), puntuados con VADER de −1 a +1; Alpha Vantage opcional | Mostrar qué dice la prensa hoy; participan en la señal solo si no hay historia de tono |
| Tono diario de la prensa | GDELT (consulta `timelinetone` del tema del fondo, p. ej. "S&P 500"), acumulado y completable hacia atrás | Historia del sentimiento: entra a la señal (contra su propio último año) y, con suficiente historia, al modelo |

Sin mirar el futuro: un titular posterior al cierre cuenta para el día de mercado siguiente, y el tono de un día calendario se usa desde el día de mercado siguiente.

### Bonos individuales dentro de cada fondo

La cartera completa de cada fondo sale de su último **formulario N-PORT** en la SEC (todo fondo registrado en EE.UU. lo presenta): emisor, CUSIP/ISIN, nominal, valor de mercado, % del fondo, tipo de emisor, país, vencimiento, cupón y si está en impago. El ETF y su fondo mutuo equivalente de Vanguard son la misma serie y comparten cartera (por ejemplo, BND y VBTLX).

Por cada bono se calcula:

| Medida | Cómo |
| --- | --- |
| Precio y TIR | Valor de mercado / nominal; TIR con cupones semestrales |
| Duración modificada | Sensibilidad del precio a un cambio de tasas |
| Diferencial | TIR − tasa del Tesoro del mismo plazo (curva ^IRX, ^FVX, ^TNX, ^TYX) |
| Calidad implícita | Por el diferencial: AA–A < 0.6 pp, BBB < 1.6, BB < 3.5, B < 6, CCC o menor. Tesoro y agencias aparte. **No es una calificación oficial** |
| Rendimiento esperado | TIR − probabilidad de impago anual de su calidad × 60% de pérdida |
| Veredicto | Puntaje (prima 45%, calidad 30%, duración 25%) con vetos del perfil: duración máxima (3.5 / 8 / 20), calidad mínima (AA–A / BBB / B), prima mínima, bonos en impago |

Los emisores (empresas o entidades) se agrupan por su LEI, con número de bonos, peso en el fondo, rendimiento ponderado y su mejor bono.

**Plan de compra:** reparte el monto de renta fija entre los bonos elegidos en lotes reales (USD 100 nominal en el Tesoro, USD 1 000 en el resto) y deja el sobrante en liquidez.

**Proyección de los bonos elegidos (Monte Carlo):** cupones reinvertidos en liquidez, impagos según la calidad (recuperación 40%) y, si el bono vence después del horizonte, venta a la TIR actual más un cambio de tasas tomado de la historia del Tesoro. Se compara con comprar el fondo completo y con la liquidez.

### Modelos predictivos

Se pronostica **directamente** el retorno al horizonte elegido. Datos divididos en entrenamiento / validación / prueba, en orden y con purga. El modelo se elige por validación y se reporta en prueba contra dos líneas base (paseo aleatorio y media histórica). **Si ningún modelo las supera por más de 2%, el pronóstico usa la media histórica y la señal no lo usa.** La banda del 90% sale de los errores de validación y se informa su cobertura real.

| Modelo | Tipo |
| --- | --- |
| Ridge | Lineal regularizado |
| **Random Forest** | Ensamble de árboles |
| Gradient Boosting / XGBoost | Boosting |
| Ensamble | Promedio de los anteriores |

**Clasificador de riesgo (RandomForestClassifier):** predice el riesgo **realizado en los próximos 63 días** (Bajo / Moderado / Alto por volatilidad y caída) con variables que solo usan el pasado, y se compara con la persistencia (suponer que el riesgo sigue igual).

### Señal

| Factor | Puntos | Condición para participar |
| --- | --- | --- |
| Pronóstico del modelo | ±2 | El modelo superó a las líneas base |
| Tendencia (media de 200 días y 6 meses) | ±2 | 200 días de historia |
| Sharpe 12 meses | +1.5 / −1.5 | 6 meses de historia |
| Desempeño vs benchmark 12 meses | ±1 | Benchmark de retorno total |
| Nivel de riesgo | +1 / −2 | — |
| Sentimiento: tono de prensa de 30 días frente a su último año (±1 desviación) | ±1 | ≥ 120 días de tono; si no, titulares (≥ 10 recientes, ±0.15) |

Puntaje ≥ 3 → **COMPRAR** · ≤ −3 → **REDUCIR** · en medio → **MANTENER** (rango real −9.5 a +8.5). La señal mueve como máximo ±5 pp la renta variable del perfil. Un **backtest semanal** muestra qué pasó después de cada señal.

### IA generativa

El LLM recibe un JSON con los indicadores en números y debe **explicar los factores**, no justificar la señal. Toda cifra del texto se compara con el JSON; las que no aparecen se muestran como advertencia.

---

## 7. Solución de problemas

| Problema | Solución |
| --- | --- |
| «No se pudo conectar con Ollama» | `ollama serve` en otra terminal y «Volver a verificar» en la barra lateral |
| «Ollama está activo pero falta el modelo» | `ollama pull` del modelo exacto de `OLLAMA_MODELO` |
| No aparecen titulares | Yahoo Finance no respondió; vuelve a intentar. Si usas Alpha Vantage, revisa la clave (su plan gratuito no da fechas pasadas) |
| Ranking de bonos vacío | Sin conexión a Yahoo: revisa internet y presiona «Actualizar datos» |
| «Historial insuficiente» | Usa un periodo de 5 o 10 años |
| El selector de perfil se ve como botones de radio | Streamlit < 1.40; actualiza con `pip install -U streamlit` |
| «No se pudo obtener la cartera» de un fondo | Revisa internet y `SEC_USER_AGENT` (la SEC rechaza consultas sin nombre y correo); si la SEC no lista el ticker, la app prueba con el fondo mutuo equivalente |
| El sentimiento no entra al modelo | Falta historia: usa «Historia del tono de prensa → Completar» con tantos meses como el periodo histórico (60 para 5 años; ~2 min) y vuelve a actualizar |

---

## 8. Limitaciones

- Yahoo Finance no publica la historia del rendimiento de los bonos ni de la ficha del fondo: en la evaluación por semana se usan los valores de hoy (la app lo avisa).
- Los titulares gratuitos de Yahoo Finance cubren pocos días; la historia del sentimiento viene del tono de GDELT, que oficialmente garantiza 3 meses por consulta (en la práctica suele devolver años anteriores). El sentimiento entra al modelo cuando ≥ 30% de los días de entrenamiento tienen dato. VADER es un analizador general de sentimiento, no especializado en finanzas.
- Las carteras N-PORT se publican con ~60 días de rezago: los precios de los bonos son los de la fecha del reporte (la app la muestra). El precio real de compra será el del mercado.
- La calidad crediticia de cada bono se infiere de su diferencial sobre el Tesoro; no es una calificación de S&P, Moody's ni Fitch. Las probabilidades de impago son promedios históricos aproximados.
- Las proyecciones no incluyen impuestos ni comisiones de intermediación.
- Los fondos mutuos equivalentes son referencia: verifica disponibilidad y montos mínimos.

Proyecto académico. No constituye asesoría financiera.

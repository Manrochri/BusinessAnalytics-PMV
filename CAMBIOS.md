# Cambios de la versión 2.3

- **El fondo analizado sale de la agrupación por perfil.** Junto al perfil hay un selector «Fondo a analizar» con los fondos de bonos de ese perfil en el orden del ranking (🟢/🟡/🔴); por defecto, el mejor. VFIAX deja de ser el fondo por defecto y sigue disponible con «Otro ticker…».
- **Flujo único:** perfil → fondo → Descriptivo, Predictivo y Prescriptivo sobre ese fondo. Cambiar de fondo lo analiza al momento (sin botón) y guarda en memoria los últimos 6 análisis.
- **Benchmark según el perfil:** BIL (letras del Tesoro) en Conservador; AGG (mercado de bonos) en Moderado y Agresivo (BND cuando el fondo es AGG); `^SP500TR` para fondos fuera del catálogo. Se puede fijar uno a mano en la barra lateral.
- **Tono de prensa propio de cada fondo de bonos** (p. ej. «high-yield bonds», «Treasury yields», «municipal bonds», «emerging market debt»).
- **Ajuste táctico coherente con la clase del fondo:** si el fondo analizado es de bonos, la señal COMPRAR suma 5 pp a la renta fija y REDUCIR los pasa a liquidez; el plan de acción habla de entrar a la renta fija, no de «aumentar la posición en un fondo de acciones».
- **Prescriptivo más directo:**
  - Paso 1: «¿Cómo quieres invertir tu renta fija?» — fondo completo, bonos específicos o liquidez. Si el fondo no es recomendable, botón para analizar el mejor del perfil.
  - Paso 2: tabla con casilla **«Comprar»** en cada bono (adiós a la lista desplegable separada de la tabla); «Tu compra» arriba, con «Sugerencia» y «Vaciar». Los filtros no borran la selección.
  - Paso 3: la proyección sigue a tu elección (★) y la compara con el fondo completo y la liquidez.
- Descriptivo: el fondo analizado se marca en el ranking y el explorador de bonos abre en él.
- Datos separados en `descargarComun` (fondos de bonos, curva, tasa) y `descargarFondo`; `descargarBase` se mantiene para el notebook y las pruebas.
- 5 pruebas nuevas (39 en total).

# Cambios de la versión 2.2

- **Noticias sin Alpha Vantage**: su plan gratuito no permite pedir fechas pasadas («premium endpoint»). Ahora:
  - **Titulares** de Yahoo Finance (gratis, sin clave), puntuados con VADER. Alpha Vantage queda como opción (`NOTICIAS_FUENTE`) y se usa como respaldo automático.
  - **Tono diario de la prensa** desde GDELT (gratis, sin clave) sobre el tema del fondo («S&P 500» para VFIAX/VOO). Se acumula en cada actualización y se completa hacia atrás desde la barra lateral («Historia del tono de prensa»).
- La **señal** usa el tono de los últimos 30 días comparado con su propio último año (±1 desviación), porque el tono de GDELT es negativo por naturaleza. Sin 120 días de tono, usa los titulares.
- El **modelo** incluye el sentimiento cuando la historia del tono cubre ≥ 30% del entrenamiento; el panel de calidad dice cuántos meses faltan completar.
- Panel de sentimiento rediseñado (tono, desviación frente a su año, historia y titulares recientes).
- 5 pruebas nuevas (34 en total).

# Cambios de la versión 2.1

- **Bonos específicos dentro de cada fondo**: la cartera completa de cada fondo se obtiene del formulario N-PORT de la SEC. Se mantienen los 15 fondos y su segmentación por perfil.
- **Evaluación individual** de cada bono (TIR, duración, diferencial sobre el Tesoro, calidad implícita, rendimiento esperado, veredicto con motivo) y de cada **emisor** (empresa o entidad).
- **Prescriptivo rediseñado** en cuatro pasos (fondo → bonos → monto y proyección → asignación y plan). El **resumen superior se construye al final con lo que eliges**: si eliges un bono no recomendable, arriba aparece la alerta en rojo y el plan agrega «reemplazar antes de comprar».
- **Plan de compra** con CUSIP, precio de referencia y lotes mínimos reales; la asignación y el plan de acción usan los bonos elegidos.
- **Proyección de bonos individuales** (cupones, impagos, cambios de tasas y tasa de reinversión simulados), comparada con el fondo completo y con la liquidez.
- **Noticias acumulativas**: cada actualización suma las nuevas a las guardadas, y la barra lateral permite pedir meses anteriores.
- **Concordancia**: el fondo analizado aparece como la parte de renta variable EE.UU.; la asignación por defecto ya no combina dos fondos del mismo segmento (como BND y AGG); el ranking del Descriptivo dice «fondos de bonos» y el explorador, «bonos».
- **Fecha correcta de la cartera**: se usa la fecha de las posiciones (`repPdDate`) y no el cierre del año fiscal del fondo.
- 9 pruebas nuevas (29 en total).

# Cambios de la versión 2

## Nuevas funciones

- **Selector de perfil en la parte superior** (Conservador / Moderado / Agresivo). Se aplica al instante en todas las pestañas, sin volver a descargar datos.
- **Bonos segmentados por perfil** (`src/catalogoBonos.py`): 15 ETF de bonos con su fondo mutuo equivalente, cinco por perfil.
- **Ranking de bonos en el dashboard Descriptivo**, con puntaje de 0 a 100, veredicto (Recomendable / Aceptable / No recomendable), motivo de cada veredicto y la indicación explícita de **no invertir** en bonos cuando ninguno compensa su riesgo frente a la liquidez.
- **Asignación con la renta fija repartida entre los bonos del perfil** según el ranking. Si ningún bono califica, esa parte queda en liquidez.
- **Proyección de la ganancia esperada** (Prescriptivo): monto inicial, aporte mensual, horizonte y rendimiento editable. Usa 3 000 escenarios Monte Carlo sobre la historia real del bono e incluye la comparación con la liquidez y con todos los bonos del perfil.
- **Backtest semanal de la señal**.
- **Verificación de cifras del informe de IA**.

## Correcciones del escaneo (hallazgo → cambio)

| # | Hallazgo | Cambio |
| --- | --- | --- |
| 1 | Benchmark de solo precio | Benchmark por defecto `^SP500TR`. Se detecta si el benchmark no es comparable y, en ese caso, no entra en la señal |
| 2 | La señal dependía de la API de noticias | El sentimiento solo participa con ≥ 10 noticias recientes y vale ±1 |
| 3 | Modelos sin habilidad | Pronóstico directo al horizonte, líneas base, validación y prueba separadas con purga. Si ningún modelo supera a las líneas base, la señal no usa el pronóstico |
| 4 | Pronóstico desde el penúltimo dato | Se conserva la fila de hoy; el pronóstico empieza el día hábil siguiente |
| 5 | Clasificador circular | El RandomForestClassifier predice el riesgo realizado en los próximos 63 días y se compara con la persistencia |
| 6 | Noticias de fin de semana perdidas | Cada noticia se asigna al siguiente día bursátil (corte a las 16:00 de Nueva York) |
| 7 | El LLM inventaba cifras | Recibe los datos como números, explica los factores y se verifican sus cifras |
| 8 | La señal nunca daba REDUCIR | Nuevo factor de tendencia, Sharpe de 12 meses y sin doble conteo. El backtest muestra REDUCIR en caídas |
| 9 | Selección y reporte sobre el mismo conjunto | Se elige con validación y se reporta con prueba |
| — | `NaN` en el riesgo, `Unnamed: 0`, rebase del benchmark, anualización fija a 30 días | Corregidos (`valorODefecto`, lectura sin índice, fecha común, horizonte real) |
| — | Caché vieja mostrada como actual | Cada dato lleva su origen y el panel de calidad avisa |
| — | Verificación del proveedor de IA en cada clic | Se reutiliza 120 s, con un botón «Volver a verificar». Ahora se exige el modelo exacto de Ollama |
| — | `app.py` de 1 405 líneas | Dividido en `src/analisis.py` y `src/vistas/*` |
| — | Memoria por semanas evaluadas | Límite configurable (`SEMANAS_EN_MEMORIA`) |
| — | Sin pruebas | 20 pruebas en `tests/` (sin red) |
| — | Dependencias incoherentes | Rangos probados, `requirements-dev.txt` y Python ≥ 3.11 |

Se conserva **Random Forest** en la regresión y en el clasificador de riesgo.

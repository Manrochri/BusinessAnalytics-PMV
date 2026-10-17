"""
asesor.py
Dashboard 4 — chat de seguimiento sobre el análisis ya calculado.
"""

import streamlit as st

from src.motorPrescriptivo import chatearConLLM, construirContexto, nombreProveedor, proveedorListo


def dibujarChatAsesor(datos, perfil, proveedorInfo, decision=None):
    """Chat con Qwen3 (o Gemini de respaldo) sobre los datos del análisis y el perfil elegido."""
    proveedor, estado, _ = proveedorInfo
    marca = f"{datos['fechaCorte']:%Y%m%d}" if datos.get("fechaCorte") is not None else "actual"
    claveHistorial = f"chat_{datos['ticker']}_{marca}"
    st.session_state.setdefault(claveHistorial, [])

    columnas = st.columns([4, 1])
    columnas[0].caption(f"Pregúntale a la IA sobre el análisis de **{datos['ticker']}** para el perfil **{perfil}**. "
                        "Solo conoce los datos calculados en esta sesión; no navega internet.")
    if columnas[1].button("Limpiar chat", use_container_width=True):
        st.session_state[claveHistorial] = []
        st.rerun()

    if not proveedorListo(estado):
        st.warning(f"**{nombreProveedor(proveedor)}**: {estado['mensaje']}")
        st.info("El chat necesita Qwen3 en Ollama, o una GEMINI_API_KEY en el .env como respaldo.")
        return

    for mensaje in st.session_state[claveHistorial]:
        with st.chat_message(mensaje["role"]):
            st.markdown(mensaje["content"])
    if not st.session_state[claveHistorial]:
        with st.chat_message("assistant"):
            st.markdown(f"Hola. Ya revisé el análisis de **{datos['ticker']}**: la señal es **{datos['senal']['accion']}**. "
                        "Puedes preguntarme *¿por qué esa señal?*, *¿por qué me sugieres estos bonos?* o *¿cuánto podría ganar?*")

    pregunta = st.chat_input("Escribe tu pregunta...")
    if pregunta:
        st.session_state[claveHistorial].append({"role": "user", "content": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)
        with st.chat_message("assistant"), st.spinner(f"{nombreProveedor(proveedor)} está pensando..."):
            respuesta, usado = chatearConLLM(st.session_state[claveHistorial], construirContexto(datos, perfil, decision), perfil, proveedorInfo)
            if respuesta:
                st.caption(f"Respondido por {nombreProveedor(usado)}.")
            else:
                respuesta = "No pude conectarme con ningún proveedor de IA. Verifica Ollama o GEMINI_API_KEY e inténtalo de nuevo."
            st.markdown(respuesta)
        st.session_state[claveHistorial].append({"role": "assistant", "content": respuesta})
    st.caption("Respuestas generadas por IA a partir de datos históricos y proyecciones. No constituyen asesoría financiera.")

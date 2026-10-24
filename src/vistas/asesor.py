"""
asesor.py
Dashboard 4 — chat de seguimiento sobre el análisis ya calculado.
"""

import streamlit as st

from src.catalogoBonos import nombreFondo
from src.motorPrescriptivo import (
    chatearConLLM,
    conclusionParaDatos,
    construirContexto,
    proveedorListo,
)

ICONO_DECISION = {"verde": "🟢", "ambar": "🟡", "naranja": "🟠", "roja": "🔴"}


def dibujarChatAsesor(datos, perfil, proveedorInfo, decision=None):
    """Chat con Qwen3 (o Gemini de respaldo) sobre los datos del análisis y el perfil elegido."""
    proveedor, estado, _ = proveedorInfo
    marca = f"{datos['fechaCorte']:%Y%m%d}" if datos.get("fechaCorte") is not None else "actual"
    # Un historial por fondo, perfil y semana: al cambiar de perfil cambia la conclusion
    claveHistorial = f"chat_{datos['ticker']}_{perfil}_{marca}"
    conclusion = (decision or {}).get("conclusion") or conclusionParaDatos(datos, perfil)
    st.session_state.setdefault(claveHistorial, [])

    columnas = st.columns([4, 1])
    columnas[0].caption(f"Pregúntale a la IA sobre **{datos.get('nombreFondo') or datos['ticker']}** para el perfil **{perfil}**. "
                        "Solo conoce los datos calculados en esta sesión; no navega internet.")
    if columnas[1].button("Limpiar chat", use_container_width=True):
        st.session_state[claveHistorial] = []
        st.rerun()

    if not proveedorListo(estado):
        st.info("El asistente de IA no está disponible en este momento. Revisa el estado en el menú lateral.")
        return

    for mensaje in st.session_state[claveHistorial]:
        with st.chat_message(mensaje["role"]):
            st.markdown(mensaje["content"])
    if not st.session_state[claveHistorial]:
        with st.chat_message("assistant"):
            fondoTxt = (f"el fondo es **{conclusion['veredicto'].lower()}** para tu perfil" if conclusion["veredicto"]
                        else "es un fondo fuera del ranking de bonos de tu perfil")
            if conclusion.get("sobre") == "bonos":
                fondoTxt = (f"hablo de los **bonos que elegiste** (el fondo completo es "
                            f"{str(conclusion.get('veredictoFondo') or 'sin ranking').lower()}, pero tus bonos se juzgan por sí mismos)")
            alternativa = (f" Como alternativa, te sugiero **{nombreFondo(conclusion['alternativa'])}**."
                           if conclusion.get("alternativa") else "")
            st.markdown(f"Hola. Ya revisé **{datos.get('nombreFondo') or datos['ticker']}** para tu perfil **{perfil}**. "
                        f"Mi conclusión: {ICONO_DECISION.get(conclusion['tono'], '')} **{conclusion['decision']}**: "
                        f"{fondoTxt} y el momento de entrada es **{conclusion['momento'].lower()}**.{alternativa}\n\n"
                        "Puedes preguntarme *¿por qué esa conclusión?*, *¿qué bonos me convienen?* o *¿cuánto podría ganar?*")

    pregunta = st.chat_input("Escribe tu pregunta...")
    if pregunta:
        st.session_state[claveHistorial].append({"role": "user", "content": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)
        with st.chat_message("assistant"), st.spinner("Pensando…"):
            respuesta, usado = chatearConLLM(st.session_state[claveHistorial], construirContexto(datos, perfil, decision), perfil, proveedorInfo)
            if not respuesta:
                respuesta = "No pude responder en este momento. Inténtalo de nuevo en unos minutos."
            st.markdown(respuesta)
        st.session_state[claveHistorial].append({"role": "assistant", "content": respuesta})
    st.caption("Respuestas generadas por IA a partir de datos históricos y proyecciones. No constituyen asesoría financiera.")
"""
estilos.py
Identidad visual de la aplicacion, tomada de los mockups de referencia:
fondo claro, tarjetas blancas con borde sutil, acento azul, tipografia Inter,
cifras grandes sobre etiquetas pequenas en mayusculas.
"""

from html import escape

import streamlit as st

# Paleta del proyecto: tonos suaves y calmos, con buen contraste (WCAG AA)
# sobre fondo claro. Los nombres se mantienen para no tocar el resto del codigo.
COLORES = {
    "azul": "#3366CC",        # acento principal (azul sereno)
    "azulClaro": "#EEF3FC",
    "azulOscuro": "#1E3F80",
    "verde": "#1E9E6A",       # positivo / recomendable
    "verdeFondo": "#E6F6EE",
    "rojo": "#D9534F",        # negativo / no recomendable (coral, menos agresivo)
    "rojoFondo": "#FDECEA",
    "ambar": "#D98A10",       # precaucion / aceptable
    "ambarFondo": "#FDF4E3",
    "turquesa": "#1A9AA0",
    "grisOscuro": "#4A5568",
    "grisMedio": "#94A3B8",
    "grisClaro": "#F6F8FB",
    "fondo": "#F4F6FA",
    "borde": "#E3E8EF",
    "texto": "#1F2937",
}
# Color por perfil (selector, insignias)
COLOR_PERFIL = {"Conservador": "turquesa", "Moderado": "azul", "Agresivo": "ambar"}

HOJA_ESTILOS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
}}
/* Texto base mas grande y con mas interlineado: se lee sin esfuerzo */
.stApp, .stMarkdown, .stMarkdown p, .stMarkdown li {{
    font-size: 1.02rem;
    line-height: 1.6;
    color: {COLORES['texto']};
}}
.stApp {{ background-color: {COLORES['fondo']}; }}

header[data-testid="stHeader"] {{
    background-color: {COLORES['fondo']};
    height: 3.2rem;
}}
.block-container {{
    padding-top: 4rem;
    padding-bottom: 3rem;
    max-width: 1320px;
}}

/* Titulos */
h1, h2, h3, h4 {{ color: {COLORES['texto']}; letter-spacing: -0.01em; }}
h4 {{ font-size: 1.25rem !important; font-weight: 700 !important; }}

/* Textos de ayuda (st.caption): mas grandes y mas oscuros que el gris de Streamlit */
div[data-testid="stCaptionContainer"], div[data-testid="stCaptionContainer"] p {{
    font-size: 0.93rem !important;
    color: {COLORES['grisOscuro']} !important;
    line-height: 1.55;
}}

/* Etiquetas de los controles */
div[data-testid="stWidgetLabel"] p, label p {{
    font-size: 0.98rem !important;
    font-weight: 600 !important;
    color: {COLORES['texto']} !important;
}}

/* Encabezado de marca */
.cabeceraApp {{
    display: flex; align-items: center; gap: 0.85rem;
    padding: 0.9rem 1.2rem;
    background: linear-gradient(90deg, {COLORES['azulClaro']} 0%, #FFFFFF 100%);
    border: 1px solid {COLORES['borde']};
    border-radius: 16px;
    margin-bottom: 1.4rem;
}}
.logoApp {{
    width: 44px; height: 44px;
    background: {COLORES['azul']};
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    color: #FFFFFF; font-size: 22px;
}}
.nombreApp {{ font-size: 1.65rem; font-weight: 700; color: {COLORES['azulOscuro']}; letter-spacing: -0.02em; }}
.lemaApp {{ font-size: 0.95rem; color: {COLORES['grisOscuro']}; }}
.etiquetaApp {{
    margin-left: auto;
    font-size: 0.8rem; font-weight: 600; color: {COLORES['azul']};
    background: #FFFFFF; border: 1px solid {COLORES['borde']};
    padding: 0.25rem 0.7rem; border-radius: 999px;
}}

/* Tarjetas de indicadores: blancas, sombra suave, etiqueta en minusculas (mas legible) */
.tarjeta {{
    background: #FFFFFF;
    border: 1px solid {COLORES['borde']};
    border-radius: 14px;
    padding: 1.1rem 1.25rem;
    height: 100%;
    box-shadow: 0 1px 3px rgba(31, 41, 55, 0.06);
}}
.tarjetaDestacada {{
    background: {COLORES['verdeFondo']};
    border: 1px solid #B7E4CF;
}}
.tarjetaEtiqueta {{
    font-size: 0.88rem;
    font-weight: 600;
    color: {COLORES['grisOscuro']};
    margin-bottom: 0.35rem;
}}
.tarjetaValor {{
    font-size: 1.75rem;
    font-weight: 700;
    color: {COLORES['texto']};
    line-height: 1.2;
    letter-spacing: -0.01em;
    overflow-wrap: anywhere;
}}
.tarjetaValorLargo {{ font-size: 1.3rem; }}
/* Tarjeta de conclusion: el color de fondo dice la decision */
.tarjetaVerde {{ background: {COLORES['verdeFondo']}; border: 1px solid #B7E4CF; border-left: 6px solid {COLORES['verde']}; }}
.tarjetaVerde .tarjetaValor {{ color: #13704A; }}
.tarjetaAmbar {{ background: {COLORES['ambarFondo']}; border: 1px solid #F3D9A6; border-left: 6px solid {COLORES['ambar']}; }}
.tarjetaAmbar .tarjetaValor {{ color: #9A5B00; }}
.tarjetaNaranja {{ background: #FDEEE3; border: 1px solid #F5C9A8; border-left: 6px solid #D9692B; }}
.tarjetaNaranja .tarjetaValor {{ color: #A2461A; }}
.tarjetaRoja {{ background: {COLORES['rojoFondo']}; border: 1px solid #F5C2C0; border-left: 6px solid {COLORES['rojo']}; }}
.tarjetaRoja .tarjetaValor {{ color: #A8322E; }}
.tarjetaValorPositivo {{ color: {COLORES['verde']}; }}
.tarjetaValorNegativo {{ color: {COLORES['rojo']}; }}
.tarjetaNota {{
    font-size: 0.88rem;
    color: {COLORES['grisOscuro']};
    margin-top: 0.35rem;
    line-height: 1.45;
}}

/* Paneles (st.container(border=True)) */
.panel {{
    background: #FFFFFF;
    border: 1px solid {COLORES['borde']};
    border-radius: 16px;
    padding: 1.4rem 1.5rem;
    margin-bottom: 1.25rem;
}}
div[data-testid="stVerticalBlockBorderWrapper"] {{
    border: 1px solid {COLORES['borde']} !important;
    border-radius: 16px !important;
    background: #FFFFFF;
    margin-bottom: 1.25rem;
    box-shadow: 0 1px 3px rgba(31, 41, 55, 0.05);
}}
div[data-testid="stVerticalBlockBorderWrapper"] > div {{ border-radius: 16px !important; }}
.panelTitulo {{
    font-size: 1.2rem;
    font-weight: 700;
    color: {COLORES['texto']};
    padding-bottom: 0.7rem;
    border-bottom: 1px solid {COLORES['borde']};
    margin-bottom: 1rem;
}}

/* Pasos del Prescriptivo: numero en circulo + titulo + explicacion */
.paso {{ display: flex; gap: 0.9rem; align-items: flex-start; margin: 0.4rem 0 0.9rem 0; }}
.pasoNumero {{
    flex: 0 0 auto; width: 38px; height: 38px; border-radius: 50%;
    background: {COLORES['azul']}; color: #FFFFFF;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 1.1rem;
}}
.pasoTitulo {{ font-size: 1.28rem; font-weight: 700; color: {COLORES['texto']}; line-height: 1.3; }}
.pasoTexto {{ font-size: 0.97rem; color: {COLORES['grisOscuro']}; margin-top: 0.15rem; }}

/* Recuadro «Lo que estás proyectando» */
.eleccion {{
    background: {COLORES['azulClaro']};
    border: 1px solid #CFDCF5;
    border-left: 5px solid {COLORES['azul']};
    border-radius: 12px;
    padding: 0.9rem 1.1rem;
    margin: 0.3rem 0 1rem 0;
}}
.eleccionTitulo {{ font-size: 0.85rem; font-weight: 700; color: {COLORES['azulOscuro']}; text-transform: uppercase; letter-spacing: 0.05em; }}
.eleccionFondo {{ font-size: 1.2rem; font-weight: 700; color: {COLORES['texto']}; margin: 0.2rem 0; }}
.eleccionDetalle {{ font-size: 0.95rem; color: {COLORES['grisOscuro']}; }}
.listaBonos {{ display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.6rem; }}
.chipBono {{
    background: #FFFFFF; border: 1px solid #CFDCF5; border-radius: 10px;
    padding: 0.35rem 0.65rem; font-size: 0.9rem; color: {COLORES['texto']};
}}
.chipBono b {{ color: {COLORES['azulOscuro']}; }}
.chipVerde {{ border-color: #B7E4CF; background: {COLORES['verdeFondo']}; }}
.chipAmbar {{ border-color: #F3D9A6; background: {COLORES['ambarFondo']}; }}
.chipRoja {{ border-color: #F5C2C0; background: {COLORES['rojoFondo']}; }}

/* Barras de asignacion */
.filaAsignacion {{ display: flex; align-items: center; gap: 1rem; padding: 0.5rem 0; }}
.nombreActivo {{ width: 280px; font-size: 0.97rem; color: {COLORES['texto']}; }}
.pistaBarra {{ flex: 1; height: 22px; background: {COLORES['grisClaro']}; border-radius: 8px; overflow: hidden; }}
.rellenoBarra {{ height: 100%; border-radius: 8px; }}
.pesoActivo {{ width: 60px; text-align: right; font-weight: 700; color: {COLORES['texto']}; }}

/* Pestanas: mas grandes, tipo «pastilla» */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0.4rem;
    border-bottom: 1px solid {COLORES['borde']};
}}
.stTabs [data-baseweb="tab"] {{
    height: 48px;
    padding: 0 1.4rem;
    font-weight: 600;
    color: {COLORES['grisOscuro']};
    border-radius: 10px 10px 0 0;
}}
.stTabs [data-baseweb="tab"] p {{ font-size: 1.05rem !important; }}
.stTabs [aria-selected="true"] {{
    color: {COLORES['azul']};
    background: #FFFFFF;
    border: 1px solid {COLORES['borde']};
    border-bottom: 3px solid {COLORES['azul']};
}}

/* Avisos (exito / alerta / error / info) con esquinas suaves */
div[data-testid="stAlert"] {{ border-radius: 12px; }}
div[data-testid="stAlert"] p {{ font-size: 0.98rem; }}

/* Botones */
.stButton > button, .stDownloadButton > button {{
    border-radius: 10px;
    font-weight: 600;
    padding: 0.45rem 1rem;
}}

/* Tablas */
.stDataFrame {{ border-radius: 12px; }}

/* Barra lateral */
section[data-testid="stSidebar"] {{
    background: #FFFFFF;
    border-right: 1px solid {COLORES['borde']};
}}

/* Insignias de estado */
.insignia {{
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
}}
.insigniaVerde {{ background: {COLORES['verdeFondo']}; color: #13704A; }}
.insigniaAmbar {{ background: {COLORES['ambarFondo']}; color: #9A5B00; }}
.insigniaRoja {{ background: {COLORES['rojoFondo']}; color: #A8322E; }}
.insigniaAzul {{ background: {COLORES['azulClaro']}; color: {COLORES['azulOscuro']}; }}
.insigniaTurquesa {{ background: #E3F5F6; color: #12696D; }}
</style>
"""


def aplicarEstilos():
    """Inyecta la hoja de estilos en la aplicacion Streamlit."""
    try:
        st.markdown(HOJA_ESTILOS, unsafe_allow_html=True)
    except Exception as error:
        st.warning(f"No se pudieron aplicar los estilos: {error}")


def mostrarCabecera(subtitulo="Proyecto académico"):
    """Dibuja la cabecera con el nombre de la aplicacion."""
    try:
        st.markdown(
            f"""
            <div class="cabeceraApp">
                <div class="logoApp">📈</div>
                <div>
                    <div class="nombreApp">FundScope</div>
                    <div class="lemaApp">Elige tu perfil y tu fondo: te mostramos qué pasó, qué podría pasar y qué hacer.</div>
                </div>
                <div class="etiquetaApp">{escape(str(subtitulo))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception as error:
        st.title("FundScope")
        st.caption(str(error))


def tarjetaMetrica(etiqueta, valor, nota=None, tono="neutro", destacada=False, color=None):
    """
    Devuelve el HTML de una tarjeta de indicador.
    tono: 'neutro', 'positivo' o 'negativo'.
    """
    try:
        claseValor = {
            "positivo": "tarjetaValor tarjetaValorPositivo",
            "negativo": "tarjetaValor tarjetaValorNegativo",
        }.get(tono, "tarjetaValor")

        if len(str(valor)) > 14:  # textos largos (p. ej. "3 bono(s) de ANGL") en un tamano menor
            claseValor += " tarjetaValorLargo"
        claseTarjeta = "tarjeta tarjetaDestacada" if destacada else "tarjeta"
        if color in ("verde", "ambar", "naranja", "roja"):  # tarjeta de conclusion
            claseTarjeta = f"tarjeta tarjeta{color.capitalize()}"
            claseValor = "tarjetaValor" + (" tarjetaValorLargo" if len(str(valor)) > 14 else "")
        textoNota = f'<div class="tarjetaNota">{escape(str(nota))}</div>' if nota else ""
        etiqueta, valor = escape(str(etiqueta)), escape(str(valor))

        return f"""
        <div class="{claseTarjeta}">
            <div class="tarjetaEtiqueta">{etiqueta}</div>
            <div class="{claseValor}">{valor}</div>
            {textoNota}
        </div>
        """
    except Exception:
        return f"<div class='tarjeta'>{etiqueta}: {valor}</div>"


def abrirPanel(titulo):
    """
    Crea un panel con borde y titulo, para usarse como bloque 'with':

        with abrirPanel("Mi titulo"):
            st.plotly_chart(...)

    Usa st.container(border=True) real de Streamlit: a diferencia de abrir y
    cerrar un <div> en dos llamadas a st.markdown separadas (que NO envuelve
    el contenido intermedio, porque cada st.markdown se renderiza en su
    propio contenedor aislado), esto sí agrupa visualmente todo lo que se
    dibuje dentro del bloque 'with'.
    """
    contenedor = st.container(border=True)
    with contenedor:
        st.markdown(f'<div class="panelTitulo">{escape(str(titulo))}</div>', unsafe_allow_html=True)
    return contenedor


def barraAsignacion(nombre, peso, color=None):
    """Devuelve el HTML de una fila de asignacion con barra de progreso."""
    try:
        colorBarra = color or COLORES["azul"]
        ancho = max(min(float(peso) * 100, 100), 0)
        return f"""
        <div class="filaAsignacion">
            <div class="nombreActivo">{escape(str(nombre))}</div>
            <div class="pistaBarra">
                <div class="rellenoBarra" style="width:{ancho:.1f}%; background:{colorBarra};"></div>
            </div>
            <div class="pesoActivo">{ancho:.0f}%</div>
        </div>
        """
    except Exception:
        return f"<div>{nombre}</div>"


def insignia(texto, tono="azul"):
    """Devuelve el HTML de una insignia de estado."""
    clases = {
        "verde": "insignia insigniaVerde",
        "ambar": "insignia insigniaAmbar",
        "roja": "insignia insigniaRoja",
        "azul": "insignia insigniaAzul",
        "turquesa": "insignia insigniaTurquesa",
    }
    return f'<span class="{clases.get(tono, clases["azul"])}">{escape(str(texto))}</span>'


def encabezadoPaso(numero, titulo, descripcion=""):
    """Titulo de un paso con su numero en un circulo y una linea de explicacion."""
    st.markdown(
        f'<div class="paso"><div class="pasoNumero">{escape(str(numero))}</div><div>'
        f'<div class="pasoTitulo">{escape(str(titulo))}</div>'
        + (f'<div class="pasoTexto">{escape(str(descripcion))}</div>' if descripcion else "")
        + "</div></div>",
        unsafe_allow_html=True,
    )


def recuadroEleccion(titulo, principal, detalle="", chips=()):
    """
    Recuadro destacado con lo que el usuario eligio (fondo y bonos).
    chips: lista de (textoHtmlSeguro, tono) con tono 'verde' / 'ambar' / 'roja' / ''.
    """
    piezas = "".join(f'<span class="chipBono {({"verde": "chipVerde", "ambar": "chipAmbar", "roja": "chipRoja"}).get(tono, "")}">'
                     f"{texto}</span>" for texto, tono in chips)
    return (f'<div class="eleccion"><div class="eleccionTitulo">{escape(str(titulo))}</div>'
            f'<div class="eleccionFondo">{escape(str(principal))}</div>'
            + (f'<div class="eleccionDetalle">{escape(str(detalle))}</div>' if detalle else "")
            + (f'<div class="listaBonos">{piezas}</div>' if piezas else "") + "</div>")
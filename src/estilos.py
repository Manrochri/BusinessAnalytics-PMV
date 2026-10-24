"""
estilos.py
Identidad visual de la aplicacion, tomada de los mockups de referencia:
fondo claro, tarjetas blancas con borde sutil, acento azul, tipografia Inter,
cifras grandes sobre etiquetas pequenas en mayusculas.

Jerarquia tipografica con la proporcion aurea (phi = 1.618): cada nivel es
raiz(phi) = 1.272 veces el anterior, y cada dos niveles, phi.
    --t-1  0.886rem  chips e insignias (lo unico por debajo del texto)
    --t0   1rem      texto, notas, etiquetas, tablas, ayudas
    --t1   1.272rem  pestanas, titulos de paso y de opcion
    --t2   1.618rem  cifras de las tarjetas, titulos de seccion
    --t3   2.058rem  nombre de la app
La raiz es 17 px en PC y 16 px en el celular: toda la escala se ajusta sola.
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

/* Escala aurea (ver la cabecera del modulo) */
:root {{
    --t-1: 0.886rem; --t0: 1rem; --t1: 1.272rem; --t2: 1.618rem; --t3: 2.058rem;
}}
/* !important: theme.baseFontSize (config.toml) se usa solo para las tablas en lienzo */
html {{ font-size: 17px !important; }}
html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
}}
/* Texto base con buen interlineado: se lee sin esfuerzo */
.stApp, .stMarkdown, .stMarkdown p, .stMarkdown li {{
    font-size: var(--t0);
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
h4 {{ font-size: var(--t1) !important; font-weight: 700 !important; }}

/* Textos de ayuda (st.caption): mas grandes y mas oscuros que el gris de Streamlit */
div[data-testid="stCaptionContainer"], div[data-testid="stCaptionContainer"] p {{
    font-size: var(--t0) !important;
    color: {COLORES['grisOscuro']} !important;
    line-height: 1.55;
}}

/* Etiquetas de los controles */
div[data-testid="stWidgetLabel"] p, label p {{
    font-size: var(--t0) !important;
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
.nombreApp {{ font-size: var(--t3); font-weight: 700; color: {COLORES['azulOscuro']}; letter-spacing: -0.02em; }}
.lemaApp {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; }}
.etiquetaApp {{
    margin-left: auto;
    font-size: var(--t-1); font-weight: 600; color: {COLORES['azul']};
    background: #FFFFFF; border: 1px solid {COLORES['borde']};
    padding: 0.25rem 0.7rem; border-radius: 999px;
}}

/* Tarjetas de indicadores: blancas, sombra suave, etiqueta en minusculas (mas legible) */
.tarjeta {{
    background: #FFFFFF;
    border: 1px solid {COLORES['borde']};
    border-radius: 14px;
    padding: 1rem 1.2rem;
    /* Misma altura para todas las tarjetas de una fila: alto fijo, textos acotados */
    height: 10rem; box-sizing: border-box; overflow: hidden;
    display: flex; flex-direction: column;
    box-shadow: 0 1px 3px rgba(31, 41, 55, 0.06);
}}
.tarjetaDestacada {{
    background: {COLORES['verdeFondo']};
    border: 1px solid #B7E4CF;
}}
.tarjetaEtiqueta {{
    font-size: var(--t0);
    font-weight: 600;
    color: {COLORES['grisOscuro']};
    margin-bottom: 0.35rem;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.tarjetaValor {{
    font-size: var(--t2);
    font-weight: 700;
    color: {COLORES['texto']};
    line-height: 1.2;
    letter-spacing: -0.01em;
    overflow-wrap: anywhere;
}}
.tarjetaValorLargo {{ font-size: var(--t1); }}
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
    font-size: var(--t0);
    color: {COLORES['grisOscuro']};
    margin-top: auto;
    line-height: 1.4;
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden;
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
    font-size: var(--t1);
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
    font-weight: 700; font-size: var(--t1);
}}
.pasoTitulo {{ font-size: var(--t1); font-weight: 700; color: {COLORES['texto']}; line-height: 1.3; }}
.pasoTexto {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; margin-top: 0.15rem; }}

/* Recuadro «Lo que estás proyectando» */
.eleccion {{
    background: {COLORES['azulClaro']};
    border: 1px solid #CFDCF5;
    border-left: 5px solid {COLORES['azul']};
    border-radius: 12px;
    padding: 0.9rem 1.1rem;
    margin: 0.3rem 0 1rem 0;
}}
.eleccionTitulo {{ font-size: var(--t-1); font-weight: 700; color: {COLORES['azulOscuro']}; text-transform: uppercase; letter-spacing: 0.05em; }}
.eleccionFondo {{ font-size: var(--t1); font-weight: 700; color: {COLORES['texto']}; margin: 0.2rem 0; }}
.eleccionDetalle {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; }}
.listaBonos {{ display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.6rem; }}
.chipBono {{
    background: #FFFFFF; border: 1px solid #CFDCF5; border-radius: 10px;
    padding: 0.35rem 0.65rem; font-size: var(--t-1); color: {COLORES['texto']};
}}
.chipBono b {{ color: {COLORES['azulOscuro']}; }}
.chipVerde {{ border-color: #B7E4CF; background: {COLORES['verdeFondo']}; }}
.chipAmbar {{ border-color: #F3D9A6; background: {COLORES['ambarFondo']}; }}
.chipRoja {{ border-color: #F5C2C0; background: {COLORES['rojoFondo']}; }}

/* Barras de asignacion */
.filaAsignacion {{ display: flex; align-items: center; gap: 1rem; padding: 0.5rem 0; }}
.nombreActivo {{ width: 280px; font-size: var(--t0); color: {COLORES['texto']}; }}
.pistaBarra {{ flex: 1; height: 22px; background: {COLORES['grisClaro']}; border-radius: 8px; overflow: hidden; }}
.rellenoBarra {{ height: 100%; border-radius: 8px; }}
.pesoActivo {{ width: 60px; text-align: right; font-weight: 700; color: {COLORES['texto']}; }}

/* Pestanas GRANDES: ocupan todo el ancho, botones iguales, la activa en azul.
   Se apunta a los atributos de BaseWeb y a los roles ARIA para cubrir distintas
   versiones de Streamlit. */
.stTabs [data-baseweb="tab-list"], .stTabs [role="tablist"] {{
    display: flex !important; width: 100% !important; gap: 0.5rem; border-bottom: none !important;
    background: {COLORES['grisClaro']}; padding: 0.4rem; border-radius: 14px; overflow: visible !important;
}}
.stTabs [data-baseweb="tab"], .stTabs button[role="tab"] {{
    flex: 1 1 0 !important; justify-content: center !important; min-height: 64px !important; height: auto !important;
    padding: 0.4rem 1rem !important; margin: 0 !important; border-radius: 12px !important;
    color: {COLORES['grisOscuro']} !important; background: transparent; border: none !important;
}}
.stTabs [data-baseweb="tab"] p, .stTabs button[role="tab"] p,
.stTabs [data-baseweb="tab"] div, .stTabs button[role="tab"] div {{
    font-size: var(--t1) !important; font-weight: 700 !important; line-height: 1.25 !important;
}}
.stTabs [data-baseweb="tab"]:hover, .stTabs button[role="tab"]:hover {{ background: #FFFFFF; }}
.stTabs [aria-selected="true"] {{
    background: {COLORES['azul']} !important; color: #FFFFFF !important;
    box-shadow: 0 2px 8px rgba(51, 102, 204, 0.3);
}}
.stTabs [aria-selected="true"] p, .stTabs [aria-selected="true"] div {{ color: #FFFFFF !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none !important; }}
/* Pestanas internas (dentro de otra pestaña): algo mas bajas */
.stTabs .stTabs [data-baseweb="tab"], .stTabs .stTabs button[role="tab"] {{ min-height: 50px !important; }}
.stTabs .stTabs [data-baseweb="tab"] p, .stTabs .stTabs button[role="tab"] p {{ font-size: var(--t0) !important; }}

/* Flujo de 3 pasos arriba de la pagina */
.flujo {{ display: flex; gap: 0.6rem; margin: 0.2rem 0 1.1rem 0; }}
.flujoPaso {{
    flex: 1; display: flex; align-items: center; gap: 0.7rem;
    background: #FFFFFF; border: 1px solid {COLORES['borde']}; border-radius: 12px; padding: 0.7rem 0.9rem;
}}
.flujoPaso.activo {{ border: 2px solid {COLORES['azul']}; background: {COLORES['azulClaro']}; }}
.flujoPaso.listo {{ border-color: #B7E4CF; }}
.flujoNumero {{
    flex: 0 0 auto; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-weight: 700; background: {COLORES['grisClaro']}; color: {COLORES['grisOscuro']}; border: 1px solid {COLORES['borde']};
}}
.flujoPaso.activo .flujoNumero {{ background: {COLORES['azul']}; color: #FFFFFF; border-color: {COLORES['azul']}; }}
.flujoPaso.listo .flujoNumero {{ background: {COLORES['verde']}; color: #FFFFFF; border-color: {COLORES['verde']}; }}
.flujoTitulo {{ font-size: var(--t-1); font-weight: 600; color: {COLORES['grisOscuro']}; text-transform: uppercase; letter-spacing: 0.05em; }}
.flujoValor {{ font-size: var(--t0); font-weight: 700; color: {COLORES['texto']}; line-height: 1.2; }}

/* Tarjetas de OPCION grandes (perfil, fondo, modo): la tarjeta describe, el boton debajo elige */
.opcion {{
    background: #FFFFFF; border: 2px solid {COLORES['borde']}; border-radius: 14px 14px 0 0; border-bottom: none;
    padding: 0.9rem 1rem 0.7rem 1rem;
    /* Altura FIJA para que todas las tarjetas de una fila (y sus botones) queden alineadas,
       sin importar cuanto texto tenga cada una */
    height: 10rem; box-sizing: border-box;
    display: flex; flex-direction: column; overflow: hidden;
}}
.opcion.compacta {{ height: 9.6rem; }}
.opcion.compacta .opcionTitulo {{ font-size: var(--t0); }}
.opcion.compacta .opcionTitulo > span:first-child {{
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }}
.opcion.compacta .opcionSub {{ -webkit-line-clamp: 1; }}
.opcionSub {{ display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden; }}

.opcion.elegida {{ border-color: {COLORES['azul']}; background: {COLORES['azulClaro']}; }}
.opcionTitulo {{ font-size: var(--t1); font-weight: 700; color: {COLORES['texto']}; line-height: 1.2;
                 display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem; }}
.opcionDato {{ font-size: var(--t0); font-weight: 700; color: {COLORES['verde']}; white-space: nowrap; }}
.opcionSub {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; margin-top: 0.2rem; line-height: 1.4; }}
.opcionChip {{
    display: inline-block; margin-top: auto; align-self: flex-start; max-width: 100%;
    padding: 0.15rem 0.6rem; border-radius: 999px; font-size: var(--t-1); font-weight: 600;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.chipVerdeF {{ background: {COLORES['verdeFondo']}; color: #13704A; }}
.chipAmbarF {{ background: {COLORES['ambarFondo']}; color: #9A5B00; }}
.chipRojaF {{ background: {COLORES['rojoFondo']}; color: #A8322E; }}
.chipGrisF {{ background: {COLORES['grisClaro']}; color: {COLORES['grisOscuro']}; }}
/* El boton que va pegado debajo de la tarjeta de opcion */
.opcionBoton + div .stButton > button, div[data-testid="stVerticalBlock"] .stButton > button {{ min-height: 46px; font-size: var(--t0); }}
.stButton > button[kind="primary"] {{ font-weight: 700; }}

/* Controles mas grandes y legibles */
div[data-baseweb="select"] > div {{ min-height: 48px; font-size: var(--t0); }}
div[data-testid="stNumberInput"] input, div[data-testid="stTextInput"] input {{ font-size: var(--t0); min-height: 46px; }}
div[data-testid="stRadio"] label p {{ font-size: var(--t0) !important; }}
div[data-testid="stSlider"] {{ padding-top: 0.3rem; }}

/* Titulo de seccion grande */
.seccion {{ font-size: var(--t2); line-height: 1.25; font-weight: 700; color: {COLORES['texto']}; margin: 1.2rem 0 0.5rem 0; }}
.seccionSub {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; margin-bottom: 0.6rem; }}

/* Avisos (exito / alerta / error / info) con esquinas suaves */
div[data-testid="stAlert"] {{ border-radius: 12px; }}
div[data-testid="stAlert"] p {{ font-size: var(--t0); }}

/* Botones */
.stButton > button, .stDownloadButton > button {{
    border-radius: 10px;
    font-weight: 600;
    padding: 0.45rem 1rem;
}}

/* Tablas -------------------------------------------------------------- */
.stDataFrame {{ border-radius: 12px; }}
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {{ border-radius: 12px; overflow: hidden; }}
/* Tablas cortas en HTML (tablaHtml): letra del tamano del texto, filas
   alternadas, encabezado fijo, cifras a la derecha, desplazamiento lateral */
.tablaFs {{
    width: 100%; overflow: auto; max-height: 34rem; margin: 0.2rem 0 0.8rem 0;
    border: 1px solid {COLORES['borde']}; border-radius: 12px; background: #FFFFFF;
    -webkit-overflow-scrolling: touch;
}}
.tablaFs table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: var(--t0); line-height: 1.45; }}
.tablaFs th {{
    position: sticky; top: 0; z-index: 1; text-align: left; white-space: nowrap;
    background: {COLORES['grisClaro']}; color: {COLORES['grisOscuro']}; font-weight: 700;
    padding: 0.7rem 0.9rem; border-bottom: 2px solid {COLORES['borde']};
}}
.tablaFs td {{
    padding: 0.65rem 0.9rem; color: {COLORES['texto']}; vertical-align: top;
    border-bottom: 1px solid {COLORES['borde']}; min-width: 4.5rem;
}}
.tablaFs tbody tr:nth-child(even) td {{ background: #FAFBFD; }}
.tablaFs tbody tr:hover td {{ background: {COLORES['azulClaro']}; }}
.tablaFs tbody tr:last-child td {{ border-bottom: none; }}
.tablaFs tr.destacada td {{ background: {COLORES['azulClaro']} !important; font-weight: 600; }}
.tablaFs tr.destacada td:first-child {{ box-shadow: inset 4px 0 0 {COLORES['azul']}; }}
.tablaFs .num {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
.tablaFs td {{ background: #FFFFFF; }}
.tablaFs td:first-child:not(.num) {{ font-weight: 600; }}
/* Primera columna fija al desplazar la tabla hacia los lados */
.tablaFs th:first-child, .tablaFs td:first-child {{ position: sticky; left: 0; }}
.tablaFs th:first-child {{ z-index: 2; }}
.tablaVacia {{ color: {COLORES['grisMedio']}; }}
.celdaChip {{ display: inline-block; padding: 0.1rem 0.6rem; border-radius: 999px; font-size: var(--t-1); font-weight: 600; white-space: nowrap; }}

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
    font-size: var(--t-1);
    font-weight: 600;
}}
.insigniaVerde {{ background: {COLORES['verdeFondo']}; color: #13704A; }}
.insigniaAmbar {{ background: {COLORES['ambarFondo']}; color: #9A5B00; }}
.insigniaRoja {{ background: {COLORES['rojoFondo']}; color: #A8322E; }}
.insigniaAzul {{ background: {COLORES['azulClaro']}; color: {COLORES['azulOscuro']}; }}
.insigniaTurquesa {{ background: #E3F5F6; color: #12696D; }}
/* Detalles plegables (st.expander): titulo legible, sin ruido */
div[data-testid="stExpander"] details {{ border-radius: 12px; border: 1px solid {COLORES['borde']}; background: #FFFFFF; }}
div[data-testid="stExpander"] summary p {{ font-size: var(--t0); font-weight: 600; color: {COLORES['texto']}; }}

/* Subtitulos de seccion (h5) */
h5 {{ font-size: var(--t1) !important; font-weight: 700 !important; margin: 0.6rem 0 0.4rem 0 !important; }}

/* ------------------------------------------------------------------ */
/* Celular y pantallas angostas: una columna, cifras mas compactas,    */
/* pestanas desplazables y menos margen lateral                        */
/* ------------------------------------------------------------------ */
@media (max-width: 640px) {{
    /* La raiz baja a 16 px: toda la escala aurea se reduce en proporcion */
    html {{ font-size: 16px !important; }}
    .block-container {{ padding: 3.6rem 0.8rem 2rem 0.8rem; }}
    .cabeceraApp {{ padding: 0.6rem 0.8rem; gap: 0.6rem; margin-bottom: 0.9rem; }}
    .logoApp {{ width: 36px; height: 36px; font-size: 18px; }}
    .nombreApp {{ font-size: var(--t2); }}
    .lemaApp, .etiquetaApp {{ display: none; }}
    .tarjeta {{ padding: 0.85rem 1rem; margin-bottom: 0.5rem; height: auto; min-height: 0; }}
    .tarjetaNota {{ -webkit-line-clamp: 3; }}
    .paso {{ gap: 0.6rem; }}
    .pasoNumero {{ width: 30px; height: 30px; font-size: var(--t0); }}
    .nombreActivo {{ width: 46%; }}
    .pesoActivo {{ width: 44px; }}
    .stTabs [data-baseweb="tab-list"], .stTabs [role="tablist"] {{ flex-wrap: wrap !important; gap: 0.35rem; }}
    .stTabs [data-baseweb="tab"], .stTabs button[role="tab"] {{ flex: 1 1 45% !important; min-height: 54px !important; padding: 0.3rem 0.5rem !important; }}
    .stTabs [data-baseweb="tab"] p, .stTabs button[role="tab"] p {{ font-size: var(--t0) !important; }}
    .flujo {{ flex-direction: column; gap: 0.4rem; }}
    .flujoPaso {{ padding: 0.5rem 0.7rem; }}
    .opcion, .opcion.compacta {{ height: auto; padding: 0.7rem 0.8rem 0.5rem 0.8rem; }}
    .opcionChip {{ margin-top: 0.45rem; }}
    .opcionTitulo {{ font-size: var(--t1); }}
    .seccion {{ font-size: var(--t1); }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{ margin-bottom: 0.8rem; }}
    .eleccion {{ padding: 0.75rem 0.85rem; }}
    .tablaFs th, .tablaFs td {{ padding: 0.55rem 0.7rem; }}
    /* En el celular el texto no se aprieta: la tabla se desplaza de lado */
    .tablaFs td:not(.num) {{ min-width: 10rem; }}
    .tablaFs td:first-child:not(.num) {{ min-width: 8.5rem; max-width: 9.5rem; box-shadow: 2px 0 0 {COLORES['borde']}; }}
    .tablaFs {{ max-height: 28rem; }}
}}
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
                    <div class="lemaApp">Elige tu perfil y tu fondo; te decimos si conviene invertir.</div>
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
        textoNota = f'<div class="tarjetaNota" title="{escape(str(nota))}">{escape(str(nota))}</div>' if nota else ""
        etiqueta, valor = escape(str(etiqueta)), escape(str(valor))

        return f"""
        <div class="{claseTarjeta}">
            <div class="tarjetaEtiqueta" title="{etiqueta}">{etiqueta}</div>
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


def flujoPasos(pasos):
    """
    Barra de flujo de 3 pasos. pasos = lista de dicts {titulo, valor, estado}
    con estado 'listo' (verde), 'activo' (azul) o '' (pendiente).
    """
    piezas = []
    for i, p in enumerate(pasos, 1):
        marca = "✓" if p.get("estado") == "listo" else str(i)
        piezas.append(f'<div class="flujoPaso {p.get("estado", "")}"><div class="flujoNumero">{marca}</div><div>'
                      f'<div class="flujoTitulo">{escape(str(p["titulo"]))}</div>'
                      f'<div class="flujoValor">{escape(str(p["valor"]))}</div></div></div>')
    return '<div class="flujo">' + "".join(piezas) + "</div>"


def tarjetaOpcion(titulo, subtitulo="", chip=None, tonoChip="gris", elegida=False, compacta=False, dato=None):
    """Tarjeta descriptiva de una opcion grande; el boton de eleccion se dibuja debajo con st.button."""
    clases = {"verde": "chipVerdeF", "ambar": "chipAmbarF", "roja": "chipRojaF"}.get(tonoChip, "chipGrisF")
    textoChip = f'<span class="opcionChip {clases}">{escape(str(chip))}</span>' if chip else ""
    clasesTarjeta = " ".join(c for c in ("opcion", "elegida" if elegida else "", "compacta" if compacta else "") if c)
    textoDato = f'<span class="opcionDato">{escape(str(dato))}</span>' if dato else ""
    return (f'<div class="{clasesTarjeta}" title="{escape(str(subtitulo))}"><div class="opcionTitulo"><span>{escape(str(titulo))}</span>{textoDato}</div>'
            + (f'<div class="opcionSub">{escape(str(subtitulo))}</div>' if subtitulo else "") + textoChip + "</div>")


def tituloSeccion(titulo, subtitulo=""):
    st.markdown(f'<div class="seccion">{escape(str(titulo))}</div>'
                + (f'<div class="seccionSub">{escape(str(subtitulo))}</div>' if subtitulo else ""), unsafe_allow_html=True)
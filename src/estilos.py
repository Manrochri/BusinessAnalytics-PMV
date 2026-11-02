"""
estilos.py
Identidad visual de FundScope, pensada como un libro de cuentas moderno:
papel frio, tinta azul oscura, cifras grandes en serif y un solo acento
(azul petroleo) que marca lo elegido. Los veredictos usan tres tonos
(musgo / ocre / teja) y nada mas lleva color.

Tipografia: Fraunces (titulos y cifras) + Source Sans 3 (texto y controles).
Escala aurea (phi = 1.618; cada nivel x 1.272):
    --t-1 0.886rem chips      --t0 1rem texto      --t1 1.272rem titulos de paso
    --t2 1.618rem cifras      --t3 2.058rem secciones   --t4 2.618rem portada
Raiz de 17 px en PC y 16 px en el celular.
"""

from html import escape

import streamlit as st

# Paleta. Los nombres antiguos (azul, verde, rojo, ambar, gris...) se mantienen
# porque los usan los graficos y las vistas; cambian los valores.
COLORES = {
    "azul": "#1E5A86",        # petroleo: acento, lo elegido, enlaces
    "azulClaro": "#E7EFF5",
    "azulOscuro": "#16233A",  # tinta
    "verde": "#2F7D5B",       # musgo: recomendable / positivo
    "verdeFondo": "#E6F1EB",
    "rojo": "#B94A48",        # teja: no recomendable / negativo
    "rojoFondo": "#F8E8E7",
    "ambar": "#B8791E",       # ocre: aceptable / precaucion
    "ambarFondo": "#F7EFE0",
    "turquesa": "#1E7F86",
    "grisOscuro": "#4E5A6B",
    "grisMedio": "#9AA5B4",
    "grisClaro": "#EEF1F4",
    "fondo": "#F3F5F7",       # papel frio
    "borde": "#D9DEE5",
    "texto": "#16233A",
}
COLOR_PERFIL = {"Conservador": "turquesa", "Moderado": "azul", "Agresivo": "ambar"}

HOJA_ESTILOS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT@9..144,500;9..144,600;9..144,700,100&family=Source+Sans+3:wght@400;600;700&display=swap');

:root {{
    --t-1: 0.886rem; --t0: 1rem; --t1: 1.272rem; --t2: 1.618rem; --t3: 2.058rem; --t4: 2.618rem;
    --serif: 'Fraunces', Georgia, serif;
    --sans: 'Source Sans 3', -apple-system, 'Segoe UI', sans-serif;
    --tinta: {COLORES['texto']}; --petroleo: {COLORES['azul']}; --papel: {COLORES['fondo']}; --borde: {COLORES['borde']};
}}
html {{ font-size: 17px !important; }}
html, body, [class*="css"], .stApp, .stMarkdown, button, input, select, textarea {{ font-family: var(--sans); }}
.stApp, .stMarkdown, .stMarkdown p, .stMarkdown li {{ font-size: var(--t0); line-height: 1.55; color: var(--tinta); }}
.stApp {{ background-color: var(--papel); }}
header[data-testid="stHeader"] {{ background-color: var(--papel); height: 2.8rem; }}
.block-container {{ padding-top: 3.4rem; padding-bottom: 3rem; max-width: 1180px; }}

/* Titulos en serif: son la voz de la app */
h1, h2, h3, h4, h5 {{ font-family: var(--serif); color: var(--tinta); letter-spacing: -0.01em; font-weight: 600; }}
h4 {{ font-size: var(--t1) !important; }}
h5 {{ font-size: var(--t1) !important; margin: 0.8rem 0 0.4rem 0 !important; }}

div[data-testid="stCaptionContainer"], div[data-testid="stCaptionContainer"] p {{
    font-size: var(--t0) !important; color: {COLORES['grisOscuro']} !important; line-height: 1.5;
}}
div[data-testid="stWidgetLabel"] p, label p {{ font-size: var(--t0) !important; font-weight: 600 !important; color: var(--tinta) !important; }}

/* Marca: una linea, sin caja */
.cabeceraApp {{ display: flex; align-items: baseline; gap: 0.8rem; padding: 0.2rem 0 0.9rem 0; border-bottom: 1px solid var(--borde); margin-bottom: 1.1rem; }}
.logoApp {{ display: none; }}
.nombreApp {{ font-family: var(--serif); font-size: var(--t2); font-weight: 700; color: var(--tinta); letter-spacing: -0.02em; }}
.lemaApp {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; }}
.etiquetaApp {{ margin-left: auto; font-size: var(--t-1); color: {COLORES['grisOscuro']}; }}

/* Portada */
.hero {{ padding: 2.2rem 0 1.4rem 0; max-width: 46rem; }}
.heroTitulo {{ font-family: var(--serif); font-size: var(--t4); line-height: 1.12; font-weight: 600; color: var(--tinta); margin: 0 0 0.8rem 0; letter-spacing: -0.015em; }}
.heroTitulo em {{ font-style: italic; font-weight: 500; color: var(--petroleo); }}
.heroTexto {{ font-size: var(--t1); line-height: 1.5; color: {COLORES['grisOscuro']}; margin: 0 0 1.2rem 0; }}
.heroPasos {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 0.6rem 0 1.4rem 0; }}
.heroPaso {{ border-top: 2px solid var(--tinta); padding-top: 0.6rem; }}
.heroPaso b {{ display: block; font-family: var(--serif); font-size: var(--t1); font-weight: 600; margin-bottom: 0.15rem; }}
.heroPaso span {{ color: {COLORES['grisOscuro']}; }}

/* Riel de pasos (arriba, fijo): en que paso estas y que elegiste */
.flujo {{ display: flex; gap: 0; margin: 0 0 1.2rem 0; border: 1px solid var(--borde); border-radius: 10px; background: #FFFFFF; overflow: hidden; }}
.flujoPaso {{ flex: 1; display: flex; align-items: center; gap: 0.65rem; padding: 0.6rem 0.9rem; border-right: 1px solid var(--borde); min-width: 0; }}
.flujoPaso:last-child {{ border-right: none; }}
.flujoPaso.activo {{ background: {COLORES['azulClaro']}; box-shadow: inset 0 -3px 0 var(--petroleo); }}
.flujoNumero {{ flex: 0 0 auto; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
               font-family: var(--serif); font-weight: 600; font-size: var(--t0); background: {COLORES['grisClaro']}; color: {COLORES['grisOscuro']}; }}
.flujoPaso.activo .flujoNumero {{ background: var(--petroleo); color: #FFFFFF; }}
.flujoPaso.listo .flujoNumero {{ background: var(--tinta); color: #FFFFFF; }}
.flujoTitulo {{ font-size: var(--t-1); color: {COLORES['grisOscuro']}; }}
.flujoValor {{ font-size: var(--t0); font-weight: 600; color: var(--tinta); line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}

/* El riel queda FIJO arriba al desplazarse: se fija el contenedor de Streamlit que lo
   envuelve (su padre es la pagina entera; el propio .flujo tiene un padre de su misma
   altura y no serviria). :has() existe en todos los navegadores actuales. */
/* Se fija el HIJO DIRECTO del bloque principal de la pagina que contiene el riel
   (cualquiera que sea su etiqueta en la version de Streamlit): su padre es la
   pagina entera, que es lo que necesita position: sticky para funcionar. */
.block-container > [data-testid="stVerticalBlock"] > div:has(.flujo),
div[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > div:has(.flujo),
[data-testid="stVerticalBlock"] > div:has(> div > [data-testid="stVerticalBlock"] .flujo),
.st-key-riel {{
    position: -webkit-sticky; position: sticky !important; top: 2.875rem !important; z-index: 60; background: var(--papel);
    border: none !important; margin: 0 !important; padding: 0.25rem 0 0.35rem 0; overflow: visible !important;
}}
.st-key-riel > div, .st-key-riel div {{ overflow: visible !important; }}
/* Ningun ancestro del riel puede recortar (overflow), o el sticky no funciona */
div[data-testid="stMainBlockContainer"], div[data-testid="stAppViewBlockContainer"], .block-container,
div[data-testid="stMainBlockContainer"] > div, [data-testid="stVerticalBlock"]:has(.flujo),
[data-testid="stVerticalBlockBorderWrapper"]:has(.flujo), [data-testid="stLayoutWrapper"]:has(.flujo) {{ overflow: visible !important; }}
.flujo a, .flujo a:hover, .flujo a:visited {{ text-decoration: none; color: inherit; }}
.flujoPaso:hover {{ background: {COLORES['grisClaro']}; }}
.flujoPaso.activo:hover {{ background: {COLORES['azulClaro']}; }}
.flujoPaso:focus-visible {{ outline: 3px solid {COLORES['azulClaro']}; outline-offset: -3px; }}
.flujoTexto {{ min-width: 0; }}
/* Al saltar a una seccion, que no quede escondida bajo el riel */
.ancla {{ scroll-margin-top: 8.5rem; height: 0; }}
.seccion[id] {{ scroll-margin-top: 8.5rem; }}
html {{ scroll-behavior: smooth; }}
@media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}

/* Titulos de seccion */
.seccion {{ font-family: var(--serif); font-size: var(--t3); font-weight: 600; color: var(--tinta); margin: 1.4rem 0 0.3rem 0; line-height: 1.15; letter-spacing: -0.015em; }}
.seccionSub {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; margin-bottom: 0.7rem; max-width: 52rem; }}

/* Tarjetas de indicadores: borde fino, cifra en serif, sin sombra */
.tarjeta {{ background: #FFFFFF; border: 1px solid var(--borde); border-radius: 10px; padding: 0.9rem 1.1rem;
           height: 10rem; box-sizing: border-box; overflow: hidden; display: flex; flex-direction: column; }}
.tarjetaDestacada {{ background: {COLORES['verdeFondo']}; border-color: #BFDCCB; }}
.tarjetaEtiqueta {{ font-size: var(--t0); font-weight: 600; color: {COLORES['grisOscuro']}; margin-bottom: 0.3rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.tarjetaValor {{ font-family: var(--serif); font-size: var(--t2); font-weight: 600; color: var(--tinta); line-height: 1.15; letter-spacing: -0.01em;
                overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }}
.tarjetaValorLargo {{ font-size: var(--t1); }}
/* La tarjeta de conclusion es el unico elemento con color de fondo: la decision se ve desde lejos */
.tarjetaVerde {{ background: {COLORES['verdeFondo']}; border-color: #BFDCCB; border-left: 6px solid {COLORES['verde']}; }}
.tarjetaVerde .tarjetaValor {{ color: #1F5C41; }}
.tarjetaAmbar {{ background: {COLORES['ambarFondo']}; border-color: #E6D2A8; border-left: 6px solid {COLORES['ambar']}; }}
.tarjetaAmbar .tarjetaValor {{ color: #7E5412; }}
.tarjetaNaranja {{ background: #F8EBE2; border-color: #E8C9B3; border-left: 6px solid #B9602C; }}
.tarjetaNaranja .tarjetaValor {{ color: #8A431B; }}
.tarjetaRoja {{ background: {COLORES['rojoFondo']}; border-color: #E6BDBC; border-left: 6px solid {COLORES['rojo']}; }}
.tarjetaRoja .tarjetaValor {{ color: #8E3331; }}
.tarjetaValorPositivo {{ color: {COLORES['verde']}; }}
.tarjetaValorNegativo {{ color: {COLORES['rojo']}; }}
.tarjetaNota {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; margin-top: auto; line-height: 1.35;
               display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }}

/* Paneles */
.panel {{ background: #FFFFFF; border: 1px solid var(--borde); border-radius: 10px; padding: 1.2rem 1.3rem; margin-bottom: 1.1rem; }}
div[data-testid="stVerticalBlockBorderWrapper"] {{ border: 1px solid var(--borde) !important; border-radius: 10px !important; background: #FFFFFF; margin-bottom: 1.1rem; }}
div[data-testid="stVerticalBlockBorderWrapper"] > div {{ border-radius: 10px !important; }}
.panelTitulo {{ font-family: var(--serif); font-size: var(--t1); font-weight: 600; color: var(--tinta); padding-bottom: 0.55rem; border-bottom: 1px solid var(--borde); margin-bottom: 0.9rem; }}

/* Pasos del Prescriptivo */
.paso {{ display: flex; gap: 0.8rem; align-items: flex-start; margin: 0.3rem 0 0.8rem 0; }}
.pasoNumero {{ flex: 0 0 auto; width: 34px; height: 34px; border-radius: 50%; background: var(--tinta); color: #FFFFFF; display: flex; align-items: center; justify-content: center; font-family: var(--serif); font-weight: 600; font-size: var(--t0); }}
.pasoTitulo {{ font-family: var(--serif); font-size: var(--t1); font-weight: 600; color: var(--tinta); line-height: 1.25; }}
.pasoTexto {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; margin-top: 0.1rem; }}

/* «Lo que estas proyectando» */
.eleccion {{ background: #FFFFFF; border: 1px solid var(--borde); border-left: 5px solid var(--petroleo); border-radius: 10px; padding: 0.8rem 1rem; margin: 0.3rem 0 1rem 0; }}
.eleccionTitulo {{ font-size: var(--t-1); font-weight: 600; color: {COLORES['grisOscuro']}; }}
.eleccionFondo {{ font-family: var(--serif); font-size: var(--t1); font-weight: 600; color: var(--tinta); margin: 0.15rem 0; }}
.eleccionDetalle {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; }}
.listaBonos {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.55rem; }}
.chipBono {{ background: {COLORES['grisClaro']}; border: 1px solid var(--borde); border-radius: 8px; padding: 0.3rem 0.6rem; font-size: var(--t-1); color: var(--tinta); }}
.chipBono b {{ color: var(--tinta); }}
.chipVerde {{ border-color: #BFDCCB; background: {COLORES['verdeFondo']}; }}
.chipAmbar {{ border-color: #E6D2A8; background: {COLORES['ambarFondo']}; }}
.chipRoja {{ border-color: #E6BDBC; background: {COLORES['rojoFondo']}; }}

/* Barras de asignacion */
.filaAsignacion {{ display: flex; align-items: center; gap: 0.9rem; padding: 0.45rem 0; }}
.nombreActivo {{ width: 280px; font-size: var(--t0); color: var(--tinta); }}
.pistaBarra {{ flex: 1; height: 18px; background: {COLORES['grisClaro']}; border-radius: 4px; overflow: hidden; }}
.rellenoBarra {{ height: 100%; border-radius: 4px; }}
.pesoActivo {{ width: 60px; text-align: right; font-weight: 600; color: var(--tinta); font-variant-numeric: tabular-nums; }}

/* Pestanas: una regla subrayada, la activa en tinta. Cada pestana es un
   bloque ancho con aire a los lados; en Streamlit >= 1.50 el contenedor ya no
   usa BaseWeb, por eso se apunta a data-testid y a los roles ARIA. */
div[data-testid="stTabs"] [role="tablist"], .stTabs [role="tablist"], .stTabs [data-baseweb="tab-list"] {{
    display: flex !important; flex-wrap: nowrap; width: 100% !important; gap: 0.75rem !important;
    border-bottom: 2px solid var(--borde) !important; background: transparent; padding: 0 !important; border-radius: 0; overflow: visible !important;
}}
div[data-testid="stTabs"] [role="tab"], .stTabs [role="tab"], .stTabs [data-baseweb="tab"] {{
    flex: 1 1 0 !important; min-width: 0 !important; max-width: none !important; width: auto !important; box-sizing: border-box;
    display: flex !important; justify-content: center !important; align-items: center !important; text-align: center;
    min-height: 60px !important; height: auto !important; padding: 0.5rem 0.9rem !important; margin: 0 0 -2px 0 !important;
    border-radius: 8px 8px 0 0 !important; border: none !important; border-bottom: 3px solid transparent !important;
    box-shadow: none !important; outline: none; overflow: visible !important;
    background: transparent !important; color: {COLORES['grisOscuro']} !important; white-space: normal !important; cursor: pointer;
    font-family: var(--serif) !important; font-size: var(--t1) !important; font-weight: 600 !important;
}}
div[data-testid="stTabs"] [role="tab"] *, .stTabs [role="tab"] *, .stTabs [data-baseweb="tab"] * {{
    font-family: var(--serif) !important; font-size: var(--t1) !important; font-weight: 600 !important; line-height: 1.25 !important;
    color: inherit !important; white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
}}
div[data-testid="stTabs"] [role="tab"]:hover, .stTabs [role="tab"]:hover {{ background: {COLORES['grisClaro']} !important; color: var(--tinta) !important; }}
div[data-testid="stTabs"] [role="tab"][aria-selected="true"], .stTabs [role="tab"][aria-selected="true"], .stTabs [aria-selected="true"] {{
    color: var(--tinta) !important; border-bottom: 3px solid var(--petroleo) !important; background: transparent !important;
    box-shadow: none !important; border-top: none !important; border-left: none !important; border-right: none !important;
}}
div[data-testid="stTabs"] [role="tab"]:focus-visible, .stTabs [role="tab"]:focus-visible {{ outline: 3px solid {COLORES['azulClaro']}; outline-offset: -3px; }}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"], div[data-testid="stTabs"] [data-baseweb="tab-border"],
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none !important; }}
/* Pestanas internas (dentro de otra pestana): mas bajas y en sans */
div[data-testid="stTabs"] div[data-testid="stTabs"] [role="tab"], .stTabs .stTabs [role="tab"] {{ min-height: 46px !important; padding: 0.4rem 0.8rem !important; }}
div[data-testid="stTabs"] div[data-testid="stTabs"] [role="tab"] *, .stTabs .stTabs [role="tab"] * {{ font-family: var(--sans) !important; font-size: var(--t0) !important; }}

/* Tarjetas de opcion (perfil, fondo, modo): borde en tinta cuando esta elegida */
.opcion {{ background: #FFFFFF; border: 1px solid var(--borde); border-radius: 10px 10px 0 0; border-bottom: none; padding: 0.85rem 1rem 0.6rem 1rem;
          height: 10rem; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden; }}
.opcion.compacta {{ height: 10.6rem; }}
.opcion.compacta .opcionTitulo {{ font-size: var(--t0); }}
.opcion.compacta .opcionTitulo > span:first-child {{ display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }}
.opcion.compacta .opcionSub {{ -webkit-line-clamp: 2; }}
.opcionSub {{ display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden; }}
.opcion.elegida {{ border: 2px solid var(--petroleo); border-bottom: none; background: #FFFFFF; }}
.opcionTitulo {{ font-family: var(--serif); font-size: var(--t1); font-weight: 600; color: var(--tinta); line-height: 1.2; display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem; }}
.opcionDato {{ font-size: var(--t0); font-weight: 600; color: {COLORES['verde']}; white-space: nowrap; font-family: var(--sans); }}
.opcionSub {{ font-size: var(--t0); color: {COLORES['grisOscuro']}; margin-top: 0.2rem; line-height: 1.35; }}
.opcionChip {{ display: inline-block; margin-top: auto; align-self: flex-start; max-width: 100%; padding: 0.1rem 0.55rem; border-radius: 6px;
              font-size: var(--t-1); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.chipVerdeF {{ background: {COLORES['verdeFondo']}; color: #1F5C41; }}
.chipAmbarF {{ background: {COLORES['ambarFondo']}; color: #7E5412; }}
.chipRojaF {{ background: {COLORES['rojoFondo']}; color: #8E3331; }}
.chipGrisF {{ background: {COLORES['grisClaro']}; color: {COLORES['grisOscuro']}; }}
div[data-testid="stVerticalBlock"] .stButton > button {{ min-height: 44px; font-size: var(--t0); }}
.stButton > button[kind="primary"] {{ font-weight: 700; }}

/* Controles */
div[data-baseweb="select"] > div {{ min-height: 46px; font-size: var(--t0); border-radius: 8px; }}
div[data-testid="stNumberInput"] input, div[data-testid="stTextInput"] input {{ font-size: var(--t0); min-height: 44px; }}
div[data-testid="stRadio"] label p {{ font-size: var(--t0) !important; }}
div[data-testid="stSlider"] {{ padding-top: 0.3rem; }}
div[data-testid="stAlert"] {{ border-radius: 8px; }}
div[data-testid="stAlert"] p {{ font-size: var(--t0); }}
.stButton > button, .stDownloadButton > button {{ border-radius: 8px; font-weight: 600; padding: 0.45rem 1rem; }}

/* Tablas */
.stDataFrame {{ border-radius: 8px; }}
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {{ border-radius: 8px; overflow: hidden; }}
.tablaFs {{ width: 100%; overflow: auto; max-height: 34rem; margin: 0.2rem 0 0.8rem 0; border: 1px solid var(--borde); border-radius: 8px; background: #FFFFFF; -webkit-overflow-scrolling: touch; }}
.tablaFs table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: var(--t0); line-height: 1.4; }}
.tablaFs th {{ position: sticky; top: 0; z-index: 1; text-align: left; white-space: nowrap; background: #FFFFFF; color: {COLORES['grisOscuro']}; font-weight: 600; padding: 0.65rem 0.85rem; border-bottom: 2px solid var(--tinta); }}
.tablaFs td {{ padding: 0.6rem 0.85rem; color: var(--tinta); vertical-align: top; border-bottom: 1px solid var(--borde); min-width: 4.5rem; background: #FFFFFF; }}
.tablaFs tbody tr:hover td {{ background: {COLORES['grisClaro']}; }}
.tablaFs tbody tr:last-child td {{ border-bottom: none; }}
.tablaFs tr.destacada td {{ background: {COLORES['azulClaro']} !important; font-weight: 600; }}
.tablaFs tr.destacada td:first-child {{ box-shadow: inset 4px 0 0 var(--petroleo); }}
.tablaFs .num {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
.tablaFs td:first-child:not(.num) {{ font-weight: 600; }}
.tablaFs th:first-child, .tablaFs td:first-child {{ position: sticky; left: 0; }}
.tablaFs th:first-child {{ z-index: 2; }}
.tablaVacia {{ color: {COLORES['grisMedio']}; }}
.celdaChip {{ display: inline-block; padding: 0.05rem 0.55rem; border-radius: 6px; font-size: var(--t-1); font-weight: 600; white-space: nowrap; }}

section[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid var(--borde); }}
.insignia {{ display: inline-block; padding: 0.2rem 0.65rem; border-radius: 6px; font-size: var(--t-1); font-weight: 600; }}
.insigniaVerde {{ background: {COLORES['verdeFondo']}; color: #1F5C41; }}
.insigniaAmbar {{ background: {COLORES['ambarFondo']}; color: #7E5412; }}
.insigniaRoja {{ background: {COLORES['rojoFondo']}; color: #8E3331; }}
.insigniaAzul {{ background: {COLORES['azulClaro']}; color: var(--petroleo); }}
.insigniaTurquesa {{ background: #E2F1F2; color: #16666B; }}
div[data-testid="stExpander"] details {{ border-radius: 10px; border: 1px solid var(--borde); background: #FFFFFF; }}
div[data-testid="stExpander"] summary p {{ font-size: var(--t0); font-weight: 600; color: var(--tinta); }}
/* Pasos 1 y 2 ya elegidos: el plegable muestra la eleccion en el titulo */
.pasoListo div[data-testid="stExpander"] summary p {{ font-family: var(--serif); font-size: var(--t1); }}

/* Portafolio: pesos */
.pesoFila {{ display: flex; align-items: center; gap: 0.8rem; padding: 0.35rem 0; border-bottom: 1px solid var(--borde); }}
.pesoNombre {{ flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.pesoValor {{ font-family: var(--serif); font-size: var(--t1); font-weight: 600; width: 4.5rem; text-align: right; font-variant-numeric: tabular-nums; }}

@media (prefers-reduced-motion: no-preference) {{
    .opcion, .stButton > button, .flujoPaso {{ transition: border-color 120ms ease, background-color 120ms ease; }}
}}
.stButton > button:focus-visible {{ outline: 3px solid {COLORES['azulClaro']}; outline-offset: 1px; }}

@media (max-width: 640px) {{
    html {{ font-size: 16px !important; }}
    .block-container {{ padding: 3.2rem 0.8rem 2rem 0.8rem; }}
    .cabeceraApp {{ gap: 0.5rem; padding-bottom: 0.6rem; margin-bottom: 0.8rem; }}
    .nombreApp {{ font-size: var(--t1); }}
    .lemaApp, .etiquetaApp {{ display: none; }}
    .hero {{ padding: 1rem 0 0.6rem 0; }}
    .heroTitulo {{ font-size: var(--t3); }}
    .heroTexto {{ font-size: var(--t0); }}
    .heroPasos {{ grid-template-columns: 1fr; gap: 0.6rem; }}
    .tarjeta {{ padding: 0.8rem 0.95rem; margin-bottom: 0.5rem; height: auto; min-height: 0; }}
    .tarjetaNota {{ -webkit-line-clamp: 3; }}
    .paso {{ gap: 0.6rem; }}
    .pasoNumero {{ width: 30px; height: 30px; font-size: var(--t0); }}
    .nombreActivo {{ width: 46%; }}
    .pesoActivo {{ width: 44px; }}
    div[data-testid="stTabs"] [role="tablist"], .stTabs [role="tablist"] {{ flex-wrap: wrap !important; gap: 0.35rem !important; }}
    div[data-testid="stTabs"] [role="tab"], .stTabs [role="tab"] {{ flex: 1 1 42% !important; min-width: 0; min-height: 48px !important; padding: 0.4rem 0.6rem !important; }}
    div[data-testid="stTabs"] [role="tab"] *, .stTabs [role="tab"] * {{ font-size: var(--t0) !important; }}
    .pesoFila {{ flex-wrap: wrap; }}
    .pesoFila .pesoNombre {{ flex: 1 1 100%; white-space: normal; }}
    .pesoFila .pistaBarra {{ flex: 1 1 auto !important; }}
    /* Riel compacto en una fila: numero y nombre del paso; el valor solo en el paso activo */
    .flujo {{ flex-direction: row; flex-wrap: wrap; }}
    .flujoPaso {{ flex: 1 1 0; flex-direction: column; align-items: center; gap: 0.2rem; padding: 0.4rem 0.3rem; text-align: center; }}
    .flujoPaso.activo {{ box-shadow: inset 0 -3px 0 var(--petroleo); }}
    .flujoNumero {{ width: 26px; height: 26px; font-size: var(--t-1); }}
    .flujoTitulo {{ font-size: var(--t-1); }}
    .flujoValor {{ display: none; }}
    /* Debajo de los cuatro pasos, una linea con el paso activo y su valor (sin romper el orden) */
    .flujo::after {{ content: attr(data-activo); flex: 1 1 100%; text-align: center; font-size: var(--t-1); font-weight: 600;
                     color: var(--tinta); background: {COLORES['azulClaro']}; padding: 0.3rem 0.6rem; border-top: 1px solid var(--borde);
                     white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .flujo[data-activo=""]::after {{ display: none; }}
    .st-key-riel, [data-testid="stVerticalBlock"] > div:has(.flujo) {{ top: 2.6rem !important; }}
    .ancla, .seccion[id] {{ scroll-margin-top: 9rem; }}
    .opcion, .opcion.compacta {{ height: auto; padding: 0.7rem 0.8rem 0.5rem 0.8rem; }}
    .opcionChip {{ margin-top: 0.45rem; }}
    .opcionTitulo {{ font-size: var(--t1); }}
    .seccion {{ font-size: var(--t2); }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{ margin-bottom: 0.8rem; }}
    .eleccion {{ padding: 0.7rem 0.8rem; }}
    .tablaFs th, .tablaFs td {{ padding: 0.55rem 0.7rem; }}
    .tablaFs {{ max-height: 28rem; }}
    .tablaFs td:not(.num) {{ min-width: 10rem; }}
    .tablaFs td:first-child:not(.num) {{ min-width: 8.5rem; max-width: 9.5rem; box-shadow: 2px 0 0 var(--borde); }}
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
                <div class="nombreApp">FundScope</div>
                <div class="lemaApp">Fondos mutuos, explicados para decidir.</div>
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

        if len(str(valor)) > 12:  # textos largos (p. ej. "3 bono(s) de ANGL") en un tamano menor
            claseValor += " tarjetaValorLargo"
        claseTarjeta = "tarjeta tarjetaDestacada" if destacada else "tarjeta"
        if color in ("verde", "ambar", "naranja", "roja"):  # tarjeta de conclusion
            claseTarjeta = f"tarjeta tarjeta{color.capitalize()}"
            claseValor = "tarjetaValor" + (" tarjetaValorLargo" if len(str(valor)) > 12 else "")
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
        # Cada paso es un enlace a su seccion (#paso-N): el riel fijo sirve para ir y volver sin desplazarse
        piezas.append(f'<a class="flujoPaso {p.get("estado", "")}" href="#paso-{i}" title="Ir a {escape(str(p["titulo"]))}">'
                      f'<div class="flujoNumero">{marca}</div><div class="flujoTexto">'
                      f'<div class="flujoTitulo">{escape(str(p["titulo"]))}</div>'
                      f'<div class="flujoValor">{escape(str(p["valor"]))}</div></div></a>')
    activo = next((p for p in pasos if p.get("estado") == "activo"), None)
    valorActivo = escape(f"{activo['titulo']}: {activo['valor']}") if activo else ""
    return f'<div class="flujo" data-activo="{valorActivo}">' + "".join(piezas) + "</div>"


def ancla(nombre):
    """Punto de salto para el riel de pasos (se dibuja justo antes de la seccion)."""
    st.markdown(f'<div class="ancla" id="{escape(str(nombre))}"></div>', unsafe_allow_html=True)


def tarjetaOpcion(titulo, subtitulo="", chip=None, tonoChip="gris", elegida=False, compacta=False, dato=None):
    """Tarjeta descriptiva de una opcion grande; el boton de eleccion se dibuja debajo con st.button."""
    clases = {"verde": "chipVerdeF", "ambar": "chipAmbarF", "roja": "chipRojaF"}.get(tonoChip, "chipGrisF")
    textoChip = f'<span class="opcionChip {clases}">{escape(str(chip))}</span>' if chip else ""
    clasesTarjeta = " ".join(c for c in ("opcion", "elegida" if elegida else "", "compacta" if compacta else "") if c)
    textoDato = f'<span class="opcionDato">{escape(str(dato))}</span>' if dato else ""
    return (f'<div class="{clasesTarjeta}" title="{escape(str(subtitulo))}"><div class="opcionTitulo"><span>{escape(str(titulo))}</span>{textoDato}</div>'
            + (f'<div class="opcionSub">{escape(str(subtitulo))}</div>' if subtitulo else "") + textoChip + "</div>")


def tituloSeccion(titulo, subtitulo="", id=None):
    atributo = f' id="{escape(str(id))}"' if id else ""
    st.markdown(f'<div class="seccion"{atributo}>{escape(str(titulo))}</div>'
                + (f'<div class="seccionSub">{escape(str(subtitulo))}</div>' if subtitulo else ""), unsafe_allow_html=True)


def portada(titulo, texto, pasos):
    """
    Portada: un titulo en serif, una linea de explicacion y los pasos del
    flujo. pasos = lista de (nombre, descripcion). El titulo admite <em>.
    """
    piezas = "".join(f"<div class='heroPaso'><b>{escape(str(n))}</b><span>{escape(str(d))}</span></div>" for n, d in pasos)
    return (f'<div class="hero"><h1 class="heroTitulo">{titulo}</h1><p class="heroTexto">{escape(str(texto))}</p>'
            f'<div class="heroPasos">{piezas}</div></div>')


def filaPeso(nombre, peso, color=None):
    """Fila del portafolio: nombre, barra y peso en %."""
    ancho = max(min(float(peso) * 100, 100), 0)
    return (f'<div class="pesoFila"><div class="pesoNombre">{escape(str(nombre))}</div>'
            f'<div class="pistaBarra" style="flex:0 0 38%"><div class="rellenoBarra" style="width:{ancho:.1f}%; background:{color or COLORES["azul"]};"></div></div>'
            f'<div class="pesoValor">{ancho:.0f}%</div></div>')
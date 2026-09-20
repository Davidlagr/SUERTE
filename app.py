import streamlit as st
import pandas as pd
import random
import json
import requests
from bs4 import BeautifulSoup
import pytesseract
from PIL import Image
from datetime import datetime

# Configuración de página
st.set_page_config(page_title="Predictor Baloto", layout="wide")

# --- 1. SCRAPING Y DATOS HISTÓRICOS ---
@st.cache_data(ttl=86400) # Se actualiza una vez al día
def obtener_historico_baloto():
    """
    Función para obtener el histórico. 
    Nota: Las páginas oficiales suelen tener bloqueos antibot. 
    Se recomienda usar un dataset CSV estático si el scraping directo falla,
    aquí se simula una extracción estructurada.
    """
    # Simulación de un histórico de los últimos 100 sorteos para el cálculo estadístico
    # En producción, reemplazar con requests.get('url_resultados') y BeautifulSoup
    datos = []
    for i in range(100):
        numeros = random.sample(range(1, 44), 5)
        super_balota = random.randint(1, 16)
        datos.append(numeros + [super_balota])
    
    df = pd.DataFrame(datos, columns=['N1', 'N2', 'N3', 'N4', 'N5', 'SuperBalota'])
    return df

# --- 2. LÓGICA DE PROBABILIDAD ---
def generar_jugada(df_historico):
    # Frecuencia de los números del 1 al 43
    numeros_planos = df_historico[['N1', 'N2', 'N3', 'N4', 'N5']].values.flatten()
    frecuencia_num = pd.Series(numeros_planos).value_counts()
    
    # Frecuencia de la Super Balota
    frecuencia_sb = df_historico['SuperBalota'].value_counts()
    
    # Descartar el 40% de los números que menos caen (los "fríos")
    top_numeros = frecuencia_num.head(int(43 * 0.6)).index.tolist()
    top_sb = frecuencia_sb.head(int(16 * 0.6)).index.tolist()
    
    # Seleccionar al azar entre los más frecuentes
    jugada_numeros = sorted(random.sample(top_numeros, 5))
    jugada_sb = random.choice(top_sb)
    
    return jugada_numeros, jugada_sb

# --- 3. PROCESAMIENTO OCR ---
def extraer_numeros_imagen(imagen):
    # Configurar Tesseract para español
    texto = pytesseract.image_to_string(imagen, lang='spa')
    # Lógica básica para buscar patrones de 5 números (1-43) y 1 super balota.
    # Esta extracción se debe afinar según el formato físico del tiquete de Baloto.
    numeros_encontrados = [int(s) for s in texto.split() if s.isdigit()]
    return numeros_encontrados # Requiere depuración según el OCR real

# --- INTERFAZ STREAMLIT ---
st.title("🎰 Predictor y Gestor de Baloto")

# Cargar histórico
df = obtener_historico_baloto()
st.sidebar.header("Gestión de Historial")

# Estado de la sesión para el historial
if 'historial_usuario' not in st.session_state:
    st.session_state.historial_usuario = []

# Cargar archivo JSON
archivo_cargado = st.sidebar.file_uploader("Sube tu historial de jugadas (JSON)", type=['json'])
if archivo_cargado is not None:
    st.session_state.historial_usuario = json.load(archivo_cargado)
    st.sidebar.success("Historial cargado correctamente.")

# Pestañas de la aplicación
tab1, tab2, tab3 = st.tabs(["Generar Jugada", "Mis Jugadas y Resultados", "Escanear Tiquete"])

with tab1:
    st.subheader("Generación Estadística")
    st.write("Se calcula eliminando el 40% de los números con menor aparición en los últimos sorteos.")
    
    if st.button("Generar Nueva Jugada", type="primary"):
        nums, sb = generar_jugada(df)
        st.markdown(f"### Tus números: **{nums[0]} - {nums[1]} - {nums[2]} - {nums[3]} - {nums[4]}**")
        st.markdown(f"### Super Balota: **{sb}**")
        
        # Guardar en memoria
        nueva_jugada = {
            "fecha": datetime.now().strftime("%Y-%m-%d"),
            "numeros": nums,
            "super_balota": sb,
            "sorteo": "Por definir"
        }
        st.session_state.historial_usuario.append(nueva_jugada)
        st.success("Jugada añadida a tu historial temporal. ¡No olvides descargarlo!")

with tab2:
    st.subheader("Comparación de Resultados")
    
    # Mostrar último resultado simulado (reemplazar con el scraping real del último sorteo)
    ultimo_sorteo = df.iloc[0]
    ultimos_nums = ultimo_sorteo[['N1', 'N2', 'N3', 'N4', 'N5']].tolist()
    ultima_sb = ultimo_sorteo['SuperBalota']
    
    st.info(f"Último sorteo ganador: **{ultimos_nums}** | SB: **{ultima_sb}**")
    
    if st.session_state.historial_usuario:
        st.write("### Tu Historial")
        df_historial = pd.DataFrame(st.session_state.historial_usuario)
        st.dataframe(df_historial, use_container_width=True)
        
        # Botón para descargar el JSON actualizado
        json_descarga = json.dumps(st.session_state.historial_usuario, indent=4)
        st.download_button(
            label="💾 Descargar Historial Actualizado",
            data=json_descarga,
            file_name="historial_baloto.json",
            mime="application/json"
        )
    else:
        st.write("No hay jugadas en el historial.")

with tab3:
    st.subheader("Sube el soporte de tu jugada")
    st.write("Sube una foto de tu tiquete para extraer los números mediante OCR.")
    imagen_soporte = st.file_uploader("Captura de tiquete", type=['jpg', 'jpeg', 'png'])
    
    if imagen_soporte is not None:
        img = Image.open(imagen_soporte)
        st.image(img, caption="Tiquete cargado", width=400)
        
        with st.spinner("Procesando imagen..."):
            numeros_extraidos = extraer_numeros_imagen(img)
            st.write("Posibles números detectados en el tiquete:")
            st.write(numeros_extraidos)
            st.warning("Verifica los números extraídos. El OCR puede tener variaciones dependiendo de la luz de la foto y la fuente del tiquete.")

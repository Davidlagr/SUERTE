import streamlit as st
import pandas as pd
import random
import json
import requests
from bs4 import BeautifulSoup
import pytesseract
from PIL import Image
from pdf2image import convert_from_bytes
from datetime import datetime
import io

# Configuración de página
st.set_page_config(page_title="Predictor Baloto", layout="wide")

# --- 1. SCRAPING Y DATOS HISTÓRICOS ---
@st.cache_data(ttl=43200) # Se actualiza cada 12 horas
def obtener_historico_baloto():
    url = "https://www.resultadobaloto.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }
    
    datos_extraidos = []
    try:
        respuesta = requests.get(url, headers=headers, timeout=10)
        respuesta.raise_for_status()
        soup = BeautifulSoup(respuesta.text, 'html.parser')
        tablas = soup.find_all('table')
        
        for tabla in tablas:
            filas = tabla.find_all('tr')
            for fila in filas[1:]: 
                columnas = fila.find_all('td')
                if len(columnas) >= 3:
                    combinacion = columnas[1].text.strip().replace('-', ' ')
                    super_balota_texto = columnas[2].text.strip()
                    numeros = combinacion.split()
                    
                    if len(numeros) == 5 and super_balota_texto.isdigit():
                        n1, n2, n3, n4, n5 = [int(n) for n in numeros]
                        sb = int(super_balota_texto)
                        datos_extraidos.append([n1, n2, n3, n4, n5, sb])
        
        if len(datos_extraidos) > 0:
            return pd.DataFrame(datos_extraidos, columns=['N1', 'N2', 'N3', 'N4', 'N5', 'SuperBalota'])
        else:
            raise ValueError("No se encontraron resultados en el formato esperado.")
            
    except Exception as e:
        st.warning(f"No se pudo conectar a los resultados en vivo. Usando modo offline. Detalle: {e}")
        for i in range(100):
            numeros = sorted(random.sample(range(1, 44), 5))
            super_balota = random.randint(1, 16)
            datos_extraidos.append(numeros + [super_balota])
            
        return pd.DataFrame(datos_extraidos, columns=['N1', 'N2', 'N3', 'N4', 'N5', 'SuperBalota'])

# --- 2. LÓGICA DE PROBABILIDAD ---
def generar_jugada(df_historico):
    numeros_planos = df_historico[['N1', 'N2', 'N3', 'N4', 'N5']].values.flatten()
    frecuencia_num = pd.Series(numeros_planos).value_counts()
    frecuencia_sb = df_historico['SuperBalota'].value_counts()
    
    # Descartar el 40% de los números "fríos"
    top_numeros = frecuencia_num.head(int(43 * 0.6)).index.tolist()
    top_sb = frecuencia_sb.head(int(16 * 0.6)).index.tolist()
    
    jugada_numeros = sorted(random.sample(top_numeros, 5))
    jugada_sb = random.choice(top_sb)
    
    return jugada_numeros, jugada_sb

# --- 3. PROCESAMIENTO OCR ---
def extraer_numeros_imagen(imagen):
    texto = pytesseract.image_to_string(imagen, lang='spa')
    numeros_encontrados = [int(s) for s in texto.split() if s.isdigit()]
    return numeros_encontrados

# --- INTERFAZ STREAMLIT ---
st.title("🎰 Predictor y Gestor de Baloto")

df = obtener_historico_baloto()
st.sidebar.header("Gestión de Historial")

if 'historial_usuario' not in st.session_state:
    st.session_state.historial_usuario = []

archivo_cargado = st.sidebar.file_uploader("Sube tu historial de jugadas (JSON)", type=['json'])
if archivo_cargado is not None:
    st.session_state.historial_usuario = json.load(archivo_cargado)
    st.sidebar.success("Historial cargado correctamente.")

tab1, tab2, tab3 = st.tabs(["Generar Jugada", "Mis Jugadas y Resultados", "Escanear Tiquete"])

with tab1:
    st.subheader("Generación Estadística")
    st.write("Se calcula eliminando el 40% de los números con menor aparición en los últimos sorteos.")
    
    if st.button("Generar Nueva Jugada", type="primary"):
        nums, sb = generar_jugada(df)
        st.markdown(f"### Tus números: **{nums[0]} - {nums[1]} - {nums[2]} - {nums[3]} - {nums[4]}**")
        st.markdown(f"### Super Balota: **{sb}**")
        
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
    st.write("### Últimos dos sorteos registrados")
    
    # Extraer los primeros 2 registros (los más recientes)
    if len(df) >= 2:
        ultimos_sorteos = df.head(2)
        for i, (_, sorteo) in enumerate(ultimos_sorteos.iterrows()):
            nums = sorteo[['N1', 'N2', 'N3', 'N4', 'N5']].tolist()
            sb = sorteo['SuperBalota']
            st.info(f"**Sorteo {i+1}**: {nums} | SB: **{sb}**")
    
    if st.session_state.historial_usuario:
        st.write("---")
        st.write("### Tu Historial")
        df_historial = pd.DataFrame(st.session_state.historial_usuario)
        st.dataframe(df_historial, use_container_width=True)
        
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
    st.write("Sube tu tiquete (Imagen o PDF) para extraer los números mediante OCR.")
    archivo_soporte = st.file_uploader("Captura de tiquete", type=['jpg', 'jpeg', 'png', 'pdf'])
    
    if archivo_soporte is not None:
        try:
            # Lógica para procesar PDF o Imágenes
            if archivo_soporte.name.lower().endswith('.pdf'):
                # Convertir la primera página del PDF a imagen
                imagenes = convert_from_bytes(archivo_soporte.read())
                img = imagenes[0]
            else:
                img = Image.open(archivo_soporte)
                
            st.image(img, caption="Tiquete cargado (Vista Previa)", width=400)
            
            with st.spinner("Procesando documento..."):
                numeros_extraidos = extraer_numeros_imagen(img)
                st.write("Posibles números detectados en el tiquete:")
                st.write(numeros_extraidos)
                st.warning("Verifica los números extraídos manualmente.")
        except Exception as e:
            st.error(f"Ocurrió un error al procesar el archivo: {e}")

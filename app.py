import streamlit as st
import pandas as pd
import random
import json
import requests
from bs4 import BeautifulSoup
import pytesseract
from PIL import Image
from pypdf import PdfReader
from datetime import datetime
import re

# Configuración de página
st.set_page_config(page_title="Predictor y Gestor de Baloto", layout="wide")

# --- 1. SCRAPING EN VIVO (SIN SIMULADOR) ---
@st.cache_data(ttl=10800) # Se actualiza cada 3 horas
def obtener_historico_baloto():
    url = "https://www.resultadobaloto.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    }
    
    datos_extraidos = []
    try:
        respuesta = requests.get(url, headers=headers, timeout=15)
        respuesta.raise_for_status()
        soup = BeautifulSoup(respuesta.text, 'html.parser')
        
        tablas = soup.find_all('table')
        if not tablas:
            return pd.DataFrame() # Retorna vacío si falla la lectura web
            
        for fila in tablas[0].find_all('tr')[1:]: 
            cols = fila.find_all('td')
            if len(cols) >= 3:
                fecha_str = cols[0].text.strip()
                baloto_str = cols[1].text.strip()
                revancha_str = cols[2].text.strip()
                
                # Extraer números descartando guiones o texto
                b_nums = [int(x) for x in re.findall(r'\b\d{1,2}\b', baloto_str)]
                r_nums = [int(x) for x in re.findall(r'\b\d{1,2}\b', revancha_str)]
                
                if len(b_nums) >= 6:
                    # Buscar el código de 4 o 5 dígitos del sorteo
                    match_s = re.search(r'(\d{4,5})', fecha_str)
                    num_sorteo = f"S{match_s.group(1)}" if match_s else "Desconocido"
                    
                    r_n = r_nums if len(r_nums) >= 6 else [0,0,0,0,0,0]
                    
                    datos_extraidos.append([
                        num_sorteo, fecha_str,
                        b_nums[0], b_nums[1], b_nums[2], b_nums[3], b_nums[4], b_nums[5],
                        r_n[0], r_n[1], r_n[2], r_n[3], r_n[4], r_n[5]
                    ])
                    
    except Exception as e:
        st.error(f"Error conectando con los resultados oficiales: {e}")
        return pd.DataFrame()
        
    columnas = [
        'Sorteo', 'Fecha', 
        'B_N1', 'B_N2', 'B_N3', 'B_N4', 'B_N5', 'B_SB',
        'R_N1', 'R_N2', 'R_N3', 'R_N4', 'R_N5', 'R_SB'
    ]
    return pd.DataFrame(datos_extraidos, columns=columnas)

# --- 2. LÓGICA DE PREMIOS ---
def verificar_premio(jugada_nums, jugada_sb, ganador_nums, ganador_sb):
    aciertos_nums = len(set(jugada_nums).intersection(set(ganador_nums)))
    acierto_sb = (jugada_sb == ganador_sb)
    
    if aciertos_nums == 5 and acierto_sb: return "¡GRAN ACUMULADO! (5+1)"
    elif aciertos_nums == 5 and not acierto_sb: return "Premio (5+0)"
    elif aciertos_nums == 4 and acierto_sb: return "Premio (4+1)"
    elif aciertos_nums == 4 and not acierto_sb: return "Premio (4+0)"
    elif aciertos_nums == 3 and acierto_sb: return "Premio (3+1)"
    elif aciertos_nums == 3 and not acierto_sb: return "Premio (3+0)"
    elif aciertos_nums == 2 and acierto_sb: return "Premio (2+1)"
    elif aciertos_nums == 0 and acierto_sb: return "Premio (0+1)"
    else: return "Sin premio"

# --- 3. PROCESAMIENTO TEXTO Y OCR ---
def extraer_datos_tiquete(texto):
    datos = {"sorteo": "Desconocido", "fecha": "Desconocida", "jugadas": []}
    texto_plano = re.sub(r'\s+', ' ', texto)
    
    match_sorteo = re.search(r'(?:S|SORTEOX?\d?.*?)\s*(\d{4,5})\b', texto_plano, re.IGNORECASE)
    if not match_sorteo:
        match_sorteo = re.search(r'(5)(\d{4})\b', texto_plano)
        
    if match_sorteo:
        num = match_sorteo.groups()[-1] 
        datos["sorteo"] = "S" + num
            
    match_fecha = re.search(r'(\d{1,2}\s+DE\s+[A-Z]+\s+\d{4})', texto_plano, re.IGNORECASE)
    if match_fecha:
        datos["fecha"] = match_fecha.group(1).title()
        
    patron_jugada = r'([A-E])[\.\s]+(?:BR|8R)?\s*(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})'
    matches = re.finditer(patron_jugada, texto_plano, re.IGNORECASE)
    
    for match in matches:
        letra = match.group(1).upper()
        nums = [int(match.group(i)) for i in range(2, 7)]
        sb = int(match.group(7))
        
        if all(1 <= n <= 43 for n in nums) and (1 <= sb <= 16):
            datos["jugadas"].append({"letra": letra, "numeros": nums, "super_balota": sb})
            
    return datos

# --- INTERFAZ STREAMLIT ---
st.title("🎰 Predictor y Gestor de Baloto")

df = obtener_historico_baloto()
st.sidebar.header("Gestión de Historial")

if 'historial_usuario' not in st.session_state:
    st.session_state.historial_usuario = []

archivo_cargado = st.sidebar.file_uploader("Sube tu historial (JSON)", type=['json'])
if archivo_cargado is not None:
    st.session_state.historial_usuario = json.load(archivo_cargado)
    st.sidebar.success("Historial cargado correctamente.")

tab1, tab2, tab3 = st.tabs(["Escanear Tiquete", "Resultados y Mis Jugadas", "Generar Probabilidad"])

with tab1:
    st.subheader("Sube tu tiquete (PDF o Imagen)")
    archivo_soporte = st.file_uploader("Captura de tiquete físico o web", type=['jpg', 'jpeg', 'png', 'pdf'])
    
    if archivo_soporte is not None:
        try:
            with st.spinner("Leyendo documento..."):
                texto_ocr = ""
                if archivo_soporte.name.lower().endswith('.pdf'):
                    lector_pdf = PdfReader(archivo_soporte)
                    for pagina in lector_pdf.pages:
                        texto_ocr += pagina.extract_text() + " "
                else:
                    img = Image.open(archivo_soporte)
                    texto_ocr = pytesseract.image_to_string(img, lang='spa')
                
                datos_tiquete = extraer_datos_tiquete(texto_ocr)
                
                if datos_tiquete["jugadas"]:
                    st.success(f"¡Tiquete procesado! Sorteo: **{datos_tiquete['sorteo']}** | Fecha: **{datos_tiquete['fecha']}**")
                    for jugada in datos_tiquete["jugadas"]:
                        st.write(f"**Jugada {jugada['letra']}**: {jugada['numeros']} | SB: **{jugada['super_balota']}**")
                        if st.button(f"Guardar Jugada {jugada['letra']}", key=f"btn_{jugada['letra']}"):
                            st.session_state.historial_usuario.append({
                                "sorteo": datos_tiquete['sorteo'],
                                "fecha_sorteo": datos_tiquete['fecha'],
                                "letra": jugada['letra'],
                                "numeros": jugada['numeros'],
                                "super_balota": jugada['super_balota']
                            })
                            st.toast(f"Jugada {jugada['letra']} guardada.")
                else:
                    st.error("No se detectaron jugadas válidas.")
        except Exception as e:
            st.error(f"Error procesando el archivo: {e}")

with tab2:
    st.subheader("Últimos Sorteos Oficiales Publicados")
    
    if not df.empty:
        ultimos_sorteos = df.head(2)
        for i, (_, sorteo) in enumerate(ultimos_sorteos.iterrows()):
            st.markdown(f"#### 🏆 Sorteo {sorteo['Sorteo']} ({sorteo['Fecha']})")
            c1, c2 = st.columns(2)
            c1.info(f"**BALOTO**: {sorteo[['B_N1', 'B_N2', 'B_N3', 'B_N4', 'B_N5']].tolist()} | SB: **{sorteo['B_SB']}**")
            c2.warning(f"**REVANCHA**: {sorteo[['R_N1', 'R_N2', 'R_N3', 'R_N4', 'R_N5']].tolist()} | SB: **{sorteo['R_SB']}**")
    else:
        st.warning("No hay datos recientes disponibles para mostrar.")

    st.write("---")
    st.write("### Mis Jugadas Guardadas")
    
    if st.session_state.historial_usuario:
        for j in st.session_state.historial_usuario:
            num_sorteo = j.get('sorteo', '')
            st.write(f"#### 🎫 Jugada {j.get('letra', '')} - Sorteo {num_sorteo} ({j.get('fecha_sorteo', '')})")
            st.write(f"Tus números: {j['numeros']} | SB: {j['super_balota']}")
            
            if not df.empty:
                resultado_oficial = df[df['Sorteo'] == num_sorteo]
                
                # VALIDACIÓN DE FUTURO/PENDIENTE
                if not resultado_oficial.empty:
                    res = resultado_oficial.iloc[0]
                    b_nums = res[['B_N1', 'B_N2', 'B_N3', 'B_N4', 'B_N5']].tolist()
                    r_nums = res[['R_N1', 'R_N2', 'R_N3', 'R_N4', 'R_N5']].tolist()
                    
                    premio_baloto = verificar_premio(j['numeros'], j['super_balota'], b_nums, res['B_SB'])
                    premio_revancha = verificar_premio(j['numeros'], j['super_balota'], r_nums, res['R_SB'])
                    
                    st.success(f"**Baloto:** {premio_baloto} | **Revancha:** {premio_revancha}")
                else:
                    st.warning("⏳ Resultados pendientes (Aún no ha jugado o la web no los ha publicado).")
            else:
                 st.warning("No se pudo conectar para validar los premios.")
            st.divider()
            
        json_descarga = json.dumps(st.session_state.historial_usuario, indent=4)
        st.download_button(label="💾 Descargar Historial Actualizado", data=json_descarga, file_name="historial_baloto.json", mime="application/json")
    else:
        st.write("No tienes jugadas guardadas.")

with tab3:
    st.subheader("Generador Estadístico (Números calientes)")
    if not df.empty:
        if st.button("Generar Nueva Jugada", type="primary"):
            nums_planos = df[['B_N1', 'B_N2', 'B_N3', 'B_N4', 'B_N5']].values.flatten()
            freq_num = pd.Series(nums_planos).value_counts().head(25).index.tolist()
            freq_sb = df['B_SB'].value_counts().head(9).index.tolist()
            
            jugada_nums = sorted(random.sample(freq_num, 5))
            jugada_sb = random.choice(freq_sb)
            
            st.markdown(f"### Tus números: **{jugada_nums[0]} - {jugada_nums[1]} - {jugada_nums[2]} - {jugada_nums[3]} - {jugada_nums[4]}**")
            st.markdown(f"### Super Balota: **{jugada_sb}**")
    else:
        st.error("Se requiere conexión a los resultados en vivo para generar estadísticas.")

import streamlit as st
import datetime
import json
import urllib.parse
import time
from PIL import Image
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials

# --- CONNESSIONE GOOGLE SHEETS ---
@st.cache_resource
def get_sheets():
    try:
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client_gs = gspread.authorize(creds)
        f = client_gs.open("Database_Pranzo") 
        return f.worksheet("users"), f.worksheet("menu"), f.worksheet("orders")
    except Exception as e:
        st.error(f"Errore credenziali Google: {e}")
        st.stop()

def get_col(row, idx):
    return str(row[idx]).strip() if idx < len(row) else ""

# Le righe che mancavano!
users_sheet, menu_sheet, orders_sheet = get_sheets()

# --- FUNZIONE AI ---
def parse_menu_from_image(file_foto):
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Uso il modello 3.7 per evitare i limiti di tentativi di oggi
        model = genai.GenerativeModel('gemini-3.7-flash')
        
        prompt = """
        Leggi il menu in questa foto. Trova la data a cui si riferisce e tutti i piatti.
        Restituisci ESATTAMENTE e SOLO un file JSON (senza formattazione markdown) con questa struttura: 
        {"Data": "GG/MM/AAAA", "Primi": ["Piatto 1"], "Secondi": ["Piatto 2"], "Contorni": ["Piatto 3"], "Fritti": [], "Piadina Panini Farciti": [], "Dolci/Frutta": []}
        Se la data non è specificata chiaramente, scrivi "Data non specificata".
        Se una categoria non c'è, metti una lista vuota [].
        """
        file_foto.seek(0) 
        immagine = Image.open(file_foto)
        response = model.generate_content([prompt, immagine])
        testo = response.text.replace("```json", "").replace("

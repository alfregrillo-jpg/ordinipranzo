import streamlit as st
import sqlite3
import datetime
import json
from PIL import Image
import google.generativeai as genai

# --- CONFIGURAZIONE DATABASE ---
def init_db():
    conn = sqlite3.connect('pranzo_ufficio.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS menu (date TEXT, category TEXT, item TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (date TEXT, username TEXT, primo TEXT, secondo TEXT, contorno TEXT, extra TEXT, not_eating BOOLEAN)''')
    c.execute("INSERT OR IGNORE INTO users VALUES ('admin', 'admin123', 'admin')")
    conn.commit()
    conn.close()

# --- FUNZIONE AI PER IL MENU ---
def parse_menu_from_image(file_foto):
    # ⚠️ INSERISCI QUI LA TUA CHIAVE API TRA LE VIRGOLETTE
    genai.configure(api_key="AQ.Ab8RN6IvjQoRbOigGu6jidu8ppA5ICdq91f7r9x0us8kTcF0mA")
    
    # ⚠️ ABBIAMO IMPOSTATO IL MODELLO PIU' RECENTE E FUNZIONANTE
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = """
    Leggi il menu in questa foto. Restituisci ESATTAMENTE e SOLO un file JSON (senza formattazione markdown) con questa struttura: 
    {"Primi": ["Piatto 1", "Piatto 2"], "Secondi": ["Piatto 3"], "Contorni": ["Piatto 4"], "Dolci/Frutta": ["Piatto 5"]}
    Se una categoria non c'è, metti una lista vuota [].
    """
    
    # Questo comando legge qualsiasi formato immagine in modo nativo
    immagine = Image.open(file_foto)
    response = model.generate_content([prompt, immagine])
    
    try:
        return json.loads(response.text)
    except:
        return {"Primi": [], "Secondi": [], "Contorni": [], "Dolci/Frutta": []}

# --- INTERFACCIA APP ---
st.set_page_config(page_title="Ordini Pranzo Ufficio", layout="centered")
init_db()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

# --- SCHERMATA DI LOGIN ---
if not st.session_state.logged_in:
    st.title("🍽️ Login Ordini Pranzo")
    user_input = st.text_input("Username")
    pass_input = st.text_input("Password", type="password")
    
    if st.button("Accedi"):
        conn = sqlite3.connect('pranzo_ufficio.db')
        c = conn.cursor()
        c.execute("SELECT role FROM users WHERE username=? AND password=?", (user_input, pass_input))
        result = c.fetchone()
        conn.close()
        
        if result:
            st.session_state.logged_in = True
            st.session_state.username = user_input
            st.session_state.role = result[0]
            st.rerun()
        else:
            st.error("Credenziali errate.")

# --- PANNELLO AMMINISTRATORE ---
elif st.session_state.role == 'admin':
    st.title(f"👑 Pannello Amministratore")
    if st.button("Esci"):
        st.session_state.logged_in = False
        st.rerun()

    tab1, tab2, tab3 = st.tabs(["Carica Menu Oggi", "Ordini di Oggi", "Gestione Utenti"])
    oggi = datetime.date.today().strftime("%Y-%m-%d")

    with tab1:
        st.subheader("Carica il Menu del giorno")
        foto_menu = st.file_uploader("Scatta o carica la foto del menu", type=['jpg', 'png', 'jpeg'])
        
        if foto_menu and st.button("Analizza e Genera Menu"):
            with st.spinner("L'Intelligenza Artificiale sta leggendo il menu..."):
                # Passa la foto direttamente all'AI
                menu_estratto = parse_menu_from_image(foto_menu)
                
                conn = sqlite3.connect('pranzo_ufficio.db')
                c = conn.cursor()
                c.execute("DELETE FROM menu WHERE date=?", (oggi,))
                for categoria, piatti in menu_estratto.items():
                    for piatto in piatti:
                        c.execute("INSERT INTO menu VALUES (?, ?, ?)", (oggi, categoria, piatto))
                conn.commit()
                conn.close()
            st.success("Menu aggiornato per tutti gli utenti!")

    with tab2:
        st.subheader("Riepilogo Ordini")
        conn = sqlite3.connect('pranzo_ufficio.db')
        c = conn.cursor()
        c.execute("SELECT username, primo, secondo, contorno, extra, not_eating FROM orders WHERE date=?", (oggi,))
        ordini = c.fetchall()
        conn.close()

        if not ordini:
            st.info("Nessun ordine ricevuto finora oggi.")
        else:
            testo_whatsapp = f"*ORDINI PRANZO DEL {oggi}*\n\n"
            totale_piatti = {}

            for ord in ordini:
                if ord[5]: 
                    continue
                piatti_scelti = [p for p in ord[1:5] if p and p != "Nessuno"]
                testo_whatsapp += f"- {ord[0]}: {', '.join(piatti_scelti)}\n"
                
                for p in piatti_scelti:
                    totale_piatti[p] = totale_piatti.get(p, 0) + 1
            
            testo_whatsapp += "\n*TOTALE PER IL RISTORANTE:*\n"
            for piatto, qta in totale_piatti.items():
                testo_whatsapp += f"{qta}x {piatto}\n"

            st.code(testo_whatsapp, language="text")
            st.caption("Premi l'icona copia in alto a destra nel riquadro per inviarlo al ristorante.")

    with tab3:
        st.subheader("Crea nuovo collega")
        new_user = st.text_input("Nome Utente Collega")
        new_pass = st.text_input("Password Collega")
        if st.button("Crea Account"):
            conn = sqlite3.connect('pranzo_ufficio.db')
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO users VALUES (?, ?, 'user')", (new_user, new_pass))
            conn.commit()
            conn.close()
            st.success(f"Utente {new_user} creato!")

# --- PANNELLO UTENTE ---
elif st.session_state.role == 'user':
    st.title(f"👋 Ciao, {st.session_state.username}")
    if st.button("Esci"):
        st.session_state.logged_in = False
        st.rerun()

    oggi = datetime.date.today().strftime("%Y-%m-%d")
    conn = sqlite3.connect('pranzo_ufficio.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM orders WHERE date=? AND username=?", (oggi, st.session_state.username))
    ha_ordinato = c.fetchone()
    
    if ha_ordinato:
        st.warning("Hai già inviato la tua scelta per oggi. Buon appetito (o buon digiuno)! 🍱")
    else:
        st.subheader("Menu di Oggi")
        c.execute("SELECT category, item FROM menu WHERE date=?", (oggi,))
        menu_items = c.fetchall()
        
        if not menu_items:
            st.info("L'amministratore non ha ancora caricato il menu di oggi.")
        else:
            menu_dict = {"Primi": ["Nessuno"], "Secondi": ["Nessuno"], "Contorni": ["Nessuno"], "Dolci/Frutta": ["Nessuno"]}
            for cat, item in menu_items:
                if cat in menu_dict:
                    menu_dict[cat].append(item)

            non_mangio = st.checkbox("Oggi non mangio / Porto da casa 🚫")

            if not non_mangio:
                primo = st.radio("Scegli il Primo:", menu_dict["Primi"])
                secondo = st.radio("Scegli il Secondo:", menu_dict["Secondi"])
                contorno = st.radio("Scegli il Contorno:", menu_dict["Contorni"])
                extra = st.radio("Scegli Dolce/Frutta:", menu_dict["Dolci/Frutta"])
            
            if st.button("Invia Ordine"):
                if non_mangio:
                    c.execute("INSERT INTO orders VALUES (?, ?, '', '', '', '', 1)", (oggi, st.session_state.username))
                else:
                    c.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, 0)", (oggi, st.session_state.username, primo, secondo, contorno, extra))
                
                conn.commit()
                st.success("Ordine inviato con successo!")
                st.rerun()
                
    conn.close()

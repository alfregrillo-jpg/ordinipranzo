import streamlit as st
import sqlite3
import datetime
import json
import urllib.parse
from PIL import Image
import google.generativeai as genai

# --- CONFIGURAZIONE DATABASE ---
def init_db():
    conn = sqlite3.connect('pranzo_ufficio_v2.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS menu (date TEXT, category TEXT, item TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
                    date TEXT, username TEXT, 
                    primo TEXT, secondo TEXT, note_secondi TEXT, 
                    contorno TEXT, fritti TEXT, piadine TEXT, 
                    extra TEXT, note_extra TEXT, pane BOOLEAN, not_eating BOOLEAN)''')
    
    c.execute("INSERT OR IGNORE INTO users VALUES ('admin', 'admin123', 'admin')")
    conn.commit()
    conn.close()

# --- FUNZIONE AI ---
def parse_menu_from_image(file_foto):
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-3.6-flash')
        
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
        
        testo = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(testo)
        
    except Exception as e:
        st.error(f"Errore di lettura AI: {str(e)}")
        return {}

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
        conn = sqlite3.connect('pranzo_ufficio_v2.db')
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
                menu_estratto = parse_menu_from_image(foto_menu)
                
                if menu_estratto:
                    conn = sqlite3.connect('pranzo_ufficio_v2.db')
                    c = conn.cursor()
                    c.execute("DELETE FROM menu WHERE date=?", (oggi,))
                    
                    for categoria, piatti in menu_estratto.items():
                        if categoria == "Data":
                            c.execute("INSERT INTO menu VALUES (?, ?, ?)", (oggi, "DataEstratta", str(piatti)))
                            continue
                        for piatto in piatti:
                            c.execute("INSERT INTO menu VALUES (?, ?, ?)", (oggi, categoria, piatto))
                    conn.commit()
                    conn.close()
                    st.success("Menu aggiornato per tutti gli utenti!")

    with tab2:
        st.subheader("Riepilogo Ordini")
        conn = sqlite3.connect('pranzo_ufficio_v2.db')
        c = conn.cursor()
        
        c.execute("SELECT item FROM menu WHERE date=? AND category='DataEstratta'", (oggi,))
        data_row = c.fetchone()
        data_menu_letto = data_row[0] if data_row else oggi
        
        c.execute("SELECT username, primo, secondo, note_secondi, contorno, fritti, piadine, extra, note_extra, pane, not_eating FROM orders WHERE date=?", (oggi,))
        ordini = c.fetchall()
        conn.close()

        if not ordini:
            st.info("Nessun ordine ricevuto finora oggi.")
        else:
            testo_schermo = "#### Dettaglio per persona (visibile solo a te)\n"
            totale_piatti = {}
            numero_colleghi = 0

            for ord in ordini:
                if ord[10]: # Se not_eating
                    testo_schermo += f"- 🚫 **{ord[0]}**: *Non mangia / Porta da casa*\n"
                    continue
                
                numero_colleghi += 1
                piatti_scelti = []
                if ord[1] and ord[1] != "Nessuno": piatti_scelti.append(ord[1])
                if ord[2] and ord[2] != "Nessuno":
                    sec = f"{ord[2]} ({ord[3]})" if ord[3] else ord[2]
                    piatti_scelti.append(sec)
                if ord[4] and ord[4] != "Nessuno": piatti_scelti.append(ord[4])
                if ord[5] and ord[5] != "Nessuno": piatti_scelti.append(ord[5])
                if ord[6] and ord[6] != "Nessuno": piatti_scelti.append(ord[6])
                if ord[7] and ord[7] != "Nessuno":
                    ext = f"{ord[7]} ({ord[8]})" if ord[8] else ord[7]
                    piatti_scelti.append(ext)
                if ord[9]: 
                    piatti_scelti.append("Pane fresco")

                testo_schermo += f"- 👤 **{ord[0]}**: {', '.join(piatti_scelti)}\n"
                
                for p in piatti_scelti:
                    totale_piatti[p] = totale_piatti.get(p, 0) + 1
            
            st.markdown(testo_schermo)
            st.markdown("---")
            
            st.subheader("Messaggio per il Ristorante")
            testo_whatsapp = f"*Ordine per pranzo NOE PUSIANO, {data_menu_letto}*\n"
            testo_whatsapp += f"*Totale colleghi:* {numero_colleghi}\n\n"
            
            for piatto, qta in totale_piatti.items():
                testo_whatsapp += f"{qta}x {piatto}\n"

            st.code(testo_whatsapp, language="text")
            
            testo_wa_url = urllib.parse.quote(testo_whatsapp)
            link_wa = f"https://wa.me/390284344847?text={testo_wa_url}"
            st.link_button("🟢 Invia Ordine su WhatsApp", link_wa)

    with tab3:
        st.subheader("Crea nuovo collega")
        new_user = st.text_input("Nome Utente Collega")
        new_pass = st.text_input("Password Collega")
        if st.button("Crea Account"):
            conn = sqlite3.connect('pranzo_ufficio_v2.db')
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
    conn = sqlite3.connect('pranzo_ufficio_v2.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM orders WHERE date=? AND username=?", (oggi, st.session_state.username))
    ha_ordinato = c.fetchone()
    
    if ha_ordinato:
        st.warning("Hai già inviato la tua scelta per oggi. Buon appetito (o buon digiuno)! 🍱")
    else:
        c.execute("SELECT category, item FROM menu WHERE date=?", (oggi,))
        menu_items = c.fetchall()
        
        data_mostrata = "Oggi"
        for cat, item in menu_items:
            if cat == "DataEstratta":
                data_mostrata = item
        
        if not menu_items:
            st.info("L'amministratore non ha ancora caricato il menu di oggi.")
        else:
            st.subheader(f"Menu del: {data_mostrata}")
            
            menu_dict = {
                "Primi": ["Nessuno"], "Secondi": ["Nessuno"], "Contorni": ["Nessuno"], 
                "Fritti": ["Nessuno"], "Piadina Panini Farciti": ["Nessuno"], "Dolci/Frutta": ["Nessuno"]
            }
            
            for cat, item in menu_items:
                if cat in menu_dict:
                    menu_dict[cat].append(item)

            non_mangio = st.checkbox("Oggi non mangio / Porto da casa 🚫")

            if not non_mangio:
                st.markdown("---")
                pane = st.checkbox("🍞 Voglio anche il pane fresco", value=False)
                st.markdown("---")
                
                # PRIMI
                primo = st.radio("Scegli il Primo:", menu_dict["Primi"])
                
                # SECONDI
                secondo_selezionato = st.radio("Scegli il Secondo:", menu_dict["Secondi"] + ["componi il tuo piatto, scrivi tu"])
                if secondo_selezionato == "componi il tuo piatto, scrivi tu":
                    secondo_finale = st.text_input("📝 Scrivi il tuo piatto qui sotto:")
                    if not secondo_finale.strip(): 
                        secondo_finale = "Piatto composto (da chiedere)"
                else:
                    secondo_finale = secondo_selezionato
                
                # CONTORNI, FRITTI, PIADINE
                contorno = st.radio("Scegli il Contorno:", menu_dict["Contorni"])
                fritti = st.radio("Scegli Fritti:", menu_dict["Fritti"])
                piadine = st.radio("Scegli Piadina o Panino:", menu_dict["Piadina Panini Farciti"])
                
                # DOLCI/FRUTTA
                extra_selezionato = st.radio("Scegli Dolce/Frutta:", menu_dict["Dolci/Frutta"] + ["scrivi la tua frutta"])
                if extra_selezionato == "scrivi la tua frutta":
                    extra_finale = st.text_input("📝 Scrivi la frutta che desideri qui sotto:")
                    if not extra_finale.strip():
                        extra_finale = "Frutta (da chiedere)"
                else:
                    extra_finale = extra_selezionato
                
            if st.button("Invia Ordine Finale"):
                if non_mangio:
                    c.execute("INSERT INTO orders VALUES (?, ?, '', '', '', '', '', '', '', '', 0, 1)", 
                              (oggi, st.session_state.username))
                else:
                    c.execute("INSERT INTO orders VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, '', ?, 0)", 
                              (oggi, st.session_state.username, primo, secondo_finale, contorno, fritti, piadine, extra_finale, pane))
                
                conn.commit()
                st.success("Ordine inviato con successo al ristorante virtuale!")
                st.rerun()
                
    conn.close()

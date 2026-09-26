import streamlit as st
import datetime
import json
import urllib.parse
from PIL import Image
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials

# --- CONNESSIONE GOOGLE SHEETS ---
@st.cache_resource
def get_gsheets_client():
    try:
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error("Errore credenziali Google. Controlla di aver copiato bene il JSON nei Secrets.")
        st.stop()

def get_col(row, idx):
    """Aiuta a leggere le righe di Google Fogli evitando errori se mancano colonne"""
    return str(row[idx]).strip() if idx < len(row) else ""

@st.cache_resource
def get_sheets():
    # Streamlit aprirà il file una sola volta e lo terrà in memoria
    client_gs = get_gsheets_client()
    f = client_gs.open_by_url("https://docs.google.com/spreadsheets/d/1y8rcz2mRrBhqC3QPuSniTZuTyKc1Oe74rKS3wNxM-ik/edit?gid=0#gid=0")
    return f.worksheet("users"), f.worksheet("menu"), f.worksheet("orders")

users_sheet, menu_sheet, orders_sheet = get_sheets()

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
        users_data = users_sheet.get_all_values()
        result = None
        # Salta la prima riga se è l'intestazione
        for row in users_data:
            if len(row) >= 3 and row[0] == user_input and row[1] == pass_input:
                result = row[2]
                break
                
        if result:
            st.session_state.logged_in = True
            st.session_state.username = user_input
            st.session_state.role = result
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
            with st.spinner("L'IA sta leggendo il menu, e salvando su Google Fogli..."):
                menu_estratto = parse_menu_from_image(foto_menu)
                
                if menu_estratto:
                    # Cancella il vecchio menu di oggi
                    tutti_menu = menu_sheet.get_all_values()
                    righe_da_cancellare = [i + 1 for i, row in enumerate(tutti_menu) if get_col(row, 0) == oggi]
                    for idx in reversed(righe_da_cancellare):
                        menu_sheet.delete_rows(idx)
                    
                    # Salva il nuovo
                    nuove_righe = []
                    for categoria, piatti in menu_estratto.items():
                        if categoria == "Data":
                            nuove_righe.append([oggi, "DataEstratta", str(piatti)])
                            continue
                        for piatto in piatti:
                            nuove_righe.append([oggi, categoria, piatto])
                    
                    if nuove_righe:
                        menu_sheet.append_rows(nuove_righe)
                        
                    st.success("Menu salvato in cassaforte su Google Fogli!")

    with tab2:
        st.subheader("Riepilogo Ordini")
        menu_data = menu_sheet.get_all_values()
        
        data_menu_letto = oggi
        for row in menu_data:
            if get_col(row, 0) == oggi and get_col(row, 1) == "DataEstratta":
                data_menu_letto = get_col(row, 2)
        
        orders_data = orders_sheet.get_all_values()
        ordini = [row for row in orders_data if get_col(row, 0) == oggi]

        if not ordini:
            st.info("Nessun ordine ricevuto finora oggi.")
        else:
            testo_schermo = "#### Dettaglio per persona (visibile solo a te)\n"
            
            totale_primi, totale_secondi, totale_contorni = {}, {}, {}
            totale_fritti, totale_piadine, totale_extra = {}, {}, {}
            totale_pane = 0
            numero_colleghi = 0

            for row in ordini:
                utente = get_col(row, 1)
                not_eating = get_col(row, 11)
                
                if not_eating in ['1', 'TRUE', 'True']:
                    testo_schermo += f"- 🚫 **{utente}**: *Non mangia / Porta da casa*\n"
                    continue
                
                numero_colleghi += 1
                piatti_scelti = []
                
                primo = get_col(row, 2)
                secondo = get_col(row, 3)
                contorno = get_col(row, 5)
                fritti = get_col(row, 6)
                piadine = get_col(row, 7)
                extra = get_col(row, 8)
                pane = get_col(row, 10)

                if primo and primo != "Nessuno": 
                    piatti_scelti.append(primo)
                    totale_primi[primo] = totale_primi.get(primo, 0) + 1
                    
                if secondo and secondo != "Nessuno":
                    piatti_scelti.append(secondo)
                    totale_secondi[secondo] = totale_secondi.get(secondo, 0) + 1
                    
                if contorno and contorno != "Nessuno": 
                    piatti_scelti.append(contorno)
                    totale_contorni[contorno] = totale_contorni.get(contorno, 0) + 1
                    
                if fritti and fritti != "Nessuno": 
                    piatti_scelti.append(fritti)
                    totale_fritti[fritti] = totale_fritti.get(fritti, 0) + 1
                    
                if piadine and piadine != "Nessuno": 
                    piatti_scelti.append(piadine)
                    totale_piadine[piadine] = totale_piadine.get(piadine, 0) + 1
                    
                if extra and extra != "Nessuno":
                    piatti_scelti.append(extra)
                    totale_extra[extra] = totale_extra.get(extra, 0) + 1
                    
                if pane in ['1', 'TRUE', 'True']: 
                    piatti_scelti.append("Pane fresco")
                    totale_pane += 1

                testo_schermo += f"- 👤 **{utente}**: {', '.join(piatti_scelti)}\n"
            
            st.markdown(testo_schermo)
            st.markdown("---")
            
            # WhatsApp Message
            st.subheader("Messaggio per il Ristorante")
            testo_whatsapp = f"*Ordine per pranzo NOE PUSIANO, {data_menu_letto}*\n"
            testo_whatsapp += f"*Totale colleghi:* {numero_colleghi}\n\n"
            
            def aggiungi_sezione(titolo, dizionario):
                t = ""
                if dizionario:
                    t += f"*{titolo}*\n"
                    for piatto, qta in dizionario.items():
                        t += f"{qta}x {piatto}\n"
                    t += "\n"
                return t

            testo_whatsapp += aggiungi_sezione("PRIMI", totale_primi)
            testo_whatsapp += aggiungi_sezione("SECONDI", totale_secondi)
            testo_whatsapp += aggiungi_sezione("CONTORNI", totale_contorni)
            testo_whatsapp += aggiungi_sezione("FRITTI", totale_fritti)
            testo_whatsapp += aggiungi_sezione("PIADINE E PANINI", totale_piadine)
            testo_whatsapp += aggiungi_sezione("DOLCI E FRUTTA", totale_extra)
            
            if totale_pane > 0:
                testo_whatsapp += f"*PANE*\n{totale_pane}x Pane fresco\n\n"

            st.code(testo_whatsapp, language="text")
            
            testo_wa_url = urllib.parse.quote(testo_whatsapp)
            link_wa = f"https://wa.me/390284344847?text={testo_wa_url}"
            st.link_button("🟢 Invia Ordine su WhatsApp", link_wa)

    with tab3:
        st.subheader("Crea nuovo collega")
        new_user = st.text_input("Nome Utente Collega")
        new_pass = st.text_input("Password Collega")
        if st.button("Crea Account"):
            utenti_esistenti = [get_col(r, 0) for r in users_sheet.get_all_values()]
            if new_user in utenti_esistenti:
                st.error("L'utente esiste già!")
            else:
                users_sheet.append_row([new_user, new_pass, 'user'])
                st.success(f"Utente {new_user} aggiunto a Google Fogli!")

# --- PANNELLO UTENTE ---
elif st.session_state.role == 'user':
    st.title(f"👋 Ciao, {st.session_state.username}")
    if st.button("Esci"):
        st.session_state.logged_in = False
        st.rerun()

    oggi = datetime.date.today().strftime("%Y-%m-%d")
    
    # Controlla se ha già ordinato
    orders_data = orders_sheet.get_all_values()
    ha_ordinato = None
    for row in orders_data:
        if get_col(row, 0) == oggi and get_col(row, 1) == st.session_state.username:
            ha_ordinato = row
            break
    
    if ha_ordinato:
        st.success("Hai già inviato la tua scelta per oggi! 🎉")
        st.markdown("### 📋 Riepilogo del tuo ordine:")
        st.markdown("---")
        
        not_eating = get_col(ha_ordinato, 11)
        if not_eating in ['1', 'TRUE', 'True']:
            st.write("🚫 **Oggi non mangi / Porti da casa**")
        else:
            p1, p2, p_cont, p_fritti, p_piad, p_extra = get_col(ha_ordinato, 2), get_col(ha_ordinato, 3), get_col(ha_ordinato, 5), get_col(ha_ordinato, 6), get_col(ha_ordinato, 7), get_col(ha_ordinato, 8)
            
            if p1 and p1 != "Nessuno": st.write(f"- **Primo:** {p1}")
            if p2 and p2 != "Nessuno": st.write(f"- **Secondo:** {p2}")
            if p_cont and p_cont != "Nessuno": st.write(f"- **Contorno:** {p_cont}")
            if p_fritti and p_fritti != "Nessuno": st.write(f"- **Fritti:** {p_fritti}")
            if p_piad and p_piad != "Nessuno": st.write(f"- **Piadina/Panino:** {p_piad}")
            if p_extra and p_extra != "Nessuno": st.write(f"- **Dolce/Frutta:** {p_extra}")
            
            if get_col(ha_ordinato, 10) in ['1', 'TRUE', 'True']: 
                st.write(f"- 🍞 **Pane fresco richiesto**")
        
    else:
        menu_data = menu_sheet.get_all_values()
        menu_items = [row for row in menu_data if get_col(row, 0) == oggi]
        
        data_mostrata = "Oggi"
        for row in menu_items:
            if get_col(row, 1) == "DataEstratta":
                data_mostrata = get_col(row, 2)
        
        if not menu_items:
            st.info("L'amministratore non ha ancora caricato il menu di oggi.")
        else:
            st.subheader(f"Menu del: {data_mostrata}")
            
            menu_dict = {
                "Primi": ["Nessuno"], "Secondi": ["Nessuno"], "Contorni": ["Nessuno"], 
                "Fritti": ["Nessuno"], "Piadina Panini Farciti": ["Nessuno"], "Dolci/Frutta": ["Nessuno"]
            }
            
            for row in menu_items:
                cat, item = get_col(row, 1), get_col(row, 2)
                if cat in menu_dict:
                    menu_dict[cat].append(item)

            non_mangio = st.checkbox("Oggi non mangio / Porto da casa 🚫")

            if not non_mangio:
                st.markdown("---")
                pane = st.checkbox("🍞 Voglio anche il pane fresco", value=False)
                st.markdown("---")
                
                primo = st.radio("Scegli il Primo:", menu_dict["Primi"])
                
                secondo_selezionato = st.radio("Scegli il Secondo:", menu_dict["Secondi"] + ["componi il tuo piatto, scrivi tu"])
                if secondo_selezionato == "componi il tuo piatto, scrivi tu":
                    secondo_finale = st.text_input("📝 Scrivi il tuo piatto qui sotto:")
                    if not secondo_finale.strip(): 
                        secondo_finale = "Piatto composto (da chiedere)"
                else:
                    secondo_finale = secondo_selezionato
                
                contorno = st.radio("Scegli il Contorno:", menu_dict["Contorni"])
                fritti = st.radio("Scegli Fritti:", menu_dict["Fritti"])
                piadine = st.radio("Scegli Piadina o Panino:", menu_dict["Piadina Panini Farciti"])
                
                extra_selezionato = st.radio("Scegli Dolce/Frutta:", menu_dict["Dolci/Frutta"] + ["scrivi la tua frutta"])
                if extra_selezionato == "scrivi la tua frutta":
                    extra_finale = st.text_input("📝 Scrivi la frutta che desideri qui sotto:")
                    if not extra_finale.strip():
                        extra_finale = "Frutta (da chiedere)"
                else:
                    extra_finale = extra_selezionato
                
            if st.button("Invia Ordine Finale"):
                # Valori da salvare su Google Fogli
                pane_str = '1' if (not non_mangio and pane) else '0'
                not_eating_str = '1' if non_mangio else '0'
                
                if non_mangio:
                    riga_ordine = [oggi, st.session_state.username, '', '', '', '', '', '', '', '', pane_str, not_eating_str]
                else:
                    riga_ordine = [oggi, st.session_state.username, primo, secondo_finale, '', contorno, fritti, piadine, extra_finale, '', pane_str, not_eating_str]
                
                with st.spinner("Invio ordine al server..."):
                    orders_sheet.append_row(riga_ordine)
                
                st.success("Ordine inviato con successo al ristorante virtuale!")
                st.rerun()

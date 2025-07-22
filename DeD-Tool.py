import requests
import os
import sys

__VERSION__ = "1.0.1"  # La versione corrente del mio script

# 🔗 URL diretti ai file nel repository GitHub
VERSION_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/version.txt"
SCRIPT_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/DeD-Tool.py"

def check_for_updates():
    try:
        response = requests.get(VERSION_URL, timeout=5)
        response.raise_for_status()
        latest_version = response.text.strip()

        if latest_version > __VERSION__:
            print(f"\n🟡 È disponibile una nuova versione: {latest_version}. Aggiornamento in corso...")

            new_code = requests.get(SCRIPT_URL).text
            script_path = os.path.abspath(__file__)

            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(new_code)

            print("✅ Aggiornamento completato. Riavvia il programma.")
            input("Premi Invio per chiudere...")
            sys.exit(0)
    except Exception as e:
        print(f"⚠️ Errore durante il controllo aggiornamenti: {e}")

# 🔁 Esegui il controllo all'avvio del programma
check_for_updates()

import base64
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import io
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from supabase import create_client, Client
import pandas as pd
import uuid
import json
from openai import OpenAI
import smtplib
from email.message import EmailMessage
from tabulate import tabulate

client = OpenAI(
    base_url="http://localhost:1234/v1",  # ← questa è la porta del server LM Studio
    api_key="lmstudio"  # ← valore fittizio richiesto dal client
)

def show_welcome_message():
    print("=" * 60)
    print("🎲 Benvenuto su D&D Tool V.1.0.1".center(60))
    print("👨‍💻 Creato da Massimo Trevisan".center(60))
    print("=" * 60)
    print()
    input("Premi Invio per iniziare...")

def load_public_env(filename="DeD-Tool.env_pub"):
    load_dotenv(filename)
    return {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_KEY_ANON": os.getenv("SUPABASE_KEY_ANON")
    }

def load_secure_env(secret_key_file="secret.key", encrypted_file="DeD-Tool.env_sec.enc"):
    try:
        if not os.path.exists(secret_key_file):
            print("🔒 Nessuna chiave segreta trovata. Ambiente sicuro non caricato.")
            return {}
        with open(secret_key_file, "rb") as key_file:
            key = key_file.read()
        with open(encrypted_file, "rb") as enc_file:
            encrypted = enc_file.read()
        decrypted = Fernet(key).decrypt(encrypted).decode()
        env_dict = {}
        for line in decrypted.splitlines():
            if line and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()
                env_dict[k.strip()] = v.strip()
        print("✅ Variabili sicure caricate.")
        return env_dict
    except Exception as e:
        print(f"❌ Errore durante il caricamento dell'ambiente sicuro: {e}")
        return {}

# Caricamento effettivo
load_public_env()
env_sec = load_secure_env()

# Usa le variabili da os.environ se ti serve compatibilità futura
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY_ANON = os.getenv("SUPABASE_KEY_ANON")
SUPABASE_KEY_SERVICE_ROLE = env_sec.get("SUPABASE_KEY_SERVICE_ROLE")

SMTP_EMAIL = env_sec.get("GMAIL_USER")
SMTP_PASSWORD = env_sec.get("GMAIL_PASS")

def send_email_notification(to_email, subject, body):
    smtp_server = "smtp.gmail.com"
    smtp_port = 465  # SSL

    sender_email = env_sec["GMAIL_USER"]
    app_password = env_sec["GMAIL_PASS"]

    if not sender_email or not app_password:
        print("❌ Email o password non trovate nel file .env")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)
        print(f"📧 Email inviata con successo a {to_email}")
    except Exception as e:
        print(f"❌ Errore durante l'invio email a {to_email}: {e}")

class DeDTool:
    # Nomi dei mesi personalizzati come richiesto
    MONTH_NAMES = [
        "NUWMONT", "VATERMONT", "THAUMONT", "FLAURMONT",
        "YARTHMONT", "KLARMONT", "FELMONT", "FYRMONT",
        "AMBYRMONT", "SVIFTMONT", "EIRMONT", "KALDMONT"
    ]

    # Stati degli obiettivi

    OBJECTIVE_STATUS = {
        "NON_INIZIATO": 0,
        "IN_CORSO": 1,
        "COMPLETATO": 2,
        "FALLITO": 3
    }    
    OBJECTIVE_STATUS_REV = {
        0: "NON_INIZIATO",
        1: "IN_CORSO",
        2: "COMPLETATO",
        3: "FALLITO"
    }

    def __init__(self):
        # Carica variabili da file .env pubblici e criptati
        env_pub = load_public_env()

        # Imposta credenziali pubbliche
        self.SUPABASE_URL = env_pub.get("SUPABASE_URL")
        self.SUPABASE_KEY_ANON = env_pub.get("SUPABASE_KEY_ANON")

        # Connessione come utente (accesso base per login)
        self.supabase = create_client(self.SUPABASE_URL, self.SUPABASE_KEY_ANON)

        # Connessione amministratore solo se disponibile
        if env_sec and "SUPABASE_KEY_SERVICE_ROLE" in env_sec:
            self.SUPABASE_KEY_SERVICE_ROLE = env_sec["SUPABASE_KEY_SERVICE_ROLE"]
            self.supabase_admin = create_client(self.SUPABASE_URL, self.SUPABASE_KEY_SERVICE_ROLE)
        else:
            print("⚠️ Modalità limitata: accesso DM disabilitato (manca .env_sec.enc o chiave admin)")
            self.supabase_admin = None  # fallback

        self.current_user = None
        self.game_date = self._load_game_date()
            
    def _clear_screen(self):
        # Clears the console screen
        os.system('cls' if os.name == 'nt' else 'clear')

    def _load_game_date(self):
        """Loads the game date from Supabase or initializes it."""
        try:
            response = self.supabase.from_('game_state').select('*').execute()
            if response.data:
                # Assuming there's only one row for game state with id 1
                date_str = response.data[0]['current_date']
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            else:
                # Initialize if no date is found (e.g., first run)
                print("Nessuna data di gioco trovata. Inizializzazione della data al 01 NUWMONT 1.")
                initial_date = datetime(1, 1, 1).date() # Year 1, Month 1, Day 1
                # Ensure game_state table has an 'id' column for updates
                # For first insert, it might generate its own UUID if ID not specified or serial
                self.supabase_admin.from_('game_state').insert({"id": 1, "current_date": initial_date.strftime('%Y-%m-%d')}).execute()
                return initial_date
        except Exception as e:
            print(f"Errore nel caricamento della data di gioco: {e}")
            print("Inizializzazione della data di gioco a una data predefinita a causa di un errore.")
            return datetime(1, 1, 1).date() # Fallback
            
    def _convert_date_to_ded_format(self, date_obj):
        """Converte una data standard in formato Mystara (es: '01 NUWMONT 1')"""
        day = date_obj.day
        month = self.MONTH_NAMES[date_obj.month - 1]  # Mesi da 0 a 11
        year = date_obj.year
        return f"{day:02d} {month} {year}"

    def _save_game_date(self):
        """Saves the current game date to Supabase."""
        try:
            # Assumes 'game_state' has a row with id 1. If not, needs a different upsert strategy.
            response = self.supabase_admin.from_('game_state').update(
                {"current_date": self.game_date.strftime('%Y-%m-%d')}
            ).eq('id', 1).execute() 
            
            if not response.data:
                # If update by ID 1 fails (e.g., no row with ID 1), try inserting
                # This assumes 'id' is not auto-incrementing on insert for 'game_state' or handles upsert.
                # If 'id' is a simple integer PK, `upsert` with a fixed ID is best.
                # For simplicity, if update fails, we might just re-insert. Or better, check if exists and then update/insert.
                check_response = self.supabase.from_('game_state').select('id').eq('id', 1).execute()
                if not check_response.data: # If no row with id 1 exists, insert it
                    self.supabase_admin.from_('game_state').insert({"id": 1, "current_date": self.game_date.strftime('%Y-%m-%d')}).execute()
                else: # If it exists but update failed, something else is wrong
                    print(f"Avviso: Data di gioco non salvata con ID 1, ma una riga esiste. Controllare database.")
        except Exception as e:
            print(f"Errore nel salvataggio della data di gioco: {e}")


    def _get_user_by_username(self, username):
        try:
            response = self.supabase.from_('users').select('*').eq('username', username).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Errore nella ricerca utente: {e}")
            return None

    def login(self):
        self._clear_screen()
        print("--- Login ---")
        username = input("Nome utente: ").strip()
        password = input("Password: ").strip()

        user = self._get_user_by_username(username)
        if user and user['password'] == password: # In un'applicazione reale, usare hashing per le password!
            self.current_user = user
            print(f"Benvenuto, {self.current_user['username']} ({self.current_user['role']})!")
            input("\nPremi Invio per continuare...")
            return True
        else:
            print("Nome utente o password non validi.")
            input("\nPremi Invio per continuare...")
            return False

    def register_user(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può registrare nuovi utenti.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Registra Nuovo Utente ---")
        while True:
            username = input("Inserisci un nuovo nome utente: ").strip()
            if not username:
                print("Il nome utente non può essere vuoto.")
                continue
            if self._get_user_by_username(username):
                print("Nome utente già esistente. Scegliere un nome utente diverso.")
            else:
                break
        
        password = input("Inserisci una password: ").strip()
        if not password:
            print("La password non può essere vuota.")
            input("\nPremi Invio per continuare...")
            return

        while True:
            role = input("Scegli il ruolo (DM/GIOCATORE): ").strip().upper()
            if role in ['DM', 'GIOCATORE']:
                break
            else:
                print("Ruolo non valido. Inserisci 'DM' o 'GIOCATORE'.")

        try:
            response = self.supabase_admin.from_('users').insert({
                "username": username,
                "password": password, # ATTENZIONE: In produzione, usare hashing + salting!
                "role": role
            }).execute()
            if response.data:
                print(f"Utente '{username}' registrato con successo come '{role}'.")
            else:
                print(f"Errore nella registrazione dell'utente: {response.json()}")
        except Exception as e:
            print(f"Si è verificato un errore: {e}")
        input("\nPremi Invio per continuare...")

    # --- Funzioni di Gestione PG (esistenti) ---
    def add_player_character(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può aggiungere personaggi giocanti.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Aggiungi Personaggio Giocante ---")
        name = input("Nome del PG: ").strip()
        if not name:
            print("Il nome del PG non può essere vuoto.")
            input("\nPremi Invio per continuare...")
            return

        # Recupera tutti gli utenti 'GIOCATORE'
        try:
            response = self.supabase.from_('users').select('*').eq('role', 'GIOCATORE').execute()
            players = response.data
            if not players:
                print("Nessun utente 'GIOCATORE' trovato. Registrare prima un GIOCATORE.")
                input("\nPremi Invio per continuare...")
                return

            print("\nUtenti 'GIOCATORE' disponibili:")
            for i, player in enumerate(players):
                print(f"{i+1}. {player['username']}")

            while True:
                try:
                    player_choice = int(input("Seleziona il numero del GIOCATORE a cui associare il PG: ")) - 1
                    if 0 <= player_choice < len(players):
                        selected_player_id = players[player_choice]['id']
                        break
                    else:
                        print("Scelta non valida. Riprova.")
                except ValueError:
                    print("Input non valido. Inserisci un numero.")

            response = self.supabase_admin.from_('player_characters').insert({
                "name": name,
                "user_id": selected_player_id
            }).execute()
            if response.data:
                print(f"Personaggio '{name}' aggiunto con successo e associato a '{players[player_choice]['username']}'.")
            else:
                print(f"Errore nell'aggiunta del personaggio: {response.json()}")
        except Exception as e:
            print(f"Si è verificato un errore: {e}")
        input("\nPremi Invio per continuare...")

    def list_player_characters(self, show_all=False, wait_for_input=True):
        self._clear_screen()
        print("--- Lista Personaggi Giocanti ---")

        try:
            if show_all:
                response = self.supabase.from_('player_characters').select('*, users(username)').execute()
            else:
                response = self.supabase.from_('player_characters').select('*, users(username)').eq('user_id', self.current_user['id']).execute()

            pgs = response.data

            if pgs:
                print("{:<4} {:<20} {:<20}".format("N.", "Nome PG", "Associato a"))
                print("-" * 50)
                for i, pg in enumerate(pgs):
                    username = pg['users']['username'] if pg.get('users') else "N/D"
                    print(f"{i+1:<4} {pg['name']:<20} {username:<20}")
                if wait_for_input:
                    input("\nPremi Invio per continuare...")
                return pgs
            else:
                print("Nessun personaggio trovato.")
                if wait_for_input:
                    input("\nPremi Invio per continuare...")
                return []
        except Exception as e:
            print(f"Errore durante il recupero dei personaggi: {e}")
            if wait_for_input:
                input("\nPremi Invio per continuare...")
            return []


    def remove_player_character(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può rimuovere personaggi giocanti.")
            input("\nPremi Invio per continuare...")
            return

        pgs = self.list_player_characters(show_all=True)
        if not pgs:
            input("\nPremi Invio per continuare...")
            return

        try:
            pg_index = int(input("\nSeleziona il numero del PG da rimuovere: ")) - 1
            if 0 <= pg_index < len(pgs):
                selected_pg = pgs[pg_index]
            else:
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        conferma = input(f"Sei sicuro di voler rimuovere il PG '{selected_pg['name']}'? (s/N): ").strip().lower()
        if conferma != 's':
            print("Operazione annullata.")
            input("\nPremi Invio per continuare...")
            return

        try:
            response = self.supabase_admin.from_('player_characters').delete().eq('id', selected_pg['id']).execute()
            if response.data:
                print(f"PG '{selected_pg['name']}' rimosso con successo.")
            else:
                print("Errore durante la rimozione del PG.")
        except Exception as e:
            print(f"Errore nella rimozione del PG: {e}")
        input("\nPremi Invio per continuare...")

    def update_player_character(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può modificare personaggi giocanti.")
            input("\nPremi Invio per continuare...")
            return

        pgs = self.list_player_characters(show_all=True)
        if not pgs:
            input("\nPremi Invio per continuare...")
            return

        try:
            pg_index = int(input("\nSeleziona il numero del PG da modificare: ")) - 1
            if 0 <= pg_index < len(pgs):
                selected_pg = pgs[pg_index]
            else:
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nModifica PG: {selected_pg['name']}")
        new_name = input(f"Nuovo nome (lascia vuoto per mantenere '{selected_pg['name']}'): ").strip()

        try:
            response = self.supabase.from_('users').select('*').eq('role', 'GIOCATORE').execute()
            players = response.data

            print("\nUtenti 'Giocatore' disponibili per riassegnazione:")
            for i, player in enumerate(players):
                print(f"{i+1}. {player['username']}")
            print("0. Non cambiare l'associazione del giocatore.")

            new_player_id = selected_pg['user_id']
            while True:
                player_choice_str = input("Seleziona il numero del nuovo giocatore (0 per non cambiare): ").strip()
                if not player_choice_str or player_choice_str == '0':
                    break
                try:
                    player_choice = int(player_choice_str) - 1
                    if 0 <= player_choice < len(players):
                        new_player_id = players[player_choice]['id']
                        break
                    else:
                        print("Scelta non valida. Riprova.")
                except ValueError:
                    print("Input non valido. Inserisci un numero.")

            update_data = {}
            if new_name:
                update_data['name'] = new_name
            if new_player_id != selected_pg['user_id']:
                update_data['user_id'] = new_player_id

            if update_data:
                response = self.supabase_admin.from_('player_characters').update(update_data).eq('id', selected_pg['id']).execute()
                if response.data:
                    print(f"PG '{selected_pg['name']}' modificato con successo.")
                else:
                    print(f"Errore nella modifica del PG: {response.json()}")
            else:
                print("Nessuna modifica da applicare.")
        except Exception as e:
            print(f"Si è verificato un errore: {e}")
        input("\nPremi Invio per continuare...")

    
    # Funzioni di Gestione Banche
    def add_bank(self):
        self._clear_screen()
        print("--- Aggiungi Nuova Banca ---")
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può aggiungere banche.")
            input("\nPremi Invio per continuare...")
            return

        name = input("Nome della Banca: ")
        location = input("Luogo della Banca: ")
        
        while True:
            try:
                annual_interest = float(input("Interessi annuali (%): "))
                break
            except ValueError:
                print("Input non valido. Inserisci un numero per gli interessi annuali.")

        while True:
            try:
                initial_balance = float(input("Fondi iniziali della Banca: "))
                break
            except ValueError:
                print("Input non valido. Inserisci un numero per il saldo iniziale.")
        
        # Aggiunta della selezione PG
        pgs = self.list_player_characters(show_all=True, wait_for_input=False)
        pg_id = None
        
        if pgs:
            print("\nSeleziona il PG a cui associare la banca (0 per nessun PG):")
            for i, pg in enumerate(pgs):
                print(f"{i+1}. {pg['name']}")
            print("0. Nessun PG (banca generica)")
            
            while True:
                try:
                    pg_choice = input("Numero del PG (0 per nessun PG): ").strip()
                    if not pg_choice:  # Se l'utente preme solo invio
                        pg_choice = '0'
                    pg_choice = int(pg_choice)
                    if pg_choice == 0:
                        break
                    elif 1 <= pg_choice <= len(pgs):
                        pg_id = pgs[pg_choice-1]['id']
                        break
                    else:
                        print("Scelta non valida. Riprova.")
                except ValueError:
                    print("Input non valido. Inserisci un numero.")

        try:
            bank_data = {
                'id': str(uuid.uuid4()), # Genera un ID univoco
                'user_id': self.current_user['id'], # Associa la banca all'utente corrente
                'name': name,
                'location': location,
                'annual_interest': annual_interest,
                'initial_balance': initial_balance,
                'current_balance': initial_balance, # Il saldo corrente inizialmente è uguale a quello iniziale
                'pg_id': pg_id if pg_id else None  # Aggiunge l'ID del PG se selezionato
            }
            response = self.supabase.table('banks').insert(bank_data).execute()
            print(f"Banca '{name}' aggiunta con successo!")
            if pg_id:
                pg_name = next(pg['name'] for pg in pgs if pg['id'] == pg_id)
                print(f"Associata al PG: {pg_name}")
        except Exception as e:
            print(f"Errore durante l'aggiunta della banca: {e}")
        input("\nPremi Invio per continuare...")

    def list_banks(self, show_all=False):
        self._clear_screen()
        print("--- Lista Conti Bancari ---\n")

        try:
            if show_all:
                response = self.supabase.from_('banks').select('*, player_characters(name)').execute()
            elif self.current_user and self.current_user['role'] == 'GIOCATORE':
                pg_response = self.supabase.from_('player_characters') \
                    .select('id') \
                    .eq('user_id', self.current_user['id']) \
                    .execute()

                user_pg_ids = [pg['id'] for pg in pg_response.data]

                if not user_pg_ids:
                    print("⚠️ Nessun personaggio trovato associato al tuo account.")
                    input("\nPremi Invio per continuare...")
                    return []

                response = self.supabase.from_('banks') \
                    .select('*, player_characters(name)') \
                    .in_('pg_id', user_pg_ids) \
                    .execute()
            else:
                print("⚠️ Accesso non autorizzato o utente non valido.")
                input("\nPremi Invio per continuare...")
                return []

            banks = response.data
            if not banks:
                print("⚠️ Nessun conto bancario trovato.")
            else:
                print("{:<3} {:<20} {:<15} {:<12} {:<15} {:<10}".format(
                    "#", "Nome Banca", "PG", "Saldo", "Luogo", "Interesse"
                ))
                print("-" * 85)
                for i, bank in enumerate(banks, 1):
                    pg_name = bank.get('player_characters', {}).get('name', 'Sconosciuto')
                    name = bank.get('name', 'N/A')
                    balance = bank.get('current_balance', 0.0)
                    location = bank.get('location', 'N/A')
                    interest = f"{bank.get('annual_interest', 0.0):.2f}%"
                    print("{:<3} {:<20} {:<15} {:<12.2f} {:<15} {:<10}".format(
                        i, name, pg_name, balance, location, interest
                    ))

            input("\nPremi Invio per continuare...")
            return banks

        except Exception as e:
            print(f"❌ Errore durante il recupero dei conti bancari: {e}")
            input("\nPremi Invio per continuare...")
            return []

    def update_bank(self):
        self._clear_screen()
        print("--- Aggiorna Banca ---")
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può aggiornare le banche.")
            input("\nPremi Invio per continuare...")
            return

        banks = self.list_banks(show_all=True, wait_for_input=False)
        if not banks:
            input("\nPremi Invio per continuare...")
            return

        try:
            bank_index = int(input("\nSeleziona il numero della banca da modificare: ")) - 1
            if 0 <= bank_index < len(banks):
                bank = banks[bank_index]
            else:
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
        except ValueError:
            print("Input non valido.")
            input("\nPremi Invio per continuare...")
            return

        try:
            if bank:
                print(f"Modifica banca: {bank['name']}")
                print(f"1. Nome attuale: {bank['name']}")
                print(f"2. Luogo attuale: {bank['location']}")
                print(f"3. Interessi annuali attuali: {bank['annual_interest']}")
                print(f"4. Saldo iniziale attuale: {bank['initial_balance']}")
                print(f"5. Saldo corrente attuale: {bank['current_balance']}")
                print(f"6. PG intestatario attuale: {bank['player_characters']['name'] if bank.get('player_characters') else 'Nessuno'}")
                print("0. Annulla")

                choice = input("Scegli il campo da modificare: ")
                updated_value = None
                field_to_update = None

                if choice == '1':
                    field_to_update = 'name'
                    updated_value = input("Nuovo nome della banca: ")
                elif choice == '2':
                    field_to_update = 'location'
                    updated_value = input("Nuovo luogo della banca: ")
                elif choice == '3':
                    field_to_update = 'annual_interest'
                    while True:
                        try:
                            updated_value = float(input("Nuovi interessi annuali (%): "))
                            break
                        except ValueError:
                            print("Input non valido. Inserisci un numero.")
                elif choice == '4':
                    field_to_update = 'initial_balance'
                    while True:
                        try:
                            updated_value = float(input("Nuovo saldo iniziale: "))
                            break
                        except ValueError:
                            print("Input non valido. Inserisci un numero.")
                elif choice == '5':
                    field_to_update = 'current_balance'
                    while True:
                        try:
                            updated_value = float(input("Nuovo saldo corrente: "))
                            break
                        except ValueError:
                            print("Input non valido. Inserisci un numero.")
                elif choice == '6':
                    # Nuova opzione per cambiare PG intestatario
                    pgs = self.list_player_characters(show_all=True, wait_for_input=False)
                    if pgs:
                        print("\nSeleziona il nuovo PG intestatario (0 per nessun PG):")
                        for i, pg in enumerate(pgs):
                            print(f"{i+1}. {pg['name']}")
                        print("0. Nessun PG (banca generica)")
                        
                        while True:
                            try:
                                pg_choice = input("Numero del PG (0 per nessun PG): ").strip()
                                if not pg_choice:  # Se l'utente preme solo invio
                                    pg_choice = '0'
                                pg_choice = int(pg_choice)
                                if pg_choice == 0:
                                    field_to_update = 'pg_id'
                                    updated_value = None
                                    break
                                elif 1 <= pg_choice <= len(pgs):
                                    field_to_update = 'pg_id'
                                    updated_value = pgs[pg_choice-1]['id']
                                    break
                                else:
                                    print("Scelta non valida. Riprova.")
                            except ValueError:
                                print("Input non valido. Inserisci un numero.")
                    else:
                        print("Nessun PG disponibile per l'associazione.")
                        input("\nPremi Invio per continuare...")
                        return
                elif choice == '0':
                    print("Aggiornamento annullato.")
                    input("\nPremi Invio per continuare...")
                    return
                else:
                    print("Opzione non valida.")
                    input("\nPremi Invio per continuare...")
                    return

                if field_to_update:
                    update_data = {field_to_update: updated_value}
                    response = self.supabase.table('banks').update(update_data).eq('id', bank['id']).execute()
                    print(f"Banca '{bank['name']}' aggiornata con successo!")
            else:
                print("Banca non trovata o non autorizzato.")
        except Exception as e:
            print(f"Errore durante l'aggiornamento della banca: {e}")
        input("\nPremi Invio per continuare...")

    def remove_bank(self):
        self._clear_screen()
        print("--- Rimuovi Banca ---")
        
        # Verifica permessi DM
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può rimuovere banche.")
            input("\nPremi Invio per continuare...")
            return

        # Lista banche disponibili
        banks = self.list_banks(show_all=True, wait_for_input=False)
        if not banks:
            print("Nessuna banca disponibile per la rimozione.")
            input("\nPremi Invio per continuare...")
            return

        try:
            # Selezione banca
            bank_index = int(input("\nSeleziona il numero della banca da rimuovere: ")) - 1
            if not (0 <= bank_index < len(banks)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return

            bank_data = banks[bank_index]  # Banca selezionata

            # Conferma rimozione
            conferma = input(f"\nSei sicuro di voler rimuovere la banca '{bank_data['name']}'? (s/N): ").strip().lower()
            if conferma != 's':
                print("Operazione annullata.")
                input("\nPremi Invio per continuare...")
                return

            # Esecuzione rimozione
            response = self.supabase.from_('banks').delete().eq('id', bank_data['id']).execute()
            
            if response.data:
                print(f"\nBanca '{bank_data['name']}' rimossa con successo!")
            else:
                print("\nErrore durante la rimozione della banca.")

        except ValueError:
            print("\nInput non valido. Inserire un numero.")
        except Exception as e:
            print(f"\nErrore durante la rimozione: {str(e)}")
        
        input("\nPremi Invio per continuare...")
 
    def view_bank_transactions(self):
        self._clear_screen()
        print("--- Storico Operazioni Bancarie ---")

        try:
            if self.current_user['role'] == 'DM':
                # Il DM può vedere tutte le transazioni
                banks_response = self.supabase.from_('banks').select('id, name').execute()
                banks = banks_response.data
            else:
                # Il giocatore può vedere solo le transazioni delle sue banche
                pg_response = self.supabase.from_('player_characters') \
                    .select('id') \
                    .eq('user_id', self.current_user['id']) \
                    .execute()
                user_pg_ids = [pg['id'] for pg in pg_response.data]

                if not user_pg_ids:
                    print("⚠️ Nessun personaggio trovato associato al tuo account.")
                    input("\nPremi Invio per continuare...")
                    return

                banks_response = self.supabase.from_('banks') \
                    .select('id, name') \
                    .in_('pg_id', user_pg_ids) \
                    .execute()
                banks = banks_response.data

            if not banks:
                print("⚠️ Nessuna banca trovata.")
                input("\nPremi Invio per continuare...")
                return

            print("\nBanche disponibili:")
            for i, bank in enumerate(banks):
                print(f"{i+1}. {bank['name']}")
            print("0. Torna al menu")

            bank_choice = input("Seleziona una banca: ")
            if bank_choice == '0':
                return

            try:
                bank_index = int(bank_choice) - 1
                if not (0 <= bank_index < len(banks)):
                    print("Scelta non valida.")
                    input("\nPremi Invio per continuare...")
                    return
            except ValueError:
                print("Input non valido.")
                input("\nPremi Invio per continuare...")
                return

            selected_bank_id = banks[bank_index]['id']
            selected_bank_name = banks[bank_index]['name']

            transactions_response = self.supabase.from_('bank_transactions') \
                .select('*') \
                .eq('bank_id', selected_bank_id) \
                .order('timestamp', desc=True) \
                .execute()
            transactions = transactions_response.data

            print(f"\n--- Transazioni per la banca '{selected_bank_name}' ---")
            if not transactions:
                print("Nessuna transazione trovata.")
            else:
                for tx in transactions:
                    ded_date = self._convert_date_to_ded_format(self.game_date)
                    print(f"- [{ded_date}] {tx['operation_type'].capitalize()} di {tx['amount']:.2f} → {tx.get('reason', 'Senza motivo')}")

        except Exception as e:
            print(f"❌ Errore durante la visualizzazione delle transazioni: {e}")

        input("\nPremi Invio per continuare...")
 
    def deposit_funds(self):
        self._clear_screen()
        print("--- Deposita Fondi ---")

        banks = self.list_banks(show_all=(self.current_user['role'] == 'DM'))
        if not banks:
            return

        try:
            index = int(input("\nSeleziona la banca per il deposito: ")) - 1
            if not (0 <= index < len(banks)):
                print("Scelta non valida.")
                return
            selected_bank = banks[index]
            amount = float(input("Importo da depositare: "))
            reason = input("Motivazione del deposito: ")

            if amount <= 0:
                print("Importo non valido.")
                return

            new_balance = selected_bank['current_balance'] + amount

            update_resp = self.supabase.from_('banks').update({'current_balance': new_balance}).eq('id', selected_bank['id']).execute()
            insert_resp = self.supabase.from_('bank_transactions').insert({
                'bank_id': selected_bank['id'],
                'operation_type': 'deposito',
                'amount': amount,
                'reason': reason
            }).execute()

            print(f"✅ Deposito di {amount:.2f} effettuato con successo.")

        except Exception as e:
            print(f"❌ Errore nel deposito: {e}")
        input("\nPremi Invio per continuare...")

    def withdraw_funds(self):
        self._clear_screen()
        print("--- Preleva Fondi ---")

        banks = self.list_banks(show_all=(self.current_user['role'] == 'DM'))
        if not banks:
            return

        try:
            index = int(input("\nSeleziona la banca da cui prelevare: ")) - 1
            if not (0 <= index < len(banks)):
                print("Scelta non valida.")
                return
            selected_bank = banks[index]
            amount = float(input("Importo da prelevare: "))
            reason = input("Motivazione del prelievo: ")

            if amount <= 0 or amount > selected_bank['current_balance']:
                print("Importo non valido o fondi insufficienti.")
                return

            new_balance = selected_bank['current_balance'] - amount

            update_resp = self.supabase.from_('banks').update({'current_balance': new_balance}).eq('id', selected_bank['id']).execute()
            insert_resp = self.supabase.from_('bank_transactions').insert({
                'bank_id': selected_bank['id'],
                'operation_type': 'prelievo',
                'amount': amount,
                'reason': reason
            }).execute()

            print(f"✅ Prelievo di {amount:.2f} effettuato con successo.")

        except Exception as e:
            print(f"❌ Errore nel prelievo: {e}")
        input("\nPremi Invio per continuare...")

    def transfer_funds(self):
        self._clear_screen()
        print("--- Trasferisci Fondi tra Banche ---")

        banks = self.list_banks(show_all=(self.current_user['role'] == 'DM'))
        if not banks or len(banks) < 2:
            print("⚠️ Sono necessarie almeno due banche per trasferire fondi.")
            input("\nPremi Invio per continuare...")
            return

        try:
            print("\nSeleziona la banca di origine:")
            for i, bank in enumerate(banks):
                print(f"{i+1}. {bank['name']} - Saldo: {bank['current_balance']:.2f}")
            from_index = int(input("Numero: ")) - 1
            from_bank = banks[from_index]

            print("\nSeleziona la banca di destinazione:")
            for i, bank in enumerate(banks):
                if i != from_index:
                    print(f"{i+1}. {bank['name']} - Saldo: {bank['current_balance']:.2f}")
            to_index = int(input("Numero: ")) - 1
            to_bank = banks[to_index]

            # Restrizione per giocatori: possono spostare solo tra banche dello stesso PG
            if self.current_user['role'] != 'DM':
                if from_bank.get('pg_id') != to_bank.get('pg_id'):
                    print("⚠️ Puoi trasferire fondi solo tra banche dello stesso PG.")
                    input("\nPremi Invio per continuare...")
                    return

            amount = float(input("Importo da trasferire: "))
            reason = input("Motivazione del trasferimento: ")

            if amount <= 0 or amount > from_bank['current_balance']:
                print("Importo non valido o fondi insufficienti.")
                return

            # Esegui trasferimento
            self.supabase.from_('banks').update({'current_balance': from_bank['current_balance'] - amount}).eq('id', from_bank['id']).execute()
            self.supabase.from_('banks').update({'current_balance': to_bank['current_balance'] + amount}).eq('id', to_bank['id']).execute()

            # Log delle operazioni
            self.supabase.from_('bank_transactions').insert({
                'bank_id': from_bank['id'],
                'operation_type': 'trasferimento',
                'amount': amount,
                'reason': f"Da {from_bank['name']} a {to_bank['name']}: {reason}"
            }).execute()

            print(f"✅ Trasferimento di {amount:.2f} completato.")

        except Exception as e:
            print(f"❌ Errore nel trasferimento: {e}")
        input("\nPremi Invio per continuare...")
 
    # --- Funzioni di Gestione Seguaci-----
    def add_follower(self):
        if not self.current_user:
            print("Devi essere loggato per aggiungere un seguace.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Aggiungi Seguace ---")

        pgs = self.list_player_characters(show_all=True if self.current_user['role'] == 'DM' else False)
        if not pgs:
            input("\nPremi Invio per continuare...")
            return
         
        if self.current_user['role'] == 'GIOCATORE':
            pgs = [pg for pg in pgs if pg['user_id'] == self.current_user['id']]
            if not pgs:
                print("Nessun PG associato al tuo account. Chiedi al DM di associare un PG.")
                input("\nPremi Invio per continuare...")
                return

        print("\nSeleziona il PG a cui associare il seguace:")
        for i, pg in enumerate(pgs):
            print(f"{i+1}. {pg['name']}")
        
        selected_pg = None
        while selected_pg is None:
            try:
                pg_choice = int(input("Numero del PG: ")) - 1
                if 0 <= pg_choice < len(pgs):
                    selected_pg = pgs[pg_choice]
                else:
                    print("Scelta non valida. Riprova.")
            except ValueError:
                print("Input non valido. Inserisci un numero.")
        
        follower_name = input("Nome del seguace: ").strip()
        if not follower_name:
            print("Il nome del seguace non può essere vuoto.")
            input("\nPremi Invio per continuare...")
            return
        
        # NUOVI CAMPI
        follower_class = input("Classe del seguace: ").strip()
        
        level = None
        while level is None:
            try:
                level_str = input("Livello del seguace (lascia vuoto per 1): ").strip()
                if not level_str:
                    level = 1
                else:
                    level = int(level_str)
                    if level <= 0:
                        print("Il livello deve essere un numero positivo.")
                        level = None # Richiedi di nuovo
            except ValueError:
                print("Input non valido. Inserisci un numero intero.")

        annual_cost = None
        while annual_cost is None:
            try:
                annual_cost_str = input("Costo annuale del seguace (lascia vuoto per 0): ").strip()
                if not annual_cost_str:
                    annual_cost = 0.0
                else:
                    annual_cost = float(annual_cost_str)
                    if annual_cost < 0:
                        print("Il costo annuale non può essere negativo.")
                        annual_cost = None # Richiedi di nuovo
            except ValueError:
                print("Input non valido. Inserisci un numero.")

        notes = input("Note sul seguace: ").strip()
        # Recupera banche associate al PG selezionato
        try:
            banks_response = self.supabase.from_('banks').select('*').eq('pg_id', selected_pg['id']).execute()
            pg_banks = banks_response.data
        except Exception as e:
            print(f"Errore nel recupero delle banche: {e}")
            pg_banks = []

        bank_destination_cost = None
        if pg_banks:
            print("\nBanche disponibili per il PG:")
            for i, bank in enumerate(pg_banks):
                print(f"{i+1}. {bank['name']} ({bank['location']})")
            print("0. Nessuna banca (lascia vuoto)")

            while True:
                try:
                    bank_choice = input("Seleziona la banca da usare per il costo (0 per nessuna): ").strip()
                    if not bank_choice or bank_choice == '0':
                        bank_destination_cost = None
                        break
                    bank_index = int(bank_choice) - 1
                    if 0 <= bank_index < len(pg_banks):
                        bank_destination_cost = pg_banks[bank_index]['id']
                        break
                    else:
                        print("Scelta non valida.")
                except ValueError:
                    print("Inserisci un numero valido.")
        else:
            print("Nessuna banca trovata per il PG. Il campo sarà lasciato vuoto.")


        description = input("Razza (es. 'Umano', 'Elfo'): ").strip() # Lasciato per coerenza se lo usi altrove

        try:
            response = self.supabase.from_('followers').insert({
                "pg_id": selected_pg['id'],
                "name": follower_name,
                "class": follower_class,      # Nuovo campo
                "level": level,               # Nuovo campo
                "annual_cost": annual_cost,   # Nuovo campo
                "notes": notes,               # Nuovo campo
                "bank_destination_cost": bank_destination_cost, # Nuovo campo
                "description": description # Già esistente, ma lo includo
            }).execute()
            if response.data:
                print(f"Seguace '{follower_name}' aggiunto con successo a {selected_pg['name']}.")
            else:
                print(f"Errore nell'aggiunta del seguace: {response.json()}")
        except Exception as e:
            print(f"Si è verificato un errore: {e}")
        input("\nPremi Invio per continuare...")

    def list_followers(self, show_all=False):
        self._clear_screen()
        print("--- Lista Seguaci Raggruppati per PG ---\n")
        try:
            if self.current_user and self.current_user['role'] == 'GIOCATORE':
                # Recupera solo i PG dell'utente loggato
                pg_response = self.supabase.from_('player_characters') \
                    .select('id') \
                    .eq('user_id', self.current_user['id']) \
                    .execute()
                user_pg_ids = [pg['id'] for pg in pg_response.data]

                if not user_pg_ids:
                    print("⚠️ Nessun personaggio trovato associato al tuo account.")
                    input("\nPremi Invio per continuare...")
                    return []

                # Filtra i seguaci dei PG dell'utente
                response = self.supabase.from_('followers') \
                    .select('*, player_characters(name, users(username)), banks(name)') \
                    .in_('pg_id', user_pg_ids) \
                    .execute()
            else:
                # DM o amministratori vedono tutti i seguaci
                response = self.supabase.from_('followers') \
                    .select('*, player_characters(name, users(username)), banks(name)') \
                    .execute()

            followers = response.data

            if not followers:
                print("Nessun seguace trovato.")
                input("\nPremi Invio per continuare...")
                return []

            # Raggruppa i seguaci per nome PG
            pg_groups = {}
            for f in followers:
                pg_name = f['player_characters']['name'] if f.get('player_characters') else 'N/A'
                if pg_name not in pg_groups:
                    pg_groups[pg_name] = []
                pg_groups[pg_name].append(f)

            # Visualizzazione
            for pg_name, group in pg_groups.items():
                print(f"Nome PG         : {pg_name}\n")

                fields = ["name", "class", "level", "annual_cost", "banks", "notes", "description"]
                labels = ["Nome Seguace", "Classe", "Livello", "Costo Ann.", "Banca", "Note", "Descrizione"]

                for label, field in zip(labels, fields):
                    row = f"{label:<15} : "
                    for follower in group:
                        value = "N/A"
                        if field == "banks":
                            value = follower["banks"]["name"] if follower.get("banks") else "Nessuna"
                        elif field == "annual_cost":
                            value = f"{follower.get(field, 0.0):.2f} MO"
                        else:
                            value = str(follower.get(field, "N/A"))
                        row += f"{value:<25}"
                    print(row)
                print("-" * 100)

            input("\nPremi Invio per continuare...")
            return followers

        except Exception as e:
            print(f"❌ Errore nel caricamento dei seguaci: {e}")
            input("\nPremi Invio per continuare...")
            return []

    def update_follower(self):
        if not self.current_user:
            print("Devi essere loggato per modificare un seguace.")
            input("\nPremi Invio per continuare...")
            return

        followers = self.list_followers(show_all=True if self.current_user['role'] == 'DM' else False)
        if not followers:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero del seguace da modificare:")
        for i, f in enumerate(followers):
            pg_name = f['player_characters']['name'] if f['player_characters'] else 'N/A'
            print(f"{i+1}. {f['name']} (PG: {pg_name})")

        try:
            follower_index = int(input("Numero: ")) - 1
            if not (0 <= follower_index < len(followers)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_follower = followers[follower_index]
            follower_id_to_update = selected_follower['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        if not selected_follower:
            print("Seguace non trovato.")
            input("\nPremi Invio per continuare...")
            return
        
        # Check permission
        if self.current_user['role'] == 'GIOCATORE':
            pg_response = self.supabase.from_('player_characters').select('id').eq('user_id', self.current_user['id']).execute()
            user_pg_ids = [pg['id'] for pg in pg_response.data]
            if selected_follower['pg_id'] not in user_pg_ids:
                print("Non hai i permessi per modificare questo seguace.")
                input("\nPremi Invio per continuare...")
                return

        print(f"\nModifica Seguace: ({selected_follower['name']}) per {selected_follower['player_characters']['name']}")
        
        update_data = {}

        new_name = input(f"Nuovo nome seguace (lascia vuoto per mantenere '{selected_follower['name']}'): ").strip()
        if new_name:
            update_data['name'] = new_name
        
        # NUOVI CAMPI PER L'UPDATE
        new_follower_class = input(f"Nuova classe (lascia vuoto per mantenere '{selected_follower.get('class', 'N/A')}'): ").strip()
        if new_follower_class:
            update_data['class'] = new_follower_class

        new_level = selected_follower.get('level')
        while True:
            level_str = input(f"Nuovo livello (lascia vuoto per mantenere '{selected_follower.get('level', 'N/A')}', 0 per rimuovere): ").strip()
            if not level_str:
                break
            try:
                level_val = int(level_str)
                if level_val == 0:
                    new_level = None # Se 0 significa rimuovere il valore
                    break
                if level_val > 0:
                    new_level = level_val
                    break
                else:
                    print("Il livello deve essere un numero positivo. Riprova.")
            except ValueError:
                print("Input non valido. Inserisci un numero intero.")
        if new_level != selected_follower.get('level'):
            update_data['level'] = new_level

        new_annual_cost = selected_follower.get('annual_cost')
        while True:
            annual_cost_str = input(f"Nuovo costo annuale (lascia vuoto per mantenere '{selected_follower.get('annual_cost', 'N/A')}', 0 per rimuovere): ").strip()
            if not annual_cost_str:
                break
            try:
                annual_cost_val = float(annual_cost_str)
                if annual_cost_val == 0:
                    new_annual_cost = 0.0 # O None se preferisci rimuovere
                    break
                if annual_cost_val >= 0:
                    new_annual_cost = annual_cost_val
                    break
                else:
                    print("Il costo annuale non può essere negativo. Riprova.")
            except ValueError:
                print("Input non valido. Inserisci un numero.")
        if new_annual_cost != selected_follower.get('annual_cost'):
            update_data['annual_cost'] = new_annual_cost

        new_notes = input(f"Nuove note (lascia vuoto per mantenere '{selected_follower.get('notes', 'N/A')}'): ").strip()
        if new_notes:
            update_data['notes'] = new_notes

        # Recupera il nome della banca attuale (se presente)
        current_bank_name = selected_follower.get('banks', {}).get('name') if selected_follower.get('banks') else 'Nessuna'
        new_bank_destination_cost = input(f"Nuova banca destinazione costo (lascia vuoto per mantenere '{current_bank_name}', 0 per rimuovere): ").strip()

        if new_bank_destination_cost == '0':
            update_data['bank_destination_cost'] = None
        elif new_bank_destination_cost:
            update_data['bank_destination_cost'] = new_bank_destination_cost
        
        new_description = input(f"Nuova descrizione (lascia vuoto per mantenere '{selected_follower['description']}'): ").strip()
        if new_description:
            update_data['description'] = new_description

        # DM can reassign PG, Players cannot
        new_pg_id = selected_follower['pg_id']
        if self.current_user['role'] == 'DM':
            pgs = self.list_player_characters(show_all=True)
            if pgs:
                print("\nSeleziona il nuovo PG a cui associare il seguace (0 per non cambiare):")
                for i, pg in enumerate(pgs):
                    print(f"{i+1}. {pg['name']}")
                
                while True:
                    try:
                        pg_choice_str = input("Numero del nuovo PG: ").strip()
                        if not pg_choice_str:
                            break
                        pg_choice = int(pg_choice_str) - 1
                        if pg_choice == -1: # Choice 0
                            break
                        elif 0 <= pg_choice < len(pgs):
                            new_pg_id = pgs[pg_choice]['id']
                            break
                        else:
                            print("Scelta non valida. Riprova.")
                    except ValueError:
                        print("Input non valido. Inserisci un numero.")
            if new_pg_id != selected_follower['pg_id']:
                update_data['pg_id'] = new_pg_id

        if update_data:
            try:
                response = self.supabase_admin.from_('followers').update(update_data).eq('id', follower_id_to_update).execute()
                if response.data:
                    print(f"Seguace '{selected_follower['name']}' modificato con successo.")
                else:
                    print(f"Errore nella modifica del seguace: {response.json()}")
            except Exception as e:
                print(f"Si è verificato un errore: {e}")
        else:
            print("Nessuna modifica da applicare.")
        input("\nPremi Invio per continuare...")

    def remove_follower(self):
        if not self.current_user:
            print("Devi essere loggato per rimuovere un seguace.")
            input("\nPremi Invio per continuare...")
            return

        followers = self.list_followers(show_all=True if self.current_user['role'] == 'DM' else False)
        if not followers:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero del seguace da rimuovere:")
        for i, f in enumerate(followers):
            pg_name = f['player_characters']['name'] if f['player_characters'] else 'N/A'
            print(f"{i+1}. {f['name']} (PG: {pg_name})")

        try:
            follower_index = int(input("Numero: ")) - 1
            if not (0 <= follower_index < len(followers)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_follower = followers[follower_index]
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        # Check permission
        if self.current_user['role'] == 'GIOCATORE':
            pg_response = self.supabase.from_('player_characters').select('id').eq('user_id', self.current_user['id']).execute()
            user_pg_ids = [pg['id'] for pg in pg_response.data]
            if selected_follower['pg_id'] not in user_pg_ids:
                print("Non hai i permessi per rimuovere questo seguace.")
                input("\nPremi Invio per continuare...")
                return

        confirm = input(f"Sei sicuro di voler rimuovere il seguace '{selected_follower['name']}'? (s/N): ").strip().lower()
        if confirm == 's':
            try:
                response = self.supabase.from_('followers').delete().eq('id', selected_follower['id']).execute()
                if response.data:
                    print(f"Seguace '{selected_follower['name']}' rimosso con successo.")
                else:
                    print(f"Errore nella rimozione del seguace: {response.json()}")
            except Exception as e:
                print(f"Si è verificato un errore: {e}")
        else:
            print("Rimozione annullata.")
        input("\nPremi Invio per continuare...")

    def followers_menu(self):
        while True:
            self._clear_screen()
            print("--- Gestione Seguaci ---")
            print("1. Aggiungi Seguace")
            print("2. Lista Seguaci")
            print("3. Modifica Seguace")
            print("4. Rimuovi Seguace")
            print("0. Torna al Menu Principale")
            
            choice = input("Scegli un'opzione: ").strip()
            
            if choice == '1':
                self.add_follower()
            elif choice == '2':
                self.list_followers(show_all=True if self.current_user['role'] == 'DM' else False)
            elif choice == '3':
                self.update_follower()
            elif choice == '4':
                self.remove_follower()
            elif choice == '0':
                break
            else:
                print("Opzione non valida. Riprova.")
                input("\nPremi Invio per continuare...")
                
    # --- Funzioni di Gestione Attività Economiche (esistenti) ---
    def add_economic_activity(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può aggiungere attività economiche.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Aggiungi Attività Economica ---")

        pgs = self.list_player_characters(show_all=True) # DM sees all PGs
        if not pgs:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il PG a cui associare l'attività economica:")
        for i, pg in enumerate(pgs):
            print(f"{i+1}. {pg['name']}")
        
        selected_pg = None
        while selected_pg is None:
            try:
                pg_choice = int(input("Numero del PG: ")) - 1
                if 0 <= pg_choice < len(pgs):
                    selected_pg = pgs[pg_choice]
                else:
                    print("Scelta non valida. Riprova.")
            except ValueError:
                print("Input non valido. Inserisci un numero.")

        description = input("Descrizione attività (es. 'Negozio di pozioni'): ").strip()
        income_str = input("Guadagno stimato (es. 50.00): ").strip()
        frequency = input("Frequenza (es. 'settimanale', 'mensile', 'giornaliera'): ").strip().lower()

        try:
            income = float(income_str)
        except ValueError:
            print("Guadagno non valido. Impostato a 0.")
            income = 0.0
        
        # Select destination bank
        banks_for_pg_response = self.supabase.from_('banks').select('*').eq('pg_id', selected_pg['id']).execute()
        banks_for_pg = banks_for_pg_response.data

        if not banks_for_pg:
            print(f"Il PG '{selected_pg['name']}' non ha conti bancari. Aggiungi un conto prima.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nSeleziona la banca di destinazione per il guadagno di '{selected_pg['name']}':")
        for i, bank in enumerate(banks_for_pg):
            print(f"{i+1}. {bank['name']} (Saldo: {bank.get('current_balance', 0.0):.2f})")
        
        selected_bank_id = None
        while selected_bank_id is None:
            try:
                bank_choice = int(input("Numero della banca: ")) - 1
                if 0 <= bank_choice < len(banks_for_pg):
                    selected_bank_id = banks_for_pg[bank_choice]['id']
                else:
                    print("Scelta non valida. Riprova.")
            except ValueError:
                print("Input non valido. Inserisci un numero.")

        try:
            response = self.supabase_admin.from_('economic_activities').insert({
                "pg_id": selected_pg['id'],
                "description": description,
                "income": income,
                "frequency": frequency,
                "destination_bank_id": selected_bank_id
            }).execute()
            if response.data:
                print(f"Attività economica '{description}' aggiunta con successo per {selected_pg['name']}.")
            else:
                print(f"Errore nell'aggiunta dell'attività economica: {response.json()}")
        except Exception as e:
            print(f"Si è verificato un errore: {e}")
        input("\nPremi Invio per continuare...")

    def list_economic_activities(self, show_all=False):
        self._clear_screen()
        print("--- Lista Attività Economiche ---\n")
        try:
            query = self.supabase.from_('economic_activities') \
                .select('*, player_characters(name, users(username)), banks(name)')

            if not show_all and self.current_user['role'] == 'GIOCATORE':
                pg_response = self.supabase.from_('player_characters').select('id').eq('user_id', self.current_user['id']).execute()
                user_pg_ids = [pg['id'] for pg in pg_response.data]
                if not user_pg_ids:
                    print("Nessuna attività economica trovata per i tuoi personaggi.")
                    input("\nPremi Invio per continuare...")
                    return []
                query = query.in_('pg_id', user_pg_ids)

            response = query.execute()
            activities = response.data

            if not activities:
                print("Nessuna attività economica trovata.")
                input("\nPremi Invio per continuare...")
                return []

            # Raggruppa per personaggio
            pg_activities = {}
            for act in activities:
                pg_name = act['player_characters']['name'] if act['player_characters'] else 'Sconosciuto'
                pg_activities.setdefault(pg_name, []).append(act)

            for pg_name, acts in pg_activities.items():
                print(f"👤 Nome PG       : {pg_name}")
                for act in acts:
                    print(f"   Descrizione   : {act.get('description', 'N/A')}")
                    print(f"   Guadagno      : {act.get('income', 0.0):.2f} MO")
                    print(f"   Frequenza     : {act.get('frequency', 'N/A')}")
                    bank_name = act['banks']['name'] if act.get('banks') else 'Nessuna'
                    print(f"   Banca Dest.   : {bank_name}")
                    print("-" * 40)
                print("")  # Riga vuota tra PG

            return activities

        except Exception as e:
            print(f"Si è verificato un errore nel recupero delle attività economiche: {e}")
            return []
        finally:
            input("\nPremi Invio per continuare...")

    def update_economic_activity(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può modificare attività economiche.")
            input("\nPremi Invio per continuare...")
            return

        activities = self.list_economic_activities(show_all=True)
        if not activities:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero dell'attività economica da modificare:")
        for i, a in enumerate(activities):
            pg_name = a['player_characters']['name'] if a['player_characters'] else 'N/A'
            print(f"{i+1}. {a['description']} (PG: {pg_name}, Guadagno: {a['income']:.2f}, Frequenza: {a['frequency']})")

        try:
            choice = int(input("Numero (0 per annullare): ").strip())
            if choice == 0:
                print("Operazione annullata.")
                input("\nPremi Invio per continuare...")
                return
            if not (1 <= choice <= len(activities)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_activity = activities[choice - 1]
            activity_id_to_update = selected_activity['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return
        
        print(f"\nModifica Attività Economica: {selected_activity['description']} per {selected_activity['player_characters']['name']}")
        
        new_description = input(f"Nuova descrizione (lascia vuoto per mantenere '{selected_activity['description']}'): ").strip()
        new_income_str = input(f"Nuovo guadagno (lascia vuoto per mantenere '{selected_activity['income']:.2f}'): ").strip()
        new_frequency = input(f"Nuova frequenza (lascia vuoto per mantenere '{selected_activity['frequency']}'): ").strip().lower()

        update_data = {}
        if new_description:
            update_data['description'] = new_description
        if new_income_str:
            try:
                update_data['income'] = float(new_income_str)
            except ValueError:
                print("Guadagno non valido, mantenuto il guadagno attuale.")
        if new_frequency:
            update_data['frequency'] = new_frequency
        
        # DM can reassign PG and destination bank
        new_pg_id = selected_activity['pg_id']
        pgs = self.list_player_characters(show_all=True)
        if pgs:
            print("\nSeleziona il nuovo PG a cui associare l'attività (0 per non cambiare):")
            for i, pg in enumerate(pgs):
                print(f"{i+1}. {pg['name']}")
            
            while True:
                try:
                    pg_choice_str = input("Numero del nuovo PG: ").strip()
                    if not pg_choice_str:
                        break
                    pg_choice = int(pg_choice_str) - 1
                    if pg_choice == -1: # Choice 0
                        break
                    elif 0 <= pg_choice < len(pgs):
                        new_pg_id = pgs[pg_choice]['id']
                        break
                    else:
                        print("Scelta non valida. Riprova.")
                except ValueError:
                    print("Input non valido. Inserisci un numero.")
        if new_pg_id != selected_activity['pg_id']:
            update_data['pg_id'] = new_pg_id

        # Update destination bank for the (potentially new) PG
        selected_pg_for_bank = next((pg for pg in pgs if pg['id'] == new_pg_id), None)
        if selected_pg_for_bank:
            banks_for_pg_response = self.supabase.from_('banks').select('*').eq('pg_id', selected_pg_for_bank['id']).execute()
            banks_for_pg = banks_for_pg_response.data

            if banks_for_pg:
                print(f"\nSeleziona la nuova banca di destinazione per il guadagno di '{selected_pg_for_bank['name']}' (0 per non cambiare):")
                for i, bank in enumerate(banks_for_pg):
                    print(f"{i+1}. {bank['name']} (Saldo: {bank.get('current_balance', 0.0):.2f})")
                
                new_bank_id = selected_activity['destination_bank_id']
                while True:
                    try:
                        bank_choice_str = input("Numero della nuova banca: ").strip()
                        if not bank_choice_str:
                            break
                        bank_choice = int(bank_choice_str) - 1
                        if bank_choice == -1: # Choice 0
                            break
                        elif 0 <= bank_choice < len(banks_for_pg):
                            new_bank_id = banks_for_pg[bank_choice]['id']
                            break
                        else:
                            print("Scelta non valida. Riprova.")
                    except ValueError:
                        print("Input non valido. Inserisci un numero.")
                if new_bank_id != selected_activity['destination_bank_id']:
                    update_data['destination_bank_id'] = new_bank_id
            else:
                print(f"Attenzione: Il PG '{selected_pg_for_bank['name']}' non ha conti bancari. La banca di destinazione non può essere modificata.")
                # Decide if you want to set destination_bank_id to None or keep old
                # For now, will set to None if no banks for new PG
                if selected_activity['bank_id'] is not None and new_pg_id != selected_activity['pg_id']:
                    print("La banca di destinazione precedente non è valida per il nuovo PG. Impostazione a NULL.")
                    update_data['bank_id'] = None 

        if update_data:
            try:
                response = self.supabase_admin.from_('economic_activities').update(update_data).eq('id', activity_id_to_update).execute()
                if response.data:
                    print(f"Attività economica '{selected_activity['description']}' modificata con successo.")
                else:
                    print(f"Errore nella modifica dell'attività economica: {response.json()}")
            except Exception as e:
                print(f"Si è verificato un errore: {e}")
        else:
            print("Nessuna modifica da applicare.")
        input("\nPremi Invio per continuare...")

    def remove_economic_activity(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può rimuovere attività economiche.")
            input("\nPremi Invio per continuare...")
            return

        activities = self.list_economic_activities(show_all=True)
        if not activities:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero dell'attività economica da rimuovere:")
        for i, a in enumerate(activities):
            pg_name = a['player_characters']['name'] if a['player_characters'] else 'N/A'
            print(f"{i+1}. {a['description']} (PG: {pg_name}, Guadagno: {a['income']:.2f}, Frequenza: {a['frequency']})")

        try:
            choice = int(input("Numero (0 per annullare): ").strip())
            if choice == 0:
                print("Operazione annullata.")
                input("\nPremi Invio per continuare...")
                return
            if not (1 <= choice <= len(activities)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_activity = activities[choice - 1]
            activity_id_to_remove = selected_activity['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        confirm = input(f"Sei sicuro di voler rimuovere l'attività economica '{selected_activity['description']}'? (s/N): ").strip().lower()
        if confirm == 's':
            try:
                response = self.supabase_admin.from_('economic_activities').delete().eq('id', activity_id_to_remove).execute()
                if response.data:
                    print(f"Attività economica '{selected_activity['description']}' rimossa con successo.")
                else:
                    print(f"Errore nella rimozione dell'attività economica: {response.json()}")
            except Exception as e:
                print(f"Si è verificato un errore: {e}")
        else:
            print("Rimozione annullata.")
        input("\nPremi Invio per continuare...")

    # --- Funzioni di Gestione Spese Fisse (esistenti) ---
    def add_fixed_expense(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può aggiungere spese fisse.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Aggiungi Spesa Fissa ---")

        pgs = self.list_player_characters(show_all=True) # DM sees all PGs
        if not pgs:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il PG a cui associare la spesa fissa:")
        for i, pg in enumerate(pgs):
            print(f"{i+1}. {pg['name']}")
        
        selected_pg = None
        while selected_pg is None:
            try:
                pg_choice = int(input("Numero del PG: ")) - 1
                if 0 <= pg_choice < len(pgs):
                    selected_pg = pgs[pg_choice]
                else:
                    print("Scelta non valida. Riprova.")
            except ValueError:
                print("Input non valido. Inserisci un numero.")

        description = input("Descrizione spesa (es. 'Affitto bottega'): ").strip()
        amount_str = input("Ammontare della spesa (es. 25.00): ").strip()
        frequency = input("Frequenza (es. 'settimanale', 'mensile', 'giornaliera'): ").strip().lower()

        try:
            amount = float(amount_str)
        except ValueError:
            print("Ammontare non valido. Impostato a 0.")
            amount = 0.0
        
        # Select source bank
        banks_for_pg_response = self.supabase.from_('banks').select('*').eq('pg_id', selected_pg['id']).execute()
        banks_for_pg = banks_for_pg_response.data

        if not banks_for_pg:
            print(f"Il PG '{selected_pg['name']}' non ha conti bancari. Aggiungi un conto prima.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nSeleziona la banca da cui prelevare la spesa per '{selected_pg['name']}':")
        for i, bank in enumerate(banks_for_pg):
            print(f"{i+1}. {bank['name']} (Saldo: {bank.get('current_balance', 0.0):.2f})")
        
        selected_bank_id = None
        while selected_bank_id is None:
            try:
                bank_choice = int(input("Numero della banca: ")) - 1
                if 0 <= bank_choice < len(banks_for_pg):
                    selected_bank_id = banks_for_pg[bank_choice]['id']
                else:
                    print("Scelta non valida. Riprova.")
            except ValueError:
                print("Input non valido. Inserisci un numero.")

        try:
            response = self.supabase_admin.from_('fixed_expenses').insert({
                "pg_id": selected_pg['id'],
                "description": description,
                "amount": amount,
                "frequency": frequency,
                "source_bank_id": selected_bank_id
            }).execute()
            if response.data:
                print(f"Spesa fissa '{description}' aggiunta con successo per {selected_pg['name']}.")
            else:
                print(f"Errore nell'aggiunta della spesa fissa: {response.json()}")
        except Exception as e:
            print(f"Si è verificato un errore: {e}")
        input("\nPremi Invio per continuare...")

    def list_fixed_expenses(self, show_all=False):
        self._clear_screen()
        print("--- Lista Spese Fisse per Personaggio ---\n")
        try:
            query = self.supabase.from_('fixed_expenses') \
                .select('*, player_characters(name, users(username)), banks(name)') \
                .order('pg_id', desc=False)

            if not self.current_user or self.current_user['role'] == 'DM':
                show_all = True
            else:
                show_all = False

            if not show_all:
                pg_response = self.supabase.from_('player_characters') \
                    .select('id') \
                    .eq('user_id', self.current_user['id']) \
                    .execute()
                user_pg_ids = [pg['id'] for pg in pg_response.data]
                if not user_pg_ids:
                    print("Nessuna spesa fissa trovata per i tuoi personaggi.")
                    input("\nPremi Invio per continuare...")
                    return []
                query = query.in_('pg_id', user_pg_ids)

            response = query.execute()
            expenses = response.data

            if not expenses:
                print("Nessuna spesa fissa trovata.")
                input("\nPremi Invio per continuare...")
                return []

            # Raggruppa per PG
            grouped = {}
            for exp in expenses:
                pg_name = exp['player_characters']['name'] if exp.get('player_characters') else 'N/A'
                grouped.setdefault(pg_name, []).append(exp)

            for pg_name, pg_expenses in grouped.items():
                print(f"Nome PG        : {pg_name}\n")

                labels = ["Descrizione", "Ammontare", "Frequenza", "Banca Sorgente"]
                rows = [[] for _ in labels]

                for exp in pg_expenses:
                    rows[0].append(exp.get('description', ''))
                    rows[1].append(f"{exp.get('amount', 0.0):.2f} MO")
                    rows[2].append(exp.get('frequency', ''))
                    rows[3].append(exp['banks']['name'] if exp.get('banks') else 'Nessuna')

                for label, values in zip(labels, rows):
                    print(f"{label:<15}: " + "  ".join(f"{v:<25}" for v in values))
                print("-" * 100)

            input("\nPremi Invio per continuare...")
            return expenses

        except Exception as e:
            print(f"❌ Errore nel recupero delle spese fisse: {e}")
            input("\nPremi Invio per continuare...")
            return []

    def update_fixed_expense(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può modificare spese fisse.")
            input("\nPremi Invio per continuare...")
            return

        expenses = self.list_fixed_expenses(show_all=True)
        if not expenses:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero della spesa fissa da modificare:")
        for i, e in enumerate(expenses):
            pg_name = e['player_characters']['name'] if e.get('player_characters') else 'N/A'
            print(f"{i+1}. {e['description']} (PG: {pg_name}, Ammontare: {e['amount']:.2f}, Frequenza: {e['frequency']})")

        try:
            choice = int(input("Numero (0 per annullare): ").strip())
            if choice == 0:
                print("Operazione annullata.")
                input("\nPremi Invio per continuare...")
                return
            if not (1 <= choice <= len(expenses)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_expense = expenses[choice - 1]
            expense_id_to_update = selected_expense['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nModifica Spesa Fissa: {selected_expense['description']} (PG: {selected_expense['player_characters']['name']})")

        new_description = input(f"Nuova descrizione (lascia vuoto per mantenere '{selected_expense['description']}'): ").strip()
        new_amount_str = input(f"Nuovo ammontare (lascia vuoto per mantenere '{selected_expense['amount']:.2f}'): ").strip()
        new_frequency = input(f"Nuova frequenza (lascia vuoto per mantenere '{selected_expense['frequency']}'): ").strip().lower()

        update_data = {}
        if new_description:
            update_data['description'] = new_description
        if new_amount_str:
            try:
                update_data['amount'] = float(new_amount_str)
            except ValueError:
                print("Ammontare non valido, mantenuto l'ammontare attuale.")
        if new_frequency:
            update_data['frequency'] = new_frequency

        # DM può cambiare PG e banca
        new_pg_id = selected_expense['pg_id']
        pgs = self.list_player_characters(show_all=True)
        if pgs:
            print("\nSeleziona il nuovo PG a cui associare la spesa (0 per non cambiare):")
            for i, pg in enumerate(pgs):
                print(f"{i+1}. {pg['name']}")

            while True:
                try:
                    pg_choice_str = input("Numero del nuovo PG: ").strip()
                    if not pg_choice_str or pg_choice_str == '0':
                        break
                    pg_choice = int(pg_choice_str) - 1
                    if 0 <= pg_choice < len(pgs):
                        new_pg_id = pgs[pg_choice]['id']
                        break
                    else:
                        print("Scelta non valida. Riprova.")
                except ValueError:
                    print("Input non valido. Inserisci un numero.")
        if new_pg_id != selected_expense['pg_id']:
            update_data['pg_id'] = new_pg_id

        # Se il PG cambia, aggiorniamo la banca
        selected_pg_for_bank = next((pg for pg in pgs if pg['id'] == new_pg_id), None)
        if selected_pg_for_bank:
            banks_for_pg_response = self.supabase.from_('banks').select('*').eq('pg_id', selected_pg_for_bank['id']).execute()
            banks_for_pg = banks_for_pg_response.data

            if banks_for_pg:
                print(f"\nSeleziona la nuova banca di origine per la spesa di '{selected_pg_for_bank['name']}' (0 per non cambiare):")
                for i, bank in enumerate(banks_for_pg):
                    print(f"{i+1}. {bank['name']} (Saldo: {bank.get('current_balance', 0.0):.2f})")

                new_bank_id = selected_expense['source_bank_id']
                while True:
                    try:
                        bank_choice_str = input("Numero della nuova banca: ").strip()
                        if not bank_choice_str or bank_choice_str == '0':
                            break
                        bank_choice = int(bank_choice_str) - 1
                        if 0 <= bank_choice < len(banks_for_pg):
                            new_bank_id = banks_for_pg[bank_choice]['id']
                            break
                        else:
                            print("Scelta non valida. Riprova.")
                    except ValueError:
                        print("Input non valido. Inserisci un numero.")
                if new_bank_id != selected_expense['source_bank_id']:
                    update_data['source_bank_id'] = new_bank_id
            else:
                print(f"Attenzione: Il PG '{selected_pg_for_bank['name']}' non ha conti bancari. La banca di origine non può essere modificata.")
                if selected_expense['source_bank_id'] is not None and new_pg_id != selected_expense['pg_id']:
                    update_data['source_bank_id'] = None

        if update_data:
            try:
                response = self.supabase_admin.from_('fixed_expenses').update(update_data).eq('id', expense_id_to_update).execute()
                if response.data:
                    print(f"Spesa fissa '{selected_expense['description']}' modificata con successo.")
                else:
                    print(f"Errore nella modifica della spesa fissa: {response.json()}")
            except Exception as e:
                print(f"Si è verificato un errore: {e}")
        else:
            print("Nessuna modifica da applicare.")
        input("\nPremi Invio per continuare...")

    def remove_fixed_expense(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può rimuovere spese fisse.")
            input("\nPremi Invio per continuare...")
            return

        expenses = self.list_fixed_expenses(show_all=True)
        if not expenses:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero della spesa fissa da rimuovere:")
        for i, e in enumerate(expenses):
            pg_name = e['player_characters']['name'] if e.get('player_characters') else 'N/A'
            print(f"{i+1}. {e['description']} (PG: {pg_name}, Ammontare: {e['amount']:.2f}, Frequenza: {e['frequency']})")

        try:
            choice = int(input("Numero (0 per annullare): ").strip())
            if choice == 0:
                print("Operazione annullata.")
                input("\nPremi Invio per continuare...")
                return
            if not (1 <= choice <= len(expenses)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_expense = expenses[choice - 1]
            expense_id_to_remove = selected_expense['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        confirm = input(f"Sei sicuro di voler rimuovere la spesa fissa '{selected_expense['description']}'? (s/N): ").strip().lower()
        if confirm == 's':
            try:
                response = self.supabase_admin.from_('fixed_expenses').delete().eq('id', expense_id_to_remove).execute()
                if response.data:
                    print(f"Spesa fissa '{selected_expense['description']}' rimossa con successo.")
                else:
                    print(f"Errore nella rimozione della spesa fissa: {response.json()}")
            except Exception as e:
                print(f"Si è verificato un errore: {e}")
        else:
            print("Rimozione annullata.")
        input("\nPremi Invio per continuare...")

    def manage_users(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Accesso negato. Solo i DM possono gestire gli utenti.")
            input("\nPremi Invio per continuare...")
            return

        while True:
            self._clear_screen()
            print("--- Gestione Utenti (Solo DM) ---")
            print("1. Aggiungi Utente")
            print("2. Modifica Utente")
            print("3. Rimuovi Utente")
            print("4. Lista Utenti")
            print("0. Torna al Menu Principale")

            choice = input("Scegli un'opzione: ")

            if choice == '1':
                self.register_user() # Re-using existing registration logic
            elif choice == '2':
                self.update_user()
            elif choice == '3':
                self.remove_user()
            elif choice == '4':
                self.list_users()
            elif choice == '0':
                break
            else:
                print("Opzione non valida. Riprova.")
                input("\nPremi Invio per continuare...")

    def list_users(self):
        self._clear_screen()
        print("--- Lista Utenti ---")
        try:
            response = self.supabase.from_('users').select('*').execute()
            users = response.data
            if not users:
                print("Nessun utente trovato.")
                return []
            
            print("{:<20} {:<10}".format("Nome Utente", "Ruolo"))
            print("-" * 35)
            for user in users:
                print(f"{user['username']:<20} {user['role']:<10}")
            
            return users
        except Exception as e:
            print(f"Si è verificato un errore nel recupero degli utenti: {e}")
            return []
        finally:
            input("\nPremi Invio per continuare...")

    def update_user(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può modificare gli utenti.")
            input("\nPremi Invio per continuare...")
            return

        users = self.list_users()
        if not users:
            return

        user_id_to_update = input("\nInserisci l'ID dell'utente da modificare: ").strip()
        selected_user = next((u for u in users if str(u['id']) == user_id_to_update), None)

        if not selected_user:
            print("Utente non trovato.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nModifica Utente: {selected_user['username']} (ID: {selected_user['id']})")
        
        new_username = input(f"Nuovo nome utente (lascia vuoto per mantenere '{selected_user['username']}'): ").strip()
        new_password = input("Nuova password (lascia vuoto per non cambiare): ").strip()
        new_role = input(f"Nuovo ruolo (DM/GIOCATORE, lascia vuoto per mantenere '{selected_user['role']}'): ").strip().upper()

        update_data = {}
        if new_username:
            # Check for unique username if changed
            if new_username != selected_user['username'] and self._get_user_by_username(new_username):
                print("Nome utente già esistente. Modifica annullata.")
                input("\nPremi Invio per continuare...")
                return
            update_data['username'] = new_username
        if new_password:
            update_data['password'] = new_password # Again, hash in real app
        if new_role and new_role in ['DM', 'GIOCATORE']:
            update_data['role'] = new_role
        elif new_role and new_role not in ['DM', 'GIOCATORE']:
            print("Ruolo non valido, mantenuto il ruolo attuale.")

        if update_data:
            try:
                response = self.supabase_admin.from_('users').update(update_data).eq('id', user_id_to_update).execute()
                if response.data:
                    print(f"Utente '{selected_user['username']}' modificato con successo.")
                else:
                    print(f"Errore nella modifica dell'utente: {response.json()}")
            except Exception as e:
                print(f"Si è verificato un errore: {e}")
        else:
            print("Nessuna modifica da applicare.")
        input("\nPremi Invio per continuare...")

    def remove_user(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può rimuovere gli utenti.")
            input("\nPremi Invio per continuare...")
            return

        users = self.list_users()
        if not users:
            return

        user_id_to_remove = input("\nInserisci l'ID dell'utente da rimuovere: ").strip()
        selected_user = next((u for u in users if str(u['id']) == user_id_to_remove), None)

        if not selected_user:
            print("Utente non trovato.")
            input("\nPremi Invio per continuare...")
            return
        
        if selected_user['id'] == self.current_user['id']:
            print("Non puoi rimuovere il tuo stesso account mentre sei loggato.")
            input("\nPremi Invio per continuare...")
            return

        confirm = input(f"Sei sicuro di voler rimuovere l'utente '{selected_user['username']}' (ID: {selected_user['id']})? Questa operazione non elimina i PG associati, ma li disassocia dall'utente. (s/N): ").strip().lower()
        if confirm == 's':
            try:
                # First, set user_id of associated PGs to NULL or another default DM user if business logic dictates
                # For this implementation, we will simply set user_id to NULL.
                self.supabase_admin.from_('player_characters').update({'user_id': None}).eq('user_id', user_id_to_remove).execute()
                print(f"PGs precedentemente associati all'utente '{selected_user['username']}' sono stati disassociati.")

                response = self.supabase_admin.from_('users').delete().eq('id', user_id_to_remove).execute()
                if response.data:
                    print(f"Utente '{selected_user['username']}' rimosso con successo.")
                else:
                    print(f"Errore nella rimozione dell'utente: {response.json()}")
            except Exception as e:
                print(f"Si è verificato un errore: {e}")
        else:
            print("Rimozione annullata.")
        input("\nPremi Invio per continuare...")

    # --- FUNZIONALITÀ OBIETTIVI SEGUACI ---

    def add_objective_event(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può inserire imprevisti.")
            input("\nPremi Invio per continuare...")
            return

        # 1. Elenco obiettivi attivi
        objectives_response = self.supabase.from_('follower_objectives') \
            .select('id, name, status, follower_id') \
            .eq('status', self.OBJECTIVE_STATUS['IN_CORSO']).execute()
        objectives = objectives_response.data

        if not objectives:
            print("Nessun obiettivo attualmente in corso.")
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona un obiettivo a cui assegnare un imprevisto:")
        for i, obj in enumerate(objectives):
            print(f"{i+1}. {obj['name']}")

        try:
            choice = int(input("Numero (0 per annullare): ").strip())
            if choice == 0:
                return
            if not (1 <= choice <= len(objectives)):
                print("Scelta non valida.")
                return
            selected_obj = objectives[choice - 1]
        except ValueError:
            print("Input non valido.")
            return

        # 2. Inserimento descrizione dell'imprevisto
        print(f"\nInserisci la descrizione dell'imprevisto per '{selected_obj['name']}':")
        description = input("Descrizione: ").strip()

        # 3. Generazione opzioni con AI
        try:
            options = self.generate_gpt_options(description)
        except Exception as e:
            print(f"❌ Errore durante la generazione delle opzioni: {e}")
            input("\nPremi Invio per continuare...")
            return

        if not options:
            print("⚠️ Nessuna opzione generata.")
            input("\nPremi Invio per continuare...")
            return

        print("\n✅ Opzioni generate automaticamente:")
        for idx, opt in enumerate(options, 1):
            print(f"\nOpzione {idx}:")
            print(f"  Descrizione: {opt.get('option', '')}")
            print(f"  Mesi aggiuntivi: {opt.get('extra_months', 0)}")
            print(f"  Costo aggiuntivo: {opt.get('extra_cost', 0)}")
            if opt.get("fail"):
                print("  ❌ Fallimento previsto")

        # 4. Modifica manuale (opzionale)
        edit = input("\nVuoi modificare una delle opzioni? (s/n): ").lower()
        if edit == 's':
            for i in range(len(options)):
                print(f"\n--- Modifica Opzione {i+1} ---")
                new_desc = input(f"Descrizione [{options[i]['option']}]: ").strip()
                if new_desc:
                    options[i]['option'] = new_desc
                try:
                    new_months = input(f"Mesi aggiuntivi [{options[i].get('extra_months', 0)}]: ").strip()
                    if new_months:
                        options[i]['extra_months'] = int(new_months)
                    new_cost = input(f"Costo aggiuntivo [{options[i].get('extra_cost', 0)}]: ").strip()
                    if new_cost:
                        options[i]['extra_cost'] = float(new_cost)
                    if 'fail' in options[i]:
                        fail_input = input(f"Fallimento? (s/n) [{ 's' if options[i]['fail'] else 'n' }]: ").lower()
                        options[i]['fail'] = True if fail_input == 's' else False
                except Exception as e:
                    print(f"⚠️ Errore nella modifica: {e}")

        # 5. Conferma finale
        print("\nEcco le opzioni finali:")
        for idx, opt in enumerate(options, 1):
            print(f"\nOpzione {idx}: {opt['option']}")
            print(f"  +{opt.get('extra_months', 0)} mesi")
            print(f"  +{opt.get('extra_cost', 0):.2f} MO")
            if opt.get("fail"):
                print("  ⚠️ Fallimento")

        conferma = input("\nConfermi l'inserimento di queste opzioni? (s/n): ").lower()
        if conferma != 's':
            print("Operazione annullata.")
            return

        # 6. Inserimento nel database
        event_data = {
            "objective_id": selected_obj['id'],
            "description": description,
            "type": "IMPREVISTO",
            "response_options": options
        }

        try:
            self.supabase_admin.from_('follower_objective_events').insert(event_data).execute()
            print("✅ Imprevisto registrato con successo.")
        except Exception as e:
            print(f"❌ Errore durante l'inserimento nel DB: {e}")
            return

        # 7. Invio email al giocatore
        try:
            follower_id = selected_obj['follower_id']
            follower_response = self.supabase.from_('followers').select('pg_id').eq('id', follower_id).single().execute()
            follower_data = follower_response.data

            if follower_data and 'pg_id' in follower_data:
                pg_id = follower_data['pg_id']
                user_response = self.supabase.from_('player_characters').select('user_id').eq('id', pg_id).single().execute()
                user_data = user_response.data

                if user_data and 'user_id' in user_data:
                    user_id = user_data['user_id']
                    email_response = self.supabase.from_('users').select('mail').eq('id', user_id).single().execute()
                    email = email_response.data['mail'] if email_response.data else None

                    if email:
                        subject = f"Imprevisto nell'obiettivo '{selected_obj['name']}'"
                        body = f"""Ciao!

    Il tuo seguace ha incontrato un imprevisto: {description}

    Scegli una delle seguenti opzioni:

    """
                        for idx, opt in enumerate(options, 1):
                            body += f"{idx}. {opt['option']} (+{opt['extra_months']} mesi, +{opt['extra_cost']:.2f} MO)\n"

                        body += "\nRispondi a questa email scrivendo solo ad esempio: SCELTA: 2\n\nBuon gioco!"

                        send_email_notification(email, subject, body)
                        print("📩 Email inviata al giocatore.")
                    else:
                        print("⚠️ Impossibile trovare l'email del giocatore.")
                else:
                    print("⚠️ Nessun utente associato al PG dell'obiettivo.")
            else:
                print("⚠️ Nessun PG associato al follower dell'obiettivo.")
        except Exception as e:
            print(f"❌ Errore durante l'invio della mail: {e}")

        input("\nPremi Invio per continuare...")

    def generate_gpt_options(self, description):
        prompt = f"""L'imprevisto è: "{description}". Crea 3 opzioni fantasy che il giocatore può scegliere.
    Ogni opzione deve contenere:
    - una breve descrizione (campo 'option')
    - un numero di mesi extra (campo 'extra_months')
    - un costo aggiuntivo in oro (campo 'extra_cost')
    - oppure, opzionalmente, un fallimento (campo 'fail': true)

    Rispondi in formato JSON:
    [
      {{ "option": "...", "extra_months": int, "extra_cost": float }},
      ...
    ]
    """

        try:
            response = client.chat.completions.create(
                model="mistral",  # nome fittizio accettato da LM Studio
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            print(f"Errore durante la generazione GPT: {e}")
            return []

    def register_objective_choice(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può registrare le scelte dei giocatori.")
            input("\nPremi Invio per continuare...")
            return

        print("\n--- Registra Scelta del Giocatore ---")

        try:
            # 1. Recupera eventi non ancora gestiti e con opzioni
            events_response = self.supabase.from_('follower_objective_events') \
                .select('id, description, response_options, player_choice, objective_id') \
                .eq('handled', False).is_('player_choice', None).execute()

            events = events_response.data
            if not events:
                print("Non ci sono eventi in attesa di risposta.")
                input("\nPremi Invio per continuare...")
                return

            for i, ev in enumerate(events):
                print(f"{i+1}. {ev['description']})")

            try:
                selected = int(input("\nSeleziona l'imprevisto da aggiornare (0 per annullare): "))
                if selected == 0:
                    return
                if not (1 <= selected <= len(events)):
                    print("❌ Scelta non valida.")
                    return
            except ValueError:
                print("❌ Input non valido.")
                return

            selected_event = events[selected - 1]
            options = selected_event['response_options']

            print(f"\nDescrizione: {selected_event['description']}")
            print("Opzioni:")
            for idx, opt in enumerate(options, 1):
                desc = opt.get('option', '')
                months = opt.get('extra_months', 0)
                cost = opt.get('extra_cost', 0)
                fail = " ❌ (Fallimento)" if opt.get('fail') else ""
                print(f"  {idx}. {desc} (+{months} mesi, +{cost:.2f} MO){fail}")

            try:
                choice_idx = int(input("\nNumero dell'opzione scelta dal giocatore: "))
                if not (1 <= choice_idx <= len(options)):
                    print("❌ Scelta non valida.")
                    return
            except ValueError:
                print("❌ Input non valido.")
                return

            selected_choice = options[choice_idx - 1]

            # Aggiorna Supabase con la scelta del giocatore
            update_data = {
                "player_choice": selected_choice,
                "handled": False  # verrà applicato nella fase eventi
            }

            self.supabase_admin.from_('follower_objective_events') \
                .update(update_data) \
                .eq('id', selected_event['id']).execute()

            print("✅ Scelta registrata con successo.")
        except Exception as e:
            print(f"❌ Errore: {e}")
        input("\nPremi Invio per continuare...")

    def add_follower_objective(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può aggiungere obiettivi per i seguaci.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Aggiungi Obiettivo per Seguace ---")

        followers = self.list_followers(show_all=True) # DM sees all followers
        if not followers:
            input("\nPremi Invio per continuare...")
            return
        
        print("\nSeleziona il Seguace a cui associare l'obiettivo:")
        for i, follower in enumerate(followers):
            pg_name = follower['player_characters']['name'] if follower['player_characters'] else 'N/A'
            print(f"{i+1}. {follower['name']} (PG: {pg_name})")
        
        selected_follower = None
        while selected_follower is None:
            try:
                follower_choice = int(input("Numero del Seguace: ")) - 1
                if 0 <= follower_choice < len(followers):
                    selected_follower = followers[follower_choice]
                else:
                    print("Scelta non valida. Riprova.")
            except ValueError:
                print("Input non valido. Inserisci un numero.")
        
        objective_name = input("Nome Obiettivo: ").strip()
        if not objective_name:
            print("Il nome dell'obiettivo non può essere vuoto.")
            input("\nPremi Invio per continuare...")
            return

        while True:
            try:
                estimated_months = int(input("Mesi Stimati al Completamento: "))
                if estimated_months <= 0:
                    print("I mesi stimati devono essere maggiori di 0.")
                    continue
                break
            except ValueError:
                print("Input non valido. Inserisci un numero intero.")

        while True:
            try:
                total_cost = float(input("Costo totale (es. 100.50): "))
                if total_cost < 0:
                    print("Il costo totale non può essere negativo.")
                    continue
                break
            except ValueError:
                print("Input non valido. Inserisci un numero.")
        
        notes = input("Note (opzionale): ").strip()

        # Select destination bank for the cost
        # Need to get PG ID from the selected follower
        selected_follower_pg_id = selected_follower['pg_id']
        banks_for_pg_response = self.supabase.from_('banks').select('*').eq('pg_id', selected_follower_pg_id).execute()
        banks_for_pg = banks_for_pg_response.data

        if not banks_for_pg:
            print(f"Il PG di '{selected_follower['name']}' non ha conti bancari. Aggiungi un conto prima di creare un obiettivo con costi.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nSeleziona la Banca destinazione costo per '{selected_follower['name']}':")
        for i, bank in enumerate(banks_for_pg):
            print(f"{i+1}. {bank['name']} (Saldo: {bank.get('current_balance', 0.0):.2f})")
        
        selected_bank_id = None
        while selected_bank_id is None:
            try:
                bank_choice = int(input("Numero della banca: ")) - 1
                if 0 <= bank_choice < len(banks_for_pg):
                    selected_bank_id = banks_for_pg[bank_choice]['id']
                else:
                    print("Scelta non valida. Riprova.")
            except ValueError:
                print("Input non valido. Inserisci un numero.")

        try:
            response = self.supabase_admin.from_('follower_objectives').insert({
                "follower_id": selected_follower['id'],
                "name": objective_name,
                "estimated_months": estimated_months,
                "total_cost": total_cost,
                "notes": notes,
                "bank_id": selected_bank_id,
                "status": self.OBJECTIVE_STATUS['NON_INIZIATO'],
                "start_date": None, # Will be set when objective starts
                "progress_percentage": 0.0 # Will be updated when objective starts
            }).execute()
            if response.data:
                print(f"Obiettivo '{objective_name}' aggiunto con successo per {selected_follower['name']}.")
            else:
                print(f"Errore nell'aggiunta dell'obiettivo: {response.json()}")
        except Exception as e:
            print(f"Si è verificato un errore: {e}")
        input("\nPremi Invio per continuare...")

    def view_follower_events(self):
        self._clear_screen()
        print("--- Cronologia Imprevisti Obiettivi Seguaci ---")

        try:
            # Recupera i seguaci visibili (tutti per DM, solo propri per giocatore)
            if self.current_user['role'] == 'DM':
                followers_response = self.supabase.from_('followers').select('id, name').execute()
            else:
                pg_response = self.supabase.from_('player_characters').select('id').eq('user_id', self.current_user['id']).execute()
                pg_ids = [pg['id'] for pg in pg_response.data]
                followers_response = self.supabase.from_('followers').select('id, name, pg_id').in_('pg_id', pg_ids).execute()

            followers = followers_response.data
            if not followers:
                print("⚠️ Nessun seguace trovato.")
                input("\nPremi Invio per continuare...")
                return

            # Mostra elenco
            print("\nSeguaci disponibili:")
            for i, f in enumerate(followers):
                print(f"{i+1}. {f['name']}")
            print("0. Torna al menu")
            choice = input("Seleziona un seguace: ")
            if choice == "0":
                return

            index = int(choice) - 1
            if not (0 <= index < len(followers)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return

            selected_follower = followers[index]
            follower_id = selected_follower['id']

            # Trova tutti gli obiettivi associati al seguace selezionato
            objectives_response = self.supabase.from_('follower_objectives').select('id').eq('follower_id', follower_id).execute()
            objective_ids = [obj['id'] for obj in objectives_response.data]

            if not objective_ids:
                print(f"⚠️ Nessun obiettivo trovato per il seguace '{selected_follower['name']}'.")
                input("\nPremi Invio per continuare...")
                return

            # Recupera eventi associati a quegli obiettivi
            events_response = self.supabase.from_('follower_objective_events') \
                .select('objective_id, extra_months, extra_cost, description, handled, event_date') \
                .in_('objective_id', objective_ids) \
                .order('event_date', desc=True) \
                .execute()
            events = events_response.data

            print(f"\n--- Imprevisti per '{selected_follower['name']}' ---")
            if not events:
                print("Nessun imprevisto registrato.")
            else:
                for event in events:
                    stato = "Gestito" if event['handled'] else "❗ NON gestito"
                    # Converti la data nel formato Mystara
                    if 'event_date' in event and event['event_date']:
                        try:
                            event_date = datetime.strptime(event['event_date'][:10], '%Y-%m-%d').date()
                            mystara_date = self._convert_date_to_ded_format(event_date)
                        except:
                            mystara_date = 'Data sconosciuta'
                    else:
                        mystara_date = 'Data sconosciuta'
                    
                    print(f"- [{mystara_date}] {event['description']} → +{event['extra_months']} mesi, +{event['extra_cost']:.2f}g ({stato})")

        except Exception as e:
            print(f"❌ Errore durante la visualizzazione degli imprevisti: {e}")
        input("\nPremi Invio per continuare...")

    def list_follower_objectives(self, show_all=False):
        self._clear_screen()
        print("--- Lista Obiettivi Seguaci Raggruppati per PG ---\n")

        try:
            query = self.supabase.from_('follower_objectives') \
                .select('*, followers(name, pg_id, player_characters(name, users(username))), banks(name)') \
                .order('follower_id', desc=False)

            # Se l'utente è un GIOCATORE, filtra i PG
            if self.current_user and self.current_user['role'] == 'GIOCATORE' and not show_all:
                pg_response = self.supabase.from_('player_characters') \
                    .select('id') \
                    .eq('user_id', self.current_user['id']) \
                    .execute()
                user_pg_ids = [pg['id'] for pg in pg_response.data]

                if not user_pg_ids:
                    print("⚠️ Nessun personaggio trovato associato al tuo account.")
                    input("\nPremi Invio per continuare...")
                    return []

                followers_response = self.supabase.from_('followers') \
                    .select('id') \
                    .in_('pg_id', user_pg_ids) \
                    .execute()
                user_follower_ids = [f['id'] for f in followers_response.data]

                if not user_follower_ids:
                    print("⚠️ Nessun seguace trovato per i tuoi personaggi.")
                    input("\nPremi Invio per continuare...")
                    return []

                query = query.in_('follower_id', user_follower_ids)

            response = query.execute()
            objectives = response.data

            if not objectives:
                print("Nessun obiettivo trovato.")
                input("\nPremi Invio per continuare...")
                return []

            # Raggruppa per PG
            grouped = {}
            for obj in objectives:
                pg_name = obj.get('followers', {}).get('player_characters', {}).get('name', 'N/A')
                if pg_name not in grouped:
                    grouped[pg_name] = []
                grouped[pg_name].append(obj)

            for pg_name, obj_list in grouped.items():
                print(f"Nome PG        : {pg_name}\n")
                labels = [
                    "Seguace", "Obiettivo", "Mesi", "Costo",
                    "Banca", "Stato", "Inizio", "Progresso", "Note"
                ]
                rows = [[] for _ in labels]

                for obj in obj_list:
                    follower_name = obj.get('followers', {}).get('name', 'N/A')
                    status = self.OBJECTIVE_STATUS_REV.get(obj.get('status'), 'Sconosciuto')
                    estimated_months = obj.get('estimated_months', 0)
                    total_cost = obj.get('total_cost') or 0.0
                    bank_name = obj.get('banks', {}).get('name', 'Nessuna')
                    start_date = obj.get('start_date') or 'N/A'
                    progress = obj.get('progress_percentage') or 0.0
                    notes = obj.get('notes', '')

                    rows[0].append(follower_name)
                    rows[1].append(obj.get('name', ''))
                    rows[2].append(str(estimated_months))
                    rows[3].append(f"{total_cost:.2f} MO")
                    rows[4].append(bank_name)
                    rows[5].append(status)
                    rows[6].append(start_date)
                    rows[7].append(f"{progress:.1f}%")
                    rows[8].append(notes)

                for label, values in zip(labels, rows):
                    print(f"{label:<12}: " + "  ".join(f"{v:<20}" for v in values))
                print("-" * 100)

            input("\nPremi Invio per continuare...")
            return objectives

        except Exception as e:
            print(f"❌ Errore nel recupero degli obiettivi: {e}")
            input("\nPremi Invio per continuare...")
            return []

    def update_follower_objective(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può modificare obiettivi dei seguaci.")
            input("\nPremi Invio per continuare...")
            return

        objectives = self.list_follower_objectives(show_all=True)
        if not objectives:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero dell'obiettivo da modificare:")
        for i, obj in enumerate(objectives):
            follower_name = obj['followers']['name'] if obj['followers'] else 'N/A'
            print(f"{i+1}. {obj['name']} (Seguace: {follower_name})")

        try:
            obj_index = int(input("Numero: ")) - 1
            if not (0 <= obj_index < len(objectives)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_objective = objectives[obj_index]
            objective_id_to_update = selected_objective['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        if not selected_objective:
            print("Obiettivo non trovato.")
            input("\nPremi Invio per continuare...")
            return
        
        print(f"\nModifica Obiettivo: {selected_objective['name']} per {selected_objective['followers']['name']}")
        
        new_name = input(f"Nuovo nome obiettivo (lascia vuoto per mantenere '{selected_objective['name']}'): ").strip()
        update_data = {}
        # Mesi stimati
        new_estimated_months_str = input("Nuovi mesi stimati (lascia vuoto per non modificare): ").strip()
        if new_estimated_months_str:
            try:
                new_estimated_months = int(new_estimated_months_str)
                update_data['estimated_months'] = new_estimated_months
            except ValueError:
                print("⚠️ Mesi stimati non validi. Ignorati.")

        # Costo totale
        new_total_cost_str = input("Nuovo costo totale (lascia vuoto per non modificare): ").strip()
        if new_total_cost_str:
            try:
                new_total_cost = float(new_total_cost_str)
                update_data['total_cost'] = new_total_cost
            except ValueError:
                print("⚠️ Costo totale non valido. Ignorato.")

        new_notes = input(f"Nuove note (lascia vuoto per mantenere '{selected_objective['notes']}'): ").strip()
        
        print("\nStati disponibili:")
        for key, value in self.OBJECTIVE_STATUS.items():
            print(f"{value}. {key}")
        new_status_str = input(f"Nuovo stato ({self.OBJECTIVE_STATUS_REV[selected_objective['status']]}, lascia vuoto per non cambiare): ").strip()

        new_progress_percentage_str = input(f"Nuova percentuale di progresso (lascia vuoto per mantenere '{selected_objective['progress_percentage']:.1f}%'): ").strip()

        update_data = {}
        if new_name:
            update_data['name'] = new_name
        if new_estimated_months_str:
            try:
                val = int(new_estimated_months_str)
                if new_estimated_months <= 0:
                    print(f"  ⚠️ ERRORE: durata stimata invalida dopo imprevisto. Salto obiettivo.")
                if val > 0: update_data['estimated_months'] = val
                else: print("Mesi stimati devono essere > 0, ignorato.")
            except ValueError: print("Mesi stimati non validi, ignorato.")
        if new_total_cost_str:
            try:
                val = float(new_total_cost_str)
                if val >= 0: update_data['total_cost'] = val
                else: print("Costo totale non può essere negativo, ignorato.")
            except ValueError: print("Costo totale non valido, ignorato.")
        if new_notes:
            update_data['notes'] = new_notes
        if new_status_str:
            try:
                val = int(new_status_str)
                if val in self.OBJECTIVE_STATUS.values():
                    update_data['status'] = val
                    if val == self.OBJECTIVE_STATUS['IN_CORSO'] and not selected_objective['start_date']:
                        update_data['start_date'] = self.game_date.strftime('%Y-%m-%d')
                    elif val != self.OBJECTIVE_STATUS['IN_CORSO'] and selected_objective['start_date']:
                        update_data['start_date'] = None # Clear start date if not in progress
                else: print("Stato non valido, ignorato.")
            except ValueError: print("Stato non valido, ignorato.")
        if new_progress_percentage_str:
            try:
                val = float(new_progress_percentage_str)
                if 0 <= val <= 100: update_data['progress_percentage'] = val
                else: print("Percentuale progresso deve essere tra 0 e 100, ignorato.")
            except ValueError: print("Percentuale progresso non valida, ignorato.")

        # Reassign follower (only DM)
        new_follower_id = selected_objective['follower_id']
        followers = self.list_followers(show_all=True)
        if followers:
            print("\nSeleziona il nuovo Seguace a cui associare l'obiettivo (0 per non cambiare):")
            for i, f in enumerate(followers):
                pg_name = f['player_characters']['name'] if f['player_characters'] else 'N/A'
                print(f"{i+1}. {f['name']} (PG: {pg_name})")
            
            while True:
                try:
                    follower_choice_str = input("Numero del nuovo Seguace: ").strip()
                    if not follower_choice_str:
                        break
                    follower_choice = int(follower_choice_str) - 1
                    if follower_choice == -1: # Choice 0
                        break
                    elif 0 <= follower_choice < len(followers):
                        new_follower_id = followers[follower_choice]['id']
                        break
                    else:
                        print("Scelta non valida. Riprova.")
                except ValueError:
                    print("Input non valido. Inserisci un numero.")
            if new_follower_id != selected_objective['follower_id']:
                update_data['follower_id'] = new_follower_id

        # Update destination bank for the (potentially new) follower's PG
        # First, get the PG of the new follower
        if new_follower_id != selected_objective['follower_id'] or 'bank_id' not in update_data:
            # Need to fetch the PG for the (new) follower to get its banks
            try:
                follower_info_response = self.supabase.from_('followers').select('pg_id').eq('id', new_follower_id).execute()
                new_follower_pg_id = follower_info_response.data[0]['pg_id'] if follower_info_response.data else None
            except Exception as e:
                new_follower_pg_id = None
                print(f"Errore nel recupero del PG del nuovo seguace: {e}")

            if new_follower_pg_id:
                banks_for_pg_response = self.supabase.from_('banks').select('*').eq('pg_id', new_follower_pg_id).execute()
                banks_for_pg = banks_for_pg_response.data

                if banks_for_pg:
                    print(f"\nSeleziona la nuova banca di destinazione costo per l'obiettivo (0 per non cambiare):")
                    for i, bank in enumerate(banks_for_pg):
                        print(f"{i+1}. {bank['name']} (Saldo: {bank.get('current_balance', 0.0):.2f})")
                    
                    new_bank_id = selected_objective['bank_id']
                    while True:
                        try:
                            bank_choice_str = input("Numero della nuova banca: ").strip()
                            if not bank_choice_str:
                                break
                            bank_choice = int(bank_choice_str) - 1
                            if bank_choice == -1: # Choice 0
                                break
                            elif 0 <= bank_choice < len(banks_for_pg):
                                new_bank_id = banks_for_pg[bank_choice]['id']
                                break
                            else:
                                print("Scelta non valida. Riprova.")
                        except ValueError:
                            print("Input non valido. Inserisci un numero.")
                    if new_bank_id != selected_objective['bank_id']:
                        update_data['bank_id'] = new_bank_id
                else:
                    print(f"Attenzione: Il PG del seguace non ha conti bancari. La banca di destinazione non può essere modificata.")
                    if selected_objective['bank_id'] is not None and new_follower_id != selected_objective['follower_id']:
                        print("La banca di destinazione precedente non è valida per il nuovo seguace. Impostazione a NULL.")
                        update_data['bank_id'] = None
            else:
                print("Attenzione: Impossibile trovare il PG per il seguace selezionato. Banca di destinazione non modificabile.")


        if update_data:
            try:
                response = self.supabase_admin.from_('follower_objectives').update(update_data).eq('id', objective_id_to_update).execute()
                if response.data:
                    print(f"Obiettivo '{selected_objective['name']}' modificato con successo.")
                else:
                    print(f"Errore nella modifica dell'obiettivo: {response.json()}")
            except Exception as e:
                print(f"Si è verificato un errore: {e}")
        else:
            print("Nessuna modifica da applicare.")
        input("\nPremi Invio per continuare...")

    def remove_follower_objective(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può rimuovere obiettivi dei seguaci.")
            input("\nPremi Invio per continuare...")
            return

        objectives = self.list_follower_objectives(show_all=True)
        if not objectives:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero dell'obiettivo da rimuovere:")
        for i, obj in enumerate(objectives):
            follower_name = obj['followers']['name'] if obj['followers'] else 'N/A'
            print(f"{i+1}. {obj['name']} (Seguace: {follower_name})")

        try:
            obj_index = int(input("Numero: ")) - 1
            if not (0 <= obj_index < len(objectives)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_objective = objectives[obj_index]
            objective_id_to_remove = selected_objective['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        confirm = input(f"Sei sicuro di voler rimuovere l'obiettivo '{selected_objective['name']}' ? L'eliminazione è definitiva. (s/N): ").strip().lower()
        if confirm == 's':
            try:
                response = self.supabase_admin.from_('follower_objectives').delete().eq('id', objective_id_to_remove).execute()
                if response.data:
                    print(f"Obiettivo '{selected_objective['name']}' rimosso con successo.")
                else:
                    print(f"Errore nella rimozione dell'obiettivo: {response.json()}")
            except Exception as e:
                print(f"Si è verificato un errore: {e}")
        else:
            print("Rimozione annullata.")
        input("\nPremi Invio per continuare...")

    def start_follower_objective(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può iniziare obiettivi dei seguaci.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Inizia Obiettivo Seguace ---")
        
        # List only NON_INIZIATO objectives
        try:
            objectives_response = self.supabase.from_('follower_objectives').select('*, followers(name, player_characters(name)), banks(name)').eq('status', self.OBJECTIVE_STATUS['NON_INIZIATO']).execute()
            non_started_objectives = objectives_response.data

            if not non_started_objectives:
                print("Nessun obiettivo con stato 'NON_INIZIATO' trovato.")
                input("\nPremi Invio per continuare...")
                return

            print("Obiettivi 'NON_INIZIATO' disponibili:")
            print("{:<5} {:<20} {:<25} {:<10} {:<10} {:<15} {:<15}".format(
                "ID", "Seguace", "Nome Obiettivo", "Mesi St.", "Costo", "Banca Dest.", "Note"
            ))
            print("-" * 100)
            for i, obj in enumerate(non_started_objectives):
                follower_name = obj['followers']['name'] if obj['followers'] else 'N/A'
                bank_name = obj['banks']['name'] if obj['banks'] else 'N/A'
                print(f"{i+1:<5} {follower_name:<20} {obj['name']:<25} {obj['estimated_months']:<10} {obj['total_cost']:.2f} {bank_name:<15} {obj['notes']:<15}")
            
            selected_choice = None
            while True:
                try:
                    choice_str = input("\nSeleziona il numero dell'obiettivo da iniziare (0 per annullare): ").strip()
                    if choice_str == '0':
                        print("Operazione annullata.")
                        input("\nPremi Invio per continuare...")
                        return
                    choice = int(choice_str) - 1
                    if 0 <= choice < len(non_started_objectives):
                        selected_objective = non_started_objectives[choice]
                        break
                    else:
                        print("Scelta non valida. Riprova.")
                except ValueError:
                    print("Input non valido. Inserisci un numero.")

            # Update objective status, start_date, and initial progress
            update_data = {
                "status": self.OBJECTIVE_STATUS['IN_CORSO'],
                "start_date": self.game_date.strftime('%Y-%m-%d'),
                "progress_percentage": 0.0
            }

            response = self.supabase_admin.from_('follower_objectives').update(update_data).eq('id', selected_objective['id']).execute()
            if response.data:
                print(f"Obiettivo '{selected_objective['name']}' iniziato con successo. Stato: IN_CORSO.")
            else:
                print(f"Errore nell'avvio dell'obiettivo: {response.json()}")

        except Exception as e:
            print(f"Si è verificato un errore: {e}")
        input("\nPremi Invio per continuare...")

    def _apply_daily_events(self):
        print("Applicazione eventi giornalieri...")

        try:
            # Attività economiche giornaliere
            economic_activities_response = self.supabase.from_('economic_activities') \
                .select('*, banks(name, current_balance)').execute()
            activities = economic_activities_response.data

            for activity in activities:
                if activity.get('frequency', '').lower() != 'giornaliera':
                    continue

                income = activity.get('income', 0.0)
                bank = activity.get('banks')
                bank_id = activity.get('destination_bank_id')

                if not bank_id or not bank:
                    print(f"  Attività '{activity.get('description', 'Sconosciuta')}' senza banca associata. Guadagno non applicato.")
                    continue

                current_balance = bank.get('current_balance', 0.0)
                new_balance = current_balance + income

                self.supabase_admin.from_('banks').update({'current_balance': new_balance}).eq('id', bank_id).execute()
                print(f"  Guadagno giornaliero di {income:.2f} applicato alla banca '{bank.get('name', 'Sconosciuta')}' per l'attività '{activity.get('description', 'Sconosciuta')}'")

            # Spese fisse giornaliere
            fixed_expenses_response = self.supabase.from_('fixed_expenses') \
                .select('*, banks(name, current_balance)').execute()
            fixed_expenses = fixed_expenses_response.data

            for expense in fixed_expenses:
                if expense.get('frequency', '').lower() != 'giornaliera':
                    continue

                amount = expense.get('amount', 0.0)
                bank = expense.get('banks')
                bank_id = expense.get('source_bank_id')

                if not bank_id or not bank:
                    print(f"  Spesa '{expense.get('description', 'Sconosciuta')}' senza banca associata. Non applicata.")
                    continue

                current_balance = bank.get('current_balance', 0.0)

                if current_balance >= amount:
                    new_balance = current_balance - amount
                    self.supabase_admin.from_('banks').update({'current_balance': new_balance}).eq('id', bank_id).execute()
                    print(f"  Spesa giornaliera '{expense.get('description', 'Sconosciuta')}' di {amount:.2f} prelevata da '{bank.get('name', 'Sconosciuta')}'")
                else:
                    print(f"  ATTENZIONE: saldo insufficiente ({current_balance:.2f}) per la spesa '{expense.get('description', 'Sconosciuta')}'")

            # Obiettivi dei seguaci – applica 1/30 di mese
            self._apply_objective_progress(frazione_mensile=1/30.0, etichetta='giornaliero')
            self.apply_unhandled_objective_events()

        except Exception as e:
            print(f"Errore nell'applicazione degli eventi giornalieri: {e}")

    def _apply_weekly_events(self):
        print("Applicazione eventi settimanali...")

        try:
            # Attività economiche settimanali
            economic_activities_response = self.supabase.from_('economic_activities').select('*, banks(name, current_balance)').execute()
            fixed_expenses_response = self.supabase.from_('fixed_expenses').select('*, banks(name, current_balance)').execute()
            
            activities = economic_activities_response.data
            expenses = fixed_expenses_response.data

            for activity in activities:
                if activity.get('frequency', '').lower() != 'settimanale':
                    continue

                bank_id = activity.get('destination_bank_id')
                income = activity.get('income', 0.0)
                bank = activity.get('banks')

                if not bank_id or not bank:
                    print(f"  Attività '{activity.get('description', 'Sconosciuta')}' senza banca associata. Guadagno non applicato.")
                    continue

                current_balance = bank.get('current_balance', 0.0)
                new_balance = current_balance + income

                self.supabase_admin.from_('banks').update({'current_balance': new_balance}).eq('id', bank_id).execute()
                print(f"  Guadagno settimanale di {income:.2f} applicato alla banca '{bank.get('name', 'Sconosciuta')}' per l'attività '{activity.get('description', 'Sconosciuta')}'")

            for expense in expenses:
                if expense.get('frequency', '').lower() != 'settimanale':
                    continue

                bank_id = expense.get('source_bank_id')
                amount = expense.get('amount', 0.0)
                bank = expense.get('banks')

                if not bank_id or not bank:
                    print(f"  Spesa '{expense.get('description', 'Sconosciuta')}' senza banca associata. Spesa non applicata.")
                    continue

                current_balance = bank.get('current_balance', 0.0)

                if current_balance >= amount:
                    new_balance = current_balance - amount
                    self.supabase_admin.from_('banks').update({'current_balance': new_balance}).eq('id', bank_id).execute()
                    print(f"  Spesa settimanale di {amount:.2f} applicata alla banca '{bank.get('name', 'Sconosciuta')}' per '{expense.get('description', 'Sconosciuta')}'")
                else:
                    print(f"  ATTENZIONE: saldo insufficiente ({current_balance:.2f}) per la spesa '{expense.get('description', 'Sconosciuta')}'")

            # Obiettivi dei seguaci – applica 1/4 di mese
            self._apply_objective_progress(frazione_mensile=1/4.0, etichetta='settimanale')
            self.apply_unhandled_objective_events()

            print("Eventi settimanali completati.")

        except Exception as e:
            print(f"Errore nell'applicazione degli eventi settimanali: {e}")

    def _apply_monthly_events(self):
        print("Applicazione eventi mensili...")

        try:
            # Spese fisse mensili
            fixed_expenses_response = self.supabase.from_('fixed_expenses').select('*, banks(name, current_balance)').execute()
            fixed_expenses = fixed_expenses_response.data

            for expense in fixed_expenses:
                if expense.get('frequency', '').lower() != 'mensile':
                    continue

                bank = expense.get('banks')
                bank_id = expense.get('source_bank_id')
                amount = expense.get('amount', 0.0)

                if bank and bank_id:
                    current_balance = bank.get('current_balance', 0.0)
                    if current_balance >= amount:
                        new_balance = current_balance - amount
                        self.supabase_admin.from_('banks').update({'current_balance': new_balance}).eq('id', bank_id).execute()
                        print(f"  Spesa mensile '{expense.get('description', 'Sconosciuta')}' di {amount:.2f} prelevata da '{bank.get('name', 'Sconosciuta')}'")
                    else:
                        print(f"  ⚠️ Fondi insufficienti per spesa '{expense.get('description', 'Sconosciuta')}'")
                else:
                    print(f"  ⚠️ Spesa '{expense.get('description', 'Sconosciuta')}' senza banca associata")

            # Guadagni mensili attività economiche
            activities_response = self.supabase.from_('economic_activities').select('*, banks(name, current_balance)').execute()
            activities = activities_response.data

            for activity in activities:
                if activity.get('frequency', '').lower() != 'mensile':
                    continue

                bank_id = activity.get('destination_bank_id')
                income = activity.get('income', 0.0)
                if not bank_id:
                    print(f"  Attività '{activity.get('description', 'Sconosciuta')}' senza banca. Guadagno non applicato.")
                    continue

                bank_res = self.supabase.from_('banks').select('current_balance').eq('id', bank_id).single().execute()
                current_balance = bank_res.data['current_balance'] if bank_res.data else 0.0
                new_balance = current_balance + income
                self.supabase_admin.from_('banks').update({'current_balance': new_balance}).eq('id', bank_id).execute()
                print(f"  Guadagno mensile di {income:.2f} applicato a '{activity.get('banks', {}).get('name', 'Sconosciuta')}'")

            # Obiettivi dei seguaci
            objectives_response = self.supabase.from_('follower_objectives') \
                .select('*, banks(name, current_balance)') \
                .eq('status', self.OBJECTIVE_STATUS['IN_CORSO']).execute()
            objectives = objectives_response.data

            for objective in objectives:
                objective_id = objective.get('id')
                name = objective.get('name', 'Sconosciuto')
                bank_id = objective.get('bank_id')
                estimated_months = objective.get('estimated_months', 0)
                total_cost = objective.get('total_cost', 0.0)
                progress_percentage = objective.get('progress_percentage', 0.0)

                base_months = objective.get('base_estimated_months', estimated_months)
                base_cost = objective.get('base_total_cost', total_cost)

                if not bank_id:
                    print(f"  Obiettivo '{name}' senza banca. Costo non applicato.")
                    continue

                if estimated_months <= 0 or base_months <= 0:
                    print(f"  Obiettivo '{name}' ha durata non valida.")
                    continue

                cost_per_month = total_cost / estimated_months
                progress_per_month = 100.0 / base_months

                bank_res = self.supabase.from_('banks').select('current_balance').eq('id', bank_id).single().execute()
                current_balance = bank_res.data['current_balance'] if bank_res.data else 0.0

                if current_balance >= cost_per_month:
                    new_balance = current_balance - cost_per_month
                    self.supabase_admin.from_('banks').update({'current_balance': new_balance}).eq('id', bank_id).execute()

                    new_progress = min(progress_percentage + progress_per_month, 100.0)
                    update_data = {'progress_percentage': new_progress}

                    if new_progress >= 100.0:
                        update_data['status'] = self.OBJECTIVE_STATUS['COMPLETATO']
                        print(f"  ✅ Obiettivo '{name}' COMPLETATO!")

                    self.supabase_admin.from_('follower_objectives').update(update_data).eq('id', objective_id).execute()
                    print(f"  📈 Obiettivo '{name}' avanzato al {new_progress:.1f}%")
                else:
                    print(f"  ⚠️ Saldo insufficiente per '{name}' ({current_balance:.2f} < {cost_per_month:.2f})")

        except Exception as e:
            print(f"Errore nell'applicazione degli eventi mensili per obiettivi: {e}")

    def _apply_objective_progress(self, frazione_mensile, etichetta='periodico'):
        try:
            print(f"📊 Avanzamento obiettivi ({etichetta})...")

            objectives_response = self.supabase.from_('follower_objectives') \
                .select('*, banks(name, current_balance)') \
                .eq('status', self.OBJECTIVE_STATUS['IN_CORSO']).execute()
            objectives = objectives_response.data

            for objective in objectives:
                objective_id = objective.get('id')
                name = objective.get('name', 'Sconosciuto')
                bank_id = objective.get('bank_id')
                estimated_months = objective.get('estimated_months', 0)
                total_cost = objective.get('total_cost', 0.0)
                progress_percentage = objective.get('progress_percentage', 0.0)
                base_months = objective.get('base_estimated_months', estimated_months)
                base_cost = objective.get('base_total_cost', total_cost)

                if not bank_id:
                    print(f"  Obiettivo '{name}' senza banca. Costo non applicato.")
                    continue
                if estimated_months <= 0 or base_months <= 0:
                    print(f"  Obiettivo '{name}' ha durata non valida.")
                    continue

                cost_per_month = total_cost / estimated_months
                progress_per_month = 100.0 / base_months

                cost = cost_per_month * frazione_mensile
                progress = progress_per_month * frazione_mensile

                bank_res = self.supabase.from_('banks').select('current_balance').eq('id', bank_id).single().execute()
                current_balance = bank_res.data['current_balance'] if bank_res.data else 0.0

                if current_balance >= cost:
                    new_balance = current_balance - cost
                    self.supabase_admin.from_('banks').update({'current_balance': new_balance}).eq('id', bank_id).execute()

                    new_progress = min(progress_percentage + progress, 100.0)
                    update_data = {'progress_percentage': new_progress}

                    if new_progress >= 100.0:
                        update_data['status'] = self.OBJECTIVE_STATUS['COMPLETATO']
                        print(f"  ✅ Obiettivo '{name}' COMPLETATO!")

                    self.supabase_admin.from_('follower_objectives').update(update_data).eq('id', objective_id).execute()
                    print(f"  📈 Obiettivo '{name}' avanzato al {new_progress:.1f}% ({etichetta})")
                else:
                    print(f"  ⚠️ Saldo insufficiente per '{name}' ({current_balance:.2f} < {cost:.2f})")

        except Exception as e:
            print(f"⚠️ Errore nell'avanzamento obiettivi ({etichetta}): {e}")

    def apply_unhandled_objective_events(self):
        print("🔄 Applicazione automatica delle scelte degli imprevisti...")

        try:
            events_response = self.supabase.from_('follower_objective_events') \
                .select('id, objective_id, player_choice, response_options, handled') \
                .eq('handled', False).execute()

            unhandled_events = events_response.data
            if not unhandled_events:
                print("✅ Nessun imprevisto da gestire.")
                return

            for event in unhandled_events:
                if not event.get('player_choice') or not event.get('response_options'):
                    print(f"⚠️ Evento {event['id']} senza scelta del giocatore o opzioni.")
                    continue

                try:
                    import json
                    selected_raw = event.get('player_choice')
                    try:
                        selected = json.loads(selected_raw) if isinstance(selected_raw, str) else selected_raw
                    except Exception:
                        print(f"⚠️ Impossibile decodificare player_choice per evento {event['id']}")
                        continue

                    if not selected or 'option' not in selected:
                        print(f"⚠️ player_choice malformato o incompleto per evento {event['id']}")
                        continue

                    objective_id = event['objective_id']

                    # Recupera nome e dati attuali dell'obiettivo
                    obj_resp = self.supabase.from_('follower_objectives') \
                        .select('name, estimated_months, total_cost') \
                        .eq('id', objective_id).single().execute()
                    objective = obj_resp.data
                    if not objective:
                        print(f"⚠️ Obiettivo {objective_id} non trovato.")
                        continue
                    objective_name = objective.get('name', 'Sconosciuto')

                    if selected.get("fail"):
                        self.supabase.from_('follower_objectives') \
                            .update({"status": self.OBJECTIVE_STATUS["FALLITO"]}) \
                            .eq('id', objective_id).execute()
                        print(f"❌ Obiettivo '{objective_name}' segnato come fallito.")
                    else:
                        add_months = int(selected.get("extra_months", 0))
                        add_cost = float(selected.get("extra_cost", 0.0))

                        updated_fields = {
                            "estimated_months": objective['estimated_months'] + add_months,
                            "total_cost": objective['total_cost'] + add_cost
                        }

                        self.supabase.from_('follower_objectives') \
                            .update(updated_fields).eq('id', objective_id).execute()

                        print(f"  ⚠️ Imprevisto su obiettivo '{objective_name}': +{add_months} mesi, +{add_cost:.2f} PO")

                        # Salva anche i valori extra nella tabella eventi
                        self.supabase.from_('follower_objective_events') \
                            .update({
                                "handled": True,
                                "extra_cost": add_cost,
                                "extra_months": add_months
                            }).eq('id', event['id']).execute()

                except Exception as inner_err:
                    print(f"⚠️ Errore durante l'applicazione dell'evento {event['id']}: {inner_err}")

            print("✅ Tutti gli imprevisti gestiti.")

        except Exception as e:
            print(f"❌ Errore durante l'applicazione delle scelte: {e}")

    def advance_days(self, days=1):
        print(f"\n⏳ Avanzamento di {days} giorno/i in corso...")

        try:
            for _ in range(days):
                self.game_date += timedelta(days=1)
                self._update_game_state_date(self.game_date)
                print(f"✅ Data aggiornata: {self._convert_date_to_ded_format(self.game_date)}")

                # Applica eventi giornalieri
                self._apply_daily_events()

                # Applica eventuali imprevisti gestiti
                self.apply_unhandled_objective_events()

        except Exception as e:
            print(f"❌ Errore durante l'avanzamento del giorno: {e}")

        input("\nPremi Invio per continuare...")

    def advance_weeks(self, weeks=1):
        print(f"\n⏳ Avanzamento di {weeks} settimana/e in corso...")

        try:
            for w in range(weeks):
                # Avanza di 7 giorni una settimana per volta
                for _ in range(7):
                    self.game_date += timedelta(days=1)
                    self._apply_daily_events()

                self._apply_weekly_events()
                self.apply_unhandled_objective_events()

            # Salva e stampa la nuova data
            self._update_game_state_date(self.game_date)
            print(f"✅ Data aggiornata: {self._convert_date_to_ded_format(self.game_date)}")

        except Exception as e:
            print(f"❌ Errore durante l'avanzamento della settimana: {e}")

        input("\nPremi Invio per continuare...")

    def advance_months(self, months=1):
        print(f"\n⏳ Avanzamento di {months} mese/i in corso...")

        try:
            from datetime import date

            if isinstance(self.game_date, (datetime, date)):
                current_date = datetime.combine(self.game_date, datetime.min.time())
            else:
                current_date = datetime.strptime(str(self.game_date), "%Y-%m-%d")

            # Aggiungi i mesi
            new_date = current_date + relativedelta(months=months)
            self.game_date = new_date  # lascia che rimanga un oggetto datetime

            # Aggiorna in Supabase
            self._update_game_state_date(self.game_date)

            print(f"✅ Data aggiornata: {self._convert_date_to_ded_format(self.game_date)}")

            # Applica eventi mensili
            self._apply_monthly_events()

            # Applica scelte dei giocatori (imprevisti)
            self.apply_unhandled_objective_events()

            print("✅ Eventi mensili e imprevisti applicati.")

        except Exception as e:
            print(f"❌ Errore durante l'avanzamento del mese: {e}")
        input("\nPremi Invio per continuare...")

    def show_current_date(self):
        """Mostra la data di gioco corrente nel formato Mystara."""
        self._clear_screen()
        print("--- Data di Gioco Attuale ---")
        print(f"📅 {self._convert_date_to_ded_format(self.game_date)}")
        input("\nPremi Invio per continuare...")

    def set_game_date_manually(self):
        try:
            print("\nInserisci la nuova data di gioco.")
            print("Formato richiesto: YYYY-MM-DD (es. 2011-05-12)")
            new_date_str = input("Nuova data: ").strip()

            # Convalida formato
            new_date = datetime.strptime(new_date_str, "%Y-%m-%d")
            self.game_date = new_date
            self._update_game_state_date(new_date_str)

            print(f"✅ Data di gioco aggiornata a {self._convert_date_to_ded_format(new_date)}.")
        except ValueError:
            print("❌ Formato data non valido. Usa il formato YYYY-MM-DD.")
        except Exception as e:
            print(f"❌ Errore durante l'aggiornamento della data: {e}")
        input("\nPremi Invio per continuare...")

    def show_pending_events(self):
        self._clear_screen()
        print("--- Imprevisti in Attesa di Scelta ---\n")

        try:
            response = self.supabase.from_('follower_objective_events') \
                .select('id, objective_id, description, extra_months, extra_cost, response_options, player_choice, event_date, follower_objectives(name)') \
                .eq('handled', False) \
                .execute()
            events = response.data

            if not events:
                print("✅ Nessun imprevisto in attesa di scelta.")
            else:
                for i, evt in enumerate(events, 1):
                    objective_name = evt.get('follower_objectives', {}).get('name', 'Obiettivo sconosciuto')

                    print(f"{i}. Imprevisto: {evt['description']}")
                    print(f"   Obiettivo: {objective_name}")
                    print(f"   Mesi aggiuntivi: {evt['extra_months']}  |  Costo aggiuntivo: {evt['extra_cost']:.2f} MO")
                    print(f"   Inviato il: {evt.get('event_date', 'N/A')}")

                    # Mostra solo il testo dell'opzione selezionata, se disponibile
                    player_choice = evt.get('player_choice')
                    if player_choice:
                        try:
                            choice_dict = json.loads(player_choice)
                            option_text = choice_dict.get("option", "Scelta sconosciuta")
                            print(f"   ✔️ Scelta del giocatore: {option_text}")
                        except Exception:
                            print(f"   ✔️ Scelta del giocatore (non parsificabile): {player_choice}")
                    else:
                        print("   ❌ Nessuna scelta ricevuta dal giocatore.")
                    print("-" * 60)

        except Exception as e:
            print(f"❌ Errore durante la lettura degli imprevisti: {e}")

        input("\nPremi Invio per continuare...")

    def _update_game_state_date(self, new_date):
        try:
            # Garantisce che sia una stringa formattata per Supabase
            formatted_date = new_date.strftime('%Y-%m-%d') if isinstance(new_date, datetime) else str(new_date)

            self.supabase_admin.from_('game_state') \
                .update({'current_date': formatted_date}) \
                .eq('id', 1).execute()

            print("📅 Data aggiornata nel database.")
        except Exception as e:
            print(f"⚠️ Errore nell'aggiornamento della data di gioco: {e}")

    def advance_time(self, days=0, weeks=0, months=0):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può avanzare il tempo.")
            input("\nPremi Invio per continuare...")
            return

        original_date = self.game_date
        
        # We need to apply events sequentially for each day/week/month advanced
        # This makes the logic more robust than checking day/weekday/month number
        
        total_days_to_advance = days + (weeks * 7) + (months * 30) # Approximate months for advancement logic

        for i in range(total_days_to_advance):
            self.game_date += timedelta(days=1)
            self._apply_daily_events()

            # Check for weekly events (e.g., if it's the start of a new week in game)
            # This logic can be tricky. A simpler way is to trigger them after every 7 days.
            if (i + 1) % 7 == 0: # After every 7 days
                self._apply_weekly_events()
            
            # Check for monthly events (e.g., if it's the start of a new month in game)
            # This is more precise by checking if the month has changed from the previous day
            if self.game_date.day == 1 and (self.game_date.month != original_date.month or self.game_date.year != original_date.year):
                self._apply_monthly_events()
            elif self.game_date.day == 1 and i == 0 and months > 0: # Edge case: if we start precisely on a new month
                 self._apply_monthly_events()


        self._save_game_date()
        print(f"\nData di gioco avanzata da {self._convert_date_to_ded_format(original_date)} a {self._convert_date_to_ded_format(self.game_date)}.")
        input("\nPremi Invio per continuare...")

    def manage_time_menu(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Accesso negato. Solo i DM possono gestire il tempo.")
            input("\nPremi Invio per continuare...")
            return

        while True:
            self._clear_screen()
            print("--- Gestione Tempo ed Imprevisti ---")
            print("1. Avanza di 1 Giorno")
            print("2. Avanza di 1 Settimana")
            print("3. Avanza di 1 Mese")
            print("4. Visualizza Data Attuale")
            print("5. Inserisci Imprevisto Obiettivo")
            print("6. Registra Scelta del Giocatore")
            print("7. Imposta Data Manualmente")
            print("8. Mostra Imprevisti in Sospeso")
            print("0. Torna al Menu Principale")

            choice = input("Scegli un'opzione: ")

            if choice == '1':
                self.advance_days(1)
            elif choice == '2':
                self.advance_weeks(1)
            elif choice == '3':
                self.advance_months(1)
            elif choice == '4':
                self.show_current_date()
            elif choice == '5':
                self.add_objective_event()
            elif choice == '6':
                self.register_objective_choice()
            elif choice == '7':
                self.set_game_date_manually()
            elif choice == '8':
                self.show_pending_events()  # ← chiamata
            elif choice == '0':
                return
            else:
                print("Opzione non valida.")
                input("\nPremi Invio per continuare...")

    def export_pg_funds_to_excel(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può esportare i fondi dei PG.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Esporta Fondi PG in Excel ---")
        try:
            # Fetch all necessary data: PGs, their banks, economic activities, fixed expenses, followers, objectives
            pgs_response = self.supabase.from_('player_characters').select('id, name, users(username)').execute()
            banks_response = self.supabase.from_('banks').select('id, pg_id, name, current_balance').execute() # simplified select
            economic_activities_response = self.supabase.from_('economic_activities') \
                .select('id, pg_id, description, income, frequency, destination_bank_id') \
                .execute()
            fixed_expenses_response = self.supabase.from_('fixed_expenses').select('id, pg_id, description, amount, frequency, source_bank_id').execute()
            followers_response = self.supabase.from_('followers').select('id, pg_id, name, description').execute()
            objectives_response = self.supabase.from_('follower_objectives').select('*, followers(name), banks(name)').execute()


            pg_data = pgs_response.data
            bank_data = banks_response.data
            activity_data = economic_activities_response.data
            expense_data = fixed_expenses_response.data
            follower_data = followers_response.data
            objective_data = objectives_response.data

            if not pg_data:
                print("Nessun personaggio giocante trovato per l'esportazione.")
                input("\nPremi Invio per continuare...")
                return

            # Prepare data for DataFrame
            export_list = []
            for pg in pg_data:
                pg_id = pg['id']
                pg_name = pg['name']
                pg_user = pg['users']['username'] if pg['users'] else 'N/A'
                
                # Get banks for this PG
                pg_banks = [b for b in bank_data if b['pg_id'] == pg_id]
                
                # Get activities for this PG
                pg_activities = [a for a in activity_data if a['pg_id'] == pg_id]

                # Get expenses for this PG
                pg_expenses = [e for e in expense_data if e['pg_id'] == pg_id]

                # Get followers for this PG
                pg_followers = [f for f in follower_data if f['pg_id'] == pg_id]

                # Initialize a base entry for PG, even if no other details
                base_entry_added = False

                if not pg_banks and not pg_activities and not pg_expenses and not pg_followers:
                    export_list.append({
                        "Nome PG": pg_name,
                        "Associato a Utente": pg_user,
                        "Tipo Voce": "Riepilogo PG",
                        "Nome Voce": "",
                        "Descrizione": "PG senza dettagli",
                        "Importo": 0.0,
                        "Frequenza": "",
                        "Banca Associata": "",
                        "Saldo Banca": 0.0,
                        "Stato Obiettivo": "", # New column for objectives
                        "Progresso Obiettivo": "" # New column for objectives
                    })
                    base_entry_added = True

                # Add bank details
                for bank in pg_banks:
                    export_list.append({
                        "Nome PG": pg_name,
                        "Associato a Utente": pg_user,
                        "Tipo Voce": "Banca",
                        "Nome Voce": bank['name'],
                        "Descrizione": "Conto Bancario",
                        "Importo": bank['current_balance'],
                        "Frequenza": "N/A",
                        "Banca Associata": bank['name'],
                        "Saldo Banca": bank['current_balance'],
                        "Stato Obiettivo": "",
                        "Progresso Obiettivo": ""
                    })
                    base_entry_added = True
                
                # Add economic activities details
                for activity in pg_activities:
                    bank_name = next((b['name'] for b in bank_data if b['id'] == activity['destination_bank_id']), 'N/A')
                    bank_balance = next((b['current_balance'] for b in bank_data if b['id'] == activity['destination_bank_id']), 0.0)
                    export_list.append({
                        "Nome PG": pg_name,
                        "Associato a Utente": pg_user,
                        "Tipo Voce": "Attività Economica",
                        "Nome Voce": activity['description'],
                        "Descrizione": activity['description'],
                        "Importo": activity['income'],
                        "Frequenza": activity['frequency'],
                        "Banca Associata": bank_name,
                        "Saldo Banca": bank_balance,
                        "Stato Obiettivo": "",
                        "Progresso Obiettivo": ""
                    })
                    base_entry_added = True

                # Add fixed expenses details
                for expense in pg_expenses:
                    bank_name = next((b['name'] for b in bank_data if b['id'] == expense['source_bank_id']), 'N/A')
                    bank_balance = next((b['current_balance'] for b in bank_data if b['id'] == expense['source_bank_id']), 0.0)
                    export_list.append({
                        "Nome PG": pg_name,
                        "Associato a Utente": pg_user,
                        "Tipo Voce": "Spesa Fissa",
                        "Nome Voce": expense['description'],
                        "Descrizione": expense['description'],
                        "Importo": -expense['amount'], # Represent as negative for expenses
                        "Frequenza": expense['frequency'],
                        "Banca Associata": bank_name,
                        "Saldo Banca": bank_balance,
                        "Stato Obiettivo": "",
                        "Progresso Obiettivo": ""
                    })
                    base_entry_added = True

                # Add follower details and their objectives
                for follower in pg_followers:
                    follower_objectives = [obj for obj in objective_data if obj['follower_id'] == follower['id']]
                    if not follower_objectives:
                        export_list.append({
                            "Nome PG": pg_name,
                            "Associato a Utente": pg_user,
                            "Tipo Voce": "Seguace",
                            "Nome Voce": follower['name'],
                            "Descrizione": follower['description'],
                            "Importo": 0.0,
                            "Frequenza": "N/A",
                            "Banca Associata": "",
                            "Saldo Banca": 0.0,
                            "Stato Obiettivo": "Nessuno",
                            "Progresso Obiettivo": ""
                        })
                        base_entry_added = True
                    else:
                        for obj in follower_objectives:
                            bank_name = obj['banks']['name'] if obj['banks'] else 'N/A'
                            bank_balance = next((b['current_balance'] for b in bank_data if b['id'] == obj['bank_id']), 0.0)

                            export_list.append({
                                "Nome PG": pg_name,
                                "Associato a Utente": pg_user,
                                "Tipo Voce": "Obiettivo Seguace",
                                "Nome Voce": obj['name'],
                                "Descrizione": obj['notes'],
                                "Importo": obj['total_cost'], # Total cost of the objective
                                "Frequenza": f"{obj['estimated_months']} mesi",
                                "Banca Associata": bank_name,
                                "Saldo Banca": bank_balance,
                                "Stato Obiettivo": self.OBJECTIVE_STATUS_REV.get(obj['status'], 'Sconosciuto'),
                                "Progresso Obiettivo": f"{obj['progress_percentage']:.1f}%"
                            })
                            base_entry_added = True
            
            if not export_list: # This might happen if there are PGs but no associated data, and the base entry wasn't added for some reason.
                print("Nessun dato da esportare.")
                input("\nPremi Invio per continuare...")
                return


            df = pd.DataFrame(export_list)
            
            # Reorder columns for better readability if desired
            df = df[[
                "Nome PG", "Associato a Utente", "Tipo Voce", "Nome Voce", 
                "Descrizione", "Importo", "Frequenza", "Banca Associata", "Saldo Banca",
                "Stato Obiettivo", "Progresso Obiettivo"
            ]]

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"FondiPG_e_Obiettivi_{timestamp}.xlsx" # Updated filename
            
            script_dir = os.path.dirname(__file__)
            export_path = os.path.join(script_dir, filename)

            df.to_excel(export_path, index=False)
            print(f"Dati esportati con successo in '{export_path}'")

        except Exception as e:
            print(f"Si è verificato un errore durante l'esportazione: {e}")
        input("\nPremi Invio per continuare...")

    def create_backup(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può creare backup.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Crea Backup Database ---")
        backup_dir = "backups"
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        tables_to_backup = [
            'users', 
            'player_characters', 
            'banks', 
            'followers', 
            'economic_activities', 
            'fixed_expenses',
            'game_state',
            'follower_objectives',
            'follower_objective_events'
        ]
        
        backup_successful = True
        for table_name in tables_to_backup:
            try:
                response = self.supabase.from_(table_name).select('*').execute()
                data = response.data
                
                filename = os.path.join(backup_dir, f"{table_name}_backup_{timestamp}.json")
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                print(f"  Backup della tabella '{table_name}' salvato in '{filename}'")
            except Exception as e:
                print(f"  Errore durante il backup della tabella '{table_name}': {e}")
                backup_successful = False
        
        if backup_successful:
            print("\nBackup del database completato con successo.")
        else:
            print("\nBackup del database completato con alcuni errori.")
        input("\nPremi Invio per continuare...")

    def restore_backup(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può ripristinare backup.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Ripristina Backup Database ---")
        backup_dir = "backups"

        if not os.path.exists(backup_dir):
            print("⚠️ Nessuna cartella di backup trovata.")
            input("\nPremi Invio per continuare...")
            return

        # Elenco dei file disponibili
        backup_files = sorted([f for f in os.listdir(backup_dir) if f.endswith(".json")])
        if not backup_files:
            print("⚠️ Nessun file di backup trovato.")
            input("\nPremi Invio per continuare...")
            return

        print("📂 File di backup disponibili:")
        for i, fname in enumerate(backup_files):
            print(f"{i+1}. {fname}")
        
        try:
            choice = int(input("Scegli il file da ripristinare (numero, 0 per annullare): "))
            if choice == 0:
                return
            selected_file = backup_files[choice - 1]
        except (ValueError, IndexError):
            print("Scelta non valida.")
            input("\nPremi Invio per continuare...")
            return

        filepath = os.path.join(backup_dir, selected_file)
        table_name = selected_file.split('_backup_')[0]

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list):
                print("❌ Il file non contiene dati validi (lista mancante).")
                input("\nPremi Invio per continuare...")
                return

            # Cancella i dati esistenti nella tabella
            self.supabase_admin.from_(table_name).delete().neq('id', '').execute()
            
            # Inserisci i dati dal backup
            for chunk_start in range(0, len(data), 100):
                chunk = data[chunk_start:chunk_start+100]
                self.supabase_admin.from_(table_name).insert(chunk).execute()

            print(f"✅ Ripristino della tabella '{table_name}' completato con successo.")
        except Exception as e:
            print(f"❌ Errore durante il ripristino: {e}")
        
        input("\nPremi Invio per continuare...")

    def view_status(self):
        self._clear_screen()
        print("--- Visualizza Stato Attuale ---")
        print(f"Data di Gioco Attuale: {self._convert_date_to_ded_format(self.game_date)}\n")

        try:
            # 1. Total PGs
            pgs_response = self.supabase.from_('player_characters').select('id, name, user_id, users(username)').execute()
            all_pgs = pgs_response.data
            
            num_pgs = len(all_pgs)
            print(f"Numero totale di Personaggi Giocanti (PG): {num_pgs}\n")

            if not all_pgs:
                print("Nessun PG, fondo, seguace, attività o spesa trovata.")
                input("\nPremi Invio per continuare...")
                return

            # Filter PGs if current user is a 'GIOCATORE'
            pgs_to_display = []
            if self.current_user and self.current_user['role'] == 'GIOCATORE':
                pgs_to_display = [pg for pg in all_pgs if pg['user_id'] == self.current_user['id']]
                if not pgs_to_display:
                    print("Nessun PG associato al tuo account per visualizzare lo stato.")
                    input("\nPremi Invio per continuare...")
                    return
            else: # DM or no user logged in (though DM check above would prevent this)
                pgs_to_display = all_pgs

            # Fetch all related data for efficiency
            banks_response = self.supabase.from_('banks').select('*').execute()
            followers_response = self.supabase.from_('followers').select('*').execute()
            economic_activities_response = self.supabase.from_('economic_activities').select('*').execute()
            fixed_expenses_response = self.supabase.from_('fixed_expenses').select('*').execute()
            follower_objectives_response = self.supabase.from_('follower_objectives').select('*, banks(name)').execute() # Fetch objectives


            all_banks = banks_response.data
            all_followers = followers_response.data
            all_activities = economic_activities_response.data
            all_expenses = fixed_expenses_response.data
            all_objectives = follower_objectives_response.data

            # 2. Funds summary per PG, Followers per PG, Activities/Expenses per PG
            for pg in pgs_to_display:
                print(f"--- Stato PG: {pg['name']} (Associato a: {pg['users']['username'] if pg['users'] else 'N/A'}) ---")

                # Funds summary
                pg_banks = [b for b in all_banks if b['pg_id'] == pg['id']]
                total_funds = sum(b['current_balance'] for b in pg_banks)
                print(f"  Fondi totali: {total_funds:.2f} (suddivisi in {len(pg_banks)} conti):")
                if pg_banks:
                    for bank in pg_banks:
                        print(f"    - {bank['name']}: {bank['current_balance']:.2f}")
                else:
                    print("    Nessun conto bancario.")
                
                # Followers and their objectives
                pg_followers = [f for f in all_followers if f['pg_id'] == pg['id']]
                print(f"  Seguaci totali: {len(pg_followers)}")
                if pg_followers:
                    for follower in pg_followers:
                        print(f"    - {follower['name']} ({follower['description']})")
                        follower_objectives = [obj for obj in all_objectives if obj['follower_id'] == follower['id']]
                        if follower_objectives:
                            print("      Obiettivi:")
                            for obj in follower_objectives:
                                status_name = self.OBJECTIVE_STATUS_REV.get(obj['status'], 'Sconosciuto')
                                bank_name = obj['banks']['name'] if obj['banks'] else 'N/A'
                                print(f"        - '{obj['name']}': Stato: {status_name}, Progresso: {obj['progress_percentage']:.1f}%, Costo: {obj['total_cost']:.2f} (Banca: {bank_name})")
                        else:
                            print("      Nessun obiettivo.")
                else:
                    print("    Nessun seguace.")

                # --- Attività Economiche ---
                pg_activities = [a for a in all_activities if a['pg_id'] == pg['id']]
                print(f"\nAttività Economiche ({len(pg_activities)} attive):")
                if pg_activities:
                    for activity in pg_activities:
                        bank_id = activity.get('destination_bank_id')
                        if not bank_id:
                            print(f"  ⚠️ Attività '{activity.get('description', 'Sconosciuta')}' senza banca associata.")
                            continue

                        bank = next((b for b in all_banks if b['id'] == bank_id), None)
                        bank_name = bank['name'] if bank else 'N/A'
                        print(f"  • {activity['description']} → {activity['income']:.2f} ({activity['frequency']}) → Banca: {bank_name}")
                else:
                    print("  Nessuna attività economica.")

                # Fixed Expenses
                pg_expenses = [e for e in all_expenses if e['pg_id'] == pg['id']]
                print(f"  Spese Fisse ({len(pg_expenses)} attive):")
                if pg_expenses:
                    for expense in pg_expenses:
                        bank_name = next((b['name'] for b in all_banks if b['id'] == expense['source_bank_id']), 'N/A')
                        print(f"    - '{expense['description']}' (-{expense['amount']:.2f} {expense['frequency']}, da: {bank_name})")
                else:
                    print("    Nessuna spesa fissa.")
                print("-" * 40) # Separator for PGs

        except Exception as e:
            print(f"Si è verificato un errore durante la visualizzazione dello stato: {e}")
        input("\nPremi Invio per continuare...")

    def main_menu(self):
        while True:
            self._clear_screen()
            print(f"--- Menu Principale ({self.current_user['username']} - {self.current_user['role']}) ---")
            print("1. Gestione PG")
            print("2. Gestione Banche")
            print("3. Gestione Seguaci")
            print("4. Gestione Attività Economiche")
            print("5. Gestione Spese Fisse")
            print("6. Gestione Tempo (Solo DM)")
            print("7. Esporta Fondi PG in Excel (Solo DM)")
            print("8. Backup/Restore Database (Solo DM)")
            print("9. Visualizza Stato (DM/GIOCATORE)")
            if self.current_user and self.current_user['role'] == 'DM':
                print("10. Gestione Utenti (Solo DM)") # Existing but promoting it
            print("0. Logout")

            choice = input("Scegli un'opzione: ")

            if choice == '1':
                self.player_character_menu()
            elif choice == '2':
                self.bank_menu()
            elif choice == '3':
                self.follower_menu()
            elif choice == '4':
                self.economic_activity_menu()
            elif choice == '5':
                self.fixed_expense_menu()
            elif choice == '6':
                self.manage_time_menu() # New
            elif choice == '7':
                self.export_pg_funds_to_excel() # New
            elif choice == "8":
                if self.current_user['role'] == 'DM':
                    self.backup_restore_menu()
                else:
                    print("⚠️ Solo il DM può accedere a questa funzione.")
                    input("\nPremi Invio per continuare...")
            elif choice == '9':
                self.view_status() # New
            elif choice == '10' and self.current_user and self.current_user['role'] == 'DM':
                self.manage_users()
            elif choice == '0':
                self.current_user = None
                print("Logout effettuato.")
                break
            else:
                print("Opzione non valida o permessi insufficienti. Riprova.")
                input("\nPremi Invio per continuare...")

    def player_character_menu(self):
        while True:
            self._clear_screen()
            print("--- Gestione Personaggi Giocanti ---")
            print("1. Aggiungi PG (Solo DM)")
            print("2. Lista PG")
            print("3. Modifica PG (Solo DM)")
            print("4. Rimuovi PG (Solo DM)")
            print("0. Torna al Menu Principale")

            choice = input("Scegli un'opzione: ")

            if choice == '1':
                self.add_player_character()
            elif choice == '2':
                self.list_player_characters(show_all=True if self.current_user['role'] == 'DM' else False)
            elif choice == '3':
                self.update_player_character()
            elif choice == '4':
                self.remove_player_character()
            elif choice == '0':
                break
            else:
                print("Opzione non valida. Riprova.")
                input("\nPremi Invio per continuare...")

    def bank_menu(self):
        while True:
            self._clear_screen()
            print("--- Gestione Conti Bancari ---")
            print("1. Aggiungi Conto")
            print("2. Lista Conti")
            print("3. Modifica Conto")
            print("4. Rimuovi Conto")
            print("5. Deposita Denaro")
            print("6. Preleva Denaro")
            print("7. Trasferisci Fondi tra Banche")
            print("8. Visualizza Storico Operazioni")
            print("0. Torna al Menu Principale")

            choice = input("Scegli un'opzione: ")

            if choice == '1':
                self.add_bank()
            elif choice == '2':
                self.list_banks(show_all=(self.current_user['role'] == 'DM'))
            elif choice == '3':
                self.update_bank()
            elif choice == '4':
                self.remove_bank()
            elif choice == '5':
                self.deposit_funds()
            elif choice == '6':
                self.withdraw_funds()
            elif choice == '7':
                self.transfer_funds()
            elif choice == '8':
                self.view_bank_transactions()
            elif choice == '0':
                break
            else:
                print("Opzione non valida. Riprova.")
                input("\nPremi Invio per continuare...")
    
    def follower_menu(self):
        while True:
            self._clear_screen()
            print("--- Gestione Seguaci ---")

            # Mostra opzioni diverse a seconda del ruolo
            if self.current_user['role'] == 'DM':
                print("1. Aggiungi Seguace")
                print("2. Lista Seguaci")
                print("3. Modifica Seguace")
                print("4. Rimuovi Seguace")
            else:
                print("2. Lista Seguaci")

            print("--- Gestione Obiettivi/Imprevisti Seguaci (Solo DM) ---")
            if self.current_user['role'] == 'DM':
                print("5. Aggiungi Obiettivo")
                print("6. Modifica Obiettivo")
                print("7. Rimuovi Obiettivo")
                print("8. Inizia Obiettivo")
            print("9. Lista Obiettivi Dettagliata")
            print("10. Visualizza Cronologia Imprevisti")
            print("0. Torna al Menu Principale")

            choice = input("Scegli un'opzione: ")

            if choice == '1' and self.current_user['role'] == 'DM':
                self.add_follower()
            elif choice == '2':
                self.list_followers(show_all=(self.current_user['role'] == 'DM'))
            elif choice == '3' and self.current_user['role'] == 'DM':
                self.update_follower()
            elif choice == '4' and self.current_user['role'] == 'DM':
                self.remove_follower()
            elif choice == '5' and self.current_user['role'] == 'DM':
                self.add_follower_objective()
            elif choice == '6' and self.current_user['role'] == 'DM':
                self.update_follower_objective()
            elif choice == '7' and self.current_user['role'] == 'DM':
                self.remove_follower_objective()
            elif choice == '8' and self.current_user['role'] == 'DM':
                self.start_follower_objective()
            elif choice == '9':
                self.list_follower_objectives(show_all=(self.current_user['role'] == 'DM'))
            elif choice == '10':
                self.view_follower_events()
            elif choice == '0':
                break
            else:
                print("Opzione non valida o permessi insufficienti.")
                input("\nPremi Invio per continuare...")

    def backup_restore_menu(self):
        if self.current_user['role'] != 'DM':
            print("⚠️ Accesso negato: solo il DM può gestire i backup.")
            input("\nPremi Invio per continuare...")
            return
        while True:
            self._clear_screen()
            print("--- Backup/Restore Database ---")
            print("1. Crea Backup Database")
            print("2. Ripristina Backup da File")
            print("0. Torna al Menu Principale")

            choice = input("Scegli un'opzione: ").strip()
            if choice == "1":
                self.create_backup()
            elif choice == "2":
                self.restore_backup()
            elif choice == "0":
                break
            else:
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")

    def economic_activity_menu(self):
        while True:
            self._clear_screen()
            print("--- Gestione Attività Economiche ---")
            print("1. Aggiungi Attività Economica (Solo DM)")
            print("2. Lista Attività Economiche")
            print("3. Modifica Attività Economica (Solo DM)")
            print("4. Rimuovi Attività Economica (Solo DM)")
            print("0. Torna al Menu Principale")

            choice = input("Scegli un'opzione: ")

            if choice == '1':
                self.add_economic_activity()
            elif choice == '2':
                self.list_economic_activities(show_all=True if self.current_user['role'] == 'DM' else False)
            elif choice == '3':
                self.update_economic_activity()
            elif choice == '4':
                self.remove_economic_activity()
            elif choice == '0':
                break
            else:
                print("Opzione non valida. Riprova.")
                input("\nPremi Invio per continuare...")

    def fixed_expense_menu(self):
        while True:
            self._clear_screen()
            print("--- Gestione Spese Fisse ---")
            print("1. Aggiungi Spesa Fissa (Solo DM)")
            print("2. Lista Spese Fisse")
            print("3. Modifica Spesa Fissa (Solo DM)")
            print("4. Rimuovi Spesa Fissa (Solo DM)")
            print("0. Torna al Menu Principale")

            choice = input("Scegli un'opzione: ")

            if choice == '1':
                self.add_fixed_expense()
            elif choice == '2':
                self.list_fixed_expenses(show_all=True if self.current_user['role'] == 'DM' else False)
            elif choice == '3':
                self.update_fixed_expense()
            elif choice == '4':
                self.remove_fixed_expense()
            elif choice == '0':
                break
            else:
                print("Opzione non valida. Riprova.")
                input("\nPremi Invio per continuare...")

if __name__ == "__main__":
    show_welcome_message()
    tool = DeDTool()
    # Ciclo di login/registrazione iniziale
    while True:
        tool._clear_screen()
        print("--- Benvenuto D&D Tool V1.0---")
        print("1. Login")
        print("0. Esci")
        
        choice = input("Scegli un'opzione: ")
        
        if choice == '1':
            if tool.login():
                tool.main_menu() # Entra nel menu principale dopo il login
        elif choice == '0':
            print("Uscita dall'applicazione. Arrivederci!")
            break
        else:
            print("Opzione non valida. Riprova.")
            input("\nPremi Invio per continuare...")
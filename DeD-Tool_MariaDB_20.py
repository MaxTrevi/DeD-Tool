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

            response = requests.get(SCRIPT_URL, timeout=5)
            response.raise_for_status()
            script_path = os.path.abspath(__file__)

            with open(script_path, 'wb') as f:
                f.write(response.content)

            print("✅ Aggiornamento completato. Riavvia il programma.")
            input("Premi Invio per chiudere...")
            sys.exit(0)
    except Exception as e:
        print(f"⚠️ Errore durante il controllo aggiornamenti: {e}")

# 🔁 Esegui il controllo all'avvio del programma
check_for_updates()

from decimal import Decimal
import mysql.connector
from mysql.connector import Error
import base64
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import io
from datetime import datetime, timedelta, date
import binascii
from dateutil.relativedelta import relativedelta
from supabase import create_client, Client
import pandas as pd
import uuid
import json
import re
from openai import OpenAI
import smtplib
from email.message import EmailMessage
from tabulate import tabulate
import tempfile
import shutil

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

def create_mariadb_connection():
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="MAXmax001!",
            database="ded-tool",
            port=3307,
            charset='utf8mb4',
            collation='utf8mb4_general_ci'
        )
        return connection
    except Error as e:
        print(f"Errore di connessione al database MariaDB: {e}")
        return None

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
# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_KEY_ANON = os.getenv("SUPABASE_KEY_ANON")
# SUPABASE_KEY_SERVICE_ROLE = env_sec.get("SUPABASE_KEY_SERVICE_ROLE")

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
        try:
            self.db = mysql.connector.connect(
                host="localhost",
                user="root",
                password="MAXmax001!",
                database="ded-tool",
                port=3307,
                charset='utf8mb4',
                collation='utf8mb4_general_ci'
            )
            if self.db.is_connected():
                print("✅ Connessione a MariaDB riuscita.")
            else:
                raise Exception("❌ Connessione a MariaDB fallita.")
        except Error as e:
            print(f"❌ Errore durante la connessione a MariaDB: {e}")
            self.db = None

        self.current_user = None
        self.game_date = self._load_game_date()
            
    def _clear_screen(self):
        # Clears the console screen
        os.system('cls' if os.name == 'nt' else 'clear')

    def _load_game_date(self):
        """Carica la data di gioco da MariaDB o la inizializza se non presente."""
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT game_date FROM game_state WHERE id = 1")
            result = cursor.fetchone()

            if result and result["game_date"]:
                return result["game_date"]  # `mysql.connector` restituisce già un oggetto `date` se la colonna è di tipo DATE
            else:
                print("Nessuna data di gioco trovata. Inizializzazione della data al 01 NUWMONT 1.")
                initial_date = datetime(1, 1, 1).date()
                cursor.execute(
                    "INSERT INTO game_state (id, game_date) VALUES (%s, %s)",
                    (1, initial_date)
                )
                self.db.commit()
                return initial_date
        except Error as e:
            print(f"Errore nel caricamento della data di gioco: {e}")
            print("Inizializzazione della data di gioco a una data predefinita a causa di un errore.")
            return datetime(1, 1, 1).date()
            
    def _convert_date_to_ded_format(self, date_obj):
        """Converte una data standard in formato Mystara (es: '01 NUWMONT 1')"""
        day = date_obj.day
        month = self.MONTH_NAMES[date_obj.month - 1]  # Mesi da 0 a 11
        year = date_obj.year
        return f"{day:02d} {month} {year}"

    def _save_game_date(self):
        """Salva la data di gioco corrente su MariaDB."""
        try:
            cursor = self.db.cursor()
            update_query = "UPDATE game_state SET game_date = %s WHERE id = 1"
            cursor.execute(update_query, (self.game_date,))
            self.db.commit()

            if cursor.rowcount == 0:
                # Nessuna riga aggiornata → la riga con ID 1 non esiste → inseriamo
                insert_query = "INSERT INTO game_state (id, game_date) VALUES (%s, %s)"
                cursor.execute(insert_query, (1, self.game_date))
                self.db.commit()

        except Error as e:
            print(f"Errore nel salvataggio della data di gioco: {e}")

    def _get_user_by_username(self, username):
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            result = cursor.fetchone()
            return result if result else None
        except Error as e:
            print(f"Errore nella ricerca utente: {e}")
            return None

    def login(self):
        self._clear_screen()
        print("--- Login ---")
        username = input("Nome utente: ").strip()
        password = input("Password: ").strip()

        user = self._get_user_by_username(username)
        if user and user['password'] == password:  # In produzione, usare hashing!
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
     
        mail = input("Inserisci l'email dell'utente: ").strip()
        diario_version = input("Inserisci la versione del diario assegnata a questo utente (es. '1.0'): ").strip()

        try:
            cursor = self.db.cursor()
            cursor.execute(
                "INSERT INTO users (username, password, role, mail, diario_version) VALUES (%s, %s, %s, %s, %s)",
                (username, password, role, mail, diario_version)
            )
            self.db.commit()
            print(f"✅ Utente '{username}' registrato con successo come '{role}'.")
        except Error as e:
            print(f"❌ Si è verificato un errore: {e}")
        finally:
            cursor.close()

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

        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT id, username FROM users WHERE role = 'GIOCATORE'")
            players = cursor.fetchall()

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

            cursor.execute(
                "INSERT INTO player_characters (name, user_id) VALUES (%s, %s)",
                (name, selected_player_id)
            )
            self.db.commit()
            print(f"Personaggio '{name}' aggiunto con successo e associato a '{players[player_choice]['username']}'.")

        except Error as e:
            print(f"Si è verificato un errore: {e}")
        input("\nPremi Invio per continuare...")

    def list_player_characters(self, show_all=False, wait_for_input=True):
        self._clear_screen()
        print("--- Lista Personaggi Giocanti ---")

        try:
            cursor = self.db.cursor(dictionary=True)

            if show_all:
                query = """
                    SELECT pc.*, u.username
                    FROM player_characters pc
                    LEFT JOIN users u ON pc.user_id = u.id
                """
                cursor.execute(query)
            else:
                query = """
                    SELECT pc.*, u.username
                    FROM player_characters pc
                    LEFT JOIN users u ON pc.user_id = u.id
                    WHERE pc.user_id = %s
                """
                cursor.execute(query, (self.current_user['id'],))

            pgs = cursor.fetchall()

            if pgs:
                print("{:<4} {:<20} {:<20}".format("N.", "Nome PG", "Associato a"))
                print("-" * 50)
                for i, pg in enumerate(pgs):
                    username = pg['username'] if pg.get('username') else "N/D"
                    print(f"{i+1:<4} {pg['name']:<20} {username:<20}")
                if wait_for_input:
                    input("\nPremi Invio per continuare...")
                return pgs
            else:
                print("Nessun personaggio trovato.")
                if wait_for_input:
                    input("\nPremi Invio per continuare...")
                return []

        except Error as e:
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
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM player_characters WHERE id = %s", (selected_pg['id'],))
            self.db.commit()

            if cursor.rowcount > 0:
                print(f"PG '{selected_pg['name']}' rimosso con successo.")
            else:
                print("Errore durante la rimozione del PG (nessuna riga eliminata).")

        except Error as e:
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
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT id, username FROM users WHERE role = 'GIOCATORE'")
            players = cursor.fetchall()

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

            update_fields = []
            update_values = []

            if new_name:
                update_fields.append("name = %s")
                update_values.append(new_name)
            if new_player_id != selected_pg['user_id']:
                update_fields.append("user_id = %s")
                update_values.append(new_player_id)

            if update_fields:
                update_values.append(selected_pg['id'])  # ID per il WHERE
                update_query = f"UPDATE player_characters SET {', '.join(update_fields)} WHERE id = %s"
                cursor.execute(update_query, tuple(update_values))
                self.db.commit()

                if cursor.rowcount > 0:
                    print(f"PG '{selected_pg['name']}' modificato con successo.")
                else:
                    print("Nessuna modifica effettuata.")
            else:
                print("Nessuna modifica da applicare.")

        except Error as e:
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

        # Selezione del PG
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
                    if not pg_choice:
                        pg_choice = '0'
                    pg_choice = int(pg_choice)
                    if pg_choice == 0:
                        break
                    elif 1 <= pg_choice <= len(pgs):
                        pg_id = pgs[pg_choice - 1]['id']
                        break
                    else:
                        print("Scelta non valida. Riprova.")
                except ValueError:
                    print("Input non valido. Inserisci un numero.")

        try:
            cursor = self.db.cursor()
            insert_query = """
                INSERT INTO banks (
                    user_id, name, location, annual_interest,
                    initial_balance, current_balance, pg_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (
                self.current_user['id'],
                name,
                location,
                annual_interest,
                initial_balance,
                initial_balance,
                pg_id
            ))
            self.db.commit()

            print(f"Banca '{name}' aggiunta con successo!")
            if pg_id:
                pg_name = next(pg['name'] for pg in pgs if pg['id'] == pg_id)
                print(f"Associata al PG: {pg_name}")

        except Error as e:
            print(f"Errore durante l'aggiunta della banca: {e}")
        input("\nPremi Invio per continuare...")

    def list_banks(self, show_all=False, wait_for_input=True):
        self._clear_screen()
        print("--- Lista Banche ---\n")
        try:
            cursor = self.db.cursor(dictionary=True)
            
            if self.current_user['role'] == 'GIOCATORE' and not show_all:
                cursor.execute("""
                    SELECT b.*, pc.name AS pg_name 
                    FROM banks b
                    LEFT JOIN player_characters pc ON b.pg_id = pc.id
                    WHERE pc.user_id = %s
                """, (self.current_user['id'],))
            else:
                cursor.execute("""
                    SELECT b.*, pc.name AS pg_name 
                    FROM banks b
                    LEFT JOIN player_characters pc ON b.pg_id = pc.id
                """)
            
            banks = cursor.fetchall()
            cursor.close()

            if not banks:
                print("Nessuna banca trovata.")
                if wait_for_input:
                    input("\nPremi Invio per continuare...")
                return []

            # ✅ Mostra banche numerate
            for idx, bank in enumerate(banks, 1):
                print(f"{idx}. 🏦 {bank['name']} ({bank.get('location','')}) - "
                      f"Saldo: {bank['current_balance']:.2f} MO - "
                      f"PG: {bank.get('pg_name', 'Nessuno')}")

            if wait_for_input:
                input("\nPremi Invio per continuare...")
            return banks

        except Exception as e:
            print(f"❌ Errore nel recupero delle banche: {e}")
            if wait_for_input:
                input("\nPremi Invio per continuare...")
            return []

    def update_bank(self):
        self._clear_screen()
        print("--- Aggiorna Banca ---")
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può aggiornare le banche.")
            input("\nPremi Invio per continuare...")
            return

        banks = self.list_banks(show_all=True)
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
            print(f"Modifica banca: {bank['name']}")
            print(f"1. Nome attuale: {bank['name']}")
            print(f"2. Luogo attuale: {bank['location']}")
            print(f"3. Interessi annuali attuali: {bank['annual_interest']}")
            print(f"4. Saldo iniziale attuale: {bank['initial_balance']}")
            print(f"5. Saldo corrente attuale: {bank['current_balance']}")
            print(f"6. PG intestatario attuale: {bank.get('pg_name', 'Nessuno')}")
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
                # Cambia il PG intestatario
                pgs = self.list_player_characters(show_all=True, wait_for_input=False)
                if pgs:
                    print("\nSeleziona il nuovo PG intestatario (0 per nessun PG):")
                    for i, pg in enumerate(pgs):
                        print(f"{i+1}. {pg['name']}")
                    print("0. Nessun PG (banca generica)")

                    while True:
                        try:
                            pg_choice = input("Numero del PG (0 per nessun PG): ").strip()
                            if not pg_choice:
                                pg_choice = '0'
                            pg_choice = int(pg_choice)
                            if pg_choice == 0:
                                field_to_update = 'pg_id'
                                updated_value = None
                                break
                            elif 1 <= pg_choice <= len(pgs):
                                field_to_update = 'pg_id'
                                updated_value = pgs[pg_choice - 1]['id']
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
                cursor = self.db.cursor()
                query = f"UPDATE banks SET {field_to_update} = %s WHERE id = %s"
                cursor.execute(query, (updated_value, bank['id']))
                self.db.commit()
                if cursor.rowcount > 0:
                    print(f"Banca '{bank['name']}' aggiornata con successo!")
                else:
                    print("⚠️ Nessuna modifica effettuata.")
            else:
                print("Nessuna modifica applicata.")

        except Error as e:
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

            bank_data = banks[bank_index]

            # Conferma rimozione
            conferma = input(f"\nSei sicuro di voler rimuovere la banca '{bank_data['name']}'? (s/N): ").strip().lower()
            if conferma != 's':
                print("Operazione annullata.")
                input("\nPremi Invio per continuare...")
                return

            # Esecuzione rimozione
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM banks WHERE id = %s", (bank_data['id'],))
            self.db.commit()

            if cursor.rowcount > 0:
                print(f"\nBanca '{bank_data['name']}' rimossa con successo!")
            else:
                print("\nErrore durante la rimozione della banca (nessuna riga eliminata).")

        except ValueError:
            print("\nInput non valido. Inserire un numero.")
        except Error as e:
            print(f"\nErrore durante la rimozione: {str(e)}")

        input("\nPremi Invio per continuare...")
 
    def view_bank_transactions(self):
        self._clear_screen()
        print("--- Storico Operazioni Bancarie ---")

        try:
            cursor = self.db.cursor(dictionary=True)

            if self.current_user['role'] == 'DM':
                # DM vede tutte le banche
                cursor.execute("SELECT id, name FROM banks")
                banks = cursor.fetchall()
            else:
                # Giocatore vede solo banche associate ai propri PG
                cursor.execute("SELECT id FROM player_characters WHERE user_id = %s", (self.current_user['id'],))
                user_pg_ids = [row['id'] for row in cursor.fetchall()]

                if not user_pg_ids:
                    print("⚠️ Nessun personaggio trovato associato al tuo account.")
                    input("\nPremi Invio per continuare...")
                    return

                placeholders = ','.join(['%s'] * len(user_pg_ids))
                query = f"SELECT id, name FROM banks WHERE pg_id IN ({placeholders})"
                cursor.execute(query, tuple(user_pg_ids))
                banks = cursor.fetchall()

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

            cursor.execute("""
                SELECT operation_type, amount, reason, timestamp
                FROM bank_transactions
                WHERE bank_id = %s
                ORDER BY timestamp DESC
            """, (selected_bank_id,))
            transactions = cursor.fetchall()

            print(f"\n--- Transazioni per la banca '{selected_bank_name}' ---")
            if not transactions:
                print("Nessuna transazione trovata.")
            else:
                for tx in transactions:
                    ded_date = self._convert_date_to_ded_format(self.game_date)
                    print(f"- [{ded_date}] {tx['operation_type'].capitalize()} di {tx['amount']:.2f} → {tx.get('reason', 'Senza motivo')}")

        except Error as e:
            print(f"❌ Errore durante la visualizzazione delle transazioni: {e}")

        input("\nPremi Invio per continuare...")
 
    def deposit_funds(self):
        self._clear_screen()
        print("--- Deposito Fondi ---")

        banks = self.list_banks(show_all=True, wait_for_input=False)
        if not banks:
            print("⚠️ Nessuna banca trovata.")
            input("\nPremi Invio per continuare...")
            return

        try:
            bank_choice = int(input("Seleziona la banca per il deposito: ")) - 1
            if bank_choice < 0 or bank_choice >= len(banks):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return

            selected_bank = banks[bank_choice]
            amount = float(input("Importo da depositare: "))
            reason = input("Motivazione del deposito: ")

            # ✅ Conversione Decimal → float
            current_balance = float(selected_bank['current_balance'])
            new_balance = current_balance + amount

            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE banks 
                SET current_balance = %s 
                WHERE id = %s
            """, (new_balance, selected_bank['id']))

            cursor.execute("""
                INSERT INTO bank_transactions 
                (bank_id, operation_type, amount, reason, timestamp) 
                VALUES (%s, 'deposito', %s, %s, NOW())
            """, (selected_bank['id'], amount, reason))
            self.db.commit()
            cursor.close()

            print(f"✅ Deposito di {amount:.2f} MO effettuato con successo.")

        except Exception as e:
            print(f"❌ Errore durante il deposito: {e}")

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

            try:
                amount = Decimal(input("Importo da prelevare: ").strip())
            except:
                print("Importo non valido.")
                return

            reason = input("Motivazione del prelievo: ")

            if amount <= 0 or amount > selected_bank['current_balance']:
                print("Importo non valido o fondi insufficienti.")
                return

            new_balance = selected_bank['current_balance'] - amount

            cursor = self.db.cursor()

            # Aggiorna il saldo
            cursor.execute(
                "UPDATE banks SET current_balance = %s WHERE id = %s",
                (new_balance, selected_bank['id'])
            )

            # Registra la transazione
            cursor.execute("""
                INSERT INTO bank_transactions (bank_id, operation_type, amount, reason, timestamp)
                VALUES (%s, %s, %s, %s, NOW())
            """, (selected_bank['id'], 'prelievo', amount, reason))

            self.db.commit()

            print(f"✅ Prelievo di {amount:.2f} effettuato con successo.")

        except Error as e:
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

            # Restrizione per giocatori
            if self.current_user['role'] != 'DM':
                if from_bank.get('pg_id') != to_bank.get('pg_id'):
                    print("⚠️ Puoi trasferire fondi solo tra banche dello stesso PG.")
                    input("\nPremi Invio per continuare...")
                    return

            try:
                amount = float(input("Importo da trasferire: "))
            except ValueError:
                print("Importo non valido.")
                return

            reason = input("Motivazione del trasferimento: ")

            if amount <= 0 or amount > from_bank['current_balance']:
                print("Importo non valido o fondi insufficienti.")
                return

            cursor = self.db.cursor()

            # Aggiorna saldo banca origine
            cursor.execute(
                "UPDATE banks SET current_balance = current_balance - %s WHERE id = %s",
                (amount, from_bank['id'])
            )

            # Aggiorna saldo banca destinazione
            cursor.execute(
                "UPDATE banks SET current_balance = current_balance + %s WHERE id = %s",
                (amount, to_bank['id'])
            )

            # Log dell'operazione
            cursor.execute("""
                INSERT INTO bank_transactions (bank_id, operation_type, amount, reason, timestamp)
                VALUES (%s, 'trasferimento', %s, %s, NOW())
            """, (from_bank['id'], amount, f"Da {from_bank['name']} a {to_bank['name']}: {reason}"))

            self.db.commit()

            print(f"✅ Trasferimento di {amount:.2f} completato.")

        except Error as e:
            print(f"❌ Errore nel trasferimento: {e}")
        except ValueError:
            print("Input non valido.")
        input("\nPremi Invio per continuare...")

    # --- Funzioni di Gestione Seguaci-----
    def add_follower(self):
        if not self.current_user:
            print("Devi essere loggato per aggiungere un seguace.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Aggiungi Seguace ---")

        pgs = self.list_player_characters(show_all=(self.current_user['role'] == 'DM'))
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

        follower_class = input("Classe del seguace: ").strip()

        level = None
        while level is None:
            try:
                level_str = input("Livello del seguace (lascia vuoto per 1): ").strip()
                level = 1 if not level_str else int(level_str)
                if level <= 0:
                    print("Il livello deve essere un numero positivo.")
                    level = None
            except ValueError:
                print("Input non valido. Inserisci un numero intero.")

        annual_cost = None
        while annual_cost is None:
            try:
                cost_str = input("Costo annuale del seguace (lascia vuoto per 0): ").strip()
                annual_cost = 0.0 if not cost_str else float(cost_str)
                if annual_cost < 0:
                    print("Il costo annuale non può essere negativo.")
                    annual_cost = None
            except ValueError:
                print("Input non valido. Inserisci un numero.")

        notes = input("Note sul seguace: ").strip()

        # ✅ Nuova richiesta Razza dopo le note, senza inserirla nel DB
        race = input("Razza del seguace (es. 'Umano', 'Elfo'): ").strip()

        # Recupera le banche del PG
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT * FROM banks WHERE pg_id = %s", (selected_pg['id'],))
            pg_banks = cursor.fetchall()
        except Error as e:
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

        try:
            cursor.execute("""
                INSERT INTO followers (pg_id, name, class, level, annual_cost, notes, bank_destination_cost, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                selected_pg['id'],
                follower_name,
                follower_class,
                level,
                annual_cost,
                notes,
                bank_destination_cost,
                race  # ✅ Inseriamo la razza in description
            ))
            self.db.commit()
            print(f"Seguace '{follower_name}' aggiunto con successo a {selected_pg['name']}.")
        except Error as e:
            print(f"Si è verificato un errore: {e}")

        input("\nPremi Invio per continuare...")

    def list_followers(self, show_all=False):
        self._clear_screen()
        print("--- Lista Seguaci Raggruppati per PG ---\n")

        try:
            cursor = self.db.cursor(dictionary=True)

            if self.current_user and self.current_user['role'] == 'GIOCATORE':
                # Recupera i PG dell'utente
                cursor.execute("SELECT id FROM player_characters WHERE user_id = %s", (self.current_user['id'],))
                user_pg_ids = [row['id'] for row in cursor.fetchall()]

                if not user_pg_ids:
                    print("⚠️ Nessun personaggio trovato associato al tuo account.")
                    input("\nPremi Invio per continuare...")
                    return []

                format_strings = ','.join(['%s'] * len(user_pg_ids))
                query = f"""
                    SELECT f.*, pc.name AS pg_name, u.username, b.name AS bank_name
                    FROM followers f
                    LEFT JOIN player_characters pc ON f.pg_id = pc.id
                    LEFT JOIN users u ON pc.user_id = u.id
                    LEFT JOIN banks b ON f.bank_destination_cost = b.id
                    WHERE f.pg_id IN ({format_strings})
                """
                cursor.execute(query, tuple(user_pg_ids))
            else:
                # DM o ADMIN vedono tutti i seguaci
                cursor.execute("""
                    SELECT f.*, pc.name AS pg_name, u.username, b.name AS bank_name
                    FROM followers f
                    LEFT JOIN player_characters pc ON f.pg_id = pc.id
                    LEFT JOIN users u ON pc.user_id = u.id
                    LEFT JOIN banks b ON f.bank_destination_cost = b.id
                """)

            followers = cursor.fetchall()
            if not followers:
                print("Nessun seguace trovato.")
                input("\nPremi Invio per continuare...")
                return []

            # Raggruppa per nome PG
            pg_groups = {}
            for f in followers:
                pg_name = f.get('pg_name', 'N/A')
                if pg_name not in pg_groups:
                    pg_groups[pg_name] = []
                pg_groups[pg_name].append(f)

            # Visualizzazione
            for pg_name, group in pg_groups.items():
                print(f"Nome PG         : {pg_name}\n")

                fields = ["name", "class", "level", "annual_cost", "bank_name", "notes", "description"]
                labels = ["Nome Seguace", "Classe", "Livello", "Costo Ann.", "Banca", "Note", "Descrizione"]

                for label, field in zip(labels, fields):
                    row = f"{label:<15} : "
                    for follower in group:
                        if field == "annual_cost":
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

        followers = self.list_followers(show_all=(self.current_user['role'] == 'DM'))
        if not followers:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero del seguace da modificare:")
        for i, f in enumerate(followers):
            pg_name = f.get('pg_name', 'N/A')
            print(f"{i+1}. {f['name']} (PG: {pg_name})")

        try:
            follower_index = int(input("Numero: ")) - 1
            if not (0 <= follower_index < len(followers)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_follower = followers[follower_index]
            follower_id = selected_follower['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        # Check permesso se è giocatore
        if self.current_user['role'] == 'GIOCATORE':
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT id FROM player_characters WHERE user_id = %s", (self.current_user['id'],))
            user_pg_ids = [pg['id'] for pg in cursor.fetchall()]
            if selected_follower['pg_id'] not in user_pg_ids:
                print("Non hai i permessi per modificare questo seguace.")
                input("\nPremi Invio per continuare...")
                return

        print(f"\nModifica Seguace: ({selected_follower['name']}) per {selected_follower['pg_name']}")
        update_fields = []
        update_values = []

        def add_field(field_name, prompt, cast_type=str, allow_zero_removal=False, default=None):
            current_value = selected_follower.get(field_name, default)
            inp = input(f"{prompt} (lascia vuoto per mantenere '{current_value}'): ").strip()
            if not inp:
                return
            if allow_zero_removal and inp == '0':
                update_fields.append(f"{field_name} = %s")
                update_values.append(None)
                return
            try:
                value = cast_type(inp)
                update_fields.append(f"{field_name} = %s")
                update_values.append(value)
            except ValueError:
                print("Input non valido ignorato.")

        add_field("name", "Nuovo nome seguace")
        add_field("class", "Nuova classe")
        add_field("level", "Nuovo livello", int, allow_zero_removal=True)
        add_field("annual_cost", "Nuovo costo annuale", float, allow_zero_removal=True)
        add_field("notes", "Nuove note")
        add_field("description", "Nuova descrizione")

        # Cambia PG solo se DM
        if self.current_user['role'] == 'DM':
            pgs = self.list_player_characters(show_all=True)
            print("\nSeleziona il nuovo PG (0 per non cambiare):")
            for i, pg in enumerate(pgs):
                print(f"{i+1}. {pg['name']}")
            pg_input = input("Numero: ").strip()
            if pg_input and pg_input != '0':
                try:
                    pg_index = int(pg_input) - 1
                    if 0 <= pg_index < len(pgs):
                        update_fields.append("pg_id = %s")
                        update_values.append(pgs[pg_index]['id'])
                except ValueError:
                    print("Input PG non valido.")

        # Cambia banca
        current_bank = selected_follower.get('bank_name', 'Nessuna')
        new_bank_id = input(f"Nuova banca destinazione costo (lascia vuoto per '{current_bank}', 0 per rimuovere): ").strip()
        if new_bank_id == '0':
            update_fields.append("bank_destination_cost = %s")
            update_values.append(None)
        elif new_bank_id:
            update_fields.append("bank_destination_cost = %s")
            update_values.append(new_bank_id)

        if update_fields:
            try:
                cursor = self.db.cursor()
                sql = f"UPDATE followers SET {', '.join(update_fields)} WHERE id = %s"
                update_values.append(follower_id)
                cursor.execute(sql, tuple(update_values))
                self.db.commit()
                print(f"Seguace '{selected_follower['name']}' modificato con successo.")
            except Exception as e:
                print(f"❌ Errore durante l'aggiornamento: {e}")
        else:
            print("Nessuna modifica da applicare.")

        input("\nPremi Invio per continuare...")

    def remove_follower(self):
        if not self.current_user:
            print("Devi essere loggato per rimuovere un seguace.")
            input("\nPremi Invio per continuare...")
            return

        followers = self.list_followers(show_all=(self.current_user['role'] == 'DM'))
        if not followers:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero del seguace da rimuovere:")
        for i, f in enumerate(followers):
            pg_name = f.get('pg_name', 'N/A')
            print(f"{i+1}. {f['name']} (PG: {pg_name})")

        try:
            index = int(input("Numero: ")) - 1
            if not (0 <= index < len(followers)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_follower = followers[index]
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        # Check permission
        if self.current_user['role'] == 'GIOCATORE':
            try:
                cursor = self.db.cursor(dictionary=True)
                cursor.execute("SELECT id FROM player_characters WHERE user_id = %s", (self.current_user['id'],))
                user_pg_ids = [pg['id'] for pg in cursor.fetchall()]
                if selected_follower['pg_id'] not in user_pg_ids:
                    print("Non hai i permessi per rimuovere questo seguace.")
                    input("\nPremi Invio per continuare...")
                    return
            except Exception as e:
                print(f"Errore nel controllo permessi: {e}")
                input("\nPremi Invio per continuare...")
                return

        conferma = input(f"Sei sicuro di voler rimuovere il seguace '{selected_follower['name']}'? (s/N): ").strip().lower()
        if conferma != 's':
            print("Rimozione annullata.")
            input("\nPremi Invio per continuare...")
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM followers WHERE id = %s", (selected_follower['id'],))
            self.db.commit()
            print(f"Seguace '{selected_follower['name']}' rimosso con successo.")
        except Exception as e:
            print(f"❌ Errore durante la rimozione: {e}")
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
                self.list_followers(show_all=(self.current_user['role'] == 'DM'))
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

        pgs = self.list_player_characters(show_all=True)  # DM vede tutti i PG
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

        # Recupera banche per il PG
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT id, name, current_balance FROM banks WHERE pg_id = %s", (selected_pg['id'],))
            banks_for_pg = cursor.fetchall()
        except Exception as e:
            print(f"Errore nel recupero delle banche: {e}")
            input("\nPremi Invio per continuare...")
            return

        if not banks_for_pg:
            print(f"Il PG '{selected_pg['name']}' non ha conti bancari. Aggiungi un conto prima.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nSeleziona la banca di destinazione per il guadagno di '{selected_pg['name']}':")
        for i, bank in enumerate(banks_for_pg):
            print(f"{i+1}. {bank['name']} (Saldo: {float(bank['current_balance']):.2f})")

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

        # Inserimento nella tabella economic_activities
        try:
            cursor.execute("""
                INSERT INTO economic_activities (pg_id, description, income, frequency, destination_bank_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (selected_pg['id'], description, income, frequency, selected_bank_id))
            self.db.commit()
            print(f"✅ Attività economica '{description}' aggiunta con successo per {selected_pg['name']}.")
        except Exception as e:
            print(f"❌ Errore durante l'inserimento: {e}")

        input("\nPremi Invio per continuare...")

    def list_economic_activities(self, show_all=False):
        self._clear_screen()
        print("--- Lista Attività Economiche ---\n")

        try:
            cursor = self.db.cursor(dictionary=True)  # ✅ Cursore locale

            if self.current_user['role'] == 'GIOCATORE' and not show_all:
                # Recupera gli ID dei PG dell'utente
                cursor.execute(
                    "SELECT id FROM player_characters WHERE user_id = %s",
                    (self.current_user['id'],)
                )
                user_pg_ids = [row['id'] for row in cursor.fetchall()]

                if not user_pg_ids:
                    print("Nessuna attività economica trovata per i tuoi personaggi.")
                    input("\nPremi Invio per continuare...")
                    return []

                format_strings = ','.join(['%s'] * len(user_pg_ids))
                query = f"""
                    SELECT ea.*, pc.name AS pg_name, b.name AS bank_name
                    FROM economic_activities ea
                    JOIN player_characters pc ON ea.pg_id = pc.id
                    LEFT JOIN banks b ON ea.destination_bank_id = b.id
                    WHERE ea.pg_id IN ({format_strings})
                    ORDER BY pc.name
                """
                cursor.execute(query, tuple(user_pg_ids))

            else:
                # DM o show_all = True: mostra tutte le attività
                query = """
                    SELECT ea.*, pc.name AS pg_name, b.name AS bank_name
                    FROM economic_activities ea
                    JOIN player_characters pc ON ea.pg_id = pc.id
                    LEFT JOIN banks b ON ea.destination_bank_id = b.id
                    ORDER BY pc.name
                """
                cursor.execute(query)

            activities = cursor.fetchall()
            if not activities:
                print("Nessuna attività economica trovata.")
                input("\nPremi Invio per continuare...")
                return []

            # Raggruppa per nome PG
            pg_activities = {}
            for act in activities:
                pg_name = act.get('pg_name', 'Sconosciuto')
                pg_activities.setdefault(pg_name, []).append(act)

            for pg_name, acts in pg_activities.items():
                print(f"👤 Nome PG       : {pg_name}")
                for act in acts:
                    print(f"   Descrizione   : {act.get('description', 'N/A')}")
                    print(f"   Guadagno      : {act.get('income', 0.0):.2f} MO")
                    print(f"   Frequenza     : {act.get('frequency', 'N/A')}")
                    print(f"   Banca Dest.   : {act.get('bank_name', 'Nessuna')}")
                    print("-" * 40)
                print("")

            return activities

        except Exception as e:
            print(f"❌ Si è verificato un errore nel recupero delle attività economiche: {e}")
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
            print(f"{i+1}. {a['description']} (PG: {a['pg_name']}, Guadagno: {a['income']:.2f}, Frequenza: {a['frequency']})")

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
            activity_id = selected_activity['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nModifica Attività Economica: {selected_activity['description']} per {selected_activity['pg_name']}")

        update_fields = []
        update_values = []

        # Descrizione
        new_description = input(f"Nuova descrizione (lascia vuoto per mantenere '{selected_activity['description']}'): ").strip()
        if new_description:
            update_fields.append("description = %s")
            update_values.append(new_description)

        # Guadagno
        new_income_str = input(f"Nuovo guadagno (lascia vuoto per mantenere '{selected_activity['income']:.2f}'): ").strip()
        if new_income_str:
            try:
                new_income = float(new_income_str)
                update_fields.append("income = %s")
                update_values.append(new_income)
            except ValueError:
                print("Guadagno non valido. Mantenuto quello attuale.")

        # Frequenza
        new_frequency = input(f"Nuova frequenza (lascia vuoto per mantenere '{selected_activity['frequency']}'): ").strip()
        if new_frequency:
            update_fields.append("frequency = %s")
            update_values.append(new_frequency)

        # Cambio PG (opzionale)
        pgs = self.list_player_characters(show_all=True)
        new_pg_id = selected_activity['pg_id']
        if pgs:
            print("\nSeleziona il nuovo PG (0 per non cambiare):")
            for i, pg in enumerate(pgs):
                print(f"{i+1}. {pg['name']}")

            while True:
                try:
                    pg_choice = input("Numero del nuovo PG: ").strip()
                    if not pg_choice or pg_choice == '0':
                        break
                    pg_index = int(pg_choice) - 1
                    if 0 <= pg_index < len(pgs):
                        new_pg_id = pgs[pg_index]['id']
                        update_fields.append("pg_id = %s")
                        update_values.append(new_pg_id)
                        break
                    else:
                        print("Scelta non valida.")
                except ValueError:
                    print("Input non valido. Inserisci un numero.")

        # Cambio banca (corretto per MariaDB)
        cursor = self.db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM banks WHERE pg_id = %s", (new_pg_id,))
        banks_for_pg = cursor.fetchall()

        new_bank_id = selected_activity['destination_bank_id']
        if banks_for_pg:
            print("\nSeleziona la nuova banca di destinazione (0 per non cambiare):")
            for i, bank in enumerate(banks_for_pg):
                saldo = float(bank.get('current_balance', 0.0))
                print(f"{i+1}. {bank['name']} (Saldo: {saldo:.2f})")

            while True:
                try:
                    bank_choice = input("Numero della nuova banca: ").strip()
                    if not bank_choice or bank_choice == '0':
                        break
                    bank_index = int(bank_choice) - 1
                    if 0 <= bank_index < len(banks_for_pg):
                        new_bank_id = banks_for_pg[bank_index]['id']
                        update_fields.append("destination_bank_id = %s")
                        update_values.append(new_bank_id)
                        break
                    else:
                        print("Scelta non valida.")
                except ValueError:
                    print("Input non valido.")
        else:
            print(f"⚠️ Il PG selezionato non ha banche. Nessuna modifica alla banca di destinazione.")

        # Aggiorna record
        if update_fields:
            update_values.append(activity_id)
            query = f"UPDATE economic_activities SET {', '.join(update_fields)} WHERE id = %s"
            try:
                cursor.execute(query, tuple(update_values))
                self.db.commit()
                print(f"✅ Attività economica '{selected_activity['description']}' modificata con successo.")
            except Exception as e:
                print(f"❌ Errore durante l'aggiornamento: {e}")
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
            print(f"{i+1}. {a['description']} (PG: {a['pg_name']}, Guadagno: {a['income']:.2f}, Frequenza: {a['frequency']})")

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

        confirm = input(
            f"Sei sicuro di voler rimuovere l'attività economica '{selected_activity['description']}'? (s/N): "
        ).strip().lower()

        if confirm == 's':
            try:
                cursor = self.db.cursor(dictionary=True)
                cursor.execute("DELETE FROM economic_activities WHERE id = %s", (activity_id_to_remove,))
                self.db.commit()
                if cursor.rowcount > 0:
                    print(f"✅ Attività economica '{selected_activity['description']}' rimossa con successo.")
                else:
                    print("⚠️ Nessuna attività rimossa: potrebbe non esistere più.")
            except Exception as e:
                print(f"❌ Errore durante l'eliminazione: {e}")
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

        pgs = self.list_player_characters(show_all=True)
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

        # Recupera le banche del PG
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT * FROM banks WHERE pg_id = %s", (selected_pg['id'],))
            banks_for_pg = cursor.fetchall()
        except Exception as e:
            print(f"❌ Errore nel recupero delle banche: {e}")
            input("\nPremi Invio per continuare...")
            return

        if not banks_for_pg:
            print(f"⚠️ Il PG '{selected_pg['name']}' non ha conti bancari.")
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

        # Inserimento nella tabella fixed_expenses
        try:
            cursor.execute("""
                INSERT INTO fixed_expenses (pg_id, description, amount, frequency, source_bank_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (selected_pg['id'], description, amount, frequency, selected_bank_id))
            self.db.commit()
            print(f"✅ Spesa fissa '{description}' aggiunta con successo per {selected_pg['name']}.")
        except Exception as e:
            print(f"❌ Errore nell'inserimento della spesa fissa: {e}")

        input("\nPremi Invio per continuare...")

    def list_fixed_expenses(self, show_all=False):
        self._clear_screen()
        print("--- Lista Spese Fisse per Personaggio ---\n")

        try:
            cursor = self.db.cursor(dictionary=True)  # ✅ Usa il cursore di MariaDB

            if not self.current_user or self.current_user['role'] == 'DM':
                show_all = True

            if show_all:
                cursor.execute("""
                    SELECT fe.*, pc.name AS pg_name, b.name AS bank_name
                    FROM fixed_expenses fe
                    LEFT JOIN player_characters pc ON fe.pg_id = pc.id
                    LEFT JOIN banks b ON fe.source_bank_id = b.id
                    ORDER BY fe.pg_id
                """)
                expenses = cursor.fetchall()
            else:
                cursor.execute("SELECT id FROM player_characters WHERE user_id = %s", (self.current_user['id'],))
                user_pg_ids = [row['id'] for row in cursor.fetchall()]
                if not user_pg_ids:
                    print("Nessuna spesa fissa trovata per i tuoi personaggi.")
                    input("\nPremi Invio per continuare...")
                    return []

                format_strings = ','.join(['%s'] * len(user_pg_ids))
                cursor.execute(f"""
                    SELECT fe.*, pc.name AS pg_name, b.name AS bank_name
                    FROM fixed_expenses fe
                    LEFT JOIN player_characters pc ON fe.pg_id = pc.id
                    LEFT JOIN banks b ON fe.source_bank_id = b.id
                    WHERE fe.pg_id IN ({format_strings})
                    ORDER BY fe.pg_id
                """, tuple(user_pg_ids))
                expenses = cursor.fetchall()

            if not expenses:
                print("Nessuna spesa fissa trovata.")
                input("\nPremi Invio per continuare...")
                return []

            # Raggruppa per nome del PG
            grouped = {}
            for exp in expenses:
                pg_name = exp.get('pg_name', 'N/A')
                grouped.setdefault(pg_name, []).append(exp)

            for pg_name, pg_expenses in grouped.items():
                print(f"Nome PG        : {pg_name}\n")

                labels = ["Descrizione", "Ammontare", "Frequenza", "Banca Sorgente"]
                rows = [[] for _ in labels]

                for exp in pg_expenses:
                    rows[0].append(exp.get('description', ''))
                    rows[1].append(f"{exp.get('amount', 0.0):.2f} MO")
                    rows[2].append(exp.get('frequency', ''))
                    rows[3].append(exp.get('bank_name', 'Nessuna'))

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
            pg_name = e.get('pg_name', 'N/A')
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
            expense_id = selected_expense['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nModifica Spesa Fissa: {selected_expense['description']} (PG: {selected_expense['pg_name']})")

        update_data = {}

        # Nuovi valori opzionali
        new_description = input(f"Nuova descrizione (lascia vuoto per mantenere '{selected_expense['description']}'): ").strip()
        if new_description:
            update_data['description'] = new_description

        new_amount_str = input(f"Nuovo ammontare (lascia vuoto per mantenere '{selected_expense['amount']:.2f}'): ").strip()
        if new_amount_str:
            try:
                update_data['amount'] = float(new_amount_str)
            except ValueError:
                print("⚠️ Ammontare non valido. Mantenuto il valore attuale.")

        new_frequency = input(f"Nuova frequenza (lascia vuoto per mantenere '{selected_expense['frequency']}'): ").strip().lower()
        if new_frequency:
            update_data['frequency'] = new_frequency

        cursor = self.db.cursor(dictionary=True)

        # Cambio PG (e potenzialmente banca)
        cursor.execute("SELECT id, name FROM player_characters ORDER BY name")
        pgs = cursor.fetchall()

        new_pg_id = selected_expense['pg_id']
        if pgs:
            print("\nSeleziona il nuovo PG a cui associare la spesa (0 per non cambiare):")
            for i, pg in enumerate(pgs):
                print(f"{i+1}. {pg['name']}")

            while True:
                pg_choice_str = input("Numero del nuovo PG: ").strip()
                if not pg_choice_str or pg_choice_str == '0':
                    break
                try:
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

        # Cambio banca
        cursor.execute("SELECT id, name, current_balance FROM banks WHERE pg_id = %s", (new_pg_id,))
        banks = cursor.fetchall()

        if banks:
            print(f"\nSeleziona la nuova banca di origine per la spesa (0 per non cambiare):")
            for i, bank in enumerate(banks):
                print(f"{i+1}. {bank['name']} (Saldo: {bank['current_balance']:.2f})")

            new_bank_id = selected_expense['source_bank_id']
            while True:
                bank_choice_str = input("Numero della nuova banca: ").strip()
                if not bank_choice_str or bank_choice_str == '0':
                    break
                try:
                    bank_choice = int(bank_choice_str) - 1
                    if 0 <= bank_choice < len(banks):
                        new_bank_id = banks[bank_choice]['id']
                        break
                    else:
                        print("Scelta non valida. Riprova.")
                except ValueError:
                    print("Input non valido. Inserisci un numero.")

            if new_bank_id != selected_expense['source_bank_id']:
                update_data['source_bank_id'] = new_bank_id
        else:
            print("⚠️ Nessuna banca trovata per il nuovo PG. Banca di origine impostata a NULL.")
            if selected_expense['source_bank_id'] is not None and new_pg_id != selected_expense['pg_id']:
                update_data['source_bank_id'] = None

        # Esecuzione update
        if update_data:
            try:
                fields = ", ".join([f"{k} = %s" for k in update_data])
                values = list(update_data.values()) + [expense_id]
                cursor.execute(f"UPDATE fixed_expenses SET {fields} WHERE id = %s", values)
                self.db.commit()
                print(f"✅ Spesa fissa '{selected_expense['description']}' modificata con successo.")
            except Exception as e:
                print(f"❌ Errore nell'aggiornamento della spesa fissa: {e}")
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
            pg_name = e.get('pg_name', 'N/A')
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
            expense_id = selected_expense['id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        confirm = input(
            f"Sei sicuro di voler rimuovere la spesa fissa '{selected_expense['description']}'? (s/N): "
        ).strip().lower()

        if confirm == 's':
            try:
                cursor = self.db.cursor(dictionary=True)
                cursor.execute("DELETE FROM fixed_expenses WHERE id = %s", (expense_id,))
                self.db.commit()
                print(f"✅ Spesa fissa '{selected_expense['description']}' rimossa con successo.")
            except Exception as e:
                print(f"❌ Si è verificato un errore durante la rimozione: {e}")
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
                self.register_user()
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

    def scarica_diario_campagna_mariadb(self):
        self._clear_screen()
        print("📘 Controllo Diario della Campagna...\n")

        VERSION_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/diario_version.txt"
        PDF_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/Diario_Campagna.pdf"

        try:
            utente = self.current_user
            versione_locale = utente.get('diario_version')

            # Scarica ultima versione disponibile da GitHub
            response = requests.get(VERSION_URL, timeout=5)
            response.raise_for_status()
            ultima_versione_online = response.text.strip()

            nome_file_pdf = f"Diario_Campagna.{ultima_versione_online}.pdf"
            DEST_PATH = os.path.join(os.getcwd(), nome_file_pdf)

            if versione_locale == ultima_versione_online:
                print(f"✅ Hai già l'ultima versione del Diario della Campagna. (Versione: {versione_locale})")
            else:
                print(f"📘 Nuova versione disponibile del Diario della Campagna!")
                print(f"🔹 Versione attuale: {versione_locale or 'Nessuna'}")
                print(f"🔸 Versione disponibile: {ultima_versione_online}")
                print("📥 Download in corso...")

                # Scarica il PDF
                r = requests.get(PDF_URL, stream=True)
                r.raise_for_status()

                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            tmp_file.write(chunk)
                    temp_path = tmp_file.name

                shutil.move(temp_path, DEST_PATH)
                print(f"\n✅ Diario scaricato con successo in: {DEST_PATH}")

                # Aggiorna diario_version nel DB MariaDB
                sql = "UPDATE users SET diario_version = %s WHERE id = %s"
                self.cursor.execute(sql, (ultima_versione_online, utente['id']))
                self.conn.commit()

                # Aggiorna localmente l'utente
                self.current_user['diario_version'] = ultima_versione_online

        except Exception as e:
            print(f"❌ Errore durante il controllo o download del Diario: {e}")

        input("\nPremi Invio per tornare al menu...")

    def list_users(self):
        self._clear_screen()
        print("--- Lista Utenti ---")
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT id, username, role FROM users")
            users = cursor.fetchall()

            if not users:
                print("Nessun utente trovato.")
                return []

            print("{:<5} {:<20} {:<10}".format("N.", "Nome Utente", "Ruolo"))
            print("-" * 40)
            for i, user in enumerate(users, start=1):
                print(f"{i:<5} {user['username']:<20} {user['role']:<10}")

            cursor.close()
            return users  # ✅ ritorna comunque la lista completa con ID reali

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

        print("\n📋 Scegli un utente da modificare (numero progressivo):")
        for i, u in enumerate(users, start=1):
            print(f"{i}. {u['username']} ({u['role']})")

        try:
            choice = int(input("\nInserisci il numero dell'utente da modificare: ").strip())
            if choice < 1 or choice > len(users):
                print("⚠️ Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_user = users[choice - 1]
        except ValueError:
            print("⚠️ Input non valido.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nModifica Utente: {selected_user['username']} (ID reale: {selected_user['id']})")

        new_username = input(f"Nuovo nome utente (lascia vuoto per mantenere '{selected_user['username']}'): ").strip()
        new_password = input("Nuova password (lascia vuoto per non cambiare): ").strip()
        new_role = input(f"Nuovo ruolo (DM/GIOCATORE, lascia vuoto per mantenere '{selected_user['role']}'): ").strip().upper()
        new_mail = input(f"Nuova mail (lascia vuoto per mantenere '{selected_user.get('mail', 'N/A')}'): ").strip()
        new_diario_version = input(f"Nuova versione diario (lascia vuoto per mantenere '{selected_user.get('diario_version', 'N/A')}'): ").strip()

        update_data = {}
        cursor = self.db.cursor(dictionary=True)

        if new_username:
            # ✅ Check unicità username
            cursor.execute("SELECT id FROM users WHERE username = %s", (new_username,))
            existing = cursor.fetchone()
            if existing and str(existing['id']) != str(selected_user['id']):
                print("⚠️ Nome utente già esistente. Modifica annullata.")
                cursor.close()
                input("\nPremi Invio per continuare...")
                return
            update_data['username'] = new_username

        if new_password:
            update_data['password'] = new_password  # ⚠️ In produzione: hash della password

        if new_role:
            if new_role in ['DM', 'GIOCATORE']:
                update_data['role'] = new_role
            else:
                print("⚠️ Ruolo non valido. Mantenuto il ruolo attuale.")

        if new_mail:
            update_data['mail'] = new_mail

        if new_diario_version:
            update_data['diario_version'] = new_diario_version

        if update_data:
            try:
                set_clause = ", ".join([f"{key} = %s" for key in update_data.keys()])
                values = list(update_data.values()) + [selected_user['id']]

                query = f"UPDATE users SET {set_clause} WHERE id = %s"
                cursor.execute(query, values)
                self.db.commit()

                print(f"✅ Utente '{selected_user['username']}' modificato con successo.")
            except Exception as e:
                print(f"❌ Errore durante l'aggiornamento dell'utente: {e}")
        else:
            print("Nessuna modifica da applicare.")

        cursor.close()
        input("\nPremi Invio per continuare...")

    def remove_user(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può rimuovere gli utenti.")
            input("\nPremi Invio per continuare...")
            return

        users = self.list_users()
        if not users:
            return

        print("\n📋 Scegli un utente da rimuovere (numero progressivo):")
        for i, u in enumerate(users, start=1):
            print(f"{i}. {u['username']} ({u['role']})")

        try:
            choice = int(input("\nInserisci il numero dell'utente da rimuovere: ").strip())
            if choice < 1 or choice > len(users):
                print("⚠️ Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_user = users[choice - 1]
        except ValueError:
            print("⚠️ Input non valido.")
            input("\nPremi Invio per continuare...")
            return

        if str(selected_user['id']) == str(self.current_user['id']):
            print("❌ Non puoi rimuovere il tuo stesso account mentre sei loggato.")
            input("\nPremi Invio per continuare...")
            return

        confirm = input(
            f"Sei sicuro di voler rimuovere l'utente '{selected_user['username']}' (ID reale: {selected_user['id']})?\n"
            "Questa operazione non elimina i PG associati, ma li disassocia dall'utente. (s/N): "
        ).strip().lower()

        if confirm == 's':
            try:
                cursor = self.db.cursor(dictionary=True)

                # 1. Disassocia i PG
                cursor.execute(
                    "UPDATE player_characters SET user_id = NULL WHERE user_id = %s",
                    (selected_user['id'],)
                )
                print(f"🔄 PGs associati all'utente '{selected_user['username']}' disassociati.")

                # 2. Elimina l'utente
                cursor.execute("DELETE FROM users WHERE id = %s", (selected_user['id'],))
                self.db.commit()

                print(f"✅ Utente '{selected_user['username']}' rimosso con successo.")

                cursor.close()

            except Exception as e:
                self.db.rollback()
                print(f"❌ Errore durante la rimozione dell'utente: {e}")
        else:
            print("Rimozione annullata.")

        input("\nPremi Invio per continuare...")

    # --- FUNZIONALITÀ OBIETTIVI SEGUACI ---
    def add_objective_event(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può inserire imprevisti.")
            input("\nPremi Invio per continuare...")
            return

        cursor = self.db.cursor(dictionary=True)

        # 1. Obiettivi attivi
        cursor.execute(
            "SELECT id, name, status, follower_id FROM follower_objectives WHERE status = %s",
            (self.OBJECTIVE_STATUS['IN_CORSO'],)
        )
        objectives = cursor.fetchall()

        if not objectives:
            print("Nessun obiettivo attualmente in corso.")
            cursor.close()
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona un obiettivo a cui assegnare un imprevisto:")
        for i, obj in enumerate(objectives):
            print(f"{i+1}. {obj['name']}")

        try:
            choice = int(input("Numero (0 per annullare): ").strip())
            if choice == 0:
                cursor.close()
                return
            if not (1 <= choice <= len(objectives)):
                print("Scelta non valida.")
                cursor.close()
                return
            selected_obj = objectives[choice - 1]
        except ValueError:
            print("Input non valido.")
            cursor.close()
            return

        # 2. Descrizione imprevisto
        print(f"\nInserisci la descrizione dell'imprevisto per '{selected_obj['name']}':")
        description = input("Descrizione: ").strip()

        # 3. Generazione opzioni con AI
        try:
            options = self.generate_gpt_options(description)
        except Exception as e:
            print(f"❌ Errore durante la generazione delle opzioni: {e}")
            cursor.close()
            input("\nPremi Invio per continuare...")
            return

        if not options:
            print("⚠️ Nessuna opzione generata.")
            cursor.close()
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

        # 4. Modifica manuale
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
                        fail_input = input(f"Fallimento? (s/n) [{'s' if options[i]['fail'] else 'n'}]: ").lower()
                        options[i]['fail'] = True if fail_input == 's' else False
                except Exception as e:
                    print(f"⚠️ Errore nella modifica: {e}")

        # 5. Conferma
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
            cursor.close()
            return

        # 6. Inserimento nel DB
        try:
            cursor.execute("""
                INSERT INTO follower_objective_events (objective_id, description, type, response_options)
                VALUES (%s, %s, %s, %s)
            """, (
                selected_obj['id'],
                description,
                "IMPREVISTO",
                json.dumps(options)
            ))
            self.db.commit()
            print("✅ Imprevisto registrato con successo.")
        except Exception as e:
            self.db.rollback()
            print(f"❌ Errore durante l'inserimento nel DB: {e}")
            cursor.close()
            return

        # 7. Invio email al giocatore
        try:
            cursor = self.db.cursor(dictionary=True)

            # Recupera il follower
            cursor.execute("SELECT id, name, pg_id FROM followers WHERE id = %s", (selected_obj['follower_id'],))
            follower_data = cursor.fetchone()

            if follower_data:
                pg_id = follower_data['pg_id']
                follower_name = follower_data['name']

                # Recupera l'utente del PG
                cursor.execute("SELECT user_id, name FROM player_characters WHERE id = %s", (pg_id,))
                pg_data = cursor.fetchone()

                if pg_data:
                    user_id = pg_data['user_id']
                    pg_name = pg_data['name']

                    # Recupera la mail del giocatore
                    cursor.execute("SELECT mail FROM users WHERE id = %s", (user_id,))
                    email_data = cursor.fetchone()
                    email = email_data['mail'] if email_data else None

                    if email:
                        subject = f"Imprevisto per {follower_name} nell'obiettivo '{selected_obj['name']}'"

                        body = f"""Ciao {pg_name},

Il tuo seguace **{follower_name}** ha incontrato un imprevisto durante l'obiettivo **"{selected_obj['name']}"**:

➡️ {description}

Scegli una delle seguenti opzioni:\n
"""
                        for idx, opt in enumerate(options, 1):
                            body += f"{idx}. {opt['option']} (+{opt['extra_months']} mesi, +{opt['extra_cost']:.2f} MO)\n"

                        body += "\nRispondi a questa email scrivendo solo ad esempio: SCELTA: 2\n\nBuon gioco!"

                        send_email_notification(email, subject, body)
                        print("📩 Email inviata al giocatore.")
                    else:
                        print("⚠️ Impossibile trovare l'email del giocatore.")
                else:
                    print("⚠️ Nessun utente associato al PG.")
            else:
                print("⚠️ Nessun PG associato al follower.")
            
            cursor.close()
        except Exception as e:
            print(f"❌ Errore durante l'invio della mail: {e}")

        # 🔹 Pausa per permettere di leggere il risultato
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
                model="mistral",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            content = response.choices[0].message.content

            # Pulizia: rimuove blocchi markdown ```json ... ```
            cleaned = re.sub(r"```(?:json)?(.*?)```", r"\1", content, flags=re.DOTALL).strip()

            # Parsing JSON
            data = json.loads(cleaned)

            # Validazione: deve essere una lista con almeno una opzione valida
            if isinstance(data, list) and all("option" in o for o in data):
                return data
            else:
                print("⚠️ Formato JSON non valido.")
                return []

        except json.JSONDecodeError as e:
            print("❌ Errore nel parsing JSON:")
            print(content)
            return []

        except Exception as e:
            print(f"❌ Errore durante la generazione GPT: {e}")
            return []

    def register_objective_choice(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può registrare le scelte dei giocatori.")
            input("\nPremi Invio per continuare...")
            return

        print("\n--- Registra Scelta del Giocatore ---")

        try:
            cursor = self.db.cursor(dictionary=True)

            # 1. Recupera eventi non ancora gestiti e senza scelta
            cursor.execute("""
                SELECT id, description, response_options, player_choice, objective_id
                FROM follower_objective_events
                WHERE handled = FALSE AND player_choice IS NULL
            """)
            events = cursor.fetchall()

            if not events:
                print("✅ Nessun evento in attesa di risposta.")
                input("\nPremi Invio per continuare...")
                return

            print("\nEventi in attesa di risposta:")
            for i, ev in enumerate(events):
                print(f"{i+1}. {ev['description']}")

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

            # 2. Parsing delle opzioni
            options_raw = selected_event.get('response_options')

            # Se il campo è in bytes → convertilo
            if isinstance(options_raw, bytes):
                try:
                    options_raw = options_raw.decode("utf-8")
                except Exception as e:
                    print(f"❌ Errore decodifica response_options: {e}")
                    return

            # Se è stringa JSON → caricalo in lista
            if isinstance(options_raw, str):
                try:
                    options = json.loads(options_raw)
                except Exception as e:
                    print(f"❌ Errore parsing JSON response_options: {e}")
                    return
            else:
                options = options_raw

            if not isinstance(options, list) or not options:
                print("⚠️ Nessuna opzione valida disponibile per questo evento.")
                return

            # 3. Mostra opzioni
            print(f"\nDescrizione: {selected_event['description']}")
            print("Opzioni:")
            for idx, opt in enumerate(options, 1):
                desc = opt.get('option', '—')
                months = opt.get('extra_months', 0)
                cost = opt.get('extra_cost', 0)
                fail = " ❌ (Fallimento previsto)" if opt.get('fail') else ""
                print(f"  {idx}. {desc} (+{months} mesi, {cost:+.2f} MO){fail}")

            try:
                choice_idx = int(input("\nNumero dell'opzione scelta dal giocatore: "))
                if not (1 <= choice_idx <= len(options)):
                    print("❌ Scelta non valida.")
                    return
            except ValueError:
                print("❌ Input non valido.")
                return

            selected_choice = options[choice_idx - 1]

            # 4. Salva su DB (anche extra_cost e extra_months)
            extra_cost = selected_choice.get("extra_cost", 0)
            extra_months = selected_choice.get("extra_months", 0)

            update_query = """
                UPDATE follower_objective_events
                SET player_choice = %s,
                    handled = FALSE,
                    extra_cost = %s,
                    extra_months = %s
                WHERE id = %s
            """
            cursor.execute(update_query, (
                json.dumps(selected_choice, ensure_ascii=False),
                extra_cost,
                extra_months,
                selected_event['id']
            ))
            self.db.commit()

            print("✅ Scelta registrata con successo.")

        except Exception as e:
            print(f"❌ Errore: {e}")
        finally:
            try:
                cursor.close()
            except:
                pass
            input("\nPremi Invio per continuare...")

    def add_follower_objective(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può aggiungere obiettivi per i seguaci.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Aggiungi Obiettivo per Seguace ---")

        # Recupera ed elenca i seguaci (la funzione list_followers() nella versione MariaDB
        # ritorna dizionari con 'pg_name' come alias della tabella player_characters)
        followers = self.list_followers(show_all=True)
        if not followers:
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il Seguace a cui associare l'obiettivo:")
        for i, follower in enumerate(followers):
            pg_name = follower.get('pg_name', 'N/A')  # usa l'alias usato da list_followers()
            print(f"{i+1}. {follower.get('name', 'N/D')} (PG: {pg_name})")

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
        follower_id = selected_follower.get('id')
        pg_id = selected_follower.get('pg_id')

        # Recupera le banche del PG (usa self.db, come nella __init__)
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("SELECT * FROM banks WHERE pg_id = %s", (pg_id,))
            banks_for_pg = cursor.fetchall()
        except Exception as e:
            print(f"Errore durante il recupero delle banche: {e}")
            input("\nPremi Invio per continuare...")
            return

        if not banks_for_pg:
            print(f"Il PG di '{selected_follower.get('name')}' non ha conti bancari. Aggiungi un conto prima di creare un obiettivo con costi.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nSeleziona la Banca destinazione costo per '{selected_follower.get('name')}':")
        for i, bank in enumerate(banks_for_pg):
            saldo = bank.get('current_balance', 0.0)
            # current_balance potrebbe essere Decimal: mostrando con float-format va bene
            print(f"{i+1}. {bank.get('name', 'N/D')} (Saldo: {float(saldo):.2f})")

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

        # Inserimento nell'archivio obiettivi (start_date NULL, progress 0.0)
        try:
            insert_query = """
                INSERT INTO follower_objectives (
                    follower_id, name, estimated_months, total_cost, notes,
                    bank_id, status, start_date, progress_percentage
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                follower_id,
                objective_name,
                estimated_months,
                total_cost,
                notes,
                selected_bank_id,
                self.OBJECTIVE_STATUS['NON_INIZIATO'],
                None,   # start_date = NULL
                0.0     # progress_percentage
            )
            cursor.execute(insert_query, params)
            self.db.commit()
            print(f"✅ Obiettivo '{objective_name}' aggiunto con successo per {selected_follower.get('name')}.")
        except Exception as e:
            # stampa errore DB in modo leggibile
            print(f"❌ Si è verificato un errore durante l'inserimento dell'obiettivo: {e}")
        finally:
            try:
                cursor.close()
            except:
                pass
            input("\nPremi Invio per continuare...")

    def view_follower_events(self):
        self._clear_screen()
        print("--- Cronologia Imprevisti Obiettivi Seguaci ---")

        try:
            cursor = self.conn.cursor(dictionary=True)

            # Recupera i seguaci visibili
            if self.current_user['role'] == 'DM':
                cursor.execute("SELECT id, name FROM followers")
                followers = cursor.fetchall()
            else:
                # Trova i PG dell'utente
                cursor.execute("SELECT id FROM player_characters WHERE user_id = %s", (self.current_user['id'],))
                pg_ids = [row['id'] for row in cursor.fetchall()]
                if not pg_ids:
                    print("⚠️ Nessun seguace trovato.")
                    input("\nPremi Invio per continuare...")
                    return

                # Trova i seguaci dei PG
                placeholders = ','.join(['%s'] * len(pg_ids))
                query = f"SELECT id, name, pg_id FROM followers WHERE pg_id IN ({placeholders})"
                cursor.execute(query, tuple(pg_ids))
                followers = cursor.fetchall()

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

            try:
                index = int(choice) - 1
            except ValueError:
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return

            if not (0 <= index < len(followers)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return

            selected_follower = followers[index]
            follower_id = selected_follower['id']

            # Trova tutti gli obiettivi associati al seguace selezionato
            cursor.execute("SELECT id FROM follower_objectives WHERE follower_id = %s", (follower_id,))
            objective_ids = [row['id'] for row in cursor.fetchall()]

            if not objective_ids:
                print(f"⚠️ Nessun obiettivo trovato per il seguace '{selected_follower['name']}'.")
                input("\nPremi Invio per continuare...")
                return

            # Recupera eventi associati
            placeholders = ','.join(['%s'] * len(objective_ids))
            query = f"""
                SELECT objective_id, extra_months, extra_cost, description, handled, event_date
                FROM follower_objective_events
                WHERE objective_id IN ({placeholders})
                ORDER BY event_date DESC
            """
            cursor.execute(query, tuple(objective_ids))
            events = cursor.fetchall()

            print(f"\n--- Imprevisti per '{selected_follower['name']}' ---")
            if not events:
                print("Nessun imprevisto registrato.")
            else:
                for event in events:
                    stato = "Gestito" if event['handled'] else "❗ NON gestito"

                    if event.get('event_date'):
                        try:
                            event_date = datetime.strptime(str(event['event_date'])[:10], '%Y-%m-%d').date()
                            mystara_date = self._convert_date_to_ded_format(event_date)
                        except Exception:
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
            cursor = self.db.cursor(dictionary=True)

            # Costruzione query base con JOIN
            base_query = """
                SELECT 
                    fo.id AS objective_id,
                    fo.name AS objective_name,
                    fo.estimated_months,
                    fo.total_cost,
                    fo.status,
                    fo.start_date,
                    fo.progress_percentage,
                    fo.notes,
                    f.name AS follower_name,
                    pc.name AS pg_name,
                    b.name AS bank_name
                FROM follower_objectives fo
                JOIN followers f ON fo.follower_id = f.id
                JOIN player_characters pc ON f.pg_id = pc.id
                LEFT JOIN users u ON pc.user_id = u.id
                LEFT JOIN banks b ON fo.bank_id = b.id
            """

            params = []
            where_clause = ""

            # Se l'utente è un GIOCATORE, filtra i PG
            if self.current_user and self.current_user['role'] == 'GIOCATORE' and not show_all:
                cursor.execute("SELECT id FROM player_characters WHERE user_id = %s", (self.current_user['id'],))
                user_pg_ids = [row['id'] for row in cursor.fetchall()]

                if not user_pg_ids:
                    print("⚠️ Nessun personaggio trovato associato al tuo account.")
                    input("\nPremi Invio per continuare...")
                    return []

                cursor.execute("SELECT id FROM followers WHERE pg_id IN (" + ",".join(["%s"]*len(user_pg_ids)) + ")", tuple(user_pg_ids))
                user_follower_ids = [row['id'] for row in cursor.fetchall()]

                if not user_follower_ids:
                    print("⚠️ Nessun seguace trovato per i tuoi personaggi.")
                    input("\nPremi Invio per continuare...")
                    return []

                where_clause = " WHERE fo.follower_id IN (" + ",".join(["%s"] * len(user_follower_ids)) + ")"
                params.extend(user_follower_ids)

            # Query finale
            final_query = base_query + where_clause + " ORDER BY fo.follower_id ASC"
            cursor.execute(final_query, tuple(params))
            objectives = cursor.fetchall()

            if not objectives:
                print("Nessun obiettivo trovato.")
                input("\nPremi Invio per continuare...")
                return []

            # Raggruppa per PG
            grouped = {}
            for obj in objectives:
                pg_name = obj.get('pg_name', 'N/A')
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
                    follower_name = obj.get('follower_name', 'N/A')
                    status = self.OBJECTIVE_STATUS_REV.get(obj.get('status'), 'Sconosciuto')
                    estimated_months = obj.get('estimated_months', 0)
                    total_cost = obj.get('total_cost') or 0.0
                    bank_name = obj.get('bank_name', 'Nessuna')
                    start_date = obj.get('start_date') or 'N/A'
                    progress = obj.get('progress_percentage') or 0.0
                    notes = obj.get('notes', '')

                    rows[0].append(follower_name)
                    rows[1].append(obj.get('objective_name', ''))
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

        # Recupero obiettivi includendo follower_id e bank_id
        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("""
                SELECT fo.id AS objective_id,
                       fo.follower_id,
                       fo.name AS objective_name,
                       fo.estimated_months,
                       fo.total_cost,
                       fo.notes,
                       fo.bank_id,
                       fo.status,
                       fo.start_date,
                       fo.progress_percentage,
                       f.name AS follower_name,
                       pc.name AS pg_name
                FROM follower_objectives fo
                JOIN followers f ON fo.follower_id = f.id
                JOIN player_characters pc ON f.pg_id = pc.id
                ORDER BY fo.id
            """)
            objectives = cursor.fetchall()
        except Exception as e:
            print(f"Errore nel recupero obiettivi: {e}")
            input("\nPremi Invio per continuare...")
            return

        if not objectives:
            print("Nessun obiettivo trovato.")
            input("\nPremi Invio per continuare...")
            return

        print("\nSeleziona il numero dell'obiettivo da modificare:")
        for i, obj in enumerate(objectives):
            print(f"{i+1}. {obj['objective_name']} (Seguace: {obj['follower_name']})")

        try:
            obj_index = int(input("Numero: ")) - 1
            if not (0 <= obj_index < len(objectives)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_objective = objectives[obj_index]
            objective_id_to_update = selected_objective['objective_id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        print(f"\nModifica Obiettivo: {selected_objective['objective_name']} per {selected_objective['follower_name']}")

        update_data = {}
        # Nome
        new_name = input(f"Nuovo nome obiettivo (lascia vuoto per mantenere '{selected_objective['objective_name']}'): ").strip()
        if new_name:
            update_data['name'] = new_name

        # Mesi stimati
        val_str = input("Nuovi mesi stimati (lascia vuoto per non modificare): ").strip()
        if val_str:
            try:
                val = int(val_str)
                if val > 0:
                    update_data['estimated_months'] = val
            except ValueError:
                print("Mesi stimati non validi, ignorato.")

        # Costo totale
        val_str = input("Nuovo costo totale (lascia vuoto per non modificare): ").strip()
        if val_str:
            try:
                val = float(val_str)
                if val >= 0:
                    update_data['total_cost'] = val
            except ValueError:
                print("Costo totale non valido, ignorato.")

        # Note
        new_notes = input(f"Nuove note (lascia vuoto per mantenere '{selected_objective.get('notes', '')}'): ").strip()
        if new_notes:
            update_data['notes'] = new_notes

        # Stato
        print("\nStati disponibili:")
        for key, value in self.OBJECTIVE_STATUS.items():
            print(f"{value}. {key}")
        new_status_str = input(f"Nuovo stato ({self.OBJECTIVE_STATUS_REV[selected_objective['status']]}, lascia vuoto per non cambiare): ").strip()
        if new_status_str:
            try:
                val = int(new_status_str)
                if val in self.OBJECTIVE_STATUS.values():
                    update_data['status'] = val
                    if val == self.OBJECTIVE_STATUS['IN_CORSO'] and not selected_objective['start_date']:
                        update_data['start_date'] = self.game_date.strftime('%Y-%m-%d')
                    elif val != self.OBJECTIVE_STATUS['IN_CORSO'] and selected_objective['start_date']:
                        update_data['start_date'] = None
            except ValueError:
                print("Stato non valido, ignorato.")

        # Progresso
        val_str = input(f"Nuova percentuale di progresso (lascia vuoto per mantenere '{selected_objective['progress_percentage']:.1f}%'): ").strip()
        if val_str:
            try:
                val = float(val_str)
                if 0 <= val <= 100:
                    update_data['progress_percentage'] = val
            except ValueError:
                print("Percentuale progresso non valida, ignorato.")

        # Cambio seguace
        new_follower_id = selected_objective['follower_id']
        followers = self.list_followers(show_all=True)
        if followers:
            print("\nSeleziona il nuovo Seguace a cui associare l'obiettivo (0 per non cambiare):")
            for i, f in enumerate(followers):
                print(f"{i+1}. {f['name']} (PG: {f.get('pg_name', 'N/A')})")

            while True:
                choice_str = input("Numero del nuovo Seguace: ").strip()
                if not choice_str:
                    break
                try:
                    choice = int(choice_str) - 1
                    if choice == -1:
                        break
                    elif 0 <= choice < len(followers):
                        new_follower_id = followers[choice]['id']
                        break
                except ValueError:
                    print("Input non valido.")

            if new_follower_id != selected_objective['follower_id']:
                update_data['follower_id'] = new_follower_id

        # Cambio banca
        cursor.execute("SELECT pg_id FROM followers WHERE id = %s", (new_follower_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute("SELECT * FROM banks WHERE pg_id = %s", (row['pg_id'],))
            banks_for_pg = cursor.fetchall()
            if banks_for_pg:
                print("\nSeleziona la nuova banca di destinazione costo (0 per non cambiare):")
                for i, bank in enumerate(banks_for_pg):
                    print(f"{i+1}. {bank['name']} (Saldo: {bank.get('current_balance', 0.0):.2f})")

                new_bank_id = selected_objective['bank_id']
                choice_str = input("Numero della nuova banca: ").strip()
                if choice_str:
                    try:
                        choice = int(choice_str) - 1
                        if choice == -1:
                            pass
                        elif 0 <= choice < len(banks_for_pg):
                            new_bank_id = banks_for_pg[choice]['id']
                    except ValueError:
                        pass
                if new_bank_id != selected_objective['bank_id']:
                    update_data['bank_id'] = new_bank_id

        # Aggiornamento
        if update_data:
            try:
                set_clause = ", ".join([f"{key} = %s" for key in update_data.keys()])
                params = list(update_data.values()) + [objective_id_to_update]
                cursor.execute(f"UPDATE follower_objectives SET {set_clause} WHERE id = %s", tuple(params))
                self.db.commit()
                print(f"Obiettivo '{selected_objective['objective_name']}' modificato con successo.")
            except Exception as e:
                print(f"Errore nell'aggiornamento: {e}")
        else:
            print("Nessuna modifica applicata.")

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
            follower_name = obj.get('follower_name', 'N/A')
            print(f"{i+1}. {obj.get('objective_name', '')} (Seguace: {follower_name})")

        try:
            obj_index = int(input("Numero: ")) - 1
            if not (0 <= obj_index < len(objectives)):
                print("Scelta non valida.")
                input("\nPremi Invio per continuare...")
                return
            selected_objective = objectives[obj_index]
            objective_id_to_remove = selected_objective['objective_id']
        except ValueError:
            print("Input non valido. Inserisci un numero.")
            input("\nPremi Invio per continuare...")
            return

        confirm = input(
            f"Sei sicuro di voler rimuovere l'obiettivo '{selected_objective['objective_name']}'? "
            "L'eliminazione è definitiva. (s/N): "
        ).strip().lower()

        if confirm == 's':
            try:
                cursor = self.db.cursor()
                cursor.execute("DELETE FROM follower_objectives WHERE id = %s", (objective_id_to_remove,))
                self.db.commit()
                if cursor.rowcount > 0:
                    print(f"Obiettivo '{selected_objective['objective_name']}' rimosso con successo.")
                else:
                    print("⚠️ Nessun obiettivo rimosso: potrebbe non esistere più.")
            except Exception as e:
                print(f"❌ Si è verificato un errore durante la rimozione: {e}")
        else:
            print("Rimozione annullata.")

        input("\nPremi Invio per continuare...")

    def _truncate(self, text, length):
        """Taglia il testo se troppo lungo e aggiunge '...'"""
        text = str(text) if text is not None else ''
        return text if len(text) <= length else text[:length-3] + '...'

    def start_follower_objective(self):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può iniziare obiettivi dei seguaci.")
            input("\nPremi Invio per continuare...")
            return

        self._clear_screen()
        print("--- Inizia Obiettivo Seguace ---")

        try:
            cursor = self.db.cursor(dictionary=True)
            cursor.execute("""
                SELECT fo.id, fo.name AS objective_name, fo.estimated_months, fo.total_cost, fo.notes,
                       f.name AS follower_name, pc.name AS pg_name, b.name AS bank_name
                FROM follower_objectives fo
                LEFT JOIN followers f ON fo.follower_id = f.id
                LEFT JOIN player_characters pc ON f.pg_id = pc.id
                LEFT JOIN banks b ON fo.bank_id = b.id
                WHERE fo.status = %s
                ORDER BY f.name
            """, (self.OBJECTIVE_STATUS['NON_INIZIATO'],))
            non_started_objectives = cursor.fetchall()

            if not non_started_objectives:
                print("Nessun obiettivo con stato 'NON_INIZIATO' trovato.")
                input("\nPremi Invio per continuare...")
                return

            print("\n📋 Obiettivi 'NON_INIZIATO' disponibili:\n")
            header = f"{'N.':<4} {'Seguace':<20} {'Obiettivo':<25} {'Mesi':<6} {'Costo':<10} {'Banca':<20} {'Note'}"
            print(header)
            print("-" * len(header))

            for i, obj in enumerate(non_started_objectives, start=1):
                follower_name = self._truncate(obj.get('follower_name', 'N/A'), 20)
                objective_name = self._truncate(obj['objective_name'], 25)
                bank_name = self._truncate(obj.get('bank_name', 'N/A'), 20)
                notes = self._truncate(obj.get('notes', ''), 30)

                print(f"{i:<4} {follower_name:<20} {objective_name:<25} "
                      f"{obj['estimated_months']:<6} {obj['total_cost']:<10.2f} {bank_name:<20} {notes}")

            print("-" * len(header))

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

            # Aggiorna stato e data di inizio
            try:
                cursor.execute("""
                    UPDATE follower_objectives
                    SET status = %s,
                        start_date = %s,
                        progress_percentage = 0.0
                    WHERE id = %s
                """, (
                    self.OBJECTIVE_STATUS['IN_CORSO'],
                    self.game_date.strftime('%Y-%m-%d'),
                    selected_objective['id']
                ))
                self.db.commit()
                if cursor.rowcount > 0:
                    print(f"\n✅ Obiettivo '{selected_objective['objective_name']}' iniziato con successo. Stato: IN_CORSO.")
                else:
                    print("\n⚠️ Nessun obiettivo aggiornato.")
            except Exception as e:
                print(f"\n❌ Errore nell'avvio dell'obiettivo: {e}")

        except Exception as e:
            print(f"\n❌ Si è verificato un errore: {e}")

        input("\nPremi Invio per continuare...")

    def _apply_daily_events(self):
        print("Applicazione eventi giornalieri...")

        try:
            cursor = self.db.cursor(dictionary=True)

            # Attività economiche giornaliere
            cursor.execute("""
                SELECT ea.*, b.name AS bank_name, b.current_balance
                FROM economic_activities ea
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
            """)
            activities = cursor.fetchall()

            for activity in activities:
                if str(activity.get('frequency', '')).lower() != 'giornaliera':
                    continue

                income = activity.get('income', 0.0) or 0.0
                bank_id = activity.get('destination_bank_id')
                bank_name = activity.get('bank_name', 'Sconosciuta')
                current_balance = activity.get('current_balance', 0.0) or 0.0

                if not bank_id or bank_name == 'Sconosciuta':
                    print(f"  Attività '{activity.get('description', 'Sconosciuta')}' senza banca associata. Guadagno non applicato.")
                    continue

                new_balance = current_balance + income

                cursor.execute("""
                    UPDATE banks SET current_balance = %s WHERE id = %s
                """, (new_balance, bank_id))
                self.db.commit()

                print(f"  Guadagno giornaliero di {income:.2f} applicato alla banca '{bank_name}' per l'attività '{activity.get('description', 'Sconosciuta')}'")

            # Spese fisse giornaliere
            cursor.execute("""
                SELECT fe.*, b.name AS bank_name, b.current_balance
                FROM fixed_expenses fe
                LEFT JOIN banks b ON fe.source_bank_id = b.id
            """)
            fixed_expenses = cursor.fetchall()

            for expense in fixed_expenses:
                if str(expense.get('frequency', '')).lower() != 'giornaliera':
                    continue

                amount = expense.get('amount', 0.0) or 0.0
                bank_id = expense.get('source_bank_id')
                bank_name = expense.get('bank_name', 'Sconosciuta')
                current_balance = expense.get('current_balance', 0.0) or 0.0

                if not bank_id or bank_name == 'Sconosciuta':
                    print(f"  Spesa '{expense.get('description', 'Sconosciuta')}' senza banca associata. Non applicata.")
                    continue

                if current_balance >= amount:
                    new_balance = current_balance - amount
                    cursor.execute("""
                        UPDATE banks SET current_balance = %s WHERE id = %s
                    """, (new_balance, bank_id))
                    self.db.commit()

                    print(f"  Spesa giornaliera '{expense.get('description', 'Sconosciuta')}' di {amount:.2f} prelevata da '{bank_name}'")
                else:
                    print(f"  ATTENZIONE: saldo insufficiente ({current_balance:.2f}) per la spesa '{expense.get('description', 'Sconosciuta')}'")

            # Obiettivi dei seguaci – applica 1/30 di mese
            self._apply_objective_progress(frazione_mensile=1/30.0, etichetta='giornaliero')
            self.apply_unhandled_objective_events()

        except Exception as e:
            print(f"❌ Errore nell'applicazione degli eventi giornalieri: {e}")

        finally:
            try:
                cursor.close()
            except:
                pass

    def _apply_weekly_events(self):
        print("Applicazione eventi settimanali...")

        try:
            cursor = self.db.cursor(dictionary=True)

            # Attività economiche settimanali
            cursor.execute("""
                SELECT ea.*, b.name AS bank_name, b.current_balance
                FROM economic_activities ea
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
            """)
            activities = cursor.fetchall()

            for activity in activities:
                if str(activity.get('frequency', '')).lower() != 'settimanale':
                    continue

                bank_id = activity.get('destination_bank_id')
                income = activity.get('income', 0.0) or 0.0
                bank_name = activity.get('bank_name', 'Sconosciuta')
                current_balance = activity.get('current_balance', 0.0) or 0.0

                if not bank_id or bank_name == 'Sconosciuta':
                    print(f"  Attività '{activity.get('description', 'Sconosciuta')}' senza banca associata. Guadagno non applicato.")
                    continue

                new_balance = current_balance + income

                cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, bank_id))
                self.db.commit()

                print(f"  Guadagno settimanale di {income:.2f} applicato alla banca '{bank_name}' per l'attività '{activity.get('description', 'Sconosciuta')}'")

            # Spese fisse settimanali
            cursor.execute("""
                SELECT fe.*, b.name AS bank_name, b.current_balance
                FROM fixed_expenses fe
                LEFT JOIN banks b ON fe.source_bank_id = b.id
            """)
            expenses = cursor.fetchall()

            for expense in expenses:
                if str(expense.get('frequency', '')).lower() != 'settimanale':
                    continue

                bank_id = expense.get('source_bank_id')
                amount = expense.get('amount', 0.0) or 0.0
                bank_name = expense.get('bank_name', 'Sconosciuta')
                current_balance = expense.get('current_balance', 0.0) or 0.0

                if not bank_id or bank_name == 'Sconosciuta':
                    print(f"  Spesa '{expense.get('description', 'Sconosciuta')}' senza banca associata. Spesa non applicata.")
                    continue

                if current_balance >= amount:
                    new_balance = current_balance - amount
                    cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, bank_id))
                    self.db.commit()

                    print(f"  Spesa settimanale di {amount:.2f} applicata alla banca '{bank_name}' per '{expense.get('description', 'Sconosciuta')}'")
                else:
                    print(f"  ATTENZIONE: saldo insufficiente ({current_balance:.2f}) per la spesa '{expense.get('description', 'Sconosciuta')}'")

            # Obiettivi dei seguaci – applica 1/4 di mese
            self._apply_objective_progress(frazione_mensile=1/4.0, etichetta='settimanale')
            self.apply_unhandled_objective_events()

            print("Eventi settimanali completati.")

        except Exception as e:
            print(f"❌ Errore nell'applicazione degli eventi settimanali: {e}")

        finally:
            try:
                cursor.close()
            except:
                pass

    def _apply_monthly_events(self):
        print("Applicazione eventi mensili...")

        try:
            cursor = self.db.cursor(dictionary=True)

            # Spese fisse mensili
            cursor.execute("""
                SELECT fe.*, b.name AS bank_name, b.current_balance
                FROM fixed_expenses fe
                LEFT JOIN banks b ON fe.source_bank_id = b.id
            """)
            fixed_expenses = cursor.fetchall()

            for expense in fixed_expenses:
                if str(expense.get('frequency', '')).lower() != 'mensile':
                    continue

                bank_id = expense.get('source_bank_id')
                amount = float(expense.get('amount', 0.0) or 0.0)
                bank_name = expense.get('bank_name', 'Sconosciuta')
                current_balance = float(expense.get('current_balance', 0.0) or 0.0)

                if bank_id:
                    if current_balance >= amount:
                        new_balance = current_balance - amount
                        cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, bank_id))
                        self.db.commit()
                        print(f"  Spesa mensile '{expense.get('description', 'Sconosciuta')}' di {amount:.2f} prelevata da '{bank_name}'")
                    else:
                        print(f"  ⚠️ Fondi insufficienti per spesa '{expense.get('description', 'Sconosciuta')}'")
                else:
                    print(f"  ⚠️ Spesa '{expense.get('description', 'Sconosciuta')}' senza banca associata")

            # Guadagni mensili attività economiche
            cursor.execute("""
                SELECT ea.*, b.name AS bank_name, b.current_balance
                FROM economic_activities ea
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
            """)
            activities = cursor.fetchall()

            for activity in activities:
                if str(activity.get('frequency', '')).lower() != 'mensile':
                    continue

                bank_id = activity.get('destination_bank_id')
                income = float(activity.get('income', 0.0) or 0.0)
                bank_name = activity.get('bank_name', 'Sconosciuta')
                current_balance = float(activity.get('current_balance', 0.0) or 0.0)

                if not bank_id:
                    print(f"  Attività '{activity.get('description', 'Sconosciuta')}' senza banca. Guadagno non applicato.")
                    continue

                new_balance = current_balance + income
                cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, bank_id))
                self.db.commit()
                print(f"  Guadagno mensile di {income:.2f} applicato a '{bank_name}'")

            # Obiettivi dei seguaci
            cursor.execute("""
                SELECT fo.*, b.name AS bank_name, b.current_balance
                FROM follower_objectives fo
                LEFT JOIN banks b ON fo.bank_id = b.id
                WHERE fo.status = %s
            """, (self.OBJECTIVE_STATUS['IN_CORSO'],))
            objectives = cursor.fetchall()

            for objective in objectives:
                objective_id = objective.get('id')
                name = objective.get('name', 'Sconosciuto')
                bank_id = objective.get('bank_id')
                estimated_months = int(objective.get('estimated_months') or 0)
                total_cost = float(objective.get('total_cost', 0.0) or 0.0)
                progress_percentage = float(objective.get('progress_percentage', 0.0) or 0.0)

                # Qui la correzione: se base_estimated_months è NULL, uso estimated_months
                base_months = int(objective.get('base_estimated_months') or estimated_months or 0)
                base_cost = float(objective.get('base_total_cost', total_cost) or 0.0)
                current_balance = float(objective.get('current_balance', 0.0) or 0.0)

                if not bank_id:
                    print(f"  Obiettivo '{name}' senza banca. Costo non applicato.")
                    continue

                if estimated_months <= 0 or base_months <= 0:
                    print(f"  Obiettivo '{name}' ha durata non valida.")
                    continue

                cost_per_month = total_cost / estimated_months
                progress_per_month = 100.0 / base_months

                if current_balance >= cost_per_month:
                    new_balance = current_balance - cost_per_month
                    cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, bank_id))
                    self.db.commit()

                    new_progress = min(progress_percentage + progress_per_month, 100.0)
                    update_data = {"progress_percentage": new_progress}

                    if new_progress >= 100.0:
                        update_data['status'] = self.OBJECTIVE_STATUS['COMPLETATO']
                        print(f"  ✅ Obiettivo '{name}' COMPLETATO!")

                    # Aggiorna l'obiettivo
                    set_clause = ", ".join([f"{key} = %s" for key in update_data])
                    params = list(update_data.values()) + [objective_id]
                    cursor.execute(f"UPDATE follower_objectives SET {set_clause} WHERE id = %s", params)
                    self.db.commit()

                    print(f"  📈 Obiettivo '{name}' avanzato al {new_progress:.1f}%")
                else:
                    print(f"  ⚠️ Saldo insufficiente per '{name}' ({current_balance:.2f} < {cost_per_month:.2f})")

        except Exception as e:
            print(f"❌ Errore nell'applicazione degli eventi mensili per obiettivi: {e}")

        finally:
            try:
                cursor.close()
            except:
                pass

    def _apply_objective_progress(self, frazione_mensile, etichetta='periodico'):
        try:
            print(f"📊 Avanzamento obiettivi ({etichetta})...")

            cursor = self.db.cursor(dictionary=True)

            # Recupera obiettivi IN_CORSO con info banca
            cursor.execute("""
                SELECT fo.*, b.name AS bank_name, b.current_balance
                FROM follower_objectives fo
                LEFT JOIN banks b ON fo.bank_id = b.id
                WHERE fo.status = %s
            """, (self.OBJECTIVE_STATUS['IN_CORSO'],))
            objectives = cursor.fetchall()

            for objective in objectives:
                objective_id = objective.get('id')
                name = objective.get('name', 'Sconosciuto')
                bank_id = objective.get('bank_id')

                # Conversione sicura Decimal → int/float
                estimated_months = int(objective.get('estimated_months') or 0)
                total_cost = float(objective.get('total_cost') or 0.0)
                progress_percentage = float(objective.get('progress_percentage') or 0.0)

                base_months_val = objective.get('base_estimated_months')
                base_months = int(base_months_val) if base_months_val not in (None, 0) else estimated_months

                base_cost_val = objective.get('base_total_cost')
                base_cost = float(base_cost_val) if base_cost_val not in (None, 0) else total_cost

                current_balance = float(objective.get('current_balance') or 0.0)

                if not bank_id:
                    print(f"  Obiettivo '{name}' senza banca. Costo non applicato.")
                    continue
                if estimated_months <= 0 or base_months <= 0:
                    print(f"  Obiettivo '{name}' ha durata non valida.")
                    continue

                # Calcoli economici e di progresso
                cost_per_month = total_cost / estimated_months
                progress_per_month = 100.0 / base_months

                cost = cost_per_month * float(frazione_mensile)
                progress = progress_per_month * float(frazione_mensile)

                if current_balance >= cost:
                    # Aggiorna saldo banca
                    new_balance = current_balance - cost
                    cursor.execute(
                        "UPDATE banks SET current_balance = %s WHERE id = %s",
                        (new_balance, bank_id)
                    )
                    self.db.commit()

                    # Aggiorna progresso obiettivo
                    new_progress = min(progress_percentage + progress, 100.0)
                    update_data = {"progress_percentage": new_progress}

                    if new_progress >= 100.0:
                        update_data['status'] = self.OBJECTIVE_STATUS['COMPLETATO']
                        print(f"  ✅ Obiettivo '{name}' COMPLETATO!")

                    set_clause = ", ".join([f"{key} = %s" for key in update_data])
                    params = list(update_data.values()) + [objective_id]
                    cursor.execute(
                        f"UPDATE follower_objectives SET {set_clause} WHERE id = %s",
                        params
                    )
                    self.db.commit()

                    print(f"  📈 Obiettivo '{name}' avanzato al {new_progress:.1f}% ({etichetta})")
                else:
                    print(f"  ⚠️ Saldo insufficiente per '{name}' ({current_balance:.2f} < {cost:.2f})")

        except Exception as e:
            print(f"⚠️ Errore nell'avanzamento obiettivi ({etichetta}): {e}")

        finally:
            try:
                cursor.close()
            except:
                pass

    def apply_unhandled_objective_events(self):
        print("🔄 Applicazione automatica delle scelte degli imprevisti...")

        try:
            cursor = self.db.cursor(dictionary=True)

            # Recupera eventi non gestiti
            cursor.execute("""
                SELECT id, objective_id, player_choice, response_options, handled
                FROM follower_objective_events
                WHERE handled = FALSE
            """)
            unhandled_events = cursor.fetchall()

            if not unhandled_events:
                print("✅ Nessun imprevisto da gestire.")
                return

            for event in unhandled_events:
                if not event.get('player_choice') or not event.get('response_options'):
                    print(f"⚠️ Evento {event['id']} senza scelta del giocatore o opzioni.")
                    continue

                # Decodifica player_choice
                try:
                    selected_raw = event.get('player_choice')
                    if isinstance(selected_raw, bytes):
                        selected_raw = selected_raw.decode('utf-8')
                    selected = json.loads(selected_raw) if isinstance(selected_raw, str) else selected_raw
                except Exception as e:
                    print(f"⚠️ Impossibile decodificare player_choice per evento {event['id']}: {e}")
                    continue

                if not selected or not isinstance(selected, dict) or 'option' not in selected:
                    print(f"⚠️ player_choice malformato o incompleto per evento {event['id']}")
                    continue

                objective_id = event['objective_id']

                # Recupera nome e dati attuali dell'obiettivo
                cursor.execute("""
                    SELECT name, estimated_months, total_cost
                    FROM follower_objectives
                    WHERE id = %s
                """, (objective_id,))
                objective = cursor.fetchone()

                if not objective:
                    print(f"⚠️ Obiettivo {objective_id} non trovato.")
                    continue

                objective_name = objective.get('name', 'Sconosciuto')

                # Conversione sicura Decimal → int/float
                est_months = int(objective['estimated_months']) if objective['estimated_months'] is not None else 0
                tot_cost = float(objective['total_cost']) if objective['total_cost'] is not None else 0.0

                if selected.get("fail"):
                    cursor.execute("""
                        UPDATE follower_objectives
                        SET status = %s
                        WHERE id = %s
                    """, (self.OBJECTIVE_STATUS["FALLITO"], objective_id))
                    self.db.commit()
                    print(f"❌ Obiettivo '{objective_name}' segnato come fallito.")
                else:
                    add_months = int(selected.get("extra_months", 0))
                    add_cost = float(selected.get("extra_cost", 0.0))

                    updated_fields = {
                        "estimated_months": est_months + add_months,
                        "total_cost": tot_cost + add_cost
                    }

                    # Aggiorna obiettivo
                    cursor.execute("""
                        UPDATE follower_objectives
                        SET estimated_months = %s, total_cost = %s
                        WHERE id = %s
                    """, (updated_fields["estimated_months"], updated_fields["total_cost"], objective_id))
                    self.db.commit()

                    print(f"⚠️ Imprevisto su obiettivo '{objective_name}': +{add_months} mesi, +{add_cost:.2f} PO")

                    # Aggiorna evento con i valori extra e handled = TRUE
                    cursor.execute("""
                        UPDATE follower_objective_events
                        SET handled = TRUE, extra_cost = %s, extra_months = %s
                        WHERE id = %s
                    """, (add_cost, add_months, event['id']))
                    self.db.commit()

            print("✅ Tutti gli imprevisti gestiti.")

        except Exception as e:
            print(f"❌ Errore durante l'applicazione delle scelte: {e}")

        finally:
            try:
                cursor.close()
            except:
                pass

    def advance_days(self, days=1):
        print(f"\n⏳ Avanzamento di {days} giorno/i in corso...")

        try:
            for _ in range(days):
                # Aggiorna data di gioco
                self.game_date += timedelta(days=1)

                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        UPDATE game_state
                        SET game_date = %s
                        WHERE id = 1
                    """, (self.game_date.strftime('%Y-%m-%d'),))
                    self.db.commit()
                except Exception as db_err:
                    print(f"⚠️ Errore nell'aggiornamento della data di gioco su DB: {db_err}")
                    continue

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

                # Eventi settimanali
                self._apply_weekly_events()

                # Eventuali imprevisti gestiti
                self.apply_unhandled_objective_events()

            # Salva la nuova data di gioco su MariaDB
            try:
                cursor = self.db.cursor()
                cursor.execute("""
                    UPDATE game_state
                    SET game_date = %s
                    WHERE id = 1
                """, (self.game_date.strftime('%Y-%m-%d'),))
                self.db.commit()
            except Exception as db_err:
                print(f"⚠️ Errore nell'aggiornamento della data di gioco su DB: {db_err}")
            finally:
                try:
                    cursor.close()
                except:
                    pass

            # Stampa data aggiornata
            print(f"✅ Data aggiornata: {self._convert_date_to_ded_format(self.game_date)}")

        except Exception as e:
            print(f"❌ Errore durante l'avanzamento della settimana: {e}")

        input("\nPremi Invio per continuare...")

    def advance_months(self, months=1):
        print(f"\n⏳ Avanzamento di {months} mese/i in corso...")

        try:
            from datetime import date

            # Normalizzazione della data
            if isinstance(self.game_date, (datetime, date)):
                game_date = datetime.combine(self.game_date, datetime.min.time())
            else:
                game_date = datetime.strptime(str(self.game_date), "%Y-%m-%d")

            # Aggiungi i mesi
            new_date = game_date + relativedelta(months=months)
            self.game_date = new_date  # Manteniamo un datetime

            # Aggiorna la data di gioco in MariaDB
            try:
                cursor = self.db.cursor()
                cursor.execute("""
                    UPDATE game_state
                    SET game_date = %s
                    WHERE id = 1
                """, (self.game_date.strftime('%Y-%m-%d'),))
                self.db.commit()
            except Exception as db_err:
                print(f"⚠️ Errore nell'aggiornamento della data di gioco su DB: {db_err}")
            finally:
                try:
                    cursor.close()
                except:
                    pass

            print(f"✅ Data aggiornata: {self._convert_date_to_ded_format(self.game_date)}")

            # Applica eventi mensili
            self._apply_monthly_events()

            # Applica eventuali imprevisti
            self.apply_unhandled_objective_events()

            print("✅ Eventi mensili e imprevisti applicati.")

        except Exception as e:
            print(f"❌ Errore durante l'avanzamento del mese: {e}")

        input("\nPremi Invio per continuare...")

    def show_current_date(self):
        """Mostra la data di gioco corrente nel formato Mystara (usa la data in memoria se disponibile)."""
        self._clear_screen()
        print("--- Data di Gioco Attuale ---")

        try:
            # Se non abbiamo una data in memoria, prova a recuperarla dal DB
            if not getattr(self, "game_date", None):
                if self.db:
                    cursor = self.db.cursor(dictionary=True)
                    cursor.execute("SELECT game_date FROM game_state WHERE id = 1")
                    row = cursor.fetchone()
                    if row and row.get("game_date"):
                        self.game_date = row["game_date"]

            if self.game_date:
                print(f"📅 {self._convert_date_to_ded_format(self.game_date)}")
            else:
                print("⚠️ Data di gioco non impostata.")
        except Exception as e:
            print(f"❌ Errore nel recupero della data di gioco: {e}")

        input("\nPremi Invio per continuare...")

    def set_game_date_manually(self):
        try:
            print("\nInserisci la nuova data di gioco.")
            print("Formato richiesto: YYYY-MM-DD (es. 2011-05-12)")
            new_date_str = input("Nuova data: ").strip()

            # Convalida formato
            new_date = datetime.strptime(new_date_str, "%Y-%m-%d")

            # Salva su DB
            cursor = self.db.cursor()
            cursor.execute("UPDATE game_state SET game_date = %s WHERE id = 1", (new_date_str,))
            self.db.commit()
            cursor.close()

            # Aggiorna anche in memoria
            self.game_date = new_date

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
            if not self.db:
                print("❌ Connessione al database non disponibile.")
                input("\nPremi Invio per continuare...")
                return

            cursor = self.db.cursor(dictionary=True)
            query = """
                SELECT e.id, e.objective_id, e.description, e.extra_months, e.extra_cost, 
                       e.response_options, e.player_choice, e.event_date, 
                       o.name AS objective_name
                FROM follower_objective_events e
                LEFT JOIN follower_objectives o ON e.objective_id = o.id
                WHERE e.handled = FALSE
            """
            cursor.execute(query)
            events = cursor.fetchall()
            cursor.close()

            if not events:
                print("✅ Nessun imprevisto in attesa di scelta.")
            else:
                for i, evt in enumerate(events, 1):
                    objective_name = evt.get('objective_name', 'Obiettivo sconosciuto')

                    print(f"{i}. Imprevisto: {evt['description']}")
                    print(f"   Obiettivo: {objective_name}")

                    # Gestione sicura dei campi che possono essere NULL
                    extra_months = evt.get('extra_months') if evt.get('extra_months') is not None else 0
                    extra_cost = evt.get('extra_cost') if evt.get('extra_cost') is not None else 0.0

                    print(f"   Mesi aggiuntivi: {extra_months}  |  Costo aggiuntivo: {extra_cost:.2f} MO")
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
            # Garantisce che sia una stringa formattata per MariaDB
            formatted_date = new_date.strftime('%Y-%m-%d') if isinstance(new_date, datetime) else str(new_date)

            cursor = self.conn.cursor()
            query = "UPDATE game_state SET game_date = %s WHERE id = 1"
            cursor.execute(query, (formatted_date,))
            self.conn.commit()
            cursor.close()

            print("📅 Data aggiornata nel database.")
        except Exception as e:
            print(f"⚠️ Errore nell'aggiornamento della data di gioco: {e}")

    def advance_time(self, days=0, weeks=0, months=0):
        if not self.current_user or self.current_user['role'] != 'DM':
            print("Solo un DM può avanzare il tempo.")
            input("\nPremi Invio per continuare...")
            return

        original_date = self.game_date

        # Calcolo giorni totali da avanzare
        total_days_to_advance = days + (weeks * 7) + (months * 30)  # Mesi stimati in 30 giorni

        try:
            for i in range(total_days_to_advance):
                self.game_date += timedelta(days=1)
                self._apply_daily_events()

                # Eventi settimanali ogni 7 giorni
                if (i + 1) % 7 == 0:
                    self._apply_weekly_events()

                # Eventi mensili: cambio mese/anno o primo giorno del mese
                if self.game_date.day == 1 and (self.game_date.month != original_date.month or self.game_date.year != original_date.year):
                    self._apply_monthly_events()
                elif self.game_date.day == 1 and i == 0 and months > 0:
                    # Caso limite: inizio direttamente in un nuovo mese
                    self._apply_monthly_events()

            # Aggiorna la data nel DB MariaDB
            self._update_game_state_date(self.game_date)

            print(f"\nData di gioco avanzata da {self._convert_date_to_ded_format(original_date)} a {self._convert_date_to_ded_format(self.game_date)}.")

        except Exception as e:
            print(f"❌ Errore durante l'avanzamento del tempo: {e}")

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

            choice = input("Scegli un'opzione: ").strip()

            if choice == '1':
                self.advance_days(1)  # Usa versione MariaDB
            elif choice == '2':
                self.advance_weeks(1)  # Usa versione MariaDB
            elif choice == '3':
                self.advance_months(1)  # Usa versione MariaDB
            elif choice == '4':
                self.show_current_date()  # Usa versione MariaDB
            elif choice == '5':
                self.add_objective_event()  # Deve già essere adattata a MariaDB
            elif choice == '6':
                self.register_objective_choice()  # Usa versione MariaDB
            elif choice == '7':
                self.set_game_date_manually()  # Usa versione MariaDB
            elif choice == '8':
                self.show_pending_events()  # Usa versione MariaDB
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
            cursor = self.db.cursor(dictionary=True)

            # Query per ottenere tutti i dati necessari
            cursor.execute("""
                SELECT pc.id, pc.name, u.username
                FROM player_characters pc
                LEFT JOIN users u ON pc.user_id = u.id
            """)
            pg_data = cursor.fetchall()

            cursor.execute("SELECT id, pg_id, name, current_balance FROM banks")
            bank_data = cursor.fetchall()

            cursor.execute("""
                SELECT id, pg_id, description, income, frequency, destination_bank_id
                FROM economic_activities
            """)
            activity_data = cursor.fetchall()

            cursor.execute("""
                SELECT id, pg_id, description, amount, frequency, source_bank_id
                FROM fixed_expenses
            """)
            expense_data = cursor.fetchall()

            cursor.execute("SELECT id, pg_id, name, description FROM followers")
            follower_data = cursor.fetchall()

            cursor.execute("""
                SELECT fo.*, f.name AS follower_name, b.name AS bank_name
                FROM follower_objectives fo
                LEFT JOIN followers f ON fo.follower_id = f.id
                LEFT JOIN banks b ON fo.bank_id = b.id
            """)
            objective_data = cursor.fetchall()

            export_list = []
            for pg in pg_data:
                pg_id = pg['id']
                pg_name = pg['name']
                pg_user = pg['username'] if pg['username'] else 'N/A'

                pg_banks = [b for b in bank_data if b['pg_id'] == pg_id]
                pg_activities = [a for a in activity_data if a['pg_id'] == pg_id]
                pg_expenses = [e for e in expense_data if e['pg_id'] == pg_id]
                pg_followers = [f for f in follower_data if f['pg_id'] == pg_id]

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
                        "Stato Obiettivo": "",
                        "Progresso Obiettivo": ""
                    })

                # Banche
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

                # Attività economiche
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

                # Spese fisse
                for expense in pg_expenses:
                    bank_name = next((b['name'] for b in bank_data if b['id'] == expense['source_bank_id']), 'N/A')
                    bank_balance = next((b['current_balance'] for b in bank_data if b['id'] == expense['source_bank_id']), 0.0)
                    export_list.append({
                        "Nome PG": pg_name,
                        "Associato a Utente": pg_user,
                        "Tipo Voce": "Spesa Fissa",
                        "Nome Voce": expense['description'],
                        "Descrizione": expense['description'],
                        "Importo": -expense['amount'],
                        "Frequenza": expense['frequency'],
                        "Banca Associata": bank_name,
                        "Saldo Banca": bank_balance,
                        "Stato Obiettivo": "",
                        "Progresso Obiettivo": ""
                    })

                # Seguaci e obiettivi
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
                    else:
                        for obj in follower_objectives:
                            bank_name = obj['bank_name'] if obj['bank_name'] else 'N/A'
                            bank_balance = next((b['current_balance'] for b in bank_data if b['id'] == obj['bank_id']), 0.0)
                            export_list.append({
                                "Nome PG": pg_name,
                                "Associato a Utente": pg_user,
                                "Tipo Voce": "Obiettivo Seguace",
                                "Nome Voce": obj['name'],
                                "Descrizione": obj['notes'],
                                "Importo": obj['total_cost'],
                                "Frequenza": f"{obj['estimated_months']} mesi",
                                "Banca Associata": bank_name,
                                "Saldo Banca": bank_balance,
                                "Stato Obiettivo": self.OBJECTIVE_STATUS_REV.get(obj['status'], 'Sconosciuto'),
                                "Progresso Obiettivo": f"{obj['progress_percentage']:.1f}%"
                            })

            cursor.close()

            if not export_list:
                print("Nessun dato da esportare.")
                input("\nPremi Invio per continuare...")
                return

            df = pd.DataFrame(export_list)
            df = df[[
                "Nome PG", "Associato a Utente", "Tipo Voce", "Nome Voce",
                "Descrizione", "Importo", "Frequenza", "Banca Associata", "Saldo Banca",
                "Stato Obiettivo", "Progresso Obiettivo"
            ]]

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"FondiPG_e_Obiettivi_{timestamp}.xlsx"
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
            'bank_transactions',
            'followers',
            'economic_activities',
            'fixed_expenses',
            'game_state',
            'follower_objectives',
            'follower_objective_events'
        ]

        backup_successful = True

        # Funzione di conversione per JSON
        def convert_for_json(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, (date, datetime)):
                return obj.isoformat()
            elif isinstance(obj, bytes):
                try:
                    return obj.decode("utf-8")
                except:
                    return obj.hex()  # come fallback
            return obj

        try:
            cursor = self.db.cursor(dictionary=True)

            for table_name in tables_to_backup:
                try:
                    cursor.execute(f"SELECT * FROM {table_name}")
                    data = cursor.fetchall()

                    # Conversione sicura di ogni valore
                    converted_data = []
                    for row in data:
                        converted_data.append({k: convert_for_json(v) for k, v in row.items()})

                    filename = os.path.join(backup_dir, f"{table_name}_backup_{timestamp}.json")
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(converted_data, f, ensure_ascii=False, indent=4)

                    print(f"  Backup della tabella '{table_name}' salvato in '{filename}'")

                except Exception as e:
                    print(f"  Errore durante il backup della tabella '{table_name}': {e}")
                    backup_successful = False

            cursor.close()

        except Exception as e:
            print(f"Errore nella connessione al database: {e}")
            backup_successful = False

        if backup_successful:
            print("\n✅ Backup del database completato con successo.")
        else:
            print("\n⚠️ Backup del database completato con alcuni errori.")

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

            # Funzione di conversione inversa
            def convert_for_restore(value):
                if value is None:
                    return None

                # Se è stringa, vediamo se è ISO date/datetime
                if isinstance(value, str):
                    # Tentativo data
                    try:
                        if len(value) == 10:  # YYYY-MM-DD
                            return datetime.strptime(value, "%Y-%m-%d").date()
                        elif "T" in value:  # datetime ISO
                            return datetime.fromisoformat(value)
                    except:
                        pass

                    # Tentativo HEX → bytes
                    try:
                        if all(c in "0123456789abcdefABCDEF" for c in value) and len(value) % 2 == 0:
                            return binascii.unhexlify(value)
                    except:
                        pass

                    # Ritorna stringa normale (UTF-8 già salvata)
                    return value

                # Float → Decimal
                if isinstance(value, float):
                    return Decimal(str(value))

                return value

            cursor = self.db.cursor()

            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            self.db.commit()

            cursor.execute(f"DELETE FROM {table_name}")
            self.db.commit()

            if data:
                columns = list(data[0].keys())
                placeholders = ", ".join(["%s"] * len(columns))
                col_names = ", ".join(columns)
                insert_query = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"

                for row in data:
                    values = [convert_for_restore(row.get(col)) for col in columns]
                    cursor.execute(insert_query, values)

                self.db.commit()

            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
            self.db.commit()

            cursor.close()

            print(f"✅ Ripristino della tabella '{table_name}' completato con successo.")

        except Exception as e:
            print(f"❌ Errore durante il ripristino: {e}")

        input("\nPremi Invio per continuare...")

    def view_status(self):
        self._clear_screen()
        print("--- Visualizza Stato Attuale ---")
        print(f"Data di Gioco Attuale: {self._convert_date_to_ded_format(self.game_date)}\n")

        try:
            cursor = self.db.cursor(dictionary=True)  # ✅ Uso connessione esistente

            # 1. PGs e utente associato
            cursor.execute("""
                SELECT pc.id, pc.name, pc.user_id, u.username
                FROM player_characters pc
                LEFT JOIN users u ON pc.user_id = u.id
            """)
            all_pgs = cursor.fetchall()
            num_pgs = len(all_pgs)
            print(f"Numero totale di Personaggi Giocanti (PG): {num_pgs}\n")

            if not all_pgs:
                print("Nessun PG, fondo, seguace, attività o spesa trovata.")
                input("\nPremi Invio per continuare...")
                return

            # Filtra PG se l'utente è un giocatore
            if self.current_user and self.current_user['role'] == 'GIOCATORE':
                pgs_to_display = [pg for pg in all_pgs if pg['user_id'] == self.current_user['id']]
                if not pgs_to_display:
                    print("Nessun PG associato al tuo account per visualizzare lo stato.")
                    input("\nPremi Invio per continuare...")
                    return
            else:
                pgs_to_display = all_pgs

            # Recupera tutte le altre tabelle
            cursor.execute("SELECT * FROM banks")
            all_banks = cursor.fetchall()

            cursor.execute("SELECT * FROM followers")
            all_followers = cursor.fetchall()

            cursor.execute("SELECT * FROM economic_activities")
            all_activities = cursor.fetchall()

            cursor.execute("SELECT * FROM fixed_expenses")
            all_expenses = cursor.fetchall()

            cursor.execute("""
                SELECT fo.*, b.name AS bank_name
                FROM follower_objectives fo
                LEFT JOIN banks b ON fo.bank_id = b.id
            """)
            all_objectives = cursor.fetchall()

            # 2. Stato per ogni PG
            for pg in pgs_to_display:
                print(f"--- Stato PG: {pg['name']} (Associato a: {pg['username'] if pg['username'] else 'N/A'}) ---")

                # Fondi
                pg_banks = [b for b in all_banks if b['pg_id'] == pg['id']]
                total_funds = sum(float(b['current_balance']) for b in pg_banks)
                print(f"  Fondi totali: {total_funds:.2f} (suddivisi in {len(pg_banks)} conti):")
                if pg_banks:
                    for bank in pg_banks:
                        print(f"    - {bank['name']}: {float(bank['current_balance']):.2f}")
                else:
                    print("    Nessun conto bancario.")

                # Seguaci e obiettivi
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
                                bank_name = obj['bank_name'] if obj['bank_name'] else 'N/A'
                                print(f"        - '{obj['name']}': Stato: {status_name}, Progresso: {float(obj['progress_percentage']):.1f}%, Costo: {float(obj['total_cost']):.2f} (Banca: {bank_name})")
                        else:
                            print("      Nessun obiettivo.")
                else:
                    print("    Nessun seguace.")

                # Attività Economiche
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
                        print(f"  • {activity['description']} → {float(activity['income']):.2f} ({activity['frequency']}) → Banca: {bank_name}")
                else:
                    print("  Nessuna attività economica.")

                # Spese Fisse
                pg_expenses = [e for e in all_expenses if e['pg_id'] == pg['id']]
                print(f"  Spese Fisse ({len(pg_expenses)} attive):")
                if pg_expenses:
                    for expense in pg_expenses:
                        bank_name = next((b['name'] for b in all_banks if b['id'] == expense['source_bank_id']), 'N/A')
                        print(f"    - '{expense['description']}' (-{float(expense['amount']):.2f} {expense['frequency']}, da: {bank_name})")
                else:
                    print("    Nessuna spesa fissa.")
                print("-" * 40)

            cursor.close()

        except Exception as e:
            print(f"Si è verificato un errore durante la visualizzazione dello stato: {e}")

        input("\nPremi Invio per continuare...")

    def main_menu(self):
        while True:
            self._clear_screen()
            username = self.current_user.get('username', 'Sconosciuto')
            role = self.current_user.get('role', 'N/A')

            print(f"--- Menu Principale ({username} - {role}) ---")
            print("1.  🧝 Gestione PG")
            print("2.  🏦 Gestione Banche")
            print("3.  🛡️ Gestione Seguaci")
            print("4.  ⚒️ Gestione Attività Economiche")
            print("5.  💰 Gestione Spese Fisse")
            print("6.  ⏳ Gestione Tempo (Solo DM)")
            print("7.  📊 Esporta Fondi PG in Excel (Solo DM)")
            print("8.  💾 Backup/Restore Database (Solo DM)")
            print("9.  🔍 Visualizza Stato (DM/GIOCATORE)")
            if role == 'DM':
                print("10. 👥 Gestione Utenti (Solo DM)")
            print("11. 📘 Scarica Diario della Campagna")
            print("0.  🚪 Logout")

            choice = input("Scegli un'opzione: ").strip()

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
                self.manage_time_menu()
            elif choice == '7':
                if role == 'DM':
                    self.export_pg_funds_to_excel()
                else:
                    print("⚠️ Solo il DM può accedere a questa funzione.")
                    input("\nPremi Invio per continuare...")
            elif choice == "8":
                if role == 'DM':
                    self.backup_restore_menu()
                else:
                    print("⚠️ Solo il DM può accedere a questa funzione.")
                    input("\nPremi Invio per continuare...")
            elif choice == '9':
                self.view_status()
            elif choice == '10' and role == 'DM':
                self.manage_users()
            elif choice == '11':
                self.scarica_diario_campagna()  # Funzione aggiornata a MariaDB
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

            choice = input("Scegli un'opzione: ").strip()

            if choice == '1':
                if self.current_user.get('role') == 'DM':
                    self.add_player_character()
                else:
                    print("⚠️ Solo un DM può aggiungere un PG.")
                    input("\nPremi Invio per continuare...")
            elif choice == '2':
                show_all = self.current_user.get('role') == 'DM'
                self.list_player_characters(show_all=show_all)
            elif choice == '3':
                if self.current_user.get('role') == 'DM':
                    self.update_player_character()
                else:
                    print("⚠️ Solo un DM può modificare un PG.")
                    input("\nPremi Invio per continuare...")
            elif choice == '4':
                if self.current_user.get('role') == 'DM':
                    self.remove_player_character()
                else:
                    print("⚠️ Solo un DM può rimuovere un PG.")
                    input("\nPremi Invio per continuare...")
            elif choice == '0':
                break
            else:
                print("Opzione non valida. Riprova.")
                input("\nPremi Invio per continuare...")

    def bank_menu(self):
        while True:
            self._clear_screen()
            print("--- Gestione Conti Bancari ---")
            print("1. Aggiungi Conto" + (" (Solo DM)" if self.current_user.get('role') != 'DM' else ""))
            print("2. Lista Conti")
            print("3. Modifica Conto" + (" (Solo DM)" if self.current_user.get('role') != 'DM' else ""))
            print("4. Rimuovi Conto" + (" (Solo DM)" if self.current_user.get('role') != 'DM' else ""))
            print("5. Deposita Denaro")
            print("6. Preleva Denaro")
            print("7. Trasferisci Fondi tra Banche")
            print("8. Visualizza Storico Operazioni")
            print("0. Torna al Menu Principale")

            choice = input("Scegli un'opzione: ").strip()

            if choice == '1':
                if self.current_user.get('role') == 'DM':
                    self.add_bank()
                else:
                    print("⚠️ Solo il DM può aggiungere conti bancari.")
                    input("\nPremi Invio per continuare...")
            elif choice == '2':
                show_all = self.current_user.get('role') == 'DM'
                self.list_banks(show_all=show_all)
            elif choice == '3':
                if self.current_user.get('role') == 'DM':
                    self.update_bank()
                else:
                    print("⚠️ Solo il DM può modificare conti bancari.")
                    input("\nPremi Invio per continuare...")
            elif choice == '4':
                if self.current_user.get('role') == 'DM':
                    self.remove_bank()
                else:
                    print("⚠️ Solo il DM può rimuovere conti bancari.")
                    input("\nPremi Invio per continuare...")
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
            ruolo = self.current_user.get('role', None)

            print("--- Gestione Seguaci ---")

            # Opzioni base
            if ruolo == 'DM':
                print("1. Aggiungi Seguace")
                print("2. Lista Seguaci")
                print("3. Modifica Seguace")
                print("4. Rimuovi Seguace")
            else:
                print("2. Lista Seguaci")

            print("--- Gestione Obiettivi/Imprevisti Seguaci ---")
            if ruolo == 'DM':
                print("5. Aggiungi Obiettivo")
                print("6. Modifica Obiettivo")
                print("7. Rimuovi Obiettivo")
                print("8. Inizia Obiettivo")
            print("9. Lista Obiettivi Dettagliata")
            print("10. Visualizza Cronologia Imprevisti")
            print("0. Torna al Menu Principale")

            choice = input("Scegli un'opzione: ").strip()

            if choice == '1':
                if ruolo == 'DM':
                    self.add_follower()
                else:
                    print("⚠️ Solo il DM può aggiungere seguaci.")
                    input("\nPremi Invio per continuare...")
            elif choice == '2':
                self.list_followers(show_all=(ruolo == 'DM'))
            elif choice == '3':
                if ruolo == 'DM':
                    self.update_follower()
                else:
                    print("⚠️ Solo il DM può modificare seguaci.")
                    input("\nPremi Invio per continuare...")
            elif choice == '4':
                if ruolo == 'DM':
                    self.remove_follower()
                else:
                    print("⚠️ Solo il DM può rimuovere seguaci.")
                    input("\nPremi Invio per continuare...")
            elif choice == '5':
                if ruolo == 'DM':
                    self.add_follower_objective()
                else:
                    print("⚠️ Solo il DM può aggiungere obiettivi.")
                    input("\nPremi Invio per continuare...")
            elif choice == '6':
                if ruolo == 'DM':
                    self.update_follower_objective()
                else:
                    print("⚠️ Solo il DM può modificare obiettivi.")
                    input("\nPremi Invio per continuare...")
            elif choice == '7':
                if ruolo == 'DM':
                    self.remove_follower_objective()
                else:
                    print("⚠️ Solo il DM può rimuovere obiettivi.")
                    input("\nPremi Invio per continuare...")
            elif choice == '8':
                if ruolo == 'DM':
                    self.start_follower_objective()
                else:
                    print("⚠️ Solo il DM può avviare obiettivi.")
                    input("\nPremi Invio per continuare...")
            elif choice == '9':
                self.list_follower_objectives(show_all=(ruolo == 'DM'))
            elif choice == '10':
                self.view_follower_events()
            elif choice == '0':
                break
            else:
                print("Opzione non valida o permessi insufficienti.")
                input("\nPremi Invio per continuare...")

    def backup_restore_menu(self):
        ruolo = self.current_user.get('role', None)

        if ruolo != 'DM':
            print("⚠️ Accesso negato: solo il DM può gestire i backup.")
            input("\nPremi Invio per continuare...")
            return

        while True:
            self._clear_screen()
            print("--- Backup/Restore Database ---")
            print("1. 💾 Crea Backup Database")
            print("2. ♻️ Ripristina Backup da File")
            print("0. 🔙 Torna al Menu Principale")

            choice = input("Scegli un'opzione: ").strip()

            if choice == "1":
                self.create_backup()
            elif choice == "2":
                self.restore_backup()
            elif choice == "0":
                break
            else:
                print("❌ Scelta non valida. Riprova.")
                input("\nPremi Invio per continuare...")

    def economic_activity_menu(self):
        while True:
            self._clear_screen()
            print("--- Gestione Attività Economiche ---")
            if self.current_user.get('role') == 'DM':
                print("1. ➕ Aggiungi Attività Economica")
            print("2. 📜 Lista Attività Economiche")
            if self.current_user.get('role') == 'DM':
                print("3. ✏️ Modifica Attività Economica")
                print("4. 🗑️ Rimuovi Attività Economica")
            print("0. 🔙 Torna al Menu Principale")

            choice = input("Scegli un'opzione: ").strip()

            if choice == '1' and self.current_user.get('role') == 'DM':
                self.add_economic_activity()
            elif choice == '2':
                self.list_economic_activities(show_all=(self.current_user.get('role') == 'DM'))
            elif choice == '3' and self.current_user.get('role') == 'DM':
                self.update_economic_activity()
            elif choice == '4' and self.current_user.get('role') == 'DM':
                self.remove_economic_activity()
            elif choice == '0':
                break
            else:
                print("❌ Opzione non valida o permessi insufficienti.")
                input("\nPremi Invio per continuare...")

    def fixed_expense_menu(self):
        while True:
            self._clear_screen()
            print("--- Gestione Spese Fisse ---")
            if self.current_user.get('role') == 'DM':
                print("1. ➕ Aggiungi Spesa Fissa")
            print("2. 📜 Lista Spese Fisse")
            if self.current_user.get('role') == 'DM':
                print("3. ✏️ Modifica Spesa Fissa")
                print("4. 🗑️ Rimuovi Spesa Fissa")
            print("0. 🔙 Torna al Menu Principale")

            choice = input("Scegli un'opzione: ").strip()

            if choice == '1' and self.current_user.get('role') == 'DM':
                self.add_fixed_expense()
            elif choice == '2':
                self.list_fixed_expenses(show_all=(self.current_user.get('role') == 'DM'))
            elif choice == '3' and self.current_user.get('role') == 'DM':
                self.update_fixed_expense()
            elif choice == '4' and self.current_user.get('role') == 'DM':
                self.remove_fixed_expense()
            elif choice == '0':
                break
            else:
                print("❌ Opzione non valida o permessi insufficienti.")
                input("\nPremi Invio per continuare...")

if __name__ == "__main__":
    show_welcome_message()
    tool = DeDTool()

    # Ciclo di login/uscita
    while True:
        tool._clear_screen()
        print("=== 🎲 Benvenuto in D&D Tool by Max ===")
        print("1. 🔑 Login")
        print("0. 🚪 Esci")

        choice = input("Scegli un'opzione: ").strip()

        if choice == '1':
            if tool.login():
                tool.main_menu()  # Entra nel menu principale dopo login riuscito
        elif choice == '0':
            print("👋 Uscita dall'applicazione. Arrivederci!")
            break
        else:
            print("❌ Opzione non valida. Riprova.")
            input("\nPremi Invio per continuare...")

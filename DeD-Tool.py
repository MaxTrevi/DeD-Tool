import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
import requests
import os
import sys
from datetime import date as date, datetime as datetime, timedelta as timedelta
from decimal import Decimal
import pymysql
from cryptography.fernet import Fernet
import json
import traceback
import pandas as pd
from openai import OpenAI
import smtplib
from email.message import EmailMessage
import re
import threading
from dbutils.pooled_db import PooledDB

__VERSION__ = "1.0.6"

# URL per aggiornamenti
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

class DeDToolGUI:
    """Classe principale per l'interfaccia grafica"""
    
    MONTH_NAMES = [
        "NUWMONT", "VATERMONT", "THAUMONT", "FLAURMONT",
        "YARTHMONT", "KLARMONT", "FELMONT", "FYRMONT",
        "AMBYRMONT", "SVIFTMONT", "EIRMONT", "KALDMONT"
    ]

    # Calendario Mystara: mesi da 28 giorni
    DAYS_PER_MONTH = 28
    MONTHS_PER_YEAR = 12
    DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR  # 336
    EPOCH_DATE = date(1, 1, 1)
    
    OBJECTIVE_STATUS = {
        "NON_INIZIATO": 0,
        "IN_CORSO": 1,
        "COMPLETATO": 2,
        "FALLITO": 3
    }
    
    OBJECTIVE_STATUS_REV = {v: k for k, v in OBJECTIVE_STATUS.items()}

    STANDARD_CLASS_CODES = {
        "CHIERICO": "CHIERICO",
        "DRUIDO": "DRUIDO",
        "GUERRIERO": "GUERRIERO",
        "LADRO": "LADRO",
        "MAGO": "MAGO",
        "MISTICO": "MISTICO",
        "ELFO": "ELFO",
        "HALFLING": "HALFLING",
        "NANO": "NANO",
    }

    CLASS_CODE_ALIASES = {
        "CLERIC": "CHIERICO",
        "CHIERICO": "CHIERICO",
        "DRUID": "DRUIDO",
        "DRUIDO": "DRUIDO",
        "FIGHTER": "GUERRIERO",
        "GUERRIERO": "GUERRIERO",
        "WARRIOR": "GUERRIERO",
        "THIEF": "LADRO",
        "LADRO": "LADRO",
        "MAGIC USER": "MAGO",
        "MAGIC-USER": "MAGO",
        "MAGO": "MAGO",
        "MAGHI": "MAGO",
        "MYSTIC": "MISTICO",
        "MISTICO": "MISTICO",
        "ELF": "ELFO",
        "ELFO": "ELFO",
        "HALFLING": "HALFLING",
        "HALFLING/MEZZUOMO": "HALFLING",
        "MEZZUOMO": "HALFLING",
        "DWARF": "NANO",
        "NANO": "NANO",
    }
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("D&D Tool - Gestione Campagna")
        
        self.root.state('zoomed')
        
        # Variabili
        self.current_user = None
        self.db = None
        self.game_date = None
        self.env_sec = {}
        self.tree_followers = None
        self.client = None

        # 🔥 INTEGRAZIONE CONNECTION POOLING - UNIFICATO 🔥
        self._pool_initialized = False
        self.connection_pool = None
        self._pool_lock = threading.Lock()

        # Configura stile
        self.setup_style()
        
        # Gestione chiusura finestra
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Carica ambiente sicuro
        self.load_secure_env()

        # Carica valori Email
        self.SMTP_EMAIL = self.env_sec.get("GMAIL_USER")
        self.SMTP_PASSWORD = self.env_sec.get("GMAIL_PASS")
        
        # Connetti al database
        self.connect_database()

        # 🔥 INIZIALIZZA IL CONNECTION POOL SUBITO DOPO LA CONNESSIONE NORMALE 🔥
        self.init_connection_pool()

        self.migrate_game_state_absolute_day()
        self.game_date = self.load_game_date()
        
        # Configura scorciatoie tastiera
        self.setup_keyboard_shortcuts()
        
        # Mostra schermata di login
        self.show_login_screen()

        # Inizializza client AI
        try:
            self.client = OpenAI(
                base_url="http://localhost:1234/v1",  # porta LM Studio
                api_key="lmstudio"
            )
        except Exception as e:
            self.client = None
            print(f"❌ Errore inizializzazione client LM Studio: {e}")

    def run(self):
        """Avvia l'applicazione"""
        self.root.mainloop()

    def on_closing(self):
        """Gestisce la chiusura dell'applicazione"""
        try:
            print("Chiusura applicazione in corso...")
            
            # 1. Chiudi tutte le finestre chat aperte e ferma polling
            self._close_all_chat_windows()
            
            # 2. Ferma eventuali altri polling (come la chat comune nei tab)
            if hasattr(self, 'content_frame'):
                for widget in self.content_frame.winfo_children():
                    if hasattr(widget, 'after_id'):
                        try:
                            widget.after_cancel(widget.after_id)
                        except:
                            pass
            
            # 3. Chiudi connessioni database
            if hasattr(self, 'db') and self.db:
                self.db.close()
                print("✓ Connessione database chiusa")
            
            # 4. Chiudi connection pool
            if hasattr(self, '_pool_initialized') and self._pool_initialized:
                if self.connection_pool:
                    try:
                        self.connection_pool.close()
                        print("✓ Connection pool chiuso")
                    except:
                        pass
            
            # 5. Distruggi la finestra principale
            self.root.quit()
            self.root.destroy()
            
        except Exception as e:
            print(f"Errore durante la chiusura: {e}")
            self.root.destroy()

    def setup_keyboard_shortcuts(self):
        """Configura scorciatoie da tastiera"""
        self.root.bind('<F11>', lambda e: self.toggle_fullscreen())
        self.root.bind('<Control-q>', lambda e: self.on_closing())
        self.root.bind('<Escape>', lambda e: self.root.attributes('-fullscreen', False))

    def show_simple_changelog(self):
        """Mostra il changelog in una finestra semplice - versione minimalista"""
        try:
            CHANGELOG_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/changelog.txt"
            
            # Scarica il changelog
            response = requests.get(CHANGELOG_URL, timeout=5)
            response.raise_for_status()
            changelog_text = response.text
            
            # Finestra semplice
            win = tk.Toplevel(self.root)
            win.title(f"Changelog - Versione {__VERSION__}")
            win.geometry("800x500")
            win.transient(self.root)
            
            # Frame principale
            main_frame = ttk.Frame(win)
            main_frame.pack(fill='both', expand=True, padx=10, pady=10)
            
            # Titolo
            title = ttk.Label(main_frame, 
                             text=f"Registro delle Modifiche - Versione Attuale: {__VERSION__}",
                             font=('Arial', 11, 'bold'))
            title.pack(pady=10)
            
            # Separatore
            ttk.Separator(main_frame, orient='horizontal').pack(fill='x', pady=5)
            
            # Text widget con scrollbar (semplice)
            text_widget = tk.Text(main_frame, wrap='word', height=20, font=('Courier', 9))
            scrollbar = ttk.Scrollbar(main_frame, orient='vertical', command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)
            
            # Layout
            text_widget.pack(side='left', fill='both', expand=True, padx=(0, 5))
            scrollbar.pack(side='right', fill='y')
            
            # Inserisci il testo e rendilo readonly
            text_widget.insert('1.0', changelog_text)
            text_widget.config(state='disabled')
            
            # Pulsante Chiudi
            ttk.Button(main_frame, text="Chiudi", 
                      command=win.destroy).pack(pady=10)
            
            # Focus sulla finestra
            win.focus_set()
            
        except Exception as e:
            messagebox.showerror("Errore", 
                               f"Impossibile caricare il changelog:\n\n{e}\n\n"
                               f"Assicurati di avere connessione internet.")

    def setup_menu_bar(self):
        """Configura la barra dei menu principale"""
        menubar = tk.Menu(self.root)
        
        # Menu File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Esporta Stato", command=lambda: self.export_status_to_txt(None))
        file_menu.add_separator()
        file_menu.add_command(label="Esci", command=self.on_closing)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Menu Visualizza
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Schermo Intero", command=lambda: self.toggle_fullscreen())
        view_menu.add_command(label="Normale", command=lambda: self.root.attributes('-fullscreen', False))
        menubar.add_cascade(label="Visualizza", menu=view_menu)
        
        # ⭐⭐ NUOVO MENU: Informazioni
        info_menu = tk.Menu(menubar, tearoff=0)
        info_menu.add_command(label="Changelog", command=self.show_simple_changelog)
        info_menu.add_command(label="Informazioni", command=self.show_about)
        menubar.add_cascade(label="Informazioni", menu=info_menu)
        
        self.root.config(menu=menubar)

    def _close_all_chat_windows(self):
        """Chiude tutte le finestre di chat segreta aperte"""
        try:
            # Trova tutte le finestre Toplevel aperte per chat segrete
            for widget in self.root.winfo_children():
                if isinstance(widget, tk.Toplevel) and "Chat segreta" in widget.title():
                    try:
                        if hasattr(widget, '_chat_after_id'):
                            widget.after_cancel(widget._chat_after_id)
                        widget.destroy()
                    except:
                        pass
        except Exception as e:
            print(f"Errore chiusura finestre chat: {e}")

    def setup_style(self):
        """Configura gli stili per l'interfaccia grafica"""
        try:
            style = ttk.Style()
            
            # Configura tema
            style.theme_use('clam')
            
            # Stili personalizzati
            style.configure('Title.TLabel', 
                          font=('Arial', 16, 'bold'),
                          foreground='#2C3E50')
            
            style.configure('Subtitle.TLabel',
                          font=('Arial', 12, 'bold'), 
                          foreground='#34495E')
            
            style.configure('Success.TLabel',
                          font=('Arial', 10),
                          foreground='#27AE60')
            
            style.configure('Error.TLabel', 
                          font=('Arial', 10),
                          foreground='#E74C3C')
            
            # Pulsanti
            style.configure('TButton',
                          font=('Arial', 10),
                          padding=6)
            
            style.configure('Accent.TButton',
                          font=('Arial', 10, 'bold'),
                          foreground='white',
                          background='#3498DB')
            
            # Entry e combobox
            style.configure('TEntry',
                          font=('Arial', 10),
                          padding=5)
            
            style.configure('TCombobox',
                          font=('Arial', 10),
                          padding=5)

            style.configure('FollowerReadonly.TEntry',
                          font=('Arial', 10),
                          padding=5,
                          fieldbackground='#EEEEEE',
                          background='#EEEEEE',
                          foreground='#555555')
            style.map('FollowerReadonly.TEntry',
                      fieldbackground=[('readonly', '#EEEEEE'), ('disabled', '#EEEEEE')],
                      foreground=[('readonly', '#555555'), ('disabled', '#555555')])

            style.configure('FollowerReadonly.TCombobox',
                          font=('Arial', 10),
                          padding=5,
                          fieldbackground='#EEEEEE',
                          background='#EEEEEE',
                          foreground='#555555',
                          arrowcolor='#777777')
            style.map('FollowerReadonly.TCombobox',
                      fieldbackground=[('readonly', '#EEEEEE'), ('disabled', '#EEEEEE')],
                      background=[('readonly', '#EEEEEE'), ('disabled', '#EEEEEE')],
                      foreground=[('readonly', '#555555'), ('disabled', '#555555')])
            
            # Notebook (tabs)
            style.configure('TNotebook',
                          font=('Arial', 10))
            
            style.configure('TNotebook.Tab',
                          font=('Arial', 10),
                          padding=[10, 5])
            
            
        except Exception as e:
            print(f"❌ Errore configurazione stili: {e}")
        
    def load_secure_env(self):
        """Carica le variabili d'ambiente sicure"""
        try:
            secret_key_file = "secret.key"
            encrypted_file = "DeD-Tool.env_sec.enc"
            
            if not os.path.exists(secret_key_file):
                messagebox.showwarning("Avviso", "Nessuna chiave segreta trovata. Ambiente sicuro non caricato.")
                return
            
            with open(secret_key_file, "rb") as key_file:
                key = key_file.read()
            
            with open(encrypted_file, "rb") as enc_file:
                encrypted = enc_file.read()
            
            decrypted = Fernet(key).decrypt(encrypted).decode()
            
            for line in decrypted.splitlines():
                if line and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()
                    self.env_sec[k.strip()] = v.strip()
                    
        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento ambiente sicuro: {e}")
    
    def connect_database(self):
        """Connette al database MariaDB"""
        try:
            self.db = pymysql.connect(
                host=self.env_sec.get("DB_HOST"),
                user=self.env_sec.get("DB_USER"),
                password=self.env_sec.get("DB_PASSWORD"),
                database=self.env_sec.get("DB_NAME"),
                port=int(self.env_sec.get("DB_PORT", 3307)),
                charset='utf8mb4',
                autocommit=True,
                cursorclass=pymysql.cursors.DictCursor
            )
            
            # Carica data di gioco
            self.game_date = self.load_game_date()
            
        except Exception as e:
            messagebox.showerror("Errore Connessione", 
                               f"Impossibile connettersi al database:\n{e}")
            sys.exit(1)

    def date_to_absolute_day(self, d):
        """
        Converte un oggetto date in absolute_day (int) usando EPOCH_DATE.
        Restituisce un int >= 0.
        """
        try:
            epoch = self.EPOCH_DATE

            if isinstance(d, datetime):
                d = d.date()
            if not isinstance(d, date):
                d = datetime.strptime(str(d), "%Y-%m-%d").date()

            return (d - epoch).days
        except Exception as e:
            self.append_time_log(f"date_to_absolute_day error: {e}")
            return 0

    def absolute_day_to_date(self, absolute_day):
        """
        Converte absolute_day (int) in oggetto date usando EPOCH_DATE.
        """
        try:
            epoch = self.EPOCH_DATE

            abs_days = int(absolute_day)
            result_date = epoch + timedelta(days=abs_days)
            
            return result_date
            
        except Exception as e:
            self.append_time_log(f"absolute_day_to_date error: {e}")
            return self.EPOCH_DATE

    def append_time_log(self, message):
        """Aggiunge una riga al riquadro log (solo GUI, nessuna stampa console)."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}\n"

        try:
            # Log nella GUI
            if hasattr(self, "time_log_text") and isinstance(self.time_log_text, tk.Text):
                self.time_log_text.configure(state='normal')
                self.time_log_text.insert(tk.END, line)
                self.time_log_text.see(tk.END)
                self.time_log_text.configure(state='disabled')
        except Exception:
            pass   # evita errori se il log non esiste ancora

    def migrate_game_state_absolute_day(self):
        """
        Garantisce che nella tabella game_state ci sia il campo absolute_day e che sia in coerenza
        con game_date. Se absolute_day è NULL o 0, lo popola a partire da game_date.
        - Non elimina il campo game_date (coexistence come richiesto).
        """
        try:
            cursor = self.db.cursor()
            # tenta di leggere absolute_day — se la colonna non esiste, la crea
            try:
                cursor.execute("SELECT id, game_date, absolute_day FROM game_state WHERE id = 1")
                row = cursor.fetchone()
            except Exception:
                # colonna probabilmente mancante: proviamo ad aggiungerla
                try:
                    cursor.execute("ALTER TABLE game_state ADD COLUMN absolute_day INT NOT NULL DEFAULT 0")
                    self.db.commit()
                    self.append_time_log("Colonna absolute_day aggiunta a game_state.")
                except Exception as e:
                    self.append_time_log(f"Impossibile aggiungere column absolute_day: {e}")
                # ora riproviamo a leggere
                try:
                    cursor.execute("SELECT id, game_date, absolute_day FROM game_state WHERE id = 1")
                    row = cursor.fetchone()
                except Exception as e:
                    self.append_time_log(f"Errore read game_state dopo alter: {e}")
                    row = None
            except Exception as e:  # ← AGGIUNGI QUESTO BLOCCO PER CHIUDERE IL PRIMO TRY
                self.append_time_log(f"Errore lettura game_state: {e}")
                row = None

            # Se non esiste alcun record game_state, creane uno coerente
            if not row:
                # default: epoch
                try:
                    initial_date = getattr(self, "EPOCH_DATE", date(1, 1, 1))
                    abs_day = self.date_to_absolute_day(initial_date)
                    cursor.execute("INSERT INTO game_state (id, game_date, absolute_day) VALUES (%s, %s, %s)",
                                   (1, initial_date.strftime("%Y-%m-%d"), abs_day))
                    self.db.commit()
                    self.append_time_log("Inserito record iniziale game_state con absolute_day.")
                    return
                except Exception as e:
                    self.append_time_log(f"Errore creazione record game_state: {e}")
                    return

            # Se c'è un record, sincronizza absolute_day <-> game_date
            try:
                db_game_date = row.get("game_date")
                db_abs = row.get("absolute_day", 0)

                if db_abs and db_abs != 0:
                    # preferiamo absolute_day (se presente) e aggiorniamo game_date in memoria
                    dt = self.absolute_day_to_date(db_abs)
                    self.game_date = dt
                    self.append_time_log(f"game_date caricato da absolute_day: {self.convert_date_to_ded_format(self.game_date)}")
                elif db_game_date:
                    # calcola absolute_day da game_date e salva
                    dt = db_game_date
                    if isinstance(dt, datetime):
                        dt = dt.date()
                    abs_day = self.date_to_absolute_day(dt)
                    cursor.execute("UPDATE game_state SET absolute_day = %s WHERE id = 1", (abs_day,))
                    self.db.commit()
                    self.game_date = dt
                    self.append_time_log("absolute_day popolato a partire da game_date.")
                else:
                    # nulla: inizializza con EPOCH_DATE
                    initial = getattr(self, "EPOCH_DATE", date(1, 1, 1))
                    abs_day = self.date_to_absolute_day(initial)
                    cursor.execute("UPDATE game_state SET game_date = %s, absolute_day = %s WHERE id = 1",
                                   (initial.strftime("%Y-%m-%d"), abs_day))
                    self.db.commit()
                    self.game_date = initial
                    self.append_time_log("game_state mancante: inizializzato con EPOCH_DATE.")
            except Exception as e:
                self.append_time_log(f"Errore migration sync absolute_day: {e}")
            finally:
                try:
                    cursor.close()
                except:
                    pass
        except Exception as e:
            self.append_time_log(f"Errore generale in migrate_game_state_absolute_day: {e}")

    def _update_game_state_date(self, new_date):
        """
        Aggiorna game_state sia nel campo game_date (YYYY-MM-DD) che absolute_day (INT).
        new_date può essere date o datetime o stringa 'YYYY-MM-DD'.
        """
        try:
            if isinstance(new_date, datetime):
                nd = new_date.date()
            elif isinstance(new_date, date):
                nd = new_date
            else:
                nd = datetime.strptime(str(new_date), "%Y-%m-%d").date()

            abs_day = self.date_to_absolute_day(nd)

            cursor = self.db.cursor()
            cursor.execute("UPDATE game_state SET game_date = %s, absolute_day = %s WHERE id = 1",
                           (nd.strftime("%Y-%m-%d"), abs_day))
            self.db.commit()
            cursor.close()
        except Exception as e:
            self.append_time_log(f"Errore aggiornamento game_state date/abs: {e}")
    
    def load_game_date(self):
        """
        Carica la data di gioco. Se absolute_day è presente lo usa per ricostruire la date,
        altrimenti legge game_date e popola absolute_day.
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT game_date, absolute_day FROM game_state WHERE id = 1")
            row = cursor.fetchone()
            cursor.close()

            if not row:
                # fallback: crea record (migrate_game_state_absolute_day dovrebbe aver già gestito)
                default_date = getattr(self, "EPOCH_DATE", date(1, 1, 1))
                return default_date

            abs_day = row.get("absolute_day")
            gd = row.get("game_date")

            if abs_day is not None and int(abs_day) != 0:
                # usa absolute_day
                return self.absolute_day_to_date(int(abs_day))
            elif gd:
                if isinstance(gd, datetime):
                    return gd.date()
                return gd
            else:
                return getattr(self, "EPOCH_DATE", date(1, 1, 1))

        except Exception as e:
            self.append_time_log(f"Errore caricamento data: {e}")
            return getattr(self, "EPOCH_DATE", date(1, 1, 1))

    def convert_date_to_ded_format(self, date_obj):
        """
        Converte una data (oggetto date) nel formato Mystara con mesi da 28 giorni.
        Usa absolute_day internamente per calcolare giorno/mese/anno Mystara coerente.
        """
        try:
            # assicurati di avere un date
            if isinstance(date_obj, datetime):
                date_obj = date_obj.date()
            if not isinstance(date_obj, date):
                date_obj = datetime.strptime(str(date_obj), "%Y-%m-%d").date()

            # calcola absolute_day dalla data
            abs_day = self.date_to_absolute_day(date_obj)

            # giorno nell'anno Mystara (0-based)
            day_of_year = abs_day % self.DAYS_PER_YEAR

            # mese e giorno (entrambi 0-based per il calcolo)
            month_index = day_of_year // self.DAYS_PER_MONTH
            day_in_month = (day_of_year % self.DAYS_PER_MONTH) + 1  # +1 per renderlo 1-based

            # anno Mystara (base year calcolato dall'EPOCH_DATE)
            base_year = getattr(self, "EPOCH_DATE", date(1, 1, 1)).year
            years_passed = abs_day // self.DAYS_PER_YEAR
            mystara_year = base_year + years_passed

            # nome mese
            month_name = self.MONTH_NAMES[month_index]

            return f"{day_in_month:02d} {month_name} {mystara_year}"

        except Exception as e:  # ← QUESTA RIGA DEVE ESSERE ALLINEATA CON IL 'try'
            self.append_time_log(f"Errore conversione data: {e}")
            return str(date_obj)

    def save_game_date(self):
        """
        Salva la data di gioco corrente su MariaDB.
        Aggiorna sia game_date che absolute_day.
        """
        try:
            # Calcola absolute_day dalla data corrente
            abs_day = self.date_to_absolute_day(self.game_date)
            
            cursor = self.db.cursor()
            
            # Query corretta per UPDATE
            update_query = "UPDATE game_state SET game_date = %s, absolute_day = %s WHERE id = 1"
            cursor.execute(update_query, (self.game_date.strftime("%Y-%m-%d"), abs_day))
            
            if cursor.rowcount == 0:
                # Nessuna riga aggiornata → inseriamo la riga
                insert_query = "INSERT INTO game_state (id, game_date, absolute_day) VALUES (%s, %s, %s)"
                cursor.execute(insert_query, (1, self.game_date.strftime("%Y-%m-%d"), abs_day))
            
            self.db.commit()
            cursor.close()
            print(f"✅ Data di gioco salvata: {self.game_date}, absolute_day: {abs_day}")
            
        except Exception as e:
            print(f"❌ Errore salvataggio data di gioco: {e}")
    
    def show_login_screen(self):
        """Mostra la schermata di login"""
        # Pulisci finestra
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Frame principale
        login_frame = ttk.Frame(self.root, padding="20")
        login_frame.place(relx=0.5, rely=0.5, anchor='center')
        
        # Titolo
        title = ttk.Label(login_frame, text="🎲 D&D Tool", style='Title.TLabel')
        title.grid(row=0, column=0, columnspan=2, pady=10)
        
        # Versione
        version_label = ttk.Label(login_frame, text=f"Versione {__VERSION__}", style='Info.TLabel')
        version_label.grid(row=1, column=0, columnspan=2, pady=2)
        
        subtitle = ttk.Label(login_frame, text="by Massimo Trevisan", style='Info.TLabel')
        subtitle.grid(row=2, column=0, columnspan=2, pady=5)
        
        # Campo username
        ttk.Label(login_frame, text="Username:").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        username_entry = ttk.Entry(login_frame, width=30)
        username_entry.grid(row=3, column=1, padx=5, pady=5)
        
        # Campo password
        ttk.Label(login_frame, text="Password:").grid(row=4, column=0, sticky='e', padx=5, pady=5)
        password_entry = ttk.Entry(login_frame, width=30, show='*')
        password_entry.grid(row=4, column=1, padx=5, pady=5)
        
        # Checkbox Ricordami
        remember_var = tk.BooleanVar()
        remember_check = ttk.Checkbutton(login_frame, text="Ricordami", variable=remember_var)
        remember_check.grid(row=5, column=0, columnspan=2, pady=10)
        
        # Pulsante login
        def attempt_login():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            remember = remember_var.get()
            
            if self.login(username, password):
                # Salva le credenziali se "Ricordami" è selezionato
                if remember:
                    self.save_credentials(username, password)
                else:
                    # Se non è selezionato, rimuovi eventuali credenziali salvate
                    self.clear_credentials()
                self.show_main_menu()
            else:
                messagebox.showerror("Errore Login", "Username o password non validi")
        
        login_btn = ttk.Button(login_frame, text="🔓 Login", command=attempt_login)
        login_btn.grid(row=6, column=0, columnspan=2, pady=20)
        
        # Bind Enter key
        password_entry.bind('<Return>', lambda e: attempt_login())
        
        # Carica credenziali salvate se esistono
        self.load_saved_credentials(username_entry, password_entry, remember_var)
        
        # Focus su username
        username_entry.focus()

    def save_credentials(self, username, password):
        """Salva username e password in un file JSON"""
        credentials = {
            'username': username,
            'password': password
        }
        
        try:
            with open('credentials.json', 'w') as f:
                json.dump(credentials, f)
        except Exception as e:
            print(f"Errore nel salvare le credenziali: {e}")

    def clear_credentials(self):
        """Rimuove il file delle credenziali se esiste"""
        try:
            if os.path.exists('credentials.json'):
                os.remove('credentials.json')
        except Exception as e:
            print(f"Errore nel rimuovere le credenziali: {e}")

    def load_saved_credentials(self, username_entry, password_entry, remember_var):
        """Carica le credenziali salvate se esistono"""
        try:
            if os.path.exists('credentials.json'):
                with open('credentials.json', 'r') as f:
                    credentials = json.load(f)
                
                username_entry.insert(0, credentials.get('username', ''))
                password_entry.insert(0, credentials.get('password', ''))
                remember_var.set(True)
        except Exception as e:
            print(f"Errore nel caricare le credenziali: {e}")
    
    def login(self, username, password):
        """Effettua il login"""
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            
            if user and user['password'] == password:
                self.current_user = user
                return True
            return False
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante il login: {e}")
            return False
    
    def show_main_menu(self):
        """Mostra il menu principale con layout più compatto"""
        # Pulisci finestra
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Configura menu bar
        self.setup_menu_bar()
        
        # Frame principale con sidebar e contenuto
        main_container = ttk.Frame(self.root)
        main_container.pack(fill='both', expand=True)
        
        # Sidebar
        sidebar = ttk.Frame(main_container, width=250, relief='raised', borderwidth=2)
        sidebar.pack(side='left', fill='y', padx=5, pady=5)
        sidebar.pack_propagate(False)
        
        row = 0
        
        # Header sidebar
        user_frame = ttk.Frame(sidebar)
        user_frame.grid(row=row, column=0, sticky='ew', padx=10, pady=10)
        row += 1
        
        ttk.Label(user_frame, text=f"👤 {self.current_user['username']}",
                 style='Subtitle.TLabel').pack()
        ttk.Label(user_frame, text=f"Ruolo: {self.current_user['role']}",
                 style='Info.TLabel').pack()
        
        # Data di gioco
        date_frame = ttk.Frame(sidebar)
        date_frame.grid(row=row, column=0, sticky='ew', padx=10, pady=5)
        row += 1
        
        ttk.Label(date_frame, text="📅 Data di Gioco:", style='Info.TLabel').pack()
        self.date_label = ttk.Label(
            date_frame,
            text=self.convert_date_to_ded_format(self.game_date),
            font=('Arial', 10, 'bold')
        )
        self.date_label.pack()
        
        ttk.Separator(sidebar, orient='horizontal').grid(row=row, column=0, sticky='ew',
                                                         padx=10, pady=5)
        row += 1

        # 🔥 **Menu disponibile a TUTTI**
        menu_items = [
            ("🏦 Banche", self.show_banks_menu),
            ("🛡️ Seguaci", self.show_followers_menu),
            ("📋 Scheda Personaggio", self.show_character_sheet_menu),
            ("⚒️ Attività Economiche", self.show_economic_menu),
            ("💰 Spese Fisse", self.show_expenses_menu),
        ]
        
        # 🔥 **SOLO DM**
        if self.current_user['role'] == 'DM':
            menu_items.insert(0, ("🧙 Personaggi", self.show_characters_menu))
            menu_items.extend([
                ("⏳ Gestione Tempo", self.show_time_menu),
                ("👥 Utenti", self.show_users_menu),
                ("💾 Backup", self.show_backup_menu),
            ])
        
        # Pulsante chat
        chat_text = "💬 Chat"
        
        counts = self._count_unread_by_category_fast()
        unread_total = counts["comune"] + counts["segreti"]
        
        if unread_total > 0:
            chat_text = f"💬 Chat ({unread_total})"
        
        chat_btn = ttk.Button(sidebar, text=chat_text, command=self.show_chat, width=23)
        chat_btn.grid(row=row, column=0, padx=10, pady=3)
        row += 1
        self.chat_button = chat_btn
                
        # Altri menu visibili a tutti
        menu_items.extend([
            ("📊 Stato Campagna", self.show_status),
        ])

        # Diario con notifica nuova versione e effetto lampeggio
        diario_label = "📘 Diario"
        self.diario_has_new_version = False
        try:
            if self.check_nuovo_diario():
                diario_label = "📘 Diario ⭐ NUOVO ⭐"
                self.diario_has_new_version = True
        except:
            pass  # In caso di errore (no internet) resta il testo normale

        menu_items.append((diario_label, self.download_diary))
        
        # Inserimento pulsanti
        for text, command in menu_items:
            # USA tk.Button invece di ttk.Button per il diario se c'è nuova versione
            if text.startswith("📘 Diario") and self.diario_has_new_version:
                btn = tk.Button(sidebar, text=text, command=command, width=23,
                              bg='SystemButtonFace', fg='black', font=('Arial', 9))
                btn.grid(row=row, column=0, padx=10, pady=3)
                self.diario_button = btn
                self.start_diario_blink()
            else:
                btn = ttk.Button(sidebar, text=text, command=command, width=23)
                btn.grid(row=row, column=0, padx=10, pady=3)
            
            row += 1
        
        ttk.Separator(sidebar, orient='horizontal').grid(row=row, column=0, sticky='ew',
                                                         padx=10, pady=5)
        row += 1
        
        logout_btn = ttk.Button(
            sidebar,
            text="🚪 Logout",
            command=self.show_login_screen,
            width=23
        )
        logout_btn.grid(row=row, column=0, padx=10, pady=3)
        
        # Frame contenuto principale
        self.content_frame = ttk.Frame(main_container)
        self.content_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        
        # Schermata iniziale
        self.show_welcome_content()

    # ==================== SCHEDA PERSONAGGIO ====================
    
    def show_character_sheet_menu(self):
        """Menu principale per la gestione della scheda personaggio"""
        try:
            # Pulisci content frame
            for widget in self.content_frame.winfo_children():
                widget.destroy()
            
            # Container principale
            main_frame = ttk.Frame(self.content_frame)
            main_frame.pack(fill='both', expand=True)
            
            # Titolo
            title = ttk.Label(main_frame, text="📋 Scheda Personaggio", style='Title.TLabel')
            title.pack(pady=10)
            
            # Seleziona personaggio (se giocatore, auto-select; se DM, scelta)
            if self.current_user['role'] == 'GIOCATORE':
                # Carica automaticamente il personaggio del giocatore
                cursor = self.db.cursor()
                cursor.execute("""
                    SELECT id, name FROM player_characters 
                    WHERE user_id = %s 
                    ORDER BY id DESC LIMIT 1
                """, (self.current_user['id'],))
                pg = cursor.fetchone()
                cursor.close()
                
                if not pg:
                    messagebox.showinfo("Info", 
                        "Non hai ancora un personaggio.\n"
                        "Il DM deve crearlo dalla sezione '🧙 Personaggi'.")
                    return
                
                self.show_character_sheet(pg['id'])
            
            else:  # DM
                # Mostra lista per selezione
                select_frame = ttk.LabelFrame(main_frame, text="Seleziona Personaggio", padding=10)
                select_frame.pack(fill='both', expand=True, padx=20, pady=10)
                
                # Treeview con personaggi
                columns = ('pg_name', 'player', 'level', 'class')
                tree = ttk.Treeview(select_frame, columns=columns, show='headings', height=15)
                
                tree.heading('pg_name', text='Personaggio')
                tree.heading('player', text='Giocatore')
                tree.heading('level', text='Livello')
                tree.heading('class', text='Classe')
                
                tree.column('pg_name', width=200)
                tree.column('player', width=150)
                tree.column('level', width=80)
                tree.column('class', width=120)
                
                # Scrollbar
                scrollbar = ttk.Scrollbar(select_frame, orient='vertical', command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                
                tree.pack(side='left', fill='both', expand=True)
                scrollbar.pack(side='right', fill='y')
                
                # Carica personaggi
                cursor = self.db.cursor()
                cursor.execute("""
                    SELECT pc.id, pc.name, u.username, 
                           COALESCE(pc.livello, 1) as livello,
                           COALESCE(pc.classe, 'Ladro') as classe
                    FROM player_characters pc
                    LEFT JOIN users u ON pc.user_id = u.id
                    ORDER BY pc.name
                """)
                characters = cursor.fetchall()
                cursor.close()
                
                for char in characters:
                    tree.insert('', 'end', values=(
                        char['name'],
                        char.get('username', 'N/A'),
                        char['livello'],
                        char['classe']
                    ), tags=(char['id'],))
                
                # Bottone apri scheda
                btn_frame = ttk.Frame(select_frame)
                btn_frame.pack(fill='x', pady=10)
                
                def open_selected():
                    selection = tree.selection()
                    if not selection:
                        messagebox.showwarning("Attenzione", "Seleziona un personaggio!")
                        return
                    
                    item = tree.item(selection[0])
                    pg_id = item['tags'][0]
                    self.show_character_sheet(pg_id)
                
                ttk.Button(btn_frame, text="📖 Apri Scheda", command=open_selected, 
                          style='Accent.TButton').pack(pady=5)
        
        except Exception as e:
            messagebox.showerror("Errore", f"Errore apertura menu scheda: {e}")
            import traceback
            traceback.print_exc()
    
    def show_character_sheet(self, pg_id):
        """Mostra la scheda completa del personaggio"""
        try:
            self.current_sheet_pg_id = int(pg_id)
            
            # Flag per tracciare se ci sono modifiche non salvate
            self.has_unsaved_changes = False
            
            # Pulisci content frame
            for widget in self.content_frame.winfo_children():
                widget.destroy()
            
            # Carica dati personaggio
            cursor = self.db.cursor()
            if self.current_user and self.current_user.get('role') == 'GIOCATORE':
                cursor.execute(
                    "SELECT * FROM player_characters WHERE id = %s AND user_id = %s",
                    (self.current_sheet_pg_id, self.current_user['id'])
                )
            else:
                cursor.execute("SELECT * FROM player_characters WHERE id = %s", (self.current_sheet_pg_id,))
            character = cursor.fetchone()
            cursor.close()
            
            if not character:
                messagebox.showerror("Errore", "Personaggio non trovato o non autorizzato.")
                return
            
            # Container principale
            main_frame = ttk.Frame(self.content_frame)
            main_frame.pack(fill='both', expand=True)
            
            # Header con nome personaggio
            header = ttk.Frame(main_frame)
            header.pack(fill='x', padx=10, pady=5)
            
            ttk.Label(header, text=f"📋 {character['name']}", 
                     font=('Arial', 16, 'bold')).pack(side='left')
            
            # PUNTO 11: Bottone Torna con conferma
            ttk.Button(header, text="🔙 Torna", 
                      command=lambda: self.confirm_close_character_sheet()).pack(side='right')
            
            ttk.Button(header, text="💾 Salva Tutto", 
                      command=lambda: self.save_all_character_data(self.current_sheet_pg_id),
                      style='Accent.TButton').pack(side='right', padx=5)
            
            # Notebook con tab
            notebook = ttk.Notebook(main_frame)
            notebook.pack(fill='both', expand=True, padx=10, pady=5)
            self.character_sheet_notebook = notebook
            
            # Bind per tracciare modifiche quando si cambia valore in un widget
            def mark_as_modified(event=None):
                self.has_unsaved_changes = True
            
            # Salva il bind per applicarlo dopo
            self.mark_modified_callback = mark_as_modified
            
            def on_tab_changed(event):
                if self.has_unsaved_changes:
                    self.save_all_character_data(self.current_sheet_pg_id, show_message=False)
            
            notebook.bind("<<NotebookTabChanged>>", on_tab_changed)
            
            # Crea tutte le tab
            self.create_character_info_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_abilities_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_combat_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_inventory_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_magic_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_notes_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_adventure_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_followers_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_spells_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_properties_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_mercenaries_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_advisors_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_specialists_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_scrolls_tab(notebook, self.current_sheet_pg_id, character)
            self.create_character_special_actions_tab(notebook, self.current_sheet_pg_id, character)

            preferred_tab = getattr(self, 'preferred_character_sheet_tab', None)
            if preferred_tab:
                for tab_id in notebook.tabs():
                    if notebook.tab(tab_id, 'text') == preferred_tab:
                        notebook.select(tab_id)
                        break
                self.preferred_character_sheet_tab = None
            
            def bind_character_sheet_modification_events(parent):
                for child in parent.winfo_children():
                    try:
                        if isinstance(child, (ttk.Entry, tk.Entry, ttk.Spinbox, tk.Spinbox,
                                             scrolledtext.ScrolledText, tk.Text, ttk.Combobox,
                                             tk.Checkbutton, ttk.Checkbutton)):
                            child.bind("<KeyRelease>", mark_as_modified, add="+")
                            child.bind("<FocusOut>", mark_as_modified, add="+")
                            if isinstance(child, ttk.Combobox):
                                child.bind("<<ComboboxSelected>>", mark_as_modified, add="+")
                            if isinstance(child, (tk.Checkbutton, ttk.Checkbutton)):
                                child.bind("<ButtonRelease-1>", mark_as_modified, add="+")
                    except Exception:
                        pass
                    bind_character_sheet_modification_events(child)

            bind_character_sheet_modification_events(main_frame)

        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento scheda: {e}")
            import traceback
            traceback.print_exc()

    def confirm_close_character_sheet(self):
        """Conferma chiusura scheda con salvataggio - PUNTO 11"""
        if self.has_unsaved_changes:
            result = messagebox.askyesnocancel(
                "Modifiche non salvate",
                "Hai modifiche non salvate. Vuoi salvare prima di uscire?\n\n"
                "Sì = Salva e torna\n"
                "No = Torna senza salvare\n"
                "Annulla = Rimani nella scheda"
            )
            
            if result is None:  # Annulla
                return
            elif result:  # Sì - Salva
                self.save_all_character_data(self.current_sheet_pg_id)
        
        # Torna al menu
        self.show_character_sheet_menu()
    
    def save_all_character_data(self, pg_id, show_message=True):
        """Salva tutti i dati e resetta flag modifiche"""
        if not self.save_character_data(pg_id, show_message=False):
            return
        if hasattr(self, 'thief_ability_widgets') and self.thief_ability_widgets:
            if self.save_thief_abilities(pg_id, show_message=False) is False:
                return
        if getattr(self, 'followers_dirty', False):
            if not self.save_current_follower(show_message=False):
                return
        self.has_unsaved_changes = False
        if show_message:
            messagebox.showinfo("Successo", "Scheda personaggio salvata con successo!")

    # ==================== CHARACTER RULE ENGINE ====================

    def normalize_class_code(self, classe_text):
        """Converte testo classe legacy in class_code standard."""
        text = (classe_text or "").strip().upper()
        text = re.sub(r"\s+", " ", text)
        return self.CLASS_CODE_ALIASES.get(text, text if text in self.STANDARD_CLASS_CODES else "LADRO")

    def get_character_class_code(self, character):
        """Usa class_code se presente; altrimenti normalizza classe legacy."""
        if character and character.get('class_code'):
            return self.normalize_class_code(character.get('class_code'))
        return self.normalize_class_code(character.get('classe') if character else None)

    def user_can_edit_rule_override(self, current_user=None):
        current_user = current_user or self.current_user
        return bool(current_user and current_user.get('role') == 'DM')

    def get_available_rule_classes(self):
        """Restituisce le classi regolamentari disponibili, con fallback locale."""
        fallback = [
            {'class_code': code, 'class_name': code.title()}
            for code in self.STANDARD_CLASS_CODES
        ]
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT class_code, class_name
                FROM rule_classes
                ORDER BY FIELD(class_code, 'CHIERICO','DRUIDO','GUERRIERO','LADRO','MAGO','MISTICO','ELFO','HALFLING','NANO'), class_name
            """)
            rows = cursor.fetchall()
            cursor.close()
            return rows or fallback
        except Exception:
            return fallback

    def get_rule_class_by_code(self, class_code):
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM rule_classes WHERE class_code = %s", (class_code,))
            row = cursor.fetchone()
            cursor.close()
            return row
        except Exception:
            return None

    def get_primary_requisite_score(self, character, class_code):
        """Restituisce punteggio del requisito primario in base alla classe."""
        class_row = self.get_rule_class_by_code(class_code) or {}
        requisite = (class_row.get('primary_requisite') or '').lower()
        if not requisite:
            requisite = {
                'CHIERICO': 'saggezza',
                'DRUIDO': 'saggezza',
                'GUERRIERO': 'forza',
                'LADRO': 'destrezza',
                'MAGO': 'intelligenza',
                'MISTICO': 'destrezza,forza',
                'ELFO': 'intelligenza,forza',
                'HALFLING': 'destrezza,forza',
                'NANO': 'forza',
            }.get(class_code, 'destrezza')
        ability_map = {
            'forza': 'forza',
            'intelligenza': 'intelligenza',
            'saggezza': 'saggezza',
            'destrezza': 'destrezza',
            'costituzione': 'costituzione',
            'carisma': 'carisma',
        }
        scores = []
        for label, field in ability_map.items():
            if label in requisite:
                try:
                    scores.append(int(character.get(field, 10) or 10))
                except Exception:
                    scores.append(10)
        return min(scores) if len(scores) > 1 else (scores[0] if scores else 10)

    def calculate_xp_modifier(self, character, class_code):
        """Calcola bonus/malus PX da tabella rule_primary_requisite_xp_bonus."""
        score = self.get_primary_requisite_score(character, class_code)
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT xp_modifier_percent
                FROM rule_primary_requisite_xp_bonus
                WHERE %s BETWEEN score_min AND score_max
                LIMIT 1
            """, (score,))
            row = cursor.fetchone()
            cursor.close()
            return int(row['xp_modifier_percent']) if row else 0
        except Exception:
            if score <= 5:
                return -20
            if score <= 8:
                return -10
            if score <= 12:
                return 0
            if score <= 15:
                return 5
            return 10

    def calculate_next_level_xp(self, class_code, level):
        """Legge rule_xp_progression e restituisce PX livello successivo."""
        try:
            next_level = min(int(level or 1) + 1, 36)
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT xp_required
                FROM rule_xp_progression
                WHERE class_code = %s AND level = %s
            """, (class_code, next_level))
            row = cursor.fetchone()
            cursor.close()
            return int(row['xp_required']) if row else 0
        except Exception:
            return 0

    def calculate_saving_throws_becmi(self, class_code, level):
        """Restituisce dict con le 5 categorie salvezza BECMI."""
        try:
            level = max(1, min(int(level or 1), 36))
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT morte_veleno, bacchette, paralisi_pietrificazione,
                       soffio_drago, incantesimi_verghe_bastoni
                FROM rule_saving_throws
                WHERE class_code = %s AND %s BETWEEN level_min AND level_max
                LIMIT 1
            """, (class_code, level))
            row = cursor.fetchone()
            cursor.close()
            if row:
                return row
        except Exception:
            pass
        return {}

    def calculate_thac0_becmi(self, class_code, level):
        """Restituisce THAC0 da rule_thac0."""
        try:
            level = max(1, min(int(level or 1), 36))
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT thac0
                FROM rule_thac0
                WHERE class_code = %s AND %s BETWEEN level_min AND level_max
                LIMIT 1
            """, (class_code, level))
            row = cursor.fetchone()
            cursor.close()
            return int(row['thac0']) if row else None
        except Exception:
            return None

    def get_rule_value(self, pg_id, scope, field_name, automatic_value):
        """
        Restituisce il valore effettivo.
        Se esiste override DM attivo usa override_value, altrimenti automatic_value.
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT override_value, reason
                FROM pc_rule_overrides
                WHERE pg_id = %s AND scope = %s AND field_name = %s AND is_active = 1
                LIMIT 1
            """, (pg_id, scope, field_name))
            row = cursor.fetchone()
            cursor.close()
            if row:
                return {
                    'automatic': automatic_value,
                    'effective': row.get('override_value'),
                    'is_override': True,
                    'reason': row.get('reason') or '',
                }
        except Exception:
            pass
        return {
            'automatic': automatic_value,
            'effective': automatic_value,
            'is_override': False,
            'reason': '',
        }

    def get_table_columns(self, table_name):
        """Restituisce le colonne reali della tabella, utile durante migrazioni manuali."""
        try:
            cursor = self.db.cursor()
            cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
            rows = cursor.fetchall()
            cursor.close()
            return {row.get('Field') for row in rows}
        except Exception:
            return set()

    def calculate_ability_modifier(self, score):
        """Calcola bonus/malus caratteristica dal valore attuale."""
        try:
            score = int(score or 10)
        except Exception:
            score = 10
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT modifier
                FROM rule_ability_modifiers
                WHERE %s BETWEEN score_min AND score_max
                LIMIT 1
            """, (score,))
            row = cursor.fetchone()
            cursor.close()
            if row and row.get('modifier') is not None:
                return int(row.get('modifier'))
        except Exception:
            pass
        return self.calculate_classic_modifier(score)

    def format_ability_modifier(self, score):
        modifier = self.calculate_ability_modifier(score)
        return f"{modifier:+d}"

    def format_hit_die_with_constitution(self, hit_die, constitution_score):
        """Mostra il dado vita con bonus/malus Costituzione applicato."""
        hit_die = str(hit_die or '').strip()
        con_mod = self.calculate_ability_modifier(constitution_score)
        if not hit_die or con_mod == 0:
            return hit_die
        sign = '+' if con_mod > 0 else ''
        return f"{hit_die}{sign}{con_mod} Cos"

    def refresh_ability_modifiers_widgets(self, pg_id=None):
        """Aggiorna bonus/malus caratteristiche usando sempre il valore attuale."""
        if not hasattr(self, 'char_widgets'):
            return
        for ability in ['forza', 'intelligenza', 'saggezza', 'destrezza', 'costituzione', 'carisma']:
            current_widget = self.char_widgets.get(ability)
            mod_widget = self.char_widgets.get(f'{ability}_mod_display')
            if not current_widget or not mod_widget:
                continue
            modifier_text = self.format_ability_modifier(current_widget.get())
            mod_widget.configure(state='normal')
            mod_widget.delete(0, 'end')
            mod_widget.insert(0, modifier_text)
            mod_widget.configure(state='readonly')
        if pg_id:
            self.refresh_character_rule_summary_widgets(pg_id)

    def normalize_weapon_type(self, weapon_type):
        text = (weapon_type or '').strip()
        aliases = {
            'Mischia': 'Corpo a Corpo',
            'MISCHIA': 'Corpo a Corpo',
            'Corpo a Corpo': 'Corpo a Corpo',
            'Corpo a Corpo & Lancio': 'Corpo a Corpo & Lancio',
            'Magica Lancio': 'Corpo a Corpo & Lancio',
            'Lancio': 'Lancio',
            'LANCIO': 'Lancio',
            'Tiro': 'Tiro',
            'TIRO': 'Tiro',
        }
        return aliases.get(text, text if text in self.get_weapon_type_options() else 'Corpo a Corpo')

    def get_weapon_type_options(self):
        return ["Corpo a Corpo", "Corpo a Corpo & Lancio", "Lancio", "Tiro"]

    def get_equipped_weapon_count(self, pg_id, exclude_weapon_id=None):
        try:
            cursor = self.db.cursor()
            if exclude_weapon_id:
                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM pc_armi
                    WHERE pg_id = %s AND COALESCE(equipped, 0) = 1 AND id <> %s
                """, (pg_id, exclude_weapon_id))
            else:
                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM pc_armi
                    WHERE pg_id = %s AND COALESCE(equipped, 0) = 1
                """, (pg_id,))
            row = cursor.fetchone()
            cursor.close()
            return int(row.get('total') or 0)
        except Exception:
            return 0

    def validate_equipped_weapon_limit(self, pg_id, equipped, exclude_weapon_id=None):
        if not equipped:
            return True
        if self.get_equipped_weapon_count(pg_id, exclude_weapon_id) >= 2:
            messagebox.showwarning("Armi impugnate", "Puoi avere al massimo 2 armi impugnate.")
            return False
        return True

    def calculate_weapon_thac0_rows(self, character, weapon, base_thac0):
        try:
            base_thac0 = int(base_thac0)
        except Exception:
            base_thac0 = 20
        weapon_bonus = int(weapon.get('bonus_magico') or 0)
        strength_mod = self.calculate_ability_modifier(character.get('forza', 10))
        dexterity_mod = self.calculate_ability_modifier(character.get('destrezza', 10))
        weapon_type = self.normalize_weapon_type(weapon.get('tipo'))

        melee_thac0 = base_thac0 - strength_mod - weapon_bonus
        ranged_medium = base_thac0 - dexterity_mod - weapon_bonus
        rows = []
        if weapon_type in ("Corpo a Corpo", "Corpo a Corpo & Lancio"):
            rows.append(("Corpo a corpo", melee_thac0, strength_mod, f"{weapon_bonus + strength_mod:+d}"))
        if weapon_type in ("Corpo a Corpo & Lancio", "Lancio", "Tiro"):
            damage_bonus = weapon_bonus + strength_mod if weapon_type in ("Corpo a Corpo & Lancio", "Lancio") else weapon_bonus
            rows.extend([
                ("Raggio corto", ranged_medium - 1, dexterity_mod, f"{damage_bonus:+d}"),
                ("Raggio medio", ranged_medium, dexterity_mod, f"{damage_bonus:+d}"),
                ("Raggio lungo", ranged_medium + 1, dexterity_mod, f"{damage_bonus:+d}"),
            ])
        return rows

    def get_current_character_sheet_tab_text(self):
        notebook = getattr(self, 'character_sheet_notebook', None)
        if not notebook:
            return None
        try:
            return notebook.tab(notebook.select(), 'text')
        except Exception:
            return None

    def refresh_character_sheet_preserving_tab(self, pg_id, preferred_tab=None):
        self.preferred_character_sheet_tab = preferred_tab or self.get_current_character_sheet_tab_text()
        self.show_character_sheet(pg_id)

    def set_rule_override(self, pg_id, scope, field_name, automatic_value, override_value, reason, current_user=None):
        """Solo DM. Crea o aggiorna override."""
        current_user = current_user or self.current_user
        if not self.user_can_edit_rule_override(current_user):
            messagebox.showerror("Errore", "Solo il DM puo' sovrascrivere valori regolamentari.")
            return False
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO pc_rule_overrides
                    (pg_id, scope, field_name, automatic_value, override_value, is_active, reason, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
                ON DUPLICATE KEY UPDATE
                    automatic_value = VALUES(automatic_value),
                    override_value = VALUES(override_value),
                    is_active = 1,
                    reason = VALUES(reason),
                    created_by_user_id = VALUES(created_by_user_id),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                pg_id, scope, field_name, str(automatic_value) if automatic_value is not None else None,
                str(override_value) if override_value is not None else None,
                reason, current_user.get('id')
            ))
            self.db.commit()
            cursor.close()
            return True
        except Exception as e:
            messagebox.showerror("Errore", f"Errore override DM: {e}")
            return False

    def clear_rule_override(self, pg_id, scope, field_name, current_user=None):
        """Solo DM. Disattiva override e torna al valore automatico."""
        current_user = current_user or self.current_user
        if not self.user_can_edit_rule_override(current_user):
            messagebox.showerror("Errore", "Solo il DM puo' ripristinare valori automatici.")
            return False
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE pc_rule_overrides
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE pg_id = %s AND scope = %s AND field_name = %s
            """, (pg_id, scope, field_name))
            self.db.commit()
            cursor.close()
            return True
        except Exception as e:
            messagebox.showerror("Errore", f"Errore ripristino automatico: {e}")
            return False

    def calculate_character_rule_summary(self, pg_id):
        """Restituisce tutti i valori automatici principali per la scheda."""
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM player_characters WHERE id = %s", (pg_id,))
        character = cursor.fetchone()
        cursor.close()
        if not character:
            return {}

        class_code = self.get_character_class_code(character)
        level = max(1, min(int(character.get('livello') or 1), 36))
        class_row = self.get_rule_class_by_code(class_code) or {}
        saves = self.calculate_saving_throws_becmi(class_code, level)
        thac0 = self.calculate_thac0_becmi(class_code, level)
        xp_modifier = self.calculate_xp_modifier(character, class_code)
        next_xp = self.calculate_next_level_xp(class_code, level)
        constitution_score = int(character.get('costituzione') or 10)
        hit_die_base = class_row.get('hit_die') or ''
        hit_die_effective = self.format_hit_die_with_constitution(hit_die_base, constitution_score)

        mapped_saves = {
            'ts_raggio': saves.get('morte_veleno'),
            'ts_veleno': saves.get('morte_veleno'),
            'ts_bacchetta': saves.get('bacchette'),
            'ts_paralisi': saves.get('paralisi_pietrificazione'),
            'ts_pietrificazione': saves.get('paralisi_pietrificazione'),
            'ts_soffio': saves.get('soffio_drago'),
            'ts_incantesimi': saves.get('incantesimi_verghe_bastoni'),
        }
        return {
            'class_code': class_code,
            'class_name': class_row.get('class_name') or class_code.title(),
            'level': level,
            'primary_requisite': class_row.get('primary_requisite') or '',
            'hit_die': hit_die_effective,
            'hit_die_base': hit_die_base,
            'constitution_modifier': self.calculate_ability_modifier(constitution_score),
            'xp_modifier': xp_modifier,
            'next_level_xp': next_xp,
            'thac0': thac0,
            'saving_throws': mapped_saves,
        }

    def refresh_character_rule_summary_widgets(self, pg_id):
        summary = self.calculate_character_rule_summary(pg_id)
        if not summary:
            return
        live_hit_die = summary.get('hit_die')
        try:
            class_widget = getattr(self, 'char_widgets', {}).get('classe')
            constitution_widget = getattr(self, 'char_widgets', {}).get('costituzione')
            if class_widget and constitution_widget:
                class_label = class_widget.get() or ''
                class_code = getattr(self, 'rule_class_code_by_label', {}).get(class_label)
                if not class_code:
                    class_code = self.normalize_class_code(class_label)
                class_row = self.get_rule_class_by_code(class_code) or {}
                live_hit_die = self.format_hit_die_with_constitution(
                    class_row.get('hit_die') or summary.get('hit_die_base') or '',
                    constitution_widget.get()
                )
        except Exception:
            live_hit_die = summary.get('hit_die')
        for key, value in {
            'requisito_primario': summary.get('primary_requisite'),
            'modificatore_px': summary.get('xp_modifier'),
            'px_prossimo_livello': summary.get('next_level_xp'),
            'dado_vita': live_hit_die,
        }.items():
            widget = getattr(self, 'char_widgets', {}).get(key)
            if widget:
                widget.configure(state='normal')
                widget.delete(0, 'end')
                widget.insert(0, '' if value is None else str(value))
                widget.configure(state='readonly')

    def calculate_thief_abilities_becmi(self, level):
        """Legge rule_thief_abilities e restituisce dict abilita ladro."""
        try:
            level = max(1, min(int(level or 1), 36))
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM rule_thief_abilities WHERE level = %s", (level,))
            row = cursor.fetchone()
            cursor.close()
            return row or {}
        except Exception:
            return {}

    def get_effective_thief_ability(self, pg_id, field_name, automatic_value):
        """Applica override DM su singola abilita ladro."""
        return self.get_rule_value(pg_id, 'thief_abilities', field_name, automatic_value)

    def calculate_turn_undead(self, class_code, level):
        """Restituisce righe scacciare non-morti per livello se la classe lo usa."""
        class_row = self.get_rule_class_by_code(class_code) or {}
        if not class_row.get('uses_turn_undead'):
            return []
        try:
            level = max(1, min(int(level or 1), 36))
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT undead_type, result_value
                FROM rule_turn_undead
                WHERE %s BETWEEN cleric_level_min AND cleric_level_max
                ORDER BY FIELD(undead_type, 'Scheletro','Zombi','Ghoul','Necrospettro','Mummia','Spettro','Vampiro','Fantasma','Lich','Speciale'), undead_type
            """, (level,))
            rows = cursor.fetchall()
            cursor.close()
            return rows or []
        except Exception:
            return []

    def calculate_spell_slots(self, class_code, character_level):
        """Restituisce dict spell_level -> slots."""
        try:
            character_level = max(1, min(int(character_level or 1), 36))
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT spell_level, slots
                FROM rule_spell_slots
                WHERE class_code = %s AND character_level = %s
                ORDER BY spell_level
            """, (class_code, character_level))
            rows = cursor.fetchall()
            cursor.close()
            return {int(row['spell_level']): int(row['slots']) for row in rows}
        except Exception:
            return {}

    def get_character_spell_list_type(self, class_code):
        """Restituisce il tipo lista incantesimi della classe."""
        class_row = self.get_rule_class_by_code(class_code) or {}
        return class_row.get('spell_list_type') or None

    def get_effective_spell_slots(self, pg_id, class_code, character_level):
        automatic_slots = self.calculate_spell_slots(class_code, character_level)
        effective = {}
        for spell_level, slots in automatic_slots.items():
            rule_value = self.get_rule_value(pg_id, 'spell_slots', f'slot_livello_{spell_level}', slots)
            try:
                effective[spell_level] = int(rule_value.get('effective') or 0)
            except Exception:
                effective[spell_level] = slots
        return effective

    def refresh_spell_preparation_limits(self, pg_id):
        """Controlla che i preparati non superino slot effettivi, salvo override DM."""
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM player_characters WHERE id = %s", (pg_id,))
            character = cursor.fetchone()
            cursor.close()
            if not character:
                return {}
            class_code = self.get_character_class_code(character)
            level = int(character.get('livello') or 1)
            slots = self.get_effective_spell_slots(pg_id, class_code, level)
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT spell_level, COALESCE(SUM(prepared_count), 0) AS prepared,
                       COALESCE(SUM(cast_count), 0) AS casted
                FROM pc_spell_prepared
                WHERE pg_id = %s
                GROUP BY spell_level
            """, (pg_id,))
            structured = {int(r['spell_level']): r for r in cursor.fetchall()}
            cursor.close()
            result = {}
            for spell_level in sorted(set(slots) | set(structured)):
                prepared = int(structured.get(spell_level, {}).get('prepared') or 0)
                casted = int(structured.get(spell_level, {}).get('casted') or 0)
                available = max(0, int(slots.get(spell_level, 0)) - casted)
                result[spell_level] = {
                    'slots': int(slots.get(spell_level, 0)),
                    'prepared': prepared,
                    'casted': casted,
                    'available': available,
                    'over_limit': prepared > int(slots.get(spell_level, 0)),
                }
            return result
        except Exception:
            return {}

    def _dexterity_ac_modifier(self, dexterity_score):
        try:
            score = int(dexterity_score or 10)
        except Exception:
            score = 10
        if score <= 3:
            return 3
        if score <= 5:
            return 2
        if score <= 8:
            return 1
        if score <= 12:
            return 0
        if score <= 15:
            return -1
        if score <= 17:
            return -2
        return -3

    def calculate_armor_class(self, pg_id):
        """
        Calcola CA automatica da armatura equipaggiata, scudo, bonus magici e Destrezza.
        Ritorna automatico/effettivo via override DM.
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT destrezza FROM player_characters WHERE id = %s", (pg_id,))
            character = cursor.fetchone() or {}
            cursor.execute("""
                SELECT pa.*, COALESCE(pa.base_ac, ra.base_ac) AS calc_base_ac,
                       COALESCE(pa.bonus_magico, 0) AS magic_bonus,
                       COALESCE(pa.equipped, 0) AS is_equipped,
                       COALESCE(ra.armor_type, 'ARMATURA') AS armor_type,
                       COALESCE(ra.ac_bonus, 0) AS rule_ac_bonus
                FROM pc_armature pa
                LEFT JOIN rule_armor ra ON pa.rule_armor_id = ra.id
                WHERE pa.pg_id = %s AND COALESCE(pa.equipped, 0) = 1
            """, (pg_id,))
            equipped = cursor.fetchall()
            cursor.close()

            base_ac = 9
            shield_bonus = 0
            magic_bonus = 0
            warnings = []
            armors = [row for row in equipped if row.get('armor_type') == 'ARMATURA']
            shields = [row for row in equipped if row.get('armor_type') == 'SCUDO']
            if len(armors) > 1:
                warnings.append("Piu armature equipaggiate: uso la CA migliore.")
            if armors:
                base_candidates = [int(row.get('calc_base_ac')) for row in armors if row.get('calc_base_ac') is not None]
                if base_candidates:
                    base_ac = min(base_candidates)
            for shield in shields:
                shield_bonus += int(shield.get('rule_ac_bonus') or 1)
            for row in equipped:
                magic_bonus += int(row.get('magic_bonus') or 0)
            dex_mod = self._dexterity_ac_modifier(character.get('destrezza', 10))
            automatic_ac = base_ac + dex_mod - shield_bonus - magic_bonus
            rule_value = self.get_rule_value(pg_id, 'armor_class', 'classe_armatura_effettiva', automatic_ac)
            return {
                'automatic': automatic_ac,
                'effective': rule_value.get('effective'),
                'is_override': rule_value.get('is_override'),
                'reason': rule_value.get('reason'),
                'warnings': warnings,
            }
        except Exception:
            return {'automatic': None, 'effective': None, 'is_override': False, 'reason': '', 'warnings': []}

    def validate_equipment_allowed_for_class(self, class_code, item_type, rule_item_id):
        """Restituisce allowed/warning/forbidden per restrizioni classe."""
        table_map = {
            'weapon': ('rule_weapons', 'allowed_class_codes', 'forbidden_class_codes'),
            'armor': ('rule_armor', 'allowed_class_codes', 'forbidden_class_codes'),
        }
        if item_type not in table_map or not rule_item_id:
            return {'status': 'allowed', 'message': ''}
        table, allowed_col, forbidden_col = table_map[item_type]
        try:
            cursor = self.db.cursor()
            cursor.execute(f"SELECT {allowed_col} AS allowed_codes, {forbidden_col} AS forbidden_codes FROM {table} WHERE id = %s", (rule_item_id,))
            row = cursor.fetchone() or {}
            cursor.close()
            forbidden = [x.strip().upper() for x in (row.get('forbidden_codes') or '').split(',') if x.strip()]
            allowed = [x.strip().upper() for x in (row.get('allowed_codes') or '').split(',') if x.strip()]
            if class_code in forbidden:
                return {'status': 'forbidden', 'message': f"Oggetto vietato per {class_code}."}
            if allowed and class_code not in allowed:
                return {'status': 'warning', 'message': f"Oggetto non incluso tra quelli consentiti per {class_code}."}
            return {'status': 'allowed', 'message': ''}
        except Exception:
            return {'status': 'allowed', 'message': ''}

    def update_character_equipment_calculations(self, pg_id):
        """Aggiorna la CA effettiva in player_characters."""
        ac = self.calculate_armor_class(pg_id)
        cursor = self.db.cursor()
        cursor.execute("""
            UPDATE player_characters
            SET classe_armatura = %s
            WHERE id = %s
        """, (
            ac.get('effective') if ac.get('effective') is not None else ac.get('automatic'),
            pg_id,
        ))
        self.db.commit()
        cursor.close()
        return {'armor_class': ac}
    
    def create_character_info_tab(self, notebook, pg_id, character):
        """Tab Info Base - CORRETTO con solo grid() e linguaggi integrati"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Info Base")
        
        # Canvas con scrollbar
        canvas = tk.Canvas(tab)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def scroll_info_page(event):
            delta = -1 if getattr(event, "num", None) == 5 else 1
            if hasattr(event, "delta") and event.delta:
                delta = -1 * int(event.delta / 120)
            canvas.yview_scroll(delta, "units")

        def bind_info_mousewheel(widget):
            widget.bind("<MouseWheel>", scroll_info_page, add="+")
            widget.bind("<Button-4>", scroll_info_page, add="+")
            widget.bind("<Button-5>", scroll_info_page, add="+")
            for child in widget.winfo_children():
                bind_info_mousewheel(child)
        
        if not hasattr(self, 'char_widgets'):
            self.char_widgets = {}
        
        current_row = 0
        
        # Configura colonna per espansione
        scrollable_frame.columnconfigure(0, weight=1)
        
        # === SEZIONE 1: Dati Principali e Linguaggi ===
        section1 = ttk.LabelFrame(scrollable_frame, text="Dati Principali e Linguaggi", padding=10)
        section1.grid(row=current_row, column=0, sticky='ew', padx=10, pady=5)
        current_row += 1
        
        # Nome (riga 0)
        ttk.Label(section1, text="Nome:").grid(row=0, column=0, sticky='w', padx=5, pady=3)
        ttk.Label(section1, text=character['name'], font=('Arial', 10, 'bold')).grid(
            row=0, column=1, sticky='w', padx=5, pady=3)
        
        # Classe (riga 0)
        rule_classes = self.get_available_rule_classes()
        self.rule_class_name_by_code = {row['class_code']: row['class_name'] for row in rule_classes}
        self.rule_class_code_by_label = {
            f"{row['class_name']} ({row['class_code']})": row['class_code']
            for row in rule_classes
        }
        selected_class_code = self.get_character_class_code(character)
        selected_class_label = next(
            (label for label, code in self.rule_class_code_by_label.items() if code == selected_class_code),
            f"{character.get('classe', 'Ladro') or 'Ladro'} ({selected_class_code})"
        )
        ttk.Label(section1, text="Classe:").grid(row=0, column=2, sticky='w', padx=5, pady=3)
        self.char_widgets['classe'] = ttk.Combobox(section1, width=28, state='readonly')
        self.char_widgets['classe']['values'] = list(self.rule_class_code_by_label.keys())
        self.char_widgets['classe'].set(selected_class_label)
        self.char_widgets['classe'].grid(row=0, column=3, sticky='w', padx=5, pady=3)
        self.char_widgets['class_code'] = self.char_widgets['classe']
        
        # Livello (riga 1)
        ttk.Label(section1, text="Livello:").grid(row=1, column=0, sticky='w', padx=5, pady=3)
        self.char_widgets['livello'] = ttk.Spinbox(section1, from_=1, to=36, width=10)
        self.char_widgets['livello'].set(character.get('livello', 1) or 1)
        self.char_widgets['livello'].grid(row=1, column=1, sticky='w', padx=5, pady=3)
        
        # Titolo (riga 1)
        ttk.Label(section1, text="Titolo:").grid(row=1, column=2, sticky='w', padx=5, pady=3)
        self.char_widgets['titolo'] = ttk.Entry(section1, width=20)
        self.char_widgets['titolo'].insert(0, character.get('titolo', '') or '')
        self.char_widgets['titolo'].grid(row=1, column=3, sticky='w', padx=5, pady=3)

        rules_frame = ttk.Frame(section1)
        rules_frame.grid(row=4, column=0, columnspan=4, sticky='ew', pady=(8, 2))

        rule_fields = [
            ('px_attuali', 'PX attuali', False),
            ('px_prossimo_livello', 'PX prossimo livello', True),
            ('requisito_primario', 'Requisito primario', True),
            ('modificatore_px', 'Modificatore PX %', True),
            ('dado_vita', 'Dado vita', True),
        ]
        for i, (field, label, readonly) in enumerate(rule_fields):
            row = i // 3
            col = (i % 3) * 2
            ttk.Label(rules_frame, text=f"{label}:").grid(row=row, column=col, sticky='w', padx=5, pady=3)
            self.char_widgets[field] = ttk.Entry(rules_frame, width=20)
            self.char_widgets[field].insert(0, character.get(field, '') if character.get(field, '') is not None else '')
            self.char_widgets[field].grid(row=row, column=col + 1, sticky='w', padx=5, pady=3)
            if readonly:
                self.char_widgets[field].configure(state='readonly')

        def refresh_rules_from_info(event=None):
            if self.save_character_data(pg_id, show_message=False):
                self.refresh_character_rule_summary_widgets(pg_id)

        self.char_widgets['classe'].bind("<<ComboboxSelected>>", refresh_rules_from_info, add="+")
        self.char_widgets['livello'].bind("<FocusOut>", refresh_rules_from_info, add="+")
        self.refresh_character_rule_summary_widgets(pg_id)
        
        # LINGUAGGI INTEGRATI (riga 2-3)
        ttk.Label(section1, text="Linguaggi:", font=('Arial', 9, 'bold')).grid(
            row=2, column=0, sticky='nw', padx=5, pady=10)
        
        # Frame per linguaggi
        lang_frame = ttk.Frame(section1)
        lang_frame.grid(row=2, column=1, columnspan=3, sticky='w', padx=5, pady=5)
        
        # Listbox per linguaggi
        self.languages_listbox = tk.Listbox(lang_frame, height=4, width=18)
        self.languages_listbox.pack(side='left', fill='y')
        
        lang_scroll = ttk.Scrollbar(lang_frame, orient='vertical', command=self.languages_listbox.yview)
        lang_scroll.pack(side='right', fill='y')
        self.languages_listbox.config(yscrollcommand=lang_scroll.set)
        
        # Bottoni linguaggi (riga 3)
        lang_btn_frame = ttk.Frame(section1)
        lang_btn_frame.grid(row=3, column=1, columnspan=3, sticky='w', padx=5, pady=2)
        
        ttk.Button(lang_btn_frame, text="➕ Aggiungi Lingua", 
                  command=lambda: self.add_language_inline(pg_id)).pack(side='left', padx=2)
        ttk.Button(lang_btn_frame, text="🗑️ Rimuovi Lingua", 
                  command=lambda: self.delete_language_inline(pg_id)).pack(side='left', padx=2)
        
        # Carica linguaggi
        self.refresh_language_inline(pg_id)
        
        # === SEZIONE 2: Abilità ===
        section2 = ttk.LabelFrame(scrollable_frame, text="Abilità", padding=10)
        section2.grid(row=current_row, column=0, sticky='ew', padx=10, pady=5)
        current_row += 1
        
        for col, label in enumerate(['Abilita', 'Valore Base', 'Valore attuale', 'Bonus/Malus', 'Motivo']):
            ttk.Label(section2, text=label, font=('Arial', 9, 'bold')).grid(
                row=0, column=col, sticky='w', padx=5, pady=(0, 5))

        abilities = ['forza', 'intelligenza', 'saggezza', 'destrezza', 'costituzione', 'carisma']
        for i, ability in enumerate(abilities, start=1):
            base_value = character.get(f'{ability}_base')
            if base_value is None:
                base_value = character.get(ability, 10) or 10
            current_value = character.get(ability, 10) or 10

            ttk.Label(section2, text=f"{ability.capitalize()}:").grid(
                row=i, column=0, sticky='w', padx=5, pady=3)

            self.char_widgets[f'{ability}_base'] = ttk.Spinbox(section2, from_=3, to=25, width=10)
            self.char_widgets[f'{ability}_base'].set(base_value)
            self.char_widgets[f'{ability}_base'].grid(row=i, column=1, sticky='w', padx=5, pady=3)

            self.char_widgets[ability] = ttk.Spinbox(section2, from_=3, to=25, width=10)
            self.char_widgets[ability].set(current_value)
            self.char_widgets[ability].grid(row=i, column=2, sticky='w', padx=5, pady=3)

            self.char_widgets[f'{ability}_mod_display'] = ttk.Entry(section2, width=10, state='readonly')
            self.char_widgets[f'{ability}_mod_display'].grid(row=i, column=3, sticky='w', padx=5, pady=3)

            self.char_widgets[f'{ability}_motivo'] = ttk.Entry(section2, width=45)
            self.char_widgets[f'{ability}_motivo'].insert(0, character.get(f'{ability}_motivo', '') or '')
            self.char_widgets[f'{ability}_motivo'].grid(row=i, column=4, sticky='ew', padx=5, pady=3)

            self.char_widgets[ability].bind(
                "<FocusOut>",
                lambda event, pg=pg_id: self.refresh_ability_modifiers_widgets(pg),
                add="+"
            )
            self.char_widgets[ability].bind(
                "<KeyRelease>",
                lambda event, pg=pg_id: self.refresh_ability_modifiers_widgets(pg),
                add="+"
            )

        section2.columnconfigure(4, weight=1)
        self.refresh_ability_modifiers_widgets(pg_id)
        
        # === SEZIONE 3: Allineamento ===
        section3 = ttk.LabelFrame(scrollable_frame, text="Allineamento", padding=10)
        section3.grid(row=current_row, column=0, sticky='ew', padx=10, pady=5)
        current_row += 1
        
        self.char_widgets['legale'] = tk.BooleanVar(value=bool(character.get('legale', 0)))
        self.char_widgets['neutrale'] = tk.BooleanVar(value=bool(character.get('neutrale', 0)))
        self.char_widgets['caotico'] = tk.BooleanVar(value=bool(character.get('caotico', 0)))
        
        ttk.Checkbutton(section3, text="Legale", variable=self.char_widgets['legale']).grid(
            row=0, column=0, padx=10, pady=5)
        ttk.Checkbutton(section3, text="Neutrale", variable=self.char_widgets['neutrale']).grid(
            row=0, column=1, padx=10, pady=5)
        ttk.Checkbutton(section3, text="Caotico", variable=self.char_widgets['caotico']).grid(
            row=0, column=2, padx=10, pady=5)
        
        # === SEZIONE 4: Aspetto ===
        section4 = ttk.LabelFrame(scrollable_frame, text="Aspetto", padding=10)
        section4.grid(row=current_row, column=0, sticky='ew', padx=10, pady=5)
        current_row += 1
        
        appearance_fields = [
            ('sesso', 'Sesso'), ('eta', 'Età'), ('capelli', 'Capelli'), ('occhi', 'Occhi'),
            ('pelle', 'Pelle'), ('altezza', 'Altezza'), ('peso', 'Peso'), ('luogo_origine', 'Luogo Origine'),
            ('compleanno', 'Compleanno'), ('nome_famiglia', 'Nome Famiglia'), ('nome_padre', 'Nome Padre'),
            ('classe_sociale', 'Classe Sociale'), ('soprannome', 'Soprannome')
        ]
        
        for i, (field, label) in enumerate(appearance_fields):
            row = i // 2
            col = (i % 2) * 2
            ttk.Label(section4, text=f"{label}:").grid(row=row, column=col, sticky='w', padx=5, pady=3)
            if field == 'eta':
                self.char_widgets[field] = ttk.Spinbox(section4, from_=0, to=999, width=18)
                self.char_widgets[field].set(character.get(field, 0) or 0)
            else:
                self.char_widgets[field] = ttk.Entry(section4, width=20)
                self.char_widgets[field].insert(0, character.get(field, '') or '')
            self.char_widgets[field].grid(row=row, column=col+1, sticky='w', padx=5, pady=3)
        
        # === SEZIONE 5: Background ===
        section5 = ttk.LabelFrame(scrollable_frame, text="Background/Storia", padding=10)
        section5.grid(row=current_row, column=0, sticky='ew', padx=10, pady=5)
        current_row += 1
        
        self.char_widgets['background'] = scrolledtext.ScrolledText(section5, height=8, wrap='word')
        self.char_widgets['background'].insert('1.0', character.get('background', '') or '')
        self.char_widgets['background'].grid(row=0, column=0, sticky='ew')
        section5.columnconfigure(0, weight=1)

        ttk.Label(section5, text="Manierismo:").grid(row=1, column=0, sticky='w', pady=(8, 2))
        self.char_widgets['manierismo'] = scrolledtext.ScrolledText(section5, height=4, wrap='word')
        self.char_widgets['manierismo'].insert('1.0', character.get('manierismo', '') or '')
        self.char_widgets['manierismo'].grid(row=2, column=0, sticky='ew')

        ttk.Label(section5, text="Bonus Speciali:").grid(row=3, column=0, sticky='w', pady=(8, 2))
        self.char_widgets['bonus_speciali'] = scrolledtext.ScrolledText(section5, height=4, wrap='word')
        self.char_widgets['bonus_speciali'].insert('1.0', character.get('bonus_speciali', '') or '')
        self.char_widgets['bonus_speciali'].grid(row=4, column=0, sticky='ew')
        
        # === SEZIONE 6+7: Cavalcature e Creature Familiari ===
        mounts_frame = ttk.Frame(scrollable_frame)
        mounts_frame.grid(row=current_row, column=0, sticky='ew', padx=10, pady=5)
        mounts_frame.columnconfigure(0, weight=1)
        current_row += 1
        
        # Cavalcature
        section7 = ttk.LabelFrame(mounts_frame, text="Cavalcature", padding=10)
        section7.grid(row=0, column=0, sticky='nsew')
        section7.columnconfigure(0, weight=1)
        
        mount_columns = ('tipo', 'nome', 'ca', 'pf', 'movimento', 'carico', 'capacita', 'salute', 'luogo')
        self.info_mount_tree = ttk.Treeview(section7, columns=mount_columns, show='headings', height=5)
        mount_labels = {
            'tipo': 'Tipo', 'nome': 'Nome', 'ca': 'CA', 'pf': 'PF',
            'movimento': 'Mov.', 'carico': 'Carico', 'capacita': 'Capacita',
            'salute': 'Salute', 'luogo': 'Luogo'
        }
        for col in mount_columns:
            self.info_mount_tree.heading(col, text=mount_labels[col])
            self.info_mount_tree.column(col, width=75 if col not in ('nome', 'luogo') else 120)
        self.info_mount_tree.grid(row=0, column=0, sticky='nsew')
        
        mount_scroll = ttk.Scrollbar(section7, orient='vertical', command=self.info_mount_tree.yview)
        mount_scroll.grid(row=0, column=1, sticky='ns')
        self.info_mount_tree.config(yscrollcommand=mount_scroll.set)
        
        mount_btn_frame = ttk.Frame(section7)
        mount_btn_frame.grid(row=1, column=0, columnspan=2, pady=5)
        ttk.Button(mount_btn_frame, text='➕ Aggiungi', 
                  command=lambda: self.add_mount_dialog(pg_id, self.info_mount_tree)).pack(side='left', padx=2)
        ttk.Button(mount_btn_frame, text='✏️ Modifica', 
                  command=lambda: self.edit_mount_dialog(pg_id, self.info_mount_tree)).pack(side='left', padx=2)
        ttk.Button(mount_btn_frame, text='🗑️ Elimina', 
                  command=lambda: self.delete_mount(pg_id, self.info_mount_tree)).pack(side='left', padx=2)
        
        # Creature familiari
        section8 = ttk.LabelFrame(mounts_frame, text="Creature Familiari", padding=10)
        section8.grid(row=1, column=0, sticky='nsew', pady=(8, 0))
        section8.columnconfigure(0, weight=1)
        
        familiar_columns = ('nome', 'classe_armatura', 'dadi_vita', 'movimento', 'attacchi', 'pf', 'ts')
        self.info_familiar_tree = ttk.Treeview(section8, columns=familiar_columns, show='headings', height=5)
        self.info_familiar_tree.heading('nome', text='Nome')
        self.info_familiar_tree.heading('classe_armatura', text='CA')
        self.info_familiar_tree.heading('dadi_vita', text='Dadi Vita')
        self.info_familiar_tree.heading('movimento', text='Movimento')
        self.info_familiar_tree.heading('attacchi', text='Attacchi')
        self.info_familiar_tree.heading('pf', text='PF')
        self.info_familiar_tree.heading('ts', text='TS')
        self.info_familiar_tree.column('nome', width=120)
        self.info_familiar_tree.column('classe_armatura', width=70)
        self.info_familiar_tree.column('dadi_vita', width=80)
        self.info_familiar_tree.column('movimento', width=70)
        self.info_familiar_tree.column('attacchi', width=70)
        self.info_familiar_tree.column('pf', width=50)
        self.info_familiar_tree.column('ts', width=80)
        self.info_familiar_tree.grid(row=0, column=0, sticky='nsew')
        
        familiar_scroll = ttk.Scrollbar(section8, orient='vertical', command=self.info_familiar_tree.yview)
        familiar_scroll.grid(row=0, column=1, sticky='ns')
        self.info_familiar_tree.config(yscrollcommand=familiar_scroll.set)
        
        familiar_btn_frame = ttk.Frame(section8)
        familiar_btn_frame.grid(row=1, column=0, columnspan=2, pady=5)
        ttk.Button(familiar_btn_frame, text='➕ Aggiungi', 
                  command=lambda: self.add_familiar_dialog(pg_id, self.info_familiar_tree)).pack(side='left', padx=2)
        ttk.Button(familiar_btn_frame, text='✏️ Modifica', 
                  command=lambda: self.edit_familiar_dialog(pg_id, self.info_familiar_tree)).pack(side='left', padx=2)
        ttk.Button(familiar_btn_frame, text='🗑️ Elimina', 
                  command=lambda: self.delete_familiar(pg_id, self.info_familiar_tree)).pack(side='left', padx=2)
        
        self.refresh_mount_list(pg_id, self.info_mount_tree)
        self.refresh_familiar_list(pg_id, self.info_familiar_tree)
        bind_info_mousewheel(tab)

    def refresh_language_inline(self, pg_id):
        """Ricarica linguaggi inline"""
        try:
            self.languages_listbox.delete(0, 'end')
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_linguaggi WHERE pg_id = %s ORDER BY lingua", (pg_id,))
            languages = cursor.fetchall()
            cursor.close()
            
            # Salva IDs
            if not hasattr(self, 'language_ids'):
                self.language_ids = {}
            
            for lang in languages:
                self.languages_listbox.insert('end', lang['lingua'])
                self.language_ids[lang['lingua']] = lang['id']
        except Exception as e:
            print(f"Errore refresh linguaggi: {e}")
    
    def add_language_inline(self, pg_id):
        """Aggiungi lingua inline"""
        from tkinter import simpledialog
        lingua = simpledialog.askstring("Aggiungi Lingua", "Nome della lingua:")
        if lingua:
            try:
                pg_id = int(pg_id)
                cursor = self.db.cursor()
                cursor.execute("INSERT INTO pc_linguaggi (pg_id, lingua) VALUES (%s, %s)", (pg_id, lingua))
                self.db.commit()
                cursor.close()
                self.refresh_language_inline(pg_id)
            except Exception as e:
                messagebox.showerror("Errore", f"Errore: {e}")
    
    def delete_language_inline(self, pg_id):
        """Elimina lingua inline"""
        selection = self.languages_listbox.curselection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona una lingua da eliminare!")
            return
        
        lingua = self.languages_listbox.get(selection[0])
        if hasattr(self, 'language_ids') and lingua in self.language_ids:
            if not messagebox.askyesno("Conferma", "Eliminare la lingua selezionata?"):
                return
            try:
                cursor = self.db.cursor()
                cursor.execute("DELETE FROM pc_linguaggi WHERE id = %s AND pg_id = %s", (self.language_ids[lingua], pg_id))
                self.db.commit()
                cursor.close()
                self.refresh_language_inline(pg_id)
            except Exception as e:
                messagebox.showerror("Errore", f"Errore: {e}")
    
    def create_character_abilities_tab(self, notebook, pg_id, character):
        """Tab Abilita Speciali: abilita ladro da regole e override DM."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Abilita Speciali")

        canvas = tk.Canvas(tab)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        main_frame = ttk.Frame(canvas)
        main_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=main_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM pc_abilita_ladro WHERE pg_id = %s", (pg_id,))
        abilities = cursor.fetchone()
        cursor.close()

        class_code = self.get_character_class_code(character)
        class_row = self.get_rule_class_by_code(class_code) or {}
        level = int(character.get('livello') or 1)
        automatic_thief = self.calculate_thief_abilities_becmi(level)

        section = ttk.LabelFrame(main_frame, text="Abilita del Ladro (%)", padding=15)
        section.pack(fill='x', expand=True, padx=10, pady=10)

        if not class_row.get('uses_thief_abilities'):
            ttk.Label(
                section,
                text="La classe corrente non usa abilita ladro automatiche. Il DM puo' comunque usare questi valori se servono eccezioni di campagna.",
                font=('Arial', 9, 'italic')
            ).grid(row=0, column=0, columnspan=7, sticky='w', padx=5, pady=(0, 8))
        header_row = 1 if not class_row.get('uses_thief_abilities') else 0
        for col, label in [
            (0, "Abilita"),
            (1, "Automatico"),
            (2, "Effettivo"),
            (4, "Stato"),
            (7, "Motivazione"),
        ]:
            ttk.Label(section, text=label, font=('Arial', 9, 'bold')).grid(row=header_row, column=col, sticky='w', padx=5, pady=(0, 6))

        ability_fields = [
            ('scassinare_serrature', 'Scassinare Serrature', 'scassinare_serrature'),
            ('scoprire_trappole', 'Scoprire Trappole', 'scoprire_trappole'),
            ('rimuovere_trappole', 'Rimuovere Trappole', 'rimuovere_trappole'),
            ('scalare', 'Scalare Pareti', 'scalare_pareti'),
            ('muoversi_silenzio', 'Muoversi in Silenzio', 'muoversi_silenzio'),
            ('nascondersi_ombre', 'Nascondersi nelle Ombre', 'nascondersi_ombre'),
            ('scippare', 'Svuotare Tasche', 'svuotare_tasche'),
            ('sentire_rumori', 'Sentire Rumori', 'sentire_rumori'),
            ('comprensione_scritti', 'Comprendere Scritti', 'comprendere_scritti'),
            ('uso_pergamene_mago', 'Uso Pergamene Mago', 'uso_pergamene_mago')
        ]

        self.thief_ability_widgets = {}
        start_row = header_row + 1
        for i, (field, label, rule_field) in enumerate(ability_fields, start=start_row):
            automatic_value = automatic_thief.get(rule_field)
            if automatic_value is None and abilities:
                automatic_value = abilities.get(field)
            rule_value = self.get_effective_thief_ability(pg_id, field, automatic_value)
            effective_value = rule_value.get('effective')

            ttk.Label(section, text=f"{label}:").grid(row=i, column=0, sticky='w', padx=5, pady=5)
            ttk.Label(section, text=f"Auto: {automatic_value if automatic_value is not None else '-'}").grid(row=i, column=1, sticky='w', padx=5, pady=5)
            self.thief_ability_widgets[field] = ttk.Spinbox(section, from_=0, to=100, width=15)
            self.thief_ability_widgets[field].set(effective_value if effective_value is not None else 0)
            self.thief_ability_widgets[field].grid(row=i, column=2, sticky='w', padx=5, pady=5)
            ttk.Label(section, text="%").grid(row=i, column=3, sticky='w')
            ttk.Label(section, text="OVERRIDE DM" if rule_value.get('is_override') else "AUTO").grid(row=i, column=4, sticky='w', padx=5, pady=5)
            reason = rule_value.get('reason') or ''
            ttk.Label(section, text=reason, wraplength=260).grid(row=i, column=7, sticky='w', padx=5, pady=5)

            if self.user_can_edit_rule_override():
                ttk.Button(section, text="Sovrascrivi", command=lambda f=field, l=label, a=automatic_value: self.override_character_rule_dialog(pg_id, 'thief_abilities', f, a, l)).grid(row=i, column=5, sticky='w', padx=2, pady=3)
                ttk.Button(section, text="Ripristina", command=lambda f=field: self.clear_character_rule_override_and_refresh(pg_id, 'thief_abilities', f)).grid(row=i, column=6, sticky='w', padx=2, pady=3)

        notes_frame = ttk.LabelFrame(main_frame, text="Regole speciali", padding=10)
        notes_frame.pack(fill='x', padx=10, pady=10)
        self.thief_ability_widgets['colpire_alle_spalle_note'] = scrolledtext.ScrolledText(notes_frame, height=3, wrap='word')
        self.thief_ability_widgets['colpire_alle_spalle_note'].insert('1.0', (abilities or {}).get('colpire_alle_spalle_note', '') or 'Colpire alle spalle: applicare le regole BECMI; eventuali modifiche del DM vanno annotate qui.')
        self.thief_ability_widgets['colpire_alle_spalle_note'].pack(fill='x')

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)

        ttk.Button(btn_frame, text="Aggiorna da tabella", command=lambda: self.calculate_thief_abilities_auto(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Salva Abilita", command=lambda: self.save_thief_abilities(pg_id)).pack(side='left', padx=5)

    def create_character_combat_tab(self, notebook, pg_id, character):
        """Tab Combattimento - PUNTO 12: Armi unificate con modifica"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Combattimento")

        canvas = tk.Canvas(tab)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        content_frame = ttk.Frame(canvas)
        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=content_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(canvas_window, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        current_row = 0

        base_combat_frame = ttk.LabelFrame(content_frame, text="Combattimento Base", padding=10)
        base_combat_frame.grid(row=current_row, column=0, sticky='ew', padx=10, pady=5)
        current_row += 1

        ttk.Label(base_combat_frame, text="PF Massimi:").grid(row=0, column=0, sticky='w', padx=5, pady=3)
        self.char_widgets['pf_massimi'] = ttk.Spinbox(base_combat_frame, from_=0, to=999, width=10)
        self.char_widgets['pf_massimi'].set(character.get('pf_massimi', 0) or 0)
        self.char_widgets['pf_massimi'].grid(row=0, column=1, sticky='w', padx=5, pady=3)

        ttk.Label(base_combat_frame, text="PF Attuali:").grid(row=0, column=2, sticky='w', padx=5, pady=3)
        self.char_widgets['pf_attuali'] = ttk.Spinbox(base_combat_frame, from_=0, to=999, width=10)
        self.char_widgets['pf_attuali'].set(character.get('pf_attuali', 0) or 0)
        self.char_widgets['pf_attuali'].grid(row=0, column=3, sticky='w', padx=5, pady=3)

        ttk.Label(base_combat_frame, text="CA:").grid(row=0, column=4, sticky='w', padx=5, pady=3)
        self.char_widgets['classe_armatura'] = ttk.Spinbox(base_combat_frame, from_=-10, to=25, width=10)
        self.char_widgets['classe_armatura'].set(character.get('classe_armatura', 10) or 10)
        self.char_widgets['classe_armatura'].grid(row=0, column=5, sticky='w', padx=5, pady=3)

        rule_summary = self.calculate_character_rule_summary(pg_id)
        automatic_thac0 = rule_summary.get('thac0')
        thac0_value = self.get_rule_value(pg_id, 'thac0', 'thac0', automatic_thac0)

        combat_rules_frame = ttk.Frame(content_frame)
        combat_rules_frame.grid(row=current_row, column=0, sticky='nsew', padx=10, pady=5)
        combat_rules_frame.columnconfigure(0, weight=3)
        combat_rules_frame.columnconfigure(1, weight=2)
        combat_rules_frame.rowconfigure(0, weight=1)

        thac0_frame = ttk.LabelFrame(combat_rules_frame, text="THAC0", padding=10)
        thac0_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5), pady=0)
        armor_side_frame = ttk.Frame(combat_rules_frame)
        armor_side_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0), pady=0)
        current_row += 1

        ttk.Label(thac0_frame, text=f"Automatico: {thac0_value.get('automatic') if thac0_value.get('automatic') is not None else '-'}").grid(row=0, column=0, sticky='w', padx=5, pady=3)
        ttk.Label(thac0_frame, text=f"Effettivo: {thac0_value.get('effective') if thac0_value.get('effective') is not None else '-'}").grid(row=0, column=1, sticky='w', padx=20, pady=3)
        ttk.Label(thac0_frame, text="OVERRIDE DM" if thac0_value.get('is_override') else "AUTO").grid(row=0, column=2, sticky='w', padx=5, pady=3)
        if thac0_value.get('reason'):
            ttk.Label(thac0_frame, text=f"Motivo: {thac0_value.get('reason')}").grid(row=1, column=0, columnspan=3, sticky='w', padx=5, pady=3)
        if self.user_can_edit_rule_override():
            ttk.Button(thac0_frame, text="Sovrascrivi", command=lambda: self.override_character_rule_dialog(pg_id, 'thac0', 'thac0', automatic_thac0, "THAC0")).grid(row=0, column=3, sticky='w', padx=5, pady=3)
            ttk.Button(thac0_frame, text="Ripristina automatico", command=lambda: self.clear_character_rule_override_and_refresh(pg_id, 'thac0', 'thac0')).grid(row=0, column=4, sticky='w', padx=5, pady=3)

        try:
            base_for_weapons = thac0_value.get('effective')
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT *
                FROM pc_armi
                WHERE pg_id = %s AND COALESCE(equipped, 0) = 1
                ORDER BY nome
            """, (pg_id,))
            equipped_weapons = cursor.fetchall()
            cursor.close()
            weapon_row = 2
            if equipped_weapons:
                ttk.Label(thac0_frame, text="Armi impugnate", font=('Arial', 9, 'bold')).grid(
                    row=weapon_row, column=0, columnspan=5, sticky='w', padx=5, pady=(8, 3))
                weapon_row += 1
            for weapon in equipped_weapons:
                bonus = int(weapon.get('bonus_magico') or 0)
                title = f"{weapon.get('nome') or 'Arma'} | {self.normalize_weapon_type(weapon.get('tipo'))} | Bonus {bonus:+d}"
                ttk.Label(thac0_frame, text=title, font=('Arial', 9, 'bold')).grid(
                    row=weapon_row, column=0, columnspan=5, sticky='w', padx=5, pady=(4, 2))
                weapon_row += 1
                for mode, value, ability_mod, damage_bonus in self.calculate_weapon_thac0_rows(character, weapon, base_for_weapons):
                    ttk.Label(
                        thac0_frame,
                        text=f"{mode}: THAC0 {value} | mod. caratteristica {ability_mod:+d} | danno {weapon.get('danno') or '-'} {damage_bonus}"
                    ).grid(row=weapon_row, column=0, columnspan=5, sticky='w', padx=18, pady=1)
                    weapon_row += 1
                if weapon.get('notes'):
                    ttk.Label(thac0_frame, text=f"Note: {weapon.get('notes')}", wraplength=820).grid(
                        row=weapon_row, column=0, columnspan=5, sticky='w', padx=18, pady=(1, 4))
                    weapon_row += 1
        except Exception as e:
            print(f"Errore riepilogo THAC0 armi: {e}")

        self.create_combat_armor_widgets(armor_side_frame, pg_id)
        
        # === TIRI SALVEZZA ===
        ts_frame = ttk.LabelFrame(content_frame, text="Tiri Salvezza", padding=10)
        ts_frame.grid(row=3, column=0, sticky='ew', padx=10, pady=5)
        current_row += 1
        
        self.ts_widgets = {}
        
        save_automatic_values = rule_summary.get('saving_throws') or {}
        saves = [
            ('ts_raggio', 'Raggio morte', 'saving_throws'),
            ('ts_bacchetta', 'Bacchette', 'saving_throws'),
            ('ts_paralisi', 'Paralisi/Pietrificazione', 'saving_throws'),
            ('ts_soffio', 'Soffio drago', 'saving_throws'),
            ('ts_incantesimi', 'Incantesimi/Verghe/Bastoni', 'saving_throws'),
            ('ts_veleno', 'Veleno', 'saving_throws'),
            ('ts_pietrificazione', 'Pietrificazione', 'saving_throws')
        ]
        
        for i, (field, label, scope) in enumerate(saves):
            automatic_value = save_automatic_values.get(field)
            if scope:
                rule_value = self.get_rule_value(pg_id, scope, field, automatic_value)
                effective_value = rule_value.get('effective')
                status = "OVERRIDE DM" if rule_value.get('is_override') else "AUTO"
            else:
                rule_value = {}
                effective_value = character.get(field, 0) or 0
                status = "MANUALE"
            ttk.Label(ts_frame, text=f"{label}:").grid(row=i, column=0, sticky='w', padx=5, pady=3)
            ttk.Label(ts_frame, text=f"Auto: {automatic_value if automatic_value is not None else '-'}").grid(row=i, column=1, sticky='w', padx=5, pady=3)
            self.ts_widgets[field] = ttk.Spinbox(ts_frame, from_=0, to=20, width=10)
            self.ts_widgets[field].set(effective_value if effective_value is not None else 0)
            if scope:
                self.ts_widgets[field].configure(state='readonly')
            self.ts_widgets[field].grid(row=i, column=2, sticky='w', padx=5, pady=3)
            ttk.Label(ts_frame, text=status).grid(row=i, column=3, sticky='w', padx=5, pady=3)
            if scope and rule_value.get('reason'):
                ttk.Label(ts_frame, text=f"Motivo: {rule_value.get('reason')}").grid(row=i, column=4, sticky='w', padx=5, pady=3)
            if scope and self.user_can_edit_rule_override():
                ttk.Button(ts_frame, text="Sovrascrivi", command=lambda f=field, l=label, a=automatic_value: self.override_character_rule_dialog(pg_id, 'saving_throws', f, a, l)).grid(row=i, column=5, sticky='w', padx=5, pady=3)
                ttk.Button(ts_frame, text="Ripristina", command=lambda f=field: self.clear_character_rule_override_and_refresh(pg_id, 'saving_throws', f)).grid(row=i, column=6, sticky='w', padx=5, pady=3)
        
        ttk.Button(ts_frame, text="🎲 Calcola TS per Livello", 
                  command=lambda: self.apply_character_rule_summary_to_sheet(pg_id)).grid(
            row=len(saves), column=0, columnspan=7, pady=5)
        
        # === ARMI UNIFICATE - PUNTO 12 ===
        weapons_frame = ttk.LabelFrame(content_frame, text="Armi - Corpo a Corpo e da Lancio/Tiro", padding=10)
        weapons_frame.grid(row=2, column=0, sticky='nsew', padx=10, pady=5)
        content_frame.rowconfigure(2, weight=1)
        content_frame.columnconfigure(0, weight=1)
        current_row += 1

        ttk.Label(
            weapons_frame,
            text="(Limite massimo di 2 armi impugnate, se permesso dal PG)",
            font=('Arial', 9, 'italic')
        ).grid(row=0, column=0, columnspan=2, sticky='w', padx=5, pady=(0, 5))
        
        # PUNTO 12: Colonne unificate
        columns = ('nome', 'tipo', 'impugnata', 'bonus_magico', 'danno', 'g_corta', 'g_media', 'g_lunga', 'quantita')
        self.weapons_tree = ttk.Treeview(weapons_frame, columns=columns, show='headings', height=10)
        
        self.weapons_tree.heading('nome', text='Nome')
        self.weapons_tree.heading('tipo', text='Tipo')
        self.weapons_tree.heading('impugnata', text='Impugnata')
        self.weapons_tree.heading('bonus_magico', text='Bonus')
        self.weapons_tree.heading('danno', text='Danno')
        self.weapons_tree.heading('g_corta', text='Corta')
        self.weapons_tree.heading('g_media', text='Media')
        self.weapons_tree.heading('g_lunga', text='Lunga')
        self.weapons_tree.heading('quantita', text='Qta')
        
        self.weapons_tree.column('nome', width=120)
        self.weapons_tree.column('tipo', width=140)
        self.weapons_tree.column('impugnata', width=80)
        self.weapons_tree.column('bonus_magico', width=60)
        self.weapons_tree.column('danno', width=80)
        self.weapons_tree.column('g_corta', width=60)
        self.weapons_tree.column('g_media', width=60)
        self.weapons_tree.column('g_lunga', width=60)
        self.weapons_tree.column('quantita', width=50)
        
        # Righe alternate
        self.weapons_tree.tag_configure('oddrow', background='white')
        self.weapons_tree.tag_configure('evenrow', background='#f0f0f0')
        
        self.weapons_tree.grid(row=1, column=0, sticky='nsew')
        weapons_scroll = ttk.Scrollbar(weapons_frame, orient='vertical', command=self.weapons_tree.yview)
        weapons_scroll.grid(row=1, column=1, sticky='ns')
        self.weapons_tree.configure(yscrollcommand=weapons_scroll.set)
        weapons_frame.rowconfigure(1, weight=1)
        weapons_frame.columnconfigure(0, weight=1)
        
        self.refresh_weapons_unified_list(pg_id)
        
        # PUNTO 12: Bottoni unificati
        btn_frame = ttk.Frame(weapons_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=5)
        
        ttk.Button(btn_frame, text="➕ Aggiungi Arma", 
                  command=lambda: self.add_weapon_unified_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Modifica Arma", 
                  command=lambda: self.edit_weapon_unified_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Elimina", 
                  command=lambda: self.delete_weapon(pg_id)).pack(side='left', padx=5)

        def scroll_combat_page(event):
            if getattr(event, 'num', None) == 4:
                delta = -3
            elif getattr(event, 'num', None) == 5:
                delta = 3
            else:
                delta = -1 * int(event.delta / 120) if event.delta else 0
            if delta:
                canvas.yview_scroll(delta, "units")
            return "break"

        def bind_combat_mousewheel(widget):
            widget.bind("<MouseWheel>", scroll_combat_page, add="+")
            widget.bind("<Button-4>", scroll_combat_page, add="+")
            widget.bind("<Button-5>", scroll_combat_page, add="+")
            for child in widget.winfo_children():
                bind_combat_mousewheel(child)

        bind_combat_mousewheel(tab)

    def override_character_rule_dialog(self, pg_id, scope, field_name, automatic_value, label):
        """Dialog DM per sovrascrivere un valore regolamentare."""
        if not self.user_can_edit_rule_override():
            messagebox.showerror("Errore", "Solo il DM puo' sovrascrivere valori regolamentari.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Sovrascrivi {label}")
        dialog.geometry("420x240")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=f"Automatico: {automatic_value if automatic_value is not None else '-'}").pack(anchor='w', padx=12, pady=(12, 4))
        ttk.Label(dialog, text="Valore DM:").pack(anchor='w', padx=12, pady=(8, 2))
        override_entry = ttk.Entry(dialog, width=25)
        override_entry.pack(anchor='w', padx=12)
        ttk.Label(dialog, text="Motivazione:").pack(anchor='w', padx=12, pady=(8, 2))
        reason_text = tk.Text(dialog, height=4, width=46)
        reason_text.pack(anchor='w', padx=12)

        def save_override():
            override_value = override_entry.get().strip()
            if not override_value:
                messagebox.showwarning("Attenzione", "Inserisci il valore deciso dal DM.")
                return
            reason = reason_text.get('1.0', 'end-1c').strip()
            if self.set_rule_override(pg_id, scope, field_name, automatic_value, override_value, reason, self.current_user):
                dialog.destroy()
                self.refresh_character_sheet_preserving_tab(pg_id)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill='x', padx=12, pady=12)
        ttk.Button(btn_frame, text="Salva override", command=save_override).pack(side='left', padx=4)
        ttk.Button(btn_frame, text="Annulla", command=dialog.destroy).pack(side='left', padx=4)

    def clear_character_rule_override_and_refresh(self, pg_id, scope, field_name):
        if self.clear_rule_override(pg_id, scope, field_name, self.current_user):
            self.refresh_character_sheet_preserving_tab(pg_id)

    def apply_character_rule_summary_to_sheet(self, pg_id):
        """Aggiorna i campi effettivi in scheda usando automatici e override attivi."""
        try:
            if not self.save_character_data(pg_id, show_message=False):
                return
            self.refresh_character_sheet_preserving_tab(pg_id)
            messagebox.showinfo("Successo", "Valori automatici aggiornati nella scheda.")
        except Exception as e:
            messagebox.showerror("Errore", f"Errore aggiornamento regole: {e}")

    def create_magic_rules_frame(self, parent, pg_id, character):
        class_code = self.get_character_class_code(character)
        level = int(character.get('livello') or 1)
        class_row = self.get_rule_class_by_code(class_code) or {}
        spell_list_type = self.get_character_spell_list_type(class_code)

        rules_frame = ttk.LabelFrame(parent, text="Regole Magiche", padding=10)
        rules_frame.pack(fill='x', padx=10, pady=8)
        ttk.Label(
            rules_frame,
            text=f"Classe: {class_row.get('class_name') or class_code} | Lista incantesimi: {spell_list_type or 'Nessuna'}"
        ).grid(row=0, column=0, columnspan=8, sticky='w', padx=5, pady=3)

        automatic_slots = self.calculate_spell_slots(class_code, level)
        if automatic_slots:
            ttk.Label(rules_frame, text="Slot incantesimi:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
            for idx, spell_level in enumerate(sorted(automatic_slots), start=1):
                automatic_value = automatic_slots[spell_level]
                rule_value = self.get_rule_value(pg_id, 'spell_slots', f'slot_livello_{spell_level}', automatic_value)
                effective = rule_value.get('effective')
                ttk.Label(rules_frame, text=f"L{spell_level} auto {automatic_value} / eff {effective}").grid(row=1, column=idx, sticky='w', padx=5, pady=5)
                if self.user_can_edit_rule_override():
                    ttk.Button(
                        rules_frame,
                        text=f"Override L{spell_level}",
                        command=lambda sl=spell_level, av=automatic_value: self.override_character_rule_dialog(pg_id, 'spell_slots', f'slot_livello_{sl}', av, f"Slot incantesimi livello {sl}")
                    ).grid(row=2, column=idx, sticky='w', padx=5, pady=3)
        else:
            ttk.Label(rules_frame, text="Nessuno slot incantesimi automatico per classe/livello corrente.").grid(row=1, column=0, sticky='w', padx=5, pady=5)

    def create_character_magic_tab(self, notebook, pg_id, character):
        """Tab Oggetti Magici - PUNTO 13:"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Oggetti Magici")

        class_code = self.get_character_class_code(character)
        level = int(character.get('livello') or 1)

        turn_rows = self.calculate_turn_undead(class_code, level)
        if turn_rows:
            turn_frame = ttk.LabelFrame(tab, text="Scacciare Non-morti", padding=10)
            turn_frame.pack(fill='x', padx=10, pady=8)
            for i, row in enumerate(turn_rows):
                undead_type = row.get('undead_type')
                automatic_value = row.get('result_value')
                rule_value = self.get_rule_value(pg_id, 'turn_undead', undead_type, automatic_value)
                ttk.Label(turn_frame, text=f"{undead_type}:").grid(row=i, column=0, sticky='w', padx=5, pady=3)
                ttk.Label(turn_frame, text=f"Auto {automatic_value} / Eff {rule_value.get('effective')}").grid(row=i, column=1, sticky='w', padx=5, pady=3)
                ttk.Label(turn_frame, text="OVERRIDE DM" if rule_value.get('is_override') else "AUTO").grid(row=i, column=2, sticky='w', padx=5, pady=3)
                if self.user_can_edit_rule_override():
                    ttk.Button(
                        turn_frame,
                        text="Sovrascrivi",
                        command=lambda u=undead_type, a=automatic_value: self.override_character_rule_dialog(pg_id, 'turn_undead', u, a, f"Scacciare {u}")
                    ).grid(row=i, column=3, sticky='w', padx=5, pady=3)
                    ttk.Button(
                        turn_frame,
                        text="Ripristina",
                        command=lambda u=undead_type: self.clear_character_rule_override_and_refresh(pg_id, 'turn_undead', u)
                    ).grid(row=i, column=4, sticky='w', padx=5, pady=3)
        
        main_frame = ttk.LabelFrame(tab, text="Oggetti Magici", padding=10)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        columns = ('oggetto', 'effetto', 'potere')
        self.magic_tree = ttk.Treeview(main_frame, columns=columns, show='headings')
        
        self.magic_tree.heading('oggetto', text='Oggetto')
        self.magic_tree.heading('effetto', text='Effetto')
        self.magic_tree.heading('potere', text='Potere')
        
        self.magic_tree.column('oggetto', width=200)
        self.magic_tree.column('effetto', width=250)
        self.magic_tree.column('potere', width=250)
        
        self.magic_tree.pack(side='left', fill='both', expand=True)
        
        magic_scroll = ttk.Scrollbar(main_frame, orient='vertical', command=self.magic_tree.yview)
        magic_scroll.pack(side='right', fill='y')
        self.magic_tree.config(yscrollcommand=magic_scroll.set)
        
        self.refresh_magic_items_list(pg_id)
        
        # PUNTO 13: Bottoni con Modifica
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(btn_frame, text="➕ Aggiungi", 
                  command=lambda: self.add_magic_item_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Modifica", 
                  command=lambda: self.edit_magic_item_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Elimina", 
                  command=lambda: self.delete_magic_item(pg_id)).pack(side='left', padx=5)

    def edit_magic_item_dialog(self, pg_id):
        """Dialog modifica oggetto magico - PUNTO 13"""
        selection = self.magic_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto magico!")
            return
        
        item = self.magic_tree.item(selection[0])
        magic_id = item['tags'][0]
        
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_oggetti_magici WHERE id = %s AND pg_id = %s", (magic_id, pg_id))
            magic = cursor.fetchone()
            cursor.close()
            
            dialog = tk.Toplevel(self.root)
            dialog.title("Modifica Oggetto Magico")
            dialog.geometry("500x280")
            dialog.transient(self.root)
            dialog.grab_set()
            
            ttk.Label(dialog, text="Oggetto:").grid(row=0, column=0, sticky='w', padx=10, pady=10)
            oggetto_var = ttk.Entry(dialog, width=50)
            oggetto_var.insert(0, magic['oggetto'])
            oggetto_var.grid(row=0, column=1, padx=10, pady=10)
            
            ttk.Label(dialog, text="Effetto:").grid(row=1, column=0, sticky='nw', padx=10, pady=10)
            effetto_text = tk.Text(dialog, width=50, height=4)
            effetto_text.insert('1.0', magic['effetto'] or '')
            effetto_text.grid(row=1, column=1, padx=10, pady=10)
            
            ttk.Label(dialog, text="Potere:").grid(row=2, column=0, sticky='nw', padx=10, pady=10)
            potere_text = tk.Text(dialog, width=50, height=4)
            potere_text.insert('1.0', magic['potere'] or '')
            potere_text.grid(row=2, column=1, padx=10, pady=10)
            
            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        UPDATE pc_oggetti_magici 
                        SET oggetto = %s, effetto = %s, potere = %s
                        WHERE id = %s AND pg_id = %s
                    """, (oggetto_var.get(), effetto_text.get('1.0', 'end-1c'),
                          potere_text.get('1.0', 'end-1c'), magic_id, pg_id))
                    self.db.commit()
                    cursor.close()
                    self.refresh_magic_items_list(pg_id)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Oggetto modificato!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")
            
            ttk.Button(dialog, text="Salva", command=save).grid(row=3, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=3, column=1, pady=10)
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def create_character_notes_tab(self, notebook, pg_id, character):
        """Tab Note e Religione - VERSIONE CORRETTA"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Note")
        
        # Frame principale (senza scroll complesso)
        main_frame = ttk.Frame(tab)
        main_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Religione
        religion_frame = ttk.LabelFrame(main_frame, text="Religione", padding=10)
        religion_frame.pack(fill='x', pady=5)
        
        if not hasattr(self, 'religion_widgets'):
            self.religion_widgets = {}
        
        fields = [
            ('divinita_persistenza', 'Divinità/Persistenza'),
            ('simbolo', 'Simbolo'),
            ('elementi', 'Elementi'),
            ('allineamento_religioso', 'Allineamento')
        ]
        
        for i, (field, label) in enumerate(fields):
            ttk.Label(religion_frame, text=f"{label}:").grid(row=i, column=0, sticky='w', padx=5, pady=3)
            self.religion_widgets[field] = ttk.Entry(religion_frame, width=40)
            self.religion_widgets[field].insert(0, character.get(field, '') or '')
            self.religion_widgets[field].grid(row=i, column=1, sticky='w', padx=5, pady=3)
        
        ttk.Label(religion_frame, text="Precetti:").grid(row=len(fields), column=0, sticky='nw', padx=5, pady=3)
        self.religion_widgets['precetti'] = scrolledtext.ScrolledText(religion_frame, height=4, width=50)
        self.religion_widgets['precetti'].insert('1.0', character.get('precetti', '') or '')
        self.religion_widgets['precetti'].grid(row=len(fields), column=1, sticky='w', padx=5, pady=3)
        
        # Note generali
        notes_frame = ttk.LabelFrame(main_frame, text="Note Generali", padding=10)
        notes_frame.pack(fill='both', expand=True, pady=5)
        
        self.char_widgets['note_religione'] = scrolledtext.ScrolledText(notes_frame, height=15)
        self.char_widgets['note_religione'].insert('1.0', character.get('note_religione', '') or '')
        self.char_widgets['note_religione'].pack(fill='both', expand=True)
        
        # Bottone salva
        ttk.Button(main_frame, text="💾 Salva Note", 
                  command=lambda: self.save_character_data(pg_id, show_message=True)).pack(pady=10)
    
    # ==================== FUNZIONI DI SUPPORTO ====================
    
    def save_character_data(self, pg_id, show_message=True):
        """Salva tutti i dati del personaggio - VERSIONE CORRETTA"""
        try:
            if not self.verify_character_sheet_pg_access(pg_id):
                messagebox.showerror("Errore", "Personaggio non autorizzato.")
                return False

            cursor = self.db.cursor()
            
            # Helper per gestire valori None
            def get_safe_value(widget, default=0):
                try:
                    val = widget.get()
                    return val if val != '' else default
                except:
                    return default
            
            class_label = self.char_widgets['classe'].get() or 'Ladro'
            class_code = getattr(self, 'rule_class_code_by_label', {}).get(class_label)
            if not class_code:
                class_code = self.normalize_class_code(class_label)
            class_name = getattr(self, 'rule_class_name_by_code', {}).get(class_code) or class_label.split(' (')[0]

            temp_character = {
                'forza': int(get_safe_value(self.char_widgets['forza'], 10)),
                'intelligenza': int(get_safe_value(self.char_widgets['intelligenza'], 10)),
                'saggezza': int(get_safe_value(self.char_widgets['saggezza'], 10)),
                'destrezza': int(get_safe_value(self.char_widgets['destrezza'], 10)),
                'costituzione': int(get_safe_value(self.char_widgets['costituzione'], 10)),
                'carisma': int(get_safe_value(self.char_widgets['carisma'], 10)),
            }
            class_row = self.get_rule_class_by_code(class_code) or {}
            level = max(1, min(int(get_safe_value(self.char_widgets['livello'], 1)), 36))
            rule_summary = {
                'requisito_primario': class_row.get('primary_requisite') or '',
                'modificatore_px': self.calculate_xp_modifier(temp_character, class_code),
                'dado_vita': self.format_hit_die_with_constitution(
                    class_row.get('hit_die') or '',
                    temp_character.get('costituzione', 10)
                ),
                'px_prossimo_livello': self.calculate_next_level_xp(class_code, level),
                'thac0': self.calculate_thac0_becmi(class_code, level),
            }

            automatic_saves = self.calculate_saving_throws_becmi(class_code, level)

            # Prepara dati da aggiornare
            update_fields = {
                'classe': class_name,
                'class_code': class_code,
                'livello': level,
                'titolo': self.char_widgets['titolo'].get() or '',
                'px_attuali': int(get_safe_value(self.char_widgets.get('px_attuali'), 0)),
                'px_prossimo_livello': int(rule_summary['px_prossimo_livello'] or 0),
                'requisito_primario': rule_summary['requisito_primario'],
                'modificatore_px': int(rule_summary['modificatore_px'] or 0),
                'dado_vita': rule_summary['dado_vita'],
                'thac0': int(rule_summary['thac0']) if rule_summary['thac0'] is not None else None,
                'forza': int(get_safe_value(self.char_widgets['forza'], 10)),
                'intelligenza': int(get_safe_value(self.char_widgets['intelligenza'], 10)),
                'saggezza': int(get_safe_value(self.char_widgets['saggezza'], 10)),
                'destrezza': int(get_safe_value(self.char_widgets['destrezza'], 10)),
                'costituzione': int(get_safe_value(self.char_widgets['costituzione'], 10)),
                'carisma': int(get_safe_value(self.char_widgets['carisma'], 10)),
                'legale': int(self.char_widgets['legale'].get()),
                'neutrale': int(self.char_widgets['neutrale'].get()),
                'caotico': int(self.char_widgets['caotico'].get()),
                'sesso': self.char_widgets['sesso'].get() or '',
                'eta': int(get_safe_value(self.char_widgets['eta'], 0)),
                'capelli': self.char_widgets['capelli'].get() or '',
                'occhi': self.char_widgets['occhi'].get() or '',
                'pelle': self.char_widgets['pelle'].get() or '',
                'altezza': self.char_widgets['altezza'].get() or '',
                'peso': self.char_widgets['peso'].get() or '',
                'luogo_origine': self.char_widgets['luogo_origine'].get() or '',
                'compleanno': self.char_widgets['compleanno'].get() or '',
                'nome_famiglia': self.char_widgets['nome_famiglia'].get() or '',
                'nome_padre': self.char_widgets['nome_padre'].get() or '',
                'classe_sociale': self.char_widgets['classe_sociale'].get() or '',
                'soprannome': self.char_widgets['soprannome'].get() or '',
                'background': self.char_widgets['background'].get('1.0', 'end-1c') or '',
                'manierismo': self.char_widgets['manierismo'].get('1.0', 'end-1c') or '',
                'bonus_speciali': self.char_widgets['bonus_speciali'].get('1.0', 'end-1c') or '',
                'pf_massimi': int(get_safe_value(self.char_widgets['pf_massimi'], 0)),
                'pf_attuali': int(get_safe_value(self.char_widgets['pf_attuali'], 0)),
                'classe_armatura': int(get_safe_value(self.char_widgets['classe_armatura'], 10)),
            }

            for ability in ['forza', 'intelligenza', 'saggezza', 'destrezza', 'costituzione', 'carisma']:
                base_widget = self.char_widgets.get(f'{ability}_base')
                reason_widget = self.char_widgets.get(f'{ability}_motivo')
                if base_widget:
                    update_fields[f'{ability}_base'] = int(get_safe_value(base_widget, update_fields[ability]))
                if reason_widget:
                    update_fields[f'{ability}_motivo'] = reason_widget.get() or ''
            
            # Aggiungi TS se esistono
            if hasattr(self, 'ts_widgets'):
                save_map = {
                    'ts_raggio': automatic_saves.get('morte_veleno'),
                    'ts_veleno': automatic_saves.get('morte_veleno'),
                    'ts_bacchetta': automatic_saves.get('bacchette'),
                    'ts_paralisi': automatic_saves.get('paralisi_pietrificazione'),
                    'ts_pietrificazione': automatic_saves.get('paralisi_pietrificazione'),
                    'ts_soffio': automatic_saves.get('soffio_drago'),
                    'ts_incantesimi': automatic_saves.get('incantesimi_verghe_bastoni'),
                }
                for ts_field in self.ts_widgets:
                    rule_value = self.get_rule_value(pg_id, 'saving_throws', ts_field, save_map.get(ts_field))
                    effective_value = rule_value.get('effective')
                    update_fields[ts_field] = int(effective_value) if effective_value not in (None, '') else 0
            
            # Aggiungi denaro se esiste
            if hasattr(self, 'money_widgets'):
                for money_field in self.money_widgets:
                    try:
                        update_fields[money_field] = int(self.money_widgets[money_field].get() or 0)
                    except:
                        update_fields[money_field] = 0
            
            # Aggiungi religione se esiste
            if hasattr(self, 'religion_widgets'):
                for rel_field, widget in self.religion_widgets.items():
                    if isinstance(widget, scrolledtext.ScrolledText):
                        update_fields[rel_field] = widget.get('1.0', 'end-1c') or ''
                    else:
                        update_fields[rel_field] = widget.get() or ''
            
            # Note religione
            if 'note_religione' in self.char_widgets:
                update_fields['note_religione'] = self.char_widgets['note_religione'].get('1.0', 'end-1c') or ''
            
            existing_columns = self.get_table_columns('player_characters')
            if existing_columns:
                update_fields = {k: v for k, v in update_fields.items() if k in existing_columns}

            # Costruisci query UPDATE
            set_clause = ', '.join([f"{k} = %s" for k in update_fields.keys()])
            values = list(update_fields.values()) + [pg_id]
            where_clause = "id = %s"
            if self.current_user and self.current_user.get('role') == 'GIOCATORE':
                where_clause = "id = %s AND user_id = %s"
                values.append(self.current_user['id'])

            cursor.execute(f"""
                UPDATE player_characters 
                SET {set_clause}
                WHERE {where_clause}
            """, values)
            
            self.db.commit()
            cursor.close()
            
            if show_message:
                messagebox.showinfo("Successo", "Dati personaggio salvati con successo!")
            return True
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore salvataggio: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def calculate_saving_throws_auto(self, character):
        """Calcola automaticamente i tiri salvezza in base al livello - CORRETTO COMPLETO"""
        try:
            level = int(self.char_widgets['livello'].get())
            
            # Tabella TS COMPLETA per Ladro (AD&D 2nd Edition)
            # Include TUTTI gli 8 tiri salvezza
            ts_table = {
                'ts_raggio': [13, 12, 11, 10, 9],
                'ts_bacchetta': [14, 12, 10, 8, 6],
                'ts_paralisi': [13, 11, 9, 7, 5],
                'ts_soffio': [16, 15, 14, 13, 12],
                'ts_incantesimi': [15, 13, 11, 9, 7],
                'ts_veleno': [13, 11, 9, 7, 5],        # AGGIUNTO
                'ts_pietrificazione': [13, 11, 9, 7, 5] # AGGIUNTO
            }
            
            # Determina indice in base al livello
            if level <= 4:
                idx = 0
            elif level <= 8:
                idx = 1
            elif level <= 12:
                idx = 2
            elif level <= 16:
                idx = 3
            else:
                idx = 4
            
            # Applica valori a TUTTI i tiri salvezza
            for field, values in ts_table.items():
                if field in self.ts_widgets:
                    self.ts_widgets[field].delete(0, 'end')
                    self.ts_widgets[field].insert(0, str(values[idx]))
            
            messagebox.showinfo("Successo", f"Tutti i tiri salvezza calcolati per livello {level}")
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore calcolo TS: {e}")
    
    def calculate_thief_abilities_auto(self, pg_id):
        """Aggiorna abilita ladro usando rule_thief_abilities e override attivi."""
        try:
            level = int(self.char_widgets['livello'].get())
            automatic = self.calculate_thief_abilities_becmi(level)
            field_map = {
                'scassinare_serrature': 'scassinare_serrature',
                'scoprire_trappole': 'scoprire_trappole',
                'rimuovere_trappole': 'rimuovere_trappole',
                'scalare': 'scalare_pareti',
                'muoversi_silenzio': 'muoversi_silenzio',
                'nascondersi_ombre': 'nascondersi_ombre',
                'scippare': 'svuotare_tasche',
                'sentire_rumori': 'sentire_rumori',
                'comprensione_scritti': 'comprendere_scritti',
                'uso_pergamene_mago': 'uso_pergamene_mago',
            }
            for widget_field, rule_field in field_map.items():
                if widget_field in self.thief_ability_widgets:
                    automatic_value = automatic.get(rule_field, 0)
                    rule_value = self.get_effective_thief_ability(pg_id, widget_field, automatic_value)
                    self.thief_ability_widgets[widget_field].delete(0, 'end')
                    self.thief_ability_widgets[widget_field].insert(0, str(rule_value.get('effective') or 0))
            messagebox.showinfo("Successo", f"Abilita ladro aggiornate per livello {level}.")
        except Exception as e:
            messagebox.showerror("Errore", f"Errore calcolo abilita ladro: {e}")

    def save_thief_abilities(self, pg_id, show_message=True):
        """Salva abilita del ladro, inclusi nuovi campi e campi legacy."""
        try:
            if not self.verify_character_sheet_pg_access(pg_id):
                messagebox.showerror("Errore", "Personaggio non autorizzato.")
                return False

            cursor = self.db.cursor()
            cursor.execute("SELECT id FROM pc_abilita_ladro WHERE pg_id = %s", (pg_id,))
            exists = cursor.fetchone()

            values = {}
            for field, widget in self.thief_ability_widgets.items():
                if isinstance(widget, scrolledtext.ScrolledText):
                    values[field] = widget.get('1.0', 'end-1c') or ''
                else:
                    try:
                        values[field] = int(widget.get() or 0)
                    except Exception:
                        values[field] = 0

            if exists:
                set_clause = ', '.join([f"{k} = %s" for k in values.keys()])
                cursor.execute(f"UPDATE pc_abilita_ladro SET {set_clause} WHERE pg_id = %s", list(values.values()) + [pg_id])
            else:
                values['pg_id'] = pg_id
                columns = ', '.join(values.keys())
                placeholders = ', '.join(['%s'] * len(values))
                cursor.execute(f"INSERT INTO pc_abilita_ladro ({columns}) VALUES ({placeholders})", list(values.values()))

            self.db.commit()
            cursor.close()
            if show_message:
                messagebox.showinfo("Successo", "Abilita salvate con successo!")
            return True
        except Exception as e:
            messagebox.showerror("Errore", f"Errore salvataggio abilita:\n{e}")
            traceback.print_exc()
            return False

    # ==================== GESTIONE ARMI ====================
    
    def refresh_weapons_list(self, pg_id):
        """Ricarica armi - Con righe alternate (VERSIONE BASE - se non usi quella unificata)"""
        try:
            self.weapons_tree.delete(*self.weapons_tree.get_children())
            self.weapons_tree.tag_configure('oddrow', background='white')
            self.weapons_tree.tag_configure('evenrow', background='#f0f0f0')
            
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_armi WHERE pg_id = %s", (pg_id,))
            weapons = cursor.fetchall()
            cursor.close()
            
            for i, weapon in enumerate(weapons):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                self.weapons_tree.insert('', 'end', values=(
                    weapon['nome'], weapon['tipo'], weapon['danno'], weapon['gittata']
                ), tags=(weapon['id'], tag))
        except Exception as e:
            print(f"Errore refresh armi: {e}")
    
    def add_weapon_dialog(self, pg_id, is_throwing=False):
        """Dialog aggiungi arma - UNIFICATO"""
        try:
            pg_id = int(pg_id)
            
            title = "Aggiungi Arma da Lancio" if is_throwing else "Aggiungi Arma Corpo a Corpo"
            dialog = tk.Toplevel(self.root)
            dialog.title(title)
            dialog.geometry("450x400" if is_throwing else "450x250")
            dialog.transient(self.root)
            dialog.grab_set()
            
            fields = {}
            row = 0
            
            # Nome
            ttk.Label(dialog, text="Nome Arma:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
            fields['nome'] = ttk.Entry(dialog, width=30)
            fields['nome'].grid(row=row, column=1, padx=10, pady=5)
            row += 1
            
            # Tipo
            ttk.Label(dialog, text="Tipo:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
            tipo_values = ["Lancio", "Magica Lancio"] if is_throwing else ["Normale", "Magica"]
            fields['tipo'] = ttk.Combobox(dialog, values=tipo_values, width=27)
            fields['tipo'].set(tipo_values[0])
            fields['tipo'].grid(row=row, column=1, padx=10, pady=5)
            row += 1
            
            if not is_throwing:
                # ARMA CORPO A CORPO
                ttk.Label(dialog, text="Danno:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
                fields['danno'] = ttk.Entry(dialog, width=30)
                fields['danno'].grid(row=row, column=1, padx=10, pady=5)
                row += 1
                
                ttk.Label(dialog, text="Gittata:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
                fields['gittata'] = ttk.Entry(dialog, width=30)
                fields['gittata'].grid(row=row, column=1, padx=10, pady=5)
                row += 1
            else:
                # ARMA DA LANCIO
                ttk.Label(dialog, text="Gittata Corta:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
                fields['gittata_corta'] = ttk.Spinbox(dialog, from_=0, to=999, width=28)
                fields['gittata_corta'].set(0)
                fields['gittata_corta'].grid(row=row, column=1, padx=10, pady=5)
                row += 1
                
                ttk.Label(dialog, text="Gittata Media:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
                fields['gittata_media'] = ttk.Spinbox(dialog, from_=0, to=999, width=28)
                fields['gittata_media'].set(0)
                fields['gittata_media'].grid(row=row, column=1, padx=10, pady=5)
                row += 1
                
                ttk.Label(dialog, text="Gittata Lunga:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
                fields['gittata_lunga'] = ttk.Spinbox(dialog, from_=0, to=999, width=28)
                fields['gittata_lunga'].set(0)
                fields['gittata_lunga'].grid(row=row, column=1, padx=10, pady=5)
                row += 1
                
                ttk.Label(dialog, text="Quantità:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
                fields['quantita'] = ttk.Spinbox(dialog, from_=1, to=999, width=28)
                fields['quantita'].set(1)
                fields['quantita'].grid(row=row, column=1, padx=10, pady=5)
                row += 1
            
            def save():
                try:
                    cursor = self.db.cursor()
                    
                    if not is_throwing:
                        # Arma corpo a corpo
                        cursor.execute("""
                            INSERT INTO pc_armi (pg_id, nome, tipo, danno, gittata, is_throwing)
                            VALUES (%s, %s, %s, %s, %s, FALSE)
                        """, (pg_id, fields['nome'].get(), fields['tipo'].get(),
                              fields['danno'].get(), fields['gittata'].get()))
                    else:
                        # Arma da lancio
                        cursor.execute("""
                            INSERT INTO pc_armi 
                            (pg_id, nome, tipo, gittata_corta, gittata_media, gittata_lunga, quantita, is_throwing)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
                        """, (pg_id, fields['nome'].get(), fields['tipo'].get(),
                              int(fields['gittata_corta'].get()), int(fields['gittata_media'].get()),
                              int(fields['gittata_lunga'].get()), int(fields['quantita'].get())))
                    
                    self.db.commit()
                    cursor.close()
                    self.refresh_weapons_unified_list(pg_id)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Arma aggiunta!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")
            
            ttk.Button(dialog, text="Salva", command=save).grid(row=row, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=row, column=1, pady=10)
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def delete_weapon(self, pg_id):
        """Elimina arma selezionata"""
        selection = self.weapons_tree.selection()
        if not selection:
            return
        
        item = self.weapons_tree.item(selection[0])
        weapon_id = item['tags'][0]
        
        if messagebox.askyesno("Conferma", "Eliminare l'arma selezionata?"):
            try:
                cursor = self.db.cursor()
                cursor.execute("DELETE FROM pc_armi WHERE id = %s AND pg_id = %s", (weapon_id, pg_id))
                self.db.commit()
                cursor.close()
                
                self.refresh_weapons_unified_list(pg_id)
                self.refresh_character_sheet_preserving_tab(pg_id, "Combattimento")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore: {e}")
    
    # ==================== GESTIONE ARMATURE ====================
    
    def delete_armor(self, pg_id):
        """Elimina armatura"""
        selection = self.armor_tree.selection()
        if not selection:
            return
        
        item = self.armor_tree.item(selection[0])
        armor_id = item['tags'][0]
        if not messagebox.askyesno("Conferma", "Eliminare l'armatura selezionata?"):
            return
        
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_armature WHERE id = %s AND pg_id = %s", (armor_id, pg_id))
            self.db.commit()
            cursor.close()
            
            self.refresh_armor_list(pg_id)
            self.update_character_equipment_calculations(pg_id)
            self.refresh_character_sheet_preserving_tab(pg_id, "Combattimento")
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    # ==================== GESTIONE EQUIPAGGIAMENTO ====================
    
    def create_combat_armor_widgets(self, parent, pg_id):
        """Riquadri CA e Armature nel TAB Combattimento."""
        summary = self.update_character_equipment_calculations(pg_id)
        calc_frame = ttk.LabelFrame(parent, text="Classe Armatura", padding=10)
        calc_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=5)
        ac = summary['armor_class']
        ttk.Label(calc_frame, text=f"Automatico: {ac.get('automatic') if ac.get('automatic') is not None else '-'}").grid(row=0, column=0, sticky='w', padx=5, pady=3)
        ttk.Label(calc_frame, text=f"Effettivo: {ac.get('effective') if ac.get('effective') is not None else '-'}").grid(row=0, column=1, sticky='w', padx=12, pady=3)
        ttk.Label(calc_frame, text="OVERRIDE DM" if ac.get('is_override') else "AUTO").grid(row=0, column=2, sticky='w', padx=5, pady=3)
        if ac.get('reason'):
            ttk.Label(calc_frame, text=f"Motivo: {ac.get('reason')}", wraplength=360).grid(row=1, column=0, columnspan=4, sticky='w', padx=5, pady=3)
        if self.user_can_edit_rule_override():
            ttk.Button(calc_frame, text="Sovrascrivi", command=lambda: self.override_character_rule_dialog(pg_id, 'armor_class', 'classe_armatura_effettiva', ac.get('automatic'), 'Classe Armatura')).grid(row=2, column=0, sticky='w', padx=5, pady=3)
            ttk.Button(calc_frame, text="Ripristina automatico", command=lambda: self.clear_character_rule_override_and_refresh(pg_id, 'armor_class', 'classe_armatura_effettiva')).grid(row=2, column=1, sticky='w', padx=5, pady=3)
            ttk.Button(calc_frame, text="Aggiorna calcoli", command=lambda: self.refresh_character_sheet_preserving_tab(pg_id, "Combattimento")).grid(row=2, column=2, sticky='w', padx=5, pady=3)

        armor_frame = ttk.LabelFrame(parent, text="Armature", padding=10)
        armor_frame.grid(row=1, column=0, sticky='nsew', padx=10, pady=5)
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        armor_columns = ('tipo', 'base_ac', 'bonus', 'equip', 'costo', 'note')
        self.armor_tree = ttk.Treeview(armor_frame, columns=armor_columns, show='headings', height=7)
        for col, label in [('tipo', 'Tipo'), ('base_ac', 'CA'), ('bonus', 'Bonus'), ('equip', 'Eq.'), ('costo', 'Costo'), ('note', 'Note')]:
            self.armor_tree.heading(col, text=label)
            self.armor_tree.column(col, width=140 if col in ('tipo', 'note') else 70)
        self.armor_tree.grid(row=0, column=0, sticky='nsew')
        armor_scroll = ttk.Scrollbar(armor_frame, orient='vertical', command=self.armor_tree.yview)
        armor_scroll.grid(row=0, column=1, sticky='ns')
        self.armor_tree.configure(yscrollcommand=armor_scroll.set)
        armor_frame.rowconfigure(0, weight=1)
        armor_frame.columnconfigure(0, weight=1)
        self.refresh_armor_list(pg_id)
        armor_btns = ttk.Frame(armor_frame)
        armor_btns.grid(row=1, column=0, columnspan=2, sticky='w', pady=5)
        ttk.Button(armor_btns, text="Aggiungi", command=lambda: self.add_armor_dialog(pg_id)).pack(side='left', padx=4)
        ttk.Button(armor_btns, text="Modifica", command=lambda: self.edit_armor_dialog(pg_id)).pack(side='left', padx=4)
        ttk.Button(armor_btns, text="Elimina", command=lambda: self.delete_armor(pg_id)).pack(side='left', padx=4)

    def create_character_equipment_tab(self, notebook, pg_id, character):
        """Tab Equipaggiamento dismesso: armature e CA sono in Combattimento, gli oggetti in Inventario."""
        return

    def create_character_inventory_tab(self, notebook, pg_id, character):
        """Tab Inventario con contenitori e disponibilita' trasportata."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Inventario")

        containers_frame = ttk.LabelFrame(tab, text="Contenitori", padding=8)
        containers_frame.pack(fill='x', padx=10, pady=5)
        self.containers_tree = ttk.Treeview(containers_frame, columns=('nome', 'tipo', 'posizione', 'note'), show='headings', height=5)
        for col, label in [('nome', 'Nome'), ('tipo', 'Tipo'), ('posizione', 'Posizione'), ('note', 'Note')]:
            self.containers_tree.heading(col, text=label)
            self.containers_tree.column(col, width=180 if col in ('nome', 'note') else 140)
        self.containers_tree.pack(fill='x')
        container_btns = ttk.Frame(containers_frame)
        container_btns.pack(anchor='w', pady=4)
        container_count = len(self.get_pg_containers(pg_id))
        multi_container_state = 'normal' if container_count > 1 else 'disabled'
        ttk.Button(container_btns, text="Aggiungi Contenitore", command=lambda: self.add_container_dialog(pg_id)).pack(side='left', padx=4)
        ttk.Button(container_btns, text="Modifica Contenitore", command=lambda: self.edit_container_dialog(pg_id)).pack(side='left', padx=4)
        ttk.Button(container_btns, text="Elimina Contenitore", command=lambda: self.delete_container(pg_id)).pack(side='left', padx=4)
        ttk.Button(container_btns, text="Travasa Contenitore", command=lambda: self.transfer_container_contents(pg_id), state=multi_container_state).pack(side='left', padx=4)

        equipment_frame = ttk.LabelFrame(tab, text="Equipaggiamento", padding=8)
        equipment_frame.pack(fill='both', expand=True, padx=10, pady=5)

        search_frame = ttk.Frame(equipment_frame)
        search_frame.pack(fill='x', pady=(0, 5))
        ttk.Label(search_frame, text="Ricerca Oggetto:").pack(side='left', padx=(0, 6))
        self.inventory_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.inventory_search_var, width=36)
        search_entry.pack(side='left', fill='x', expand=True)
        self.inventory_search_var.trace_add('write', lambda *_: self.refresh_inventory_lists(pg_id))

        columns = ('oggetto', 'quantita', 'contenitore', 'posizione', 'trasportato', 'consumabile')
        tree_frame = ttk.Frame(equipment_frame)
        tree_frame.pack(fill='both', expand=True)
        self.inventory_tree = ttk.Treeview(tree_frame, columns=columns, show='headings')
        headings = [
            ('oggetto', 'Oggetto'),
            ('quantita', 'Quantita'),
            ('contenitore', 'Contenitore'),
            ('posizione', 'Collocazione'),
            ('trasportato', 'Trasportato'),
            ('consumabile', 'Consumabile'),
        ]
        for col, label in headings:
            if col in ('oggetto', 'contenitore'):
                self.inventory_tree.heading(col, text=label, command=lambda c=col: self.sort_inventory_by_column(pg_id, c))
            else:
                self.inventory_tree.heading(col, text=label)
            self.inventory_tree.column(col, width=180 if col in ('oggetto', 'contenitore') else 110)
        self.inventory_tree.pack(side='left', fill='both', expand=True)
        inventory_scroll = ttk.Scrollbar(tree_frame, orient='vertical', command=self.inventory_tree.yview)
        inventory_scroll.pack(side='right', fill='y')
        self.inventory_tree.configure(yscrollcommand=inventory_scroll.set)

        equipment_btns = ttk.Frame(equipment_frame)
        equipment_btns.pack(fill='x', pady=5)
        ttk.Button(equipment_btns, text="Aggiungi", command=lambda: self.add_inventory_dialog(pg_id)).pack(side='left', padx=4)
        ttk.Button(equipment_btns, text="Modifica", command=lambda: self.edit_inventory_item_dialog(pg_id)).pack(side='left', padx=4)
        ttk.Button(equipment_btns, text="Sposta in altro contenitore", command=lambda: self.move_inventory_item_container(pg_id), state=multi_container_state).pack(side='left', padx=4)
        ttk.Button(equipment_btns, text="Elimina", command=lambda: self.delete_inventory_item(pg_id)).pack(side='left', padx=4)

        self.refresh_container_list(pg_id)
        self.refresh_inventory_lists(pg_id)

        money_frame = ttk.LabelFrame(tab, text="Denaro Trasportato", padding=10)
        money_frame.pack(fill='x', padx=10, pady=5)
        if not hasattr(self, 'money_widgets'):
            self.money_widgets = {}
        coins = [('denaro_mo', 'MO'), ('denaro_me', 'ME'), ('denaro_ma', 'MA'), ('denaro_mr', 'MR')]
        for i, (field, label) in enumerate(coins):
            ttk.Label(money_frame, text=f"{label}:").grid(row=0, column=i * 2, sticky='w', padx=5, pady=3)
            self.money_widgets[field] = ttk.Entry(money_frame, width=12)
            self.money_widgets[field].insert(0, character.get(field, 0))
            self.money_widgets[field].grid(row=0, column=i * 2 + 1, sticky='w', padx=5, pady=3)

    def _fetch_catalog_rows(self, table, name_col):
        try:
            cursor = self.db.cursor()
            cursor.execute(f"SELECT * FROM {table} ORDER BY {name_col}")
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Exception:
            return []

    def refresh_weapons_unified_list(self, pg_id):
        try:
            self.weapons_tree.delete(*self.weapons_tree.get_children())
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_armi WHERE pg_id = %s ORDER BY nome", (pg_id,))
            for i, weapon in enumerate(cursor.fetchall()):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                self.weapons_tree.insert('', 'end', values=(
                    weapon['nome'], self.normalize_weapon_type(weapon.get('tipo')),
                    "Si" if weapon.get('equipped') else "No",
                    weapon.get('bonus_magico', 0) or 0,
                    weapon.get('danno') or '', weapon.get('gittata_corta', 0) or 0,
                    weapon.get('gittata_media', 0) or 0, weapon.get('gittata_lunga', 0) or 0,
                    weapon.get('quantita', 1) or 1
                ), tags=(weapon['id'], tag))
            cursor.close()
        except Exception as e:
            print(f"Errore refresh armi: {e}")

    def add_weapon_unified_dialog(self, pg_id):
        try:
            pg_id = int(pg_id)
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM player_characters WHERE id = %s", (pg_id,))
            character = cursor.fetchone() or {}
            cursor.close()
            class_code = self.get_character_class_code(character)
            weapons = self._fetch_catalog_rows('rule_weapons', 'weapon_name')

            dialog = tk.Toplevel(self.root)
            dialog.title("Aggiungi Arma")
            dialog.geometry("560x560")
            dialog.transient(self.root)
            dialog.grab_set()

            fields = {}
            ttk.Label(dialog, text="Catalogo:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
            catalog_combo = ttk.Combobox(dialog, width=38, state='readonly')
            catalog_combo['values'] = [w['weapon_name'] for w in weapons]
            catalog_combo.grid(row=0, column=1, padx=10, pady=5)
            fields['nome'] = ttk.Entry(dialog, width=40)
            fields['tipo'] = ttk.Combobox(dialog, values=self.get_weapon_type_options(), state='readonly', width=37)
            fields['bonus_magico'] = ttk.Spinbox(dialog, from_=-5, to=10, width=38)
            fields['danno'] = ttk.Entry(dialog, width=40)
            fields['gittata_corta'] = ttk.Spinbox(dialog, from_=0, to=999, width=38)
            fields['gittata_media'] = ttk.Spinbox(dialog, from_=0, to=999, width=38)
            fields['gittata_lunga'] = ttk.Spinbox(dialog, from_=0, to=999, width=38)
            fields['quantita'] = ttk.Spinbox(dialog, from_=1, to=999, width=38)
            fields['cost_mo'] = ttk.Entry(dialog, width=40)
            fields['ammunition_current'] = ttk.Spinbox(dialog, from_=0, to=999, width=38)
            fields['ammunition_max'] = ttk.Spinbox(dialog, from_=0, to=999, width=38)
            notes_text = tk.Text(dialog, width=40, height=4)
            equipped_var = tk.BooleanVar(value=False)
            carried_var = tk.BooleanVar(value=True)
            rule_weapon_id = {'value': None}

            labels = [('nome', 'Nome'), ('tipo', 'Tipo'), ('bonus_magico', 'Bonus Magico'), ('danno', 'Danno'),
                      ('gittata_corta', 'Gittata Corta'), ('gittata_media', 'Gittata Media'), ('gittata_lunga', 'Gittata Lunga'),
                      ('quantita', 'Quantita'), ('cost_mo', 'Costo MO'),
                      ('ammunition_current', 'Munizioni attuali'), ('ammunition_max', 'Munizioni max')]
            for row, (field, label) in enumerate(labels, start=1):
                ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=4)
                fields[field].grid(row=row, column=1, padx=10, pady=4)
            fields['tipo'].set("Corpo a Corpo")
            fields['bonus_magico'].set(0)
            fields['quantita'].set(1)
            fields['gittata_corta'].set(0)
            fields['gittata_media'].set(0)
            fields['gittata_lunga'].set(0)
            fields['ammunition_current'].set(0)
            fields['ammunition_max'].set(0)
            ttk.Label(dialog, text="Note/Speciale:").grid(row=12, column=0, sticky='nw', padx=10, pady=4)
            notes_text.grid(row=12, column=1, padx=10, pady=4)
            ttk.Checkbutton(dialog, text="Impugnata", variable=equipped_var).grid(row=13, column=0, padx=10, pady=4)
            ttk.Checkbutton(dialog, text="Trasportata", variable=carried_var).grid(row=13, column=1, padx=10, pady=4, sticky='w')
            warning_label = ttk.Label(dialog, text="", foreground='darkred')
            warning_label.grid(row=14, column=0, columnspan=2, sticky='w', padx=10, pady=4)

            def fill_from_catalog(event=None):
                idx = catalog_combo.current()
                if idx < 0:
                    return
                w = weapons[idx]
                rule_weapon_id['value'] = w['id']
                mapping = {
                    'nome': w.get('weapon_name') or '',
                    'tipo': {'MISCHIA': 'Corpo a Corpo', 'TIRO': 'Tiro', 'LANCIO': 'Lancio', 'ALTRO': 'Corpo a Corpo'}.get(w.get('category'), 'Corpo a Corpo'),
                    'danno': w.get('damage') or '',
                    'gittata_corta': w.get('short_range') or 0,
                    'gittata_media': w.get('medium_range') or 0,
                    'gittata_lunga': w.get('long_range') or 0,
                    'cost_mo': w.get('cost_mo') or '',
                }
                for field, value in mapping.items():
                    fields[field].delete(0, 'end')
                    fields[field].insert(0, str(value))
                validation = self.validate_equipment_allowed_for_class(class_code, 'weapon', w['id'])
                warning_label.config(text=validation['message'])

            catalog_combo.bind('<<ComboboxSelected>>', fill_from_catalog)

            def save():
                if not self.validate_equipped_weapon_limit(pg_id, int(equipped_var.get())):
                    return
                validation = self.validate_equipment_allowed_for_class(class_code, 'weapon', rule_weapon_id['value'])
                if validation['status'] == 'forbidden' and not self.user_can_edit_rule_override():
                    messagebox.showerror("Restrizione classe", validation['message'])
                    return
                if validation['status'] in ('forbidden', 'warning') and self.user_can_edit_rule_override():
                    reason = simpledialog.askstring("Motivazione DM", "Motivo per ignorare restrizione classe:")
                    self.set_rule_override(pg_id, 'equipment_restriction', f"weapon_{rule_weapon_id['value']}", validation['message'], 'CONSENTITO', reason or '', self.current_user)
                cursor = self.db.cursor()
                cursor.execute("""
                    INSERT INTO pc_armi
                        (pg_id, rule_weapon_id, nome, tipo, bonus_magico, danno, gittata_corta, gittata_media, gittata_lunga,
                         quantita, equipped, carried, ammunition_current, ammunition_max, cost_mo, notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    pg_id, rule_weapon_id['value'], fields['nome'].get(), self.normalize_weapon_type(fields['tipo'].get()),
                    int(fields['bonus_magico'].get() or 0), fields['danno'].get(),
                    int(fields['gittata_corta'].get() or 0), int(fields['gittata_media'].get() or 0),
                    int(fields['gittata_lunga'].get() or 0), int(fields['quantita'].get() or 1),
                    int(equipped_var.get()), int(carried_var.get()), int(fields['ammunition_current'].get() or 0),
                    int(fields['ammunition_max'].get() or 0),
                    Decimal(fields['cost_mo'].get() or 0) if fields['cost_mo'].get() else None,
                    notes_text.get('1.0', 'end-1c').strip()
                ))
                self.db.commit()
                cursor.close()
                self.refresh_weapons_unified_list(pg_id)
                self.update_character_equipment_calculations(pg_id)
                dialog.destroy()
                self.refresh_character_sheet_preserving_tab(pg_id, "Combattimento")

            ttk.Button(dialog, text="Salva", command=save).grid(row=15, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=15, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore arma: {e}")

    def edit_weapon_unified_dialog(self, pg_id):
        selection = self.weapons_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un'arma da modificare.")
            return
        weapon_id = self.weapons_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_armi WHERE id = %s AND pg_id = %s", (weapon_id, pg_id))
            weapon = cursor.fetchone()
            cursor.close()
            if not weapon:
                messagebox.showerror("Errore", "Arma non trovata.")
                return

            dialog = tk.Toplevel(self.root)
            dialog.title("Modifica Arma")
            dialog.geometry("520x520")
            dialog.transient(self.root)
            dialog.grab_set()

            fields = {
                'nome': ttk.Entry(dialog, width=40),
                'tipo': ttk.Combobox(dialog, values=self.get_weapon_type_options(), state='readonly', width=37),
                'bonus_magico': ttk.Spinbox(dialog, from_=-5, to=10, width=38),
                'danno': ttk.Entry(dialog, width=40),
                'gittata_corta': ttk.Spinbox(dialog, from_=0, to=999, width=38),
                'gittata_media': ttk.Spinbox(dialog, from_=0, to=999, width=38),
                'gittata_lunga': ttk.Spinbox(dialog, from_=0, to=999, width=38),
                'quantita': ttk.Spinbox(dialog, from_=1, to=999, width=38),
                'ammunition_current': ttk.Spinbox(dialog, from_=0, to=999, width=38),
                'ammunition_max': ttk.Spinbox(dialog, from_=0, to=999, width=38),
            }
            labels = [
                ('nome', 'Nome'), ('tipo', 'Tipo'), ('bonus_magico', 'Bonus Magico'),
                ('danno', 'Danno'), ('gittata_corta', 'Gittata Corta'),
                ('gittata_media', 'Gittata Media'), ('gittata_lunga', 'Gittata Lunga'),
                ('quantita', 'Quantita'), ('ammunition_current', 'Munizioni attuali'),
                ('ammunition_max', 'Munizioni max')
            ]
            for row, (field, label) in enumerate(labels):
                ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=4)
                fields[field].grid(row=row, column=1, padx=10, pady=4)

            fields['nome'].insert(0, weapon.get('nome') or '')
            fields['tipo'].set(self.normalize_weapon_type(weapon.get('tipo')))
            fields['bonus_magico'].set(weapon.get('bonus_magico', 0) or 0)
            fields['danno'].insert(0, weapon.get('danno') or '')
            for field in ['gittata_corta', 'gittata_media', 'gittata_lunga', 'quantita', 'ammunition_current', 'ammunition_max']:
                default = 1 if field == 'quantita' else 0
                fields[field].set(weapon.get(field, default) or default)

            notes_text = tk.Text(dialog, width=40, height=4)
            ttk.Label(dialog, text="Note/Speciale:").grid(row=10, column=0, sticky='nw', padx=10, pady=4)
            notes_text.grid(row=10, column=1, padx=10, pady=4)
            notes_text.insert('1.0', weapon.get('notes') or '')

            equipped_var = tk.BooleanVar(value=bool(weapon.get('equipped')))
            carried_var = tk.BooleanVar(value=bool(weapon.get('carried', 1)))
            ttk.Checkbutton(dialog, text="Impugnata", variable=equipped_var).grid(row=11, column=0, padx=10, pady=4)
            ttk.Checkbutton(dialog, text="Trasportata", variable=carried_var).grid(row=11, column=1, padx=10, pady=4, sticky='w')

            def save():
                if not self.validate_equipped_weapon_limit(pg_id, int(equipped_var.get()), weapon_id):
                    return
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        UPDATE pc_armi
                        SET nome=%s, tipo=%s, bonus_magico=%s, danno=%s,
                            gittata_corta=%s, gittata_media=%s, gittata_lunga=%s,
                            quantita=%s, equipped=%s, carried=%s,
                            ammunition_current=%s, ammunition_max=%s, notes=%s
                        WHERE id=%s AND pg_id=%s
                    """, (
                        fields['nome'].get(),
                        self.normalize_weapon_type(fields['tipo'].get()),
                        int(fields['bonus_magico'].get() or 0),
                        fields['danno'].get(),
                        int(fields['gittata_corta'].get() or 0),
                        int(fields['gittata_media'].get() or 0),
                        int(fields['gittata_lunga'].get() or 0),
                        int(fields['quantita'].get() or 1),
                        int(equipped_var.get()),
                        int(carried_var.get()),
                        int(fields['ammunition_current'].get() or 0),
                        int(fields['ammunition_max'].get() or 0),
                        notes_text.get('1.0', 'end-1c').strip(),
                        weapon_id,
                        pg_id,
                    ))
                    self.db.commit()
                    cursor.close()
                    self.refresh_weapons_unified_list(pg_id)
                    dialog.destroy()
                    self.refresh_character_sheet_preserving_tab(pg_id, "Combattimento")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore modifica arma: {e}")

            ttk.Button(dialog, text="Salva", command=save).grid(row=12, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=12, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore arma: {e}")

    def refresh_armor_list(self, pg_id):
        try:
            self.armor_tree.delete(*self.armor_tree.get_children())
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_armature WHERE pg_id = %s ORDER BY equipped DESC, tipo", (pg_id,))
            for i, armor in enumerate(cursor.fetchall()):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                self.armor_tree.insert('', 'end', values=(
                    armor.get('tipo') or '', armor.get('base_ac') if armor.get('base_ac') is not None else '',
                    armor.get('bonus_magico', 0) or 0, "Si" if armor.get('equipped') else "No",
                    armor.get('cost_mo') or '', armor.get('notes') or ''
                ), tags=(armor['id'], tag))
            cursor.close()
        except Exception as e:
            print(f"Errore refresh armature: {e}")

    def add_armor_dialog(self, pg_id):
        try:
            pg_id = int(pg_id)
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM player_characters WHERE id = %s", (pg_id,))
            character = cursor.fetchone() or {}
            cursor.close()
            class_code = self.get_character_class_code(character)
            armors = self._fetch_catalog_rows('rule_armor', 'armor_name')
            dialog = tk.Toplevel(self.root)
            dialog.title("Aggiungi Armatura")
            dialog.geometry("500x460")
            dialog.transient(self.root)
            dialog.grab_set()
            armor_combo = ttk.Combobox(dialog, width=35, state='readonly')
            armor_combo['values'] = [a['armor_name'] for a in armors]
            fields = {name: ttk.Entry(dialog, width=36) for name in ['tipo', 'base_ac', 'bonus_magico', 'cost_mo']}
            notes_text = tk.Text(dialog, width=36, height=4)
            equipped_var = tk.BooleanVar(value=True)
            rule_armor_id = {'value': None}
            ttk.Label(dialog, text="Catalogo:").grid(row=0, column=0, padx=10, pady=5, sticky='w')
            armor_combo.grid(row=0, column=1, padx=10, pady=5)
            for row, (name, label) in enumerate([('tipo', 'Tipo'), ('base_ac', 'CA base'), ('bonus_magico', 'Bonus magico'), ('cost_mo', 'Costo MO')], start=1):
                ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, padx=10, pady=5, sticky='w')
                fields[name].grid(row=row, column=1, padx=10, pady=5)
            fields['bonus_magico'].insert(0, "0")
            ttk.Label(dialog, text="Note:").grid(row=5, column=0, padx=10, pady=5, sticky='nw')
            notes_text.grid(row=5, column=1, padx=10, pady=5)
            ttk.Checkbutton(dialog, text="Equipaggiata", variable=equipped_var).grid(row=6, column=1, sticky='w', padx=10)
            warning_label = ttk.Label(dialog, text="", foreground='darkred')
            warning_label.grid(row=7, column=0, columnspan=2, sticky='w', padx=10)

            def fill(event=None):
                idx = armor_combo.current()
                if idx < 0:
                    return
                armor = armors[idx]
                rule_armor_id['value'] = armor['id']
                values = {
                    'tipo': armor.get('armor_name') or '',
                    'base_ac': armor.get('base_ac') if armor.get('base_ac') is not None else '',
                    'cost_mo': armor.get('cost_mo') or '',
                }
                for k, v in values.items():
                    fields[k].delete(0, 'end')
                    fields[k].insert(0, str(v))
                validation = self.validate_equipment_allowed_for_class(class_code, 'armor', armor['id'])
                warning_label.config(text=validation['message'])

            armor_combo.bind('<<ComboboxSelected>>', fill)

            def save():
                validation = self.validate_equipment_allowed_for_class(class_code, 'armor', rule_armor_id['value'])
                if validation['status'] == 'forbidden' and not self.user_can_edit_rule_override():
                    messagebox.showerror("Restrizione classe", validation['message'])
                    return
                cursor = self.db.cursor()
                cursor.execute("""
                    INSERT INTO pc_armature
                        (pg_id, rule_armor_id, tipo, base_ac, bonus_magico, equipped, cost_mo, notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    pg_id, rule_armor_id['value'], fields['tipo'].get(),
                    int(fields['base_ac'].get()) if fields['base_ac'].get() else None,
                    int(fields['bonus_magico'].get() or 0), int(equipped_var.get()),
                    Decimal(fields['cost_mo'].get() or 0) if fields['cost_mo'].get() else None,
                    notes_text.get('1.0', 'end-1c').strip()
                ))
                self.db.commit()
                cursor.close()
                self.refresh_armor_list(pg_id)
                self.update_character_equipment_calculations(pg_id)
                dialog.destroy()
                self.refresh_character_sheet_preserving_tab(pg_id, "Combattimento")

            ttk.Button(dialog, text="Salva", command=save).grid(row=8, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=8, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore armatura: {e}")

    def edit_armor_dialog(self, pg_id):
        selection = self.armor_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un'armatura da modificare.")
            return
        armor_id = self.armor_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_armature WHERE id = %s AND pg_id = %s", (armor_id, pg_id))
            armor = cursor.fetchone()
            cursor.close()
            if not armor:
                messagebox.showerror("Errore", "Armatura non trovata.")
                return

            dialog = tk.Toplevel(self.root)
            dialog.title("Modifica Armatura")
            dialog.geometry("500x420")
            dialog.transient(self.root)
            dialog.grab_set()

            fields = {name: ttk.Entry(dialog, width=36) for name in ['tipo', 'base_ac', 'bonus_magico', 'cost_mo']}
            for row, (name, label) in enumerate([('tipo', 'Tipo'), ('base_ac', 'CA base'), ('bonus_magico', 'Bonus magico'), ('cost_mo', 'Costo MO')]):
                ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, padx=10, pady=5, sticky='w')
                fields[name].grid(row=row, column=1, padx=10, pady=5)
                value = armor.get(name)
                fields[name].insert(0, '' if value is None else str(value))

            notes_text = tk.Text(dialog, width=36, height=5)
            ttk.Label(dialog, text="Note:").grid(row=4, column=0, padx=10, pady=5, sticky='nw')
            notes_text.grid(row=4, column=1, padx=10, pady=5)
            notes_text.insert('1.0', armor.get('notes') or '')

            equipped_var = tk.BooleanVar(value=bool(armor.get('equipped')))
            ttk.Checkbutton(dialog, text="Equipaggiata", variable=equipped_var).grid(row=5, column=1, sticky='w', padx=10, pady=5)

            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        UPDATE pc_armature
                        SET tipo=%s, base_ac=%s, bonus_magico=%s, equipped=%s, cost_mo=%s, notes=%s
                        WHERE id=%s AND pg_id=%s
                    """, (
                        fields['tipo'].get(),
                        int(fields['base_ac'].get()) if fields['base_ac'].get() else None,
                        int(fields['bonus_magico'].get() or 0),
                        int(equipped_var.get()),
                        Decimal(fields['cost_mo'].get() or 0) if fields['cost_mo'].get() else None,
                        notes_text.get('1.0', 'end-1c').strip(),
                        armor_id,
                        pg_id,
                    ))
                    self.db.commit()
                    cursor.close()
                    self.refresh_armor_list(pg_id)
                    self.update_character_equipment_calculations(pg_id)
                    dialog.destroy()
                    self.refresh_character_sheet_preserving_tab(pg_id, "Combattimento")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore modifica armatura: {e}")

            ttk.Button(dialog, text="Salva", command=save).grid(row=6, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=6, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore armatura: {e}")

    def refresh_container_list(self, pg_id):
        tree = getattr(self, 'containers_tree', None)
        if not tree:
            return
        try:
            tree.delete(*tree.get_children())
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_containers WHERE pg_id = %s ORDER BY container_name", (pg_id,))
            for row in cursor.fetchall():
                tree.insert('', 'end', values=(row['container_name'], row.get('container_type') or '', row.get('location') or '', row.get('notes') or ''), tags=(row['id'],))
            cursor.close()
        except Exception as e:
            print(f"Errore contenitori: {e}")

    def get_inventory_item_name_options(self, pg_id):
        names = []
        try:
            for item in self._fetch_catalog_rows('rule_equipment', 'item_name'):
                name = item.get('item_name')
                if name and name not in names:
                    names.append(name)
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT DISTINCT oggetto
                FROM pc_inventario
                WHERE pg_id = %s AND oggetto IS NOT NULL AND oggetto <> ''
                ORDER BY oggetto
            """, (pg_id,))
            for row in cursor.fetchall():
                name = row.get('oggetto')
                if name and name not in names:
                    names.append(name)
            cursor.close()
        except Exception:
            pass
        return sorted(names, key=lambda value: value.lower())

    def get_pg_containers(self, pg_id):
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT id, container_name FROM pc_containers WHERE pg_id = %s ORDER BY container_name", (pg_id,))
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Exception:
            return []

    def add_container_dialog(self, pg_id):
        dialog = tk.Toplevel(self.root)
        dialog.title("Aggiungi Contenitore")
        dialog.geometry("420x250")
        dialog.transient(self.root)
        dialog.grab_set()
        fields = {name: ttk.Entry(dialog, width=34) for name in ['container_name', 'container_type', 'location', 'notes']}
        labels = [('container_name', 'Nome'), ('container_type', 'Tipo'), ('location', 'Posizione'), ('notes', 'Note')]
        for row, (field, label) in enumerate(labels):
            ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, padx=10, pady=5, sticky='w')
            fields[field].grid(row=row, column=1, padx=10, pady=5)

        def save():
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO pc_containers (pg_id, container_name, container_type, location, notes)
                VALUES (%s,%s,%s,%s,%s)
            """, (pg_id, fields['container_name'].get(), fields['container_type'].get(), fields['location'].get(), fields['notes'].get()))
            self.db.commit()
            cursor.close()
            self.refresh_container_list(pg_id)
            dialog.destroy()
            self.refresh_character_sheet_preserving_tab(pg_id, "Inventario")

        ttk.Button(dialog, text="Salva", command=save).grid(row=5, column=0, pady=10)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=5, column=1, pady=10)

    def edit_container_dialog(self, pg_id):
        selection = self.containers_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un contenitore da modificare.")
            return
        container_id = self.containers_tree.item(selection[0])['tags'][0]
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM pc_containers WHERE id = %s AND pg_id = %s", (container_id, pg_id))
        container = cursor.fetchone()
        cursor.close()
        if not container:
            messagebox.showerror("Errore", "Contenitore non trovato.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Contenitore")
        dialog.geometry("420x250")
        dialog.transient(self.root)
        dialog.grab_set()
        fields = {name: ttk.Entry(dialog, width=34) for name in ['container_name', 'container_type', 'location', 'notes']}
        labels = [('container_name', 'Nome'), ('container_type', 'Tipo'), ('location', 'Posizione'), ('notes', 'Note')]
        for row, (field, label) in enumerate(labels):
            ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, padx=10, pady=5, sticky='w')
            fields[field].grid(row=row, column=1, padx=10, pady=5)
            fields[field].insert(0, container.get(field) or '')

        def save():
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE pc_containers
                SET container_name=%s, container_type=%s, location=%s, notes=%s
                WHERE id=%s AND pg_id=%s
            """, (
                fields['container_name'].get(),
                fields['container_type'].get(),
                fields['location'].get(),
                fields['notes'].get(),
                container_id,
                pg_id,
            ))
            self.db.commit()
            cursor.close()
            self.refresh_container_list(pg_id)
            self.refresh_inventory_lists(pg_id)
            dialog.destroy()
            self.refresh_character_sheet_preserving_tab(pg_id, "Inventario")

        ttk.Button(dialog, text="Salva", command=save).grid(row=5, column=0, pady=10)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=5, column=1, pady=10)

    def delete_container(self, pg_id):
        selection = self.containers_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un contenitore da eliminare.")
            return
        container_id = self.containers_tree.item(selection[0])['tags'][0]
        cursor = self.db.cursor()
        cursor.execute("SELECT container_name FROM pc_containers WHERE id = %s AND pg_id = %s", (container_id, pg_id))
        container = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS count_items FROM pc_inventario WHERE pg_id = %s AND container_id = %s", (pg_id, container_id))
        count_items = (cursor.fetchone() or {}).get('count_items') or 0
        cursor.close()
        if not container:
            messagebox.showerror("Errore", "Contenitore non trovato.")
            return

        message = (
            f"Eliminare il contenitore '{container.get('container_name')}'?\n\n"
            f"Attenzione: verranno eliminati anche {count_items} oggetti contenuti al suo interno."
        )
        if not messagebox.askyesno("Conferma eliminazione contenitore", message):
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_inventario WHERE pg_id = %s AND container_id = %s", (pg_id, container_id))
            cursor.execute("DELETE FROM pc_containers WHERE id = %s AND pg_id = %s", (container_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_container_list(pg_id)
            self.refresh_inventory_lists(pg_id)
            self.refresh_character_sheet_preserving_tab(pg_id, "Inventario")
        except Exception as e:
            messagebox.showerror("Errore", f"Errore eliminazione contenitore: {e}")

    def transfer_container_contents(self, pg_id):
        containers = self.get_pg_containers(pg_id)
        if len(containers) < 2:
            messagebox.showwarning("Attenzione", "Servono almeno due contenitori per travasare gli oggetti.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Travasa Contenitore")
        dialog.geometry("420x180")
        dialog.transient(self.root)
        dialog.grab_set()
        names = [c['container_name'] for c in containers]
        source_combo = ttk.Combobox(dialog, values=names, width=34, state='readonly')
        target_combo = ttk.Combobox(dialog, values=names, width=34, state='readonly')
        ttk.Label(dialog, text="Da contenitore:").grid(row=0, column=0, padx=10, pady=8, sticky='w')
        source_combo.grid(row=0, column=1, padx=10, pady=8)
        ttk.Label(dialog, text="A contenitore:").grid(row=1, column=0, padx=10, pady=8, sticky='w')
        target_combo.grid(row=1, column=1, padx=10, pady=8)

        def save():
            if source_combo.current() < 0 or target_combo.current() < 0:
                messagebox.showwarning("Attenzione", "Seleziona entrambi i contenitori.")
                return
            source_id = containers[source_combo.current()]['id']
            target_id = containers[target_combo.current()]['id']
            if source_id == target_id:
                messagebox.showwarning("Attenzione", "Il contenitore di partenza e quello di arrivo devono essere diversi.")
                return
            cursor = self.db.cursor()
            cursor.execute("UPDATE pc_inventario SET container_id = %s WHERE pg_id = %s AND container_id = %s", (target_id, pg_id, source_id))
            self.db.commit()
            cursor.close()
            self.refresh_inventory_lists(pg_id)
            dialog.destroy()

        ttk.Button(dialog, text="Travasa", command=save).grid(row=2, column=0, pady=12)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=2, column=1, pady=12)

    def refresh_inventory_lists(self, pg_id):
        try:
            cursor = self.db.cursor()
            self.inventory_tree.delete(*self.inventory_tree.get_children())
            search_var = getattr(self, 'inventory_search_var', None)
            search_text = search_var.get().strip() if search_var else ''
            order_column = getattr(self, 'inventory_sort_column', 'oggetto')
            order_dir = getattr(self, 'inventory_sort_dir', 'ASC')
            order_map = {
                'oggetto': 'pi.oggetto',
                'contenitore': 'pc.container_name',
            }
            order_sql = order_map.get(order_column, 'pi.oggetto')
            params = [pg_id]
            where = "WHERE pi.pg_id = %s"
            if search_text:
                where += " AND pi.oggetto LIKE %s"
                params.append(f"%{search_text}%")
            cursor.execute(f"""
                SELECT pi.*, pc.container_name
                FROM pc_inventario pi
                LEFT JOIN pc_containers pc ON pi.container_id = pc.id
                {where}
                ORDER BY {order_sql} {order_dir}, pi.oggetto ASC
            """, tuple(params))
            for i, item in enumerate(cursor.fetchall()):
                self.inventory_tree.insert('', 'end', values=(
                    item.get('oggetto') or '', item.get('quantita') or 1,
                    item.get('container_name') or '', item.get('location') or '',
                    "Si" if item.get('carried', 1) else "No",
                    "Si" if item.get('consumable') else "No"
                ), tags=(item['id'], 'evenrow' if i % 2 == 0 else 'oddrow'))
            cursor.close()
        except Exception as e:
            print(f"Errore refresh inventario: {e}")

    def sort_inventory_by_column(self, pg_id, column):
        current_column = getattr(self, 'inventory_sort_column', 'oggetto')
        current_dir = getattr(self, 'inventory_sort_dir', 'ASC')
        self.inventory_sort_column = column
        self.inventory_sort_dir = 'DESC' if current_column == column and current_dir == 'ASC' else 'ASC'
        self.refresh_inventory_lists(pg_id)

    def add_inventory_dialog(self, pg_id, tipo='equipaggiamento'):
        try:
            items = self._fetch_catalog_rows('rule_equipment', 'item_name')
            cursor = self.db.cursor()
            cursor.execute("SELECT id, container_name FROM pc_containers WHERE pg_id = %s ORDER BY container_name", (pg_id,))
            containers = cursor.fetchall()
            cursor.close()
            dialog = tk.Toplevel(self.root)
            dialog.title("Aggiungi Equipaggiamento")
            dialog.geometry("470x360")
            dialog.transient(self.root)
            dialog.grab_set()
            item_combo = ttk.Combobox(dialog, width=36)
            item_combo['values'] = self.get_inventory_item_name_options(pg_id)
            qty = ttk.Spinbox(dialog, from_=1, to=999, width=34)
            qty.set(1)
            container_combo = ttk.Combobox(dialog, width=36, state='readonly')
            container_combo['values'] = [c['container_name'] for c in containers]
            location = ttk.Entry(dialog, width=38)
            carried_var = tk.BooleanVar(value=True)
            consumable_var = tk.BooleanVar(value=False)
            rule_equipment_id = {'value': None}
            for row, (label, widget) in enumerate([('Oggetto', item_combo), ('Quantita', qty), ('Contenitore', container_combo), ('Collocazione', location)]):
                ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, padx=10, pady=5, sticky='w')
                widget.grid(row=row, column=1, padx=10, pady=5)
            ttk.Checkbutton(dialog, text="Trasportato", variable=carried_var).grid(row=4, column=0, padx=10, pady=5)
            ttk.Checkbutton(dialog, text="Consumabile", variable=consumable_var).grid(row=4, column=1, padx=10, pady=5, sticky='w')

            def fill(event=None):
                selected_name = item_combo.get().strip()
                if not selected_name:
                    return
                item = next((row for row in items if row.get('item_name') == selected_name), None)
                if not item:
                    rule_equipment_id['value'] = None
                    return
                rule_equipment_id['value'] = item['id']
                consumable_var.set(bool(item.get('is_consumable')))

            item_combo.bind('<<ComboboxSelected>>', fill)
            item_combo.bind('<FocusOut>', fill, add='+')

            def save():
                quantity = int(qty.get() or 1)
                container_id = containers[container_combo.current()]['id'] if container_combo.current() >= 0 else None
                cursor = self.db.cursor()
                cursor.execute("""
                    INSERT INTO pc_inventario
                        (pg_id, tipo, oggetto, quantita, rule_equipment_id, container_id, location,
                         carried, consumable)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (pg_id, tipo, item_combo.get(), quantity, rule_equipment_id['value'], container_id, location.get(), int(carried_var.get()), int(consumable_var.get())))
                self.db.commit()
                cursor.close()
                self.refresh_inventory_lists(pg_id)
                self.update_character_equipment_calculations(pg_id)
                dialog.destroy()

            ttk.Button(dialog, text="Salva", command=save).grid(row=5, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=5, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore inventario: {e}")

    def get_selected_inventory_item_id(self):
        selection = self.inventory_tree.selection()
        if not selection:
            return None
        return self.inventory_tree.item(selection[0])['tags'][0]

    def edit_inventory_item_dialog(self, pg_id):
        item_id = self.get_selected_inventory_item_id()
        if not item_id:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto da modificare.")
            return
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM pc_inventario WHERE id = %s AND pg_id = %s", (item_id, pg_id))
        item = cursor.fetchone()
        containers = self.get_pg_containers(pg_id)
        cursor.close()
        if not item:
            messagebox.showerror("Errore", "Oggetto non trovato.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Equipaggiamento")
        dialog.geometry("470x360")
        dialog.transient(self.root)
        dialog.grab_set()
        name = ttk.Entry(dialog, width=38)
        qty = ttk.Spinbox(dialog, from_=1, to=999, width=36)
        container_combo = ttk.Combobox(dialog, width=36, state='readonly')
        container_combo['values'] = [''] + [c['container_name'] for c in containers]
        location = ttk.Entry(dialog, width=38)
        carried_var = tk.BooleanVar(value=bool(item.get('carried', 1)))
        consumable_var = tk.BooleanVar(value=bool(item.get('consumable')))

        fields = [('Oggetto', name), ('Quantita', qty), ('Contenitore', container_combo), ('Collocazione', location)]
        for row, (label, widget) in enumerate(fields):
            ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, padx=10, pady=5, sticky='w')
            widget.grid(row=row, column=1, padx=10, pady=5)
        name.insert(0, item.get('oggetto') or '')
        qty.set(item.get('quantita') or 1)
        location.insert(0, item.get('location') or '')
        current_container_id = item.get('container_id')
        if current_container_id:
            for index, container in enumerate(containers, start=1):
                if container['id'] == current_container_id:
                    container_combo.current(index)
                    break
        else:
            container_combo.current(0)
        ttk.Checkbutton(dialog, text="Trasportato", variable=carried_var).grid(row=4, column=0, padx=10, pady=5)
        ttk.Checkbutton(dialog, text="Consumabile", variable=consumable_var).grid(row=4, column=1, padx=10, pady=5, sticky='w')

        def save():
            container_id = None
            if container_combo.current() > 0:
                container_id = containers[container_combo.current() - 1]['id']
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE pc_inventario
                SET oggetto=%s, quantita=%s, container_id=%s, location=%s, carried=%s, consumable=%s
                WHERE id=%s AND pg_id=%s
            """, (
                name.get(),
                int(qty.get() or 1),
                container_id,
                location.get(),
                int(carried_var.get()),
                int(consumable_var.get()),
                item_id,
                pg_id,
            ))
            self.db.commit()
            cursor.close()
            self.refresh_inventory_lists(pg_id)
            dialog.destroy()

        ttk.Button(dialog, text="Salva", command=save).grid(row=5, column=0, pady=10)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=5, column=1, pady=10)

    def move_inventory_item_container(self, pg_id):
        item_id = self.get_selected_inventory_item_id()
        if not item_id:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto da spostare.")
            return
        containers = self.get_pg_containers(pg_id)
        if len(containers) <= 1:
            messagebox.showwarning("Attenzione", "Servono almeno due contenitori per spostare un oggetto.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Sposta in altro contenitore")
        dialog.geometry("420x140")
        dialog.transient(self.root)
        dialog.grab_set()
        target_combo = ttk.Combobox(dialog, values=[c['container_name'] for c in containers], width=34, state='readonly')
        ttk.Label(dialog, text="Nuovo contenitore:").grid(row=0, column=0, padx=10, pady=12, sticky='w')
        target_combo.grid(row=0, column=1, padx=10, pady=12)

        def save():
            if target_combo.current() < 0:
                messagebox.showwarning("Attenzione", "Seleziona un contenitore.")
                return
            target_id = containers[target_combo.current()]['id']
            cursor = self.db.cursor()
            cursor.execute("UPDATE pc_inventario SET container_id = %s WHERE id = %s AND pg_id = %s", (target_id, item_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_inventory_lists(pg_id)
            dialog.destroy()

        ttk.Button(dialog, text="Sposta", command=save).grid(row=1, column=0, pady=10)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=1, column=1, pady=10)

    def delete_inventory_item(self, pg_id, tipo=None):
        """Elimina oggetto inventario dalla lista equipaggiamento unica."""
        item_id = self.get_selected_inventory_item_id()
        if not item_id:
            return
        if not messagebox.askyesno("Conferma", "Eliminare l'oggetto selezionato?"):
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_inventario WHERE id = %s AND pg_id = %s", (item_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_inventory_lists(pg_id)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")

    # ==================== GESTIONE OGGETTI MAGICI ====================
    
    def refresh_magic_items_list(self, pg_id):
        """Ricarica oggetti magici - Con righe alternate"""
        try:
            self.magic_tree.delete(*self.magic_tree.get_children())
            self.magic_tree.tag_configure('oddrow', background='white')
            self.magic_tree.tag_configure('evenrow', background='#f0f0f0')
            
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_oggetti_magici WHERE pg_id = %s", (pg_id,))
            items = cursor.fetchall()
            cursor.close()
            
            for i, item in enumerate(items):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                self.magic_tree.insert('', 'end', values=(
                    item['oggetto'], item['effetto'], item['potere']
                ), tags=(item['id'], tag))
        except Exception as e:
            print(f"Errore refresh oggetti magici: {e}")
    
    def add_magic_item_dialog(self, pg_id):
        """Dialog aggiungi oggetto magico"""
        try:
            if not pg_id or pg_id == '' or pg_id == 'None':
                pg_id = self.current_sheet_pg_id
                
            pg_id = int(pg_id)
            
            dialog = tk.Toplevel(self.root)
            dialog.title("Aggiungi Oggetto Magico")
            dialog.geometry("450x230")
            dialog.transient(self.root)
            dialog.grab_set()
            
            ttk.Label(dialog, text="Oggetto:").grid(row=0, column=0, sticky='w', padx=10, pady=10)
            oggetto_var = ttk.Entry(dialog, width=40)
            oggetto_var.grid(row=0, column=1, padx=10, pady=10)
            
            ttk.Label(dialog, text="Effetto:").grid(row=1, column=0, sticky='nw', padx=10, pady=10)
            effetto_text = tk.Text(dialog, width=40, height=3)
            effetto_text.grid(row=1, column=1, padx=10, pady=10)
            
            ttk.Label(dialog, text="Potere:").grid(row=2, column=0, sticky='nw', padx=10, pady=10)
            potere_text = tk.Text(dialog, width=40, height=3)
            potere_text.grid(row=2, column=1, padx=10, pady=10)
            
            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("SELECT id FROM player_characters WHERE id = %s", (pg_id,))
                    if not cursor.fetchone():
                        cursor.close()
                        messagebox.showerror("Errore", "Personaggio non trovato!")
                        return
                    
                    cursor.execute("""
                        INSERT INTO pc_oggetti_magici (pg_id, oggetto, effetto, potere)
                        VALUES (%s, %s, %s, %s)
                    """, (pg_id, oggetto_var.get(), 
                          effetto_text.get('1.0', 'end-1c'),
                          potere_text.get('1.0', 'end-1c')))
                    self.db.commit()
                    cursor.close()
                    
                    self.refresh_magic_items_list(pg_id)
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")
            
            ttk.Button(dialog, text="Salva", command=save).grid(row=3, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=3, column=1, pady=10)
            
        except ValueError:
            messagebox.showerror("Errore", "ID personaggio non valido!")
    
    def delete_magic_item(self, pg_id):
        """Elimina oggetto magico"""
        selection = self.magic_tree.selection()
        if not selection:
            return
        
        item = self.magic_tree.item(selection[0])
        item_id = item['tags'][0]
        if not messagebox.askyesno("Conferma", "Eliminare l'oggetto magico selezionato?"):
            return
        
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_oggetti_magici WHERE id = %s AND pg_id = %s", (item_id, pg_id))
            self.db.commit()
            cursor.close()
            
            self.refresh_magic_items_list(pg_id)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")

    def create_character_followers_tab(self, notebook, pg_id, character):
        """Tab Seguaci della scheda personaggio."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Seguaci")

        # NOTA 2026-05-23:
        # Cavalcature e creature familiari non sono piu' mostrate nel TAB Seguaci.
        # Le tabelle pc_cavalcature e pc_creature_familiari restano nel DB per compatibilita'.
        self.followers_pg_id = int(pg_id)
        self.current_follower_id = None
        self.followers_mode = "view"
        self.followers_dirty = False
        self.followers_loading_form = False
        self.follower_widgets = {}
        self.followers_row_map = {}
        self.follower_bank_map = {}

        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=3)
        tab.rowconfigure(0, weight=1)

        list_frame = ttk.LabelFrame(tab, text="Seguaci del PG", padding=8)
        list_frame.grid(row=0, column=0, sticky='nsew', padx=(10, 5), pady=10)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        columns = ('Nome', 'Classe', 'Liv', 'Stato', 'Morale')
        self.character_followers_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=18)
        widths = {'Nome': 150, 'Classe': 95, 'Liv': 45, 'Stato': 90, 'Morale': 60}
        for col in columns:
            self.character_followers_tree.heading(col, text=col)
            self.character_followers_tree.column(col, width=widths[col], anchor='center')
        self.character_followers_tree.grid(row=0, column=0, sticky='nsew')

        follower_scroll = ttk.Scrollbar(list_frame, orient='vertical', command=self.character_followers_tree.yview)
        follower_scroll.grid(row=0, column=1, sticky='ns')
        self.character_followers_tree.configure(yscrollcommand=follower_scroll.set)
        self.character_followers_tree.bind("<<TreeviewSelect>>", self.on_character_follower_selected)

        button_frame = ttk.Frame(list_frame)
        button_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        if self.current_user and self.current_user.get('role') == 'DM':
            ttk.Button(button_frame, text="Nuovo Seguace", command=self.new_character_follower).pack(side='left', padx=2)
        ttk.Button(button_frame, text="Salva Seguace", command=self.save_current_follower).pack(side='left', padx=2)
        if self.current_user and self.current_user.get('role') == 'DM':
            ttk.Button(button_frame, text="Elimina Seguace", command=self.delete_current_follower).pack(side='left', padx=2)
        ttk.Button(button_frame, text="Annulla modifiche", command=self.cancel_follower_changes).pack(side='left', padx=2)
        ttk.Button(button_frame, text="Refresh", command=lambda: self.load_followers_for_pg(pg_id)).pack(side='left', padx=2)

        loyalty_frame = ttk.LabelFrame(list_frame, text="Carisma e seguaci", padding=6)
        loyalty_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        follower_rules = self.calculate_follower_limits(pg_id)
        ttk.Label(
            loyalty_frame,
            text=(
                f"Carisma {follower_rules['charisma']} | "
                f"max seguaci {follower_rules['max_followers']} | "
                f"morale base {follower_rules['base_morale']} | "
                f"reazioni {follower_rules['reaction_modifier']:+d} | "
                f"attuali {follower_rules['current_followers']}"
            )
        ).pack(side='left', padx=5)
        if self.user_can_edit_rule_override():
            ttk.Button(
                loyalty_frame,
                text="Override Max",
                command=lambda: self.override_character_rule_dialog(pg_id, 'followers', 'max_followers', follower_rules['max_followers'], 'Massimo Seguaci')
            ).pack(side='left', padx=3)
            ttk.Button(
                loyalty_frame,
                text="Override Morale",
                command=lambda: self.override_character_rule_dialog(pg_id, 'followers', 'base_morale', follower_rules['base_morale'], 'Morale Base Seguaci')
            ).pack(side='left', padx=3)

        detail_frame = ttk.LabelFrame(tab, text="Scheda seguace", padding=8)
        detail_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 10), pady=10)
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)

        detail_canvas = tk.Canvas(detail_frame, highlightthickness=0)
        detail_canvas.grid(row=0, column=0, sticky='nsew')
        detail_xscroll = ttk.Scrollbar(detail_frame, orient='horizontal', command=detail_canvas.xview)
        detail_xscroll.grid(row=1, column=0, sticky='ew', pady=(4, 0))
        detail_canvas.configure(xscrollcommand=detail_xscroll.set)

        detail_content = ttk.Frame(detail_canvas)
        detail_window = detail_canvas.create_window((0, 0), window=detail_content, anchor='nw')

        def update_follower_detail_scrollregion(event=None):
            detail_canvas.update_idletasks()
            requested_width = detail_content.winfo_reqwidth()
            visible_width = detail_canvas.winfo_width()
            detail_canvas.itemconfigure(detail_window, width=max(requested_width, visible_width))
            detail_canvas.configure(scrollregion=detail_canvas.bbox('all'))

        detail_content.bind("<Configure>", update_follower_detail_scrollregion)
        detail_canvas.bind("<Configure>", update_follower_detail_scrollregion)

        detail_notebook = ttk.Notebook(detail_content)
        self.follower_detail_notebook = detail_notebook
        detail_notebook.grid(row=0, column=0, sticky='nsew')
        detail_content.rowconfigure(0, weight=1)
        detail_content.columnconfigure(0, weight=1)

        self.build_follower_identity_tab(detail_notebook)
        self.build_follower_stats_tab(detail_notebook)
        self.build_follower_combat_tab(detail_notebook)
        self.build_follower_management_tab(detail_notebook)
        self.build_follower_equipment_tab(detail_notebook)
        self.build_follower_skills_tab(detail_notebook)
        self.build_follower_story_tab(detail_notebook)

        self.load_follower_banks(pg_id)
        self.clear_follower_form()
        self.load_followers_for_pg(pg_id)

    def set_follower_detail_tabs_enabled(self, enabled):
        notebook = getattr(self, 'follower_detail_notebook', None)
        if not notebook:
            return
        for index in range(len(notebook.tabs())):
            state = 'normal' if enabled or index == 0 else 'disabled'
            try:
                notebook.tab(index, state=state)
            except Exception:
                pass
        if not enabled:
            try:
                notebook.select(0)
            except Exception:
                pass

    def follower_text_fields(self):
        return {
            'weapons_damage', 'equipment', 'magic_items_permanent',
            'magic_items_temporary', 'gems_treasures', 'class_abilities',
            'spells', 'general_skills', 'known_languages',
            'physical_appearance', 'personality', 'background', 'notes',
            'equipment_supplied_by_pg', 'dm_private_notes'
        }

    def follower_int_fields(self):
        return {
            'level', 'forza', 'forza_mod', 'intelligenza', 'intelligenza_mod',
            'saggezza', 'saggezza_mod', 'destrezza', 'destrezza_mod',
            'costituzione', 'costituzione_mod', 'carisma', 'carisma_mod',
            'pf_attuali', 'pf_massimi', 'classe_armatura', 'thac0',
            'ts_morte_veleno', 'ts_bacchette', 'ts_paralisi_pietrificazione',
            'ts_soffi', 'ts_incantesimi', 'px', 'px_next_level', 'morale',
            'money_mp', 'money_mo', 'money_me', 'money_ma', 'money_mr',
            'loyalty'
        }

    def follower_decimal_fields(self):
        return {'annual_cost'}

    def follower_player_readonly_fields(self):
        return {
            'forza', 'forza_mod', 'intelligenza', 'intelligenza_mod',
            'saggezza', 'saggezza_mod', 'destrezza', 'destrezza_mod',
            'costituzione', 'costituzione_mod', 'carisma', 'carisma_mod',
            'px', 'annual_cost'
        }

    def follower_field_is_player_readonly(self, field):
        return (
            self.current_user
            and self.current_user.get('role') == 'GIOCATORE'
            and field in self.follower_player_readonly_fields()
        )

    def apply_follower_widget_permissions(self, field, widget):
        if not self.follower_field_is_player_readonly(field):
            return
        try:
            if isinstance(widget, ttk.Combobox):
                widget.configure(style='FollowerReadonly.TCombobox')
                widget.configure(state='disabled')
            elif isinstance(widget, tk.Entry):
                widget.configure(
                    readonlybackground='#EEEEEE',
                    disabledbackground='#EEEEEE',
                    foreground='#555555',
                    disabledforeground='#555555',
                    state='readonly'
                )
            else:
                widget.configure(style='FollowerReadonly.TEntry')
                widget.configure(state='readonly')
        except Exception:
            try:
                widget.configure(background='#EEEEEE', foreground='#555555')
                widget.configure(state='disabled')
            except Exception:
                pass

    def add_follower_entry(self, parent, row, col, field, label, width=18, values=None):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky='w', padx=5, pady=3)
        if values:
            widget = ttk.Combobox(parent, width=width, values=values)
        elif self.follower_field_is_player_readonly(field):
            widget = tk.Entry(parent, width=width, relief='solid', bd=1)
        else:
            widget = ttk.Entry(parent, width=width)
        widget.grid(row=row, column=col + 1, sticky='w', padx=5, pady=3)
        widget.bind("<KeyRelease>", self.mark_followers_dirty, add="+")
        widget.bind("<FocusOut>", self.mark_followers_dirty, add="+")
        if isinstance(widget, ttk.Combobox):
            widget.bind("<<ComboboxSelected>>", self.mark_followers_dirty, add="+")
        self.follower_widgets[field] = widget
        self.apply_follower_widget_permissions(field, widget)
        return widget

    def add_follower_text(self, parent, row, field, label, height=4):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='nw', padx=5, pady=3)
        widget = scrolledtext.ScrolledText(parent, height=height, wrap='word')
        widget.grid(row=row, column=1, columnspan=3, sticky='nsew', padx=5, pady=3)
        widget.bind("<KeyRelease>", self.mark_followers_dirty, add="+")
        widget.bind("<FocusOut>", self.mark_followers_dirty, add="+")
        self.follower_widgets[field] = widget
        return widget

    def build_follower_identity_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text="Identita")
        for col in (1, 3):
            frame.columnconfigure(col, weight=0)
        self.add_follower_entry(frame, 0, 0, 'name', 'Nome', width=15)
        self.add_follower_entry(frame, 0, 2, 'race', 'Razza', width=15, values=['Umano', 'Nano', 'Elfo', 'Halfling', 'Altro'])
        self.add_follower_entry(frame, 1, 0, 'class', 'Classe', width=15, values=['Guerriero', 'Chierico', 'Mago', 'Ladro', 'Elfo', 'Nano', 'Halfling', 'Altro'])
        self.add_follower_entry(frame, 1, 2, 'level', 'Livello', width=15)
        self.add_follower_entry(frame, 2, 0, 'alignment', 'Allineamento', width=15, values=['Legale', 'Neutrale', 'Caotico'])
        self.add_follower_entry(frame, 2, 2, 'role_task', 'Mansione/Ruolo', width=15)
        self.add_follower_entry(frame, 3, 0, 'status', 'Stato', width=15, values=['ATTIVO', 'FERITO', 'MORTO', 'DISPERSO', 'LICENZIATO', 'IN_MISSIONE', 'IN_ATTESA'])
        self.add_follower_entry(frame, 3, 2, 'loyalty', 'Lealta', width=15)
        self.add_follower_entry(frame, 4, 0, 'description', 'Descrizione breve', width=15)
        self.add_follower_entry(frame, 5, 0, 'age', 'Eta', width=15)
        self.add_follower_entry(frame, 5, 2, 'gender', 'Genere', width=15)
        self.add_follower_entry(frame, 6, 0, 'height', 'Altezza', width=15)
        self.add_follower_entry(frame, 6, 2, 'weight', 'Peso', width=15)

    def build_follower_stats_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text="Caratteristiche")
        for col in (1, 3):
            frame.columnconfigure(col, weight=0)
        stats = [
            ('forza', 'Forza', 'forza_mod', 'Mod. Forza'),
            ('intelligenza', 'Intelligenza', 'intelligenza_mod', 'Mod. Intelligenza'),
            ('saggezza', 'Saggezza', 'saggezza_mod', 'Mod. Saggezza'),
            ('destrezza', 'Destrezza', 'destrezza_mod', 'Mod. Destrezza'),
            ('costituzione', 'Costituzione', 'costituzione_mod', 'Mod. Costituzione'),
            ('carisma', 'Carisma', 'carisma_mod', 'Mod. Carisma'),
        ]
        for row, (score_field, score_label, mod_field, mod_label) in enumerate(stats):
            self.add_follower_entry(frame, row, 0, score_field, score_label, width=3)
            self.add_follower_entry(frame, row, 2, mod_field, mod_label, width=3)
        if self.current_user and self.current_user.get('role') == 'DM':
            ttk.Button(frame, text="Calcola Modificatori", command=self.calculate_follower_modifiers).grid(
                row=len(stats), column=0, columnspan=4, pady=10
            )

    def build_follower_combat_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text="Combattimento")
        for col in (1, 3):
            frame.columnconfigure(col, weight=0)
        fields = [
            ('pf_attuali', 'PF attuali'), ('pf_massimi', 'PF massimi'),
            ('classe_armatura', 'Classe Armatura'), ('thac0', 'THAC0'),
            ('movimento', 'Movimento'), ('ts_morte_veleno', 'TS Morte/Veleno'),
            ('ts_bacchette', 'TS Bacchette'), ('ts_paralisi_pietrificazione', 'TS Paralisi/Pietr.'),
            ('ts_soffi', 'TS Soffi'), ('ts_incantesimi', 'TS Incantesimi'),
        ]
        for index, (field, label) in enumerate(fields):
            self.add_follower_entry(frame, index // 2, (index % 2) * 2, field, label, width=4)

    def build_follower_management_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text="Gestione")
        frame.columnconfigure(1, weight=1)

        compact_frame = ttk.Frame(frame)
        compact_frame.grid(row=0, column=0, columnspan=2, sticky='w')
        left_frame = ttk.Frame(compact_frame)
        left_frame.grid(row=0, column=0, sticky='nw')
        right_frame = ttk.Frame(compact_frame)
        right_frame.grid(row=0, column=1, sticky='nw', padx=(18, 0))

        left_fields = [
            ('px', 'PX'),
            ('annual_cost', 'Costo annuo'),
            ('morale', 'Morale'),
            ('hire_date', 'Data ingaggio'),
            ('last_payment_date', 'Ultimo pagamento'),
        ]
        right_fields = [
            ('px_next_level', 'PX livello successivo'),
            ('salary_agreement', 'Paga/Accordo'),
            ('pay_frequency', 'Frequenza paga'),
            ('current_location', 'Luogo attuale'),
            ('next_payment_date', 'Prossimo pagamento'),
        ]
        for row, (field, label) in enumerate(left_fields):
            self.add_follower_entry(left_frame, row, 0, field, label, width=25)
        for row, (field, label) in enumerate(right_fields):
            self.add_follower_entry(right_frame, row, 0, field, label, width=25)

        ttk.Label(frame, text="Banca costo/salario").grid(row=1, column=0, sticky='w', padx=5, pady=3)
        bank_combo = ttk.Combobox(frame, width=25, state='readonly')
        bank_combo.grid(row=1, column=1, sticky='w', padx=5, pady=3)
        bank_combo.bind("<<ComboboxSelected>>", self.mark_followers_dirty, add="+")
        self.follower_widgets['bank_destination_cost'] = bank_combo
        self.add_follower_entry(frame, 2, 0, 'treasure_share', 'Quota tesoro', width=25)
        self.add_follower_text(frame, 3, 'equipment_supplied_by_pg', 'Equipaggiamento fornito dal PG', height=4)
        if self.current_user and self.current_user.get('role') == 'DM':
            self.add_follower_text(frame, 4, 'dm_private_notes', 'Note private DM', height=4)

    def build_follower_equipment_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text="Equipaggiamento")
        frame.columnconfigure(1, weight=1)

        money_frame = ttk.Frame(frame)
        money_frame.grid(row=0, column=0, columnspan=2, sticky='w')
        money_left_frame = ttk.Frame(money_frame)
        money_left_frame.grid(row=0, column=0, sticky='nw')
        money_right_frame = ttk.Frame(money_frame)
        money_right_frame.grid(row=0, column=1, sticky='nw', padx=(18, 0))

        money_left = [
            ('money_mp', 'MP'),
            ('money_me', 'ME'),
            ('money_mr', 'MR'),
        ]
        money_right = [
            ('money_mo', 'MO'),
            ('money_ma', 'MA'),
        ]
        for row, (field, label) in enumerate(money_left):
            self.add_follower_entry(money_left_frame, row, 0, field, label, width=10)
        for row, (field, label) in enumerate(money_right):
            self.add_follower_entry(money_right_frame, row, 0, field, label, width=10)

        for row, (field, label, height) in enumerate([
            ('weapons_damage', 'Armi e danni', 3),
            ('equipment', 'Equipaggiamento', 4),
            ('magic_items_permanent', 'Oggetti magici permanenti', 3),
            ('magic_items_temporary', 'Oggetti magici temporanei/cariche', 3),
            ('gems_treasures', 'Gemme e tesori', 3),
        ], start=1):
            frame.rowconfigure(row, weight=1)
            self.add_follower_text(frame, row, field, label, height=height)

    def build_follower_skills_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text="Abilita")
        frame.columnconfigure(1, weight=1)
        for row, (field, label, height) in enumerate([
            ('class_abilities', 'Abilita di classe', 5),
            ('spells', 'Incantesimi', 5),
            ('general_skills', 'Abilita generali', 5),
            ('known_languages', 'Lingue conosciute', 4),
        ]):
            frame.rowconfigure(row, weight=1)
            self.add_follower_text(frame, row, field, label, height=height)

    def build_follower_story_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text="Narrativa")
        frame.columnconfigure(1, weight=1)
        for row, (field, label, height) in enumerate([
            ('physical_appearance', 'Aspetto fisico', 4),
            ('personality', 'Personalita', 4),
            ('background', 'Background', 5),
            ('notes', 'Note', 5),
        ]):
            frame.rowconfigure(row, weight=1)
            self.add_follower_text(frame, row, field, label, height=height)

    def verify_character_sheet_pg_access(self, pg_id):
        if not self.current_user:
            return False
        if self.current_user.get('role') == 'DM':
            return True
        cursor = self.db.cursor()
        try:
            cursor.execute(
                "SELECT id FROM player_characters WHERE id = %s AND user_id = %s",
                (pg_id, self.current_user['id'])
            )
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    def load_follower_banks(self, pg_id):
        cursor = self.db.cursor()
        try:
            cursor.execute("SELECT id, name, location FROM banks WHERE pg_id = %s ORDER BY name ASC", (pg_id,))
            banks = cursor.fetchall()
        finally:
            cursor.close()
        values = ["Nessuna banca"]
        self.follower_bank_map = {"Nessuna banca": None}
        for bank in banks:
            label = bank['name'] or 'Banca senza nome'
            if bank.get('location'):
                label = f"{label} - {bank['location']}"
            values.append(label)
            self.follower_bank_map[label] = bank['id']
        combo = self.follower_widgets.get('bank_destination_cost')
        if combo:
            combo['values'] = values
            combo.set("Nessuna banca")

    def load_followers_for_pg(self, pg_id, select_follower_id=None):
        if not self.verify_character_sheet_pg_access(pg_id):
            messagebox.showerror("Errore", "Personaggio non autorizzato.")
            return
        tree = getattr(self, 'character_followers_tree', None)
        if not tree:
            return
        for item in tree.get_children():
            tree.delete(item)
        self.followers_row_map = {}
        cursor = self.db.cursor()
        try:
            cursor.execute("""
                SELECT id, name, race, `class`, `level`, status, role_task, morale
                FROM followers
                WHERE pg_id = %s
                ORDER BY name ASC, id ASC
            """, (pg_id,))
            rows = cursor.fetchall()
        except Exception as e:
            messagebox.showerror(
                "Migrazione richiesta",
                "Il TAB Seguaci richiede l'esecuzione dello script SQL "
                ".github/docs/followers_extended_sheet_migration.sql.\n\n"
                f"Dettaglio: {e}"
            )
            return
        finally:
            cursor.close()
        item_to_select = None
        for row in rows:
            values = (
                row.get('name') or '',
                row.get('class') or '',
                row.get('level') or 0,
                row.get('status') or 'ATTIVO',
                row.get('morale') or 0,
            )
            item = tree.insert('', 'end', values=values, tags=(str(row['id']),))
            self.followers_row_map[item] = row['id']
            if select_follower_id and int(row['id']) == int(select_follower_id):
                item_to_select = item
        if item_to_select:
            tree.selection_set(item_to_select)
            tree.focus(item_to_select)
            self.load_follower_detail(select_follower_id, pg_id)

    def get_selected_character_follower_id(self):
        tree = getattr(self, 'character_followers_tree', None)
        if not tree:
            return None
        selected = tree.selection()
        item = selected[0] if selected else tree.focus()
        if not item:
            return None
        follower_id = self.followers_row_map.get(item)
        if follower_id:
            return follower_id
        tags = tree.item(item).get('tags') or ()
        if tags:
            try:
                return int(tags[0])
            except Exception:
                return tags[0]
        return None

    def on_character_follower_selected(self, event=None):
        if getattr(self, 'followers_loading_form', False):
            return
        follower_id = self.get_selected_character_follower_id()
        if not follower_id:
            return
        if getattr(self, 'followers_dirty', False):
            if not self.save_current_follower(show_message=False, reload_after=False):
                return
            self.load_followers_for_pg(self.followers_pg_id, select_follower_id=follower_id)
            return
        self.load_follower_detail(follower_id, self.followers_pg_id)

    def load_follower_detail(self, follower_id, pg_id):
        if not self.verify_character_sheet_pg_access(pg_id):
            messagebox.showerror("Errore", "Personaggio non autorizzato.")
            return
        cursor = self.db.cursor()
        try:
            cursor.execute("SELECT * FROM followers WHERE id = %s AND pg_id = %s", (follower_id, pg_id))
            follower = cursor.fetchone()
        finally:
            cursor.close()
        if not follower:
            messagebox.showerror("Errore", "Seguace non trovato.")
            return
        self.populate_follower_form(follower)
        self.current_follower_id = follower_id
        self.followers_mode = "edit"
        self.followers_dirty = False
        self.set_follower_detail_tabs_enabled(True)

    def default_follower_values(self):
        data = {field: '' for field in self.follower_widgets}
        for field in self.follower_int_fields():
            data[field] = 0
        for field in self.follower_decimal_fields():
            data[field] = '0'
        data.update({
            'level': 1,
            'forza': 10,
            'intelligenza': 10,
            'saggezza': 10,
            'destrezza': 10,
            'costituzione': 10,
            'carisma': 10,
            'classe_armatura': 10,
            'thac0': 20,
            'status': 'ATTIVO',
        })
        return data

    def populate_follower_form(self, data):
        self.followers_loading_form = True
        try:
            for field, widget in self.follower_widgets.items():
                value = data.get(field, '')
                previous_state = None
                try:
                    previous_state = widget.cget('state')
                    if previous_state in ('readonly', 'disabled'):
                        widget.configure(state='normal')
                except Exception:
                    previous_state = None
                if field == 'race' and not value:
                    value = data.get('description', '')
                if field == 'bank_destination_cost':
                    label = "Nessuna banca"
                    for bank_label, bank_id in self.follower_bank_map.items():
                        if bank_id == value:
                            label = bank_label
                            break
                    widget.set(label)
                elif field in self.follower_text_fields():
                    widget.delete('1.0', 'end')
                    widget.insert('1.0', value or '')
                else:
                    widget.delete(0, 'end')
                    widget.insert(0, '' if value is None else str(value))
                if previous_state:
                    try:
                        widget.configure(state=previous_state)
                    except Exception:
                        pass
        finally:
            self.followers_loading_form = False

    def clear_follower_form(self):
        self.populate_follower_form(self.default_follower_values())
        self.current_follower_id = None
        self.followers_mode = "view"
        self.followers_dirty = False
        self.set_follower_detail_tabs_enabled(False)

    def new_character_follower(self):
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Errore", "Solo il DM puo' creare nuovi seguaci.")
            return
        if getattr(self, 'followers_dirty', False):
            if not self.save_current_follower(show_message=False):
                return
        tree = getattr(self, 'character_followers_tree', None)
        if tree:
            tree.selection_remove(tree.selection())
        self.clear_follower_form()
        self.followers_mode = "new"
        self.set_follower_detail_tabs_enabled(True)

    def mark_followers_dirty(self, event=None):
        if getattr(self, 'followers_loading_form', False):
            return
        if not self.current_follower_id and getattr(self, 'followers_mode', 'view') != "new":
            return
        self.followers_dirty = True
        self.has_unsaved_changes = True

    def calculate_classic_modifier(self, score):
        score = int(score)
        if score <= 3:
            return -3
        if score <= 5:
            return -2
        if score <= 8:
            return -1
        if score <= 12:
            return 0
        if score <= 15:
            return 1
        if score <= 17:
            return 2
        return 3

    def calculate_follower_modifiers(self):
        pairs = [
            ('forza', 'forza_mod'), ('intelligenza', 'intelligenza_mod'),
            ('saggezza', 'saggezza_mod'), ('destrezza', 'destrezza_mod'),
            ('costituzione', 'costituzione_mod'), ('carisma', 'carisma_mod')
        ]
        try:
            for score_field, mod_field in pairs:
                score = int(self.follower_widgets[score_field].get() or 10)
                mod = self.calculate_classic_modifier(score)
                widget = self.follower_widgets[mod_field]
                widget.delete(0, 'end')
                widget.insert(0, str(mod))
            self.mark_followers_dirty()
        except ValueError:
            messagebox.showerror("Errore", "Le caratteristiche devono essere numeri interi.")

    def collect_follower_form_data(self):
        data = {'pg_id': self.followers_pg_id}
        for field, widget in self.follower_widgets.items():
            if field == 'bank_destination_cost':
                data[field] = self.follower_bank_map.get(widget.get(), None)
            elif field in self.follower_text_fields():
                data[field] = widget.get('1.0', 'end-1c').strip()
            else:
                data[field] = widget.get().strip()

        if not data.get('name'):
            raise ValueError("Nome obbligatorio.")
        if not data.get('class'):
            raise ValueError("Classe obbligatoria.")

        for field in self.follower_int_fields():
            value = data.get(field, '')
            data[field] = int(value) if str(value).strip() else 0
        for field in self.follower_decimal_fields():
            value = data.get(field, '')
            data[field] = Decimal(str(value).replace(',', '.')) if str(value).strip() else Decimal('0')

        data['description'] = data.get('description') or data.get('race') or ''
        return data

    def save_current_follower(self, show_message=True, reload_after=True):
        if not hasattr(self, 'follower_widgets') or not self.follower_widgets:
            return True
        if not self.verify_character_sheet_pg_access(self.followers_pg_id):
            messagebox.showerror("Errore", "Personaggio non autorizzato.")
            return False
        try:
            data = self.collect_follower_form_data()
        except (ValueError, ArithmeticError) as e:
            messagebox.showerror("Errore", f"Dati seguace non validi: {e}")
            return False

        if not self.current_follower_id and (
            not self.current_user or self.current_user.get('role') != 'DM'
        ):
            messagebox.showwarning("Avviso", "Seleziona un seguace da modificare.")
            return False

        fields = [
            'name', 'race', 'class', 'level', 'alignment', 'role_task', 'description',
            'forza', 'forza_mod', 'intelligenza', 'intelligenza_mod', 'saggezza',
            'saggezza_mod', 'destrezza', 'destrezza_mod', 'costituzione',
            'costituzione_mod', 'carisma', 'carisma_mod', 'pf_attuali', 'pf_massimi',
            'classe_armatura', 'thac0', 'movimento', 'ts_morte_veleno',
            'ts_bacchette', 'ts_paralisi_pietrificazione', 'ts_soffi',
            'ts_incantesimi', 'px', 'px_next_level', 'annual_cost',
            'salary_agreement', 'morale', 'bank_destination_cost', 'weapons_damage',
            'equipment', 'magic_items_permanent', 'magic_items_temporary',
            'money_mp', 'money_mo', 'money_me', 'money_ma', 'money_mr',
            'gems_treasures', 'class_abilities', 'spells',
            'general_skills', 'known_languages', 'physical_appearance', 'age',
            'gender', 'height', 'weight', 'personality', 'background', 'notes',
            'status', 'loyalty', 'hire_date', 'current_location', 'pay_frequency',
            'treasure_share', 'equipment_supplied_by_pg', 'last_payment_date',
            'next_payment_date', 'dm_private_notes'
        ]
        fields = [field for field in fields if field in data]
        cursor = self.db.cursor()
        try:
            if self.current_follower_id:
                data['id'] = self.current_follower_id
                set_clause = ", ".join([f"`{field}` = %({field})s" if field == 'class' else f"{field} = %({field})s" for field in fields])
                cursor.execute(f"""
                    UPDATE followers
                    SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %(id)s AND pg_id = %(pg_id)s
                """, data)
                saved_id = self.current_follower_id
            else:
                insert_fields = ['pg_id'] + fields
                column_clause = ", ".join([f"`{field}`" if field == 'class' else field for field in insert_fields])
                value_clause = ", ".join([f"%({field})s" for field in insert_fields])
                cursor.execute(f"INSERT INTO followers ({column_clause}) VALUES ({value_clause})", data)
                saved_id = cursor.lastrowid
                self.current_follower_id = saved_id
            self.db.commit()
            self.followers_mode = "edit"
            self.followers_dirty = False
            if reload_after:
                self.load_followers_for_pg(self.followers_pg_id, select_follower_id=saved_id)
            if show_message:
                messagebox.showinfo("Successo", "Seguace salvato correttamente.")
            return True
        except Exception as e:
            self.db.rollback()
            messagebox.showerror("Errore", f"Errore durante il salvataggio del seguace: {e}")
            return False
        finally:
            cursor.close()

    def cancel_follower_changes(self):
        if self.current_follower_id:
            self.load_follower_detail(self.current_follower_id, self.followers_pg_id)
        else:
            self.clear_follower_form()

    def delete_current_follower(self):
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Errore", "Solo il DM puo' eliminare seguaci.")
            return
        follower_id = self.current_follower_id
        if not follower_id:
            messagebox.showwarning("Avviso", "Seleziona un seguace da eliminare.")
            return
        if not messagebox.askyesno("Conferma", "Eliminare il seguace selezionato?"):
            return
        cursor = self.db.cursor()
        try:
            cursor.execute("SELECT COUNT(*) AS total FROM follower_objectives WHERE follower_id = %s", (follower_id,))
            linked = cursor.fetchone().get('total', 0)
            if linked:
                messagebox.showwarning(
                    "Eliminazione bloccata",
                    "Impossibile eliminare il seguace: sono presenti obiettivi collegati.\n\n"
                    "Elimina o riassegna prima gli obiettivi del seguace."
                )
                return
            cursor.execute("DELETE FROM followers WHERE id = %s AND pg_id = %s", (follower_id, self.followers_pg_id))
            self.db.commit()
            self.clear_follower_form()
            self.load_followers_for_pg(self.followers_pg_id)
            messagebox.showinfo("Successo", "Seguace eliminato con successo.")
        except Exception as e:
            self.db.rollback()
            messagebox.showerror("Errore", f"Errore durante l'eliminazione del seguace: {e}")
        finally:
            cursor.close()

    def create_character_languages_tab(self, notebook, pg_id, character):
        """Tab Linguaggi"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Linguaggi")
        
        # Frame principale
        main_frame = ttk.LabelFrame(tab, text="Linguaggi Conosciuti", padding=10)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        columns = ('lingua',)
        self.language_tree = ttk.Treeview(main_frame, columns=columns, show='headings')
        self.language_tree.heading('lingua', text='Lingua')
        self.language_tree.column('lingua', width=300)
        self.language_tree.pack(side='left', fill='both', expand=True)
        
        lang_scroll = ttk.Scrollbar(main_frame, orient='vertical', command=self.language_tree.yview)
        lang_scroll.pack(side='right', fill='y')
        self.language_tree.config(yscrollcommand=lang_scroll.set)
        
        self.refresh_language_list(pg_id)
        
        # Bottoni
        if not is_dm:
            return
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(btn_frame, text="➕ Aggiungi Linguaggio", 
                  command=lambda: self.add_language_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Elimina", 
                  command=lambda: self.delete_language(pg_id)).pack(side='left', padx=5)

    def create_character_mercenaries_tab(self, notebook, pg_id, character):
        """Tab Mercenari"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Mercenari")
        
        main_frame = ttk.LabelFrame(tab, text="Truppe Mercenarie", padding=10)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        columns = ('categoria', 'tipo_truppa', 'quantita')
        self.mercenary_tree = ttk.Treeview(main_frame, columns=columns, show='headings')
        
        self.mercenary_tree.heading('categoria', text='Categoria')
        self.mercenary_tree.heading('tipo_truppa', text='Tipo Truppa')
        self.mercenary_tree.heading('quantita', text='Quantità')
        
        self.mercenary_tree.column('categoria', width=200)
        self.mercenary_tree.column('tipo_truppa', width=250)
        self.mercenary_tree.column('quantita', width=100)
        
        self.mercenary_tree.pack(side='left', fill='both', expand=True)
        
        merc_scroll = ttk.Scrollbar(main_frame, orient='vertical', command=self.mercenary_tree.yview)
        merc_scroll.pack(side='right', fill='y')
        self.mercenary_tree.config(yscrollcommand=merc_scroll.set)
        
        self.refresh_mercenary_list(pg_id)
        
        # Bottoni
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(btn_frame, text="➕ Aggiungi Mercenari", 
                  command=lambda: self.add_mercenary_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Modifica", 
                  command=lambda: self.edit_mercenary_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Elimina", 
                  command=lambda: self.delete_mercenary(pg_id)).pack(side='left', padx=5)

    def create_character_advisors_tab(self, notebook, pg_id, character):
        """Tab Consiglieri e Ufficiali"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Consiglieri")
        
        main_frame = ttk.LabelFrame(tab, text="Consiglieri e Ufficiali", padding=10)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        columns = ('mansione', 'nome', 'classe', 'livello', 'fe', 'in_', 'sa', 'de', 'co', 'ca')
        self.advisor_tree = ttk.Treeview(main_frame, columns=columns, show='headings')
        
        self.advisor_tree.heading('mansione', text='Mansione')
        self.advisor_tree.heading('nome', text='Nome')
        self.advisor_tree.heading('classe', text='Classe')
        self.advisor_tree.heading('livello', text='Liv')
        self.advisor_tree.heading('fe', text='FE')
        self.advisor_tree.heading('in_', text='IN')
        self.advisor_tree.heading('sa', text='SA')
        self.advisor_tree.heading('de', text='DE')
        self.advisor_tree.heading('co', text='CO')
        self.advisor_tree.heading('ca', text='CA')
        
        for col in columns:
            self.advisor_tree.column(col, width=80)
        self.advisor_tree.column('mansione', width=120)
        self.advisor_tree.column('nome', width=120)
        
        self.advisor_tree.pack(side='left', fill='both', expand=True)
        
        adv_scroll = ttk.Scrollbar(main_frame, orient='vertical', command=self.advisor_tree.yview)
        adv_scroll.pack(side='right', fill='y')
        self.advisor_tree.config(yscrollcommand=adv_scroll.set)
        
        self.refresh_advisor_list(pg_id)
        
        # Bottoni
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(btn_frame, text="➕ Aggiungi Consigliere", 
                  command=lambda: self.add_advisor_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Modifica", 
                  command=lambda: self.edit_advisor_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Elimina", 
                  command=lambda: self.delete_advisor(pg_id)).pack(side='left', padx=5)

    def create_character_specialists_tab(self, notebook, pg_id, character):
        """Tab Specialisti"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Specialisti")
        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        
        main_frame = ttk.LabelFrame(tab, text="Specialisti Assunti", padding=10)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        columns = ('tipo', 'nome', 'localita', 'costo', 'frequenza', 'servizio')
        self.specialist_tree = ttk.Treeview(main_frame, columns=columns, show='headings')
        
        self.specialist_tree.heading('tipo', text='Tipo')
        self.specialist_tree.heading('nome', text='Nome')
        self.specialist_tree.heading('localita', text='Località')
        self.specialist_tree.heading('costo', text='Costo (MO)')
        self.specialist_tree.heading('frequenza', text='Frequenza')
        self.specialist_tree.heading('servizio', text='In servizio')
        
        self.specialist_tree.column('tipo', width=120)
        self.specialist_tree.column('nome', width=150)
        self.specialist_tree.column('localita', width=150)
        self.specialist_tree.column('costo', width=100)
        self.specialist_tree.column('frequenza', width=110)
        self.specialist_tree.column('servizio', width=90)
        
        self.specialist_tree.pack(side='left', fill='both', expand=True)
        self.specialist_tree.bind("<Double-1>", lambda e: self.show_specialist_details_dialog(pg_id))
        
        spec_scroll = ttk.Scrollbar(main_frame, orient='vertical', command=self.specialist_tree.yview)
        spec_scroll.pack(side='right', fill='y')
        self.specialist_tree.config(yscrollcommand=spec_scroll.set)
        
        self.refresh_specialist_list(pg_id)
        
        # Bottoni
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(btn_frame, text="➕ Aggiungi Specialista", 
                  command=lambda: self.add_specialist_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Modifica", 
                  command=lambda: self.edit_specialist_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Elimina", 
                  command=lambda: self.delete_specialist(pg_id)).pack(side='left', padx=5)

    def create_character_scrolls_tab(self, notebook, pg_id, character):
        """Tab Pergamene"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Pergamene")
        
        main_frame = ttk.LabelFrame(tab, text="Pergamene e Documenti", padding=10)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.scroll_sort_column = getattr(self, 'scroll_sort_column', 'nome')
        self.scroll_sort_reverse = getattr(self, 'scroll_sort_reverse', False)
        columns = (
            'nome', 'tipo', 'livello', 'lista_magica', 'identificata',
            'consumata', 'trasportata', 'collocazione', 'quantita', 'valore_mo'
        )
        headings = {
            'nome': ('Nome', 180),
            'tipo': ('Tipo', 110),
            'livello': ('Livello', 70),
            'lista_magica': ('Lista', 90),
            'identificata': ('Identificata', 90),
            'consumata': ('Consumata', 85),
            'trasportata': ('Trasportata', 90),
            'collocazione': ('Collocazione', 150),
            'quantita': ('Quantita', 75),
            'valore_mo': ('Valore MO', 90),
        }
        self.scroll_tree = ttk.Treeview(main_frame, columns=columns, show='headings', height=12)
        for col in columns:
            text, width = headings[col]
            if col in ('nome', 'tipo', 'trasportata'):
                self.scroll_tree.heading(col, text=text, command=lambda c=col: self.sort_scrolls_by(pg_id, c))
            else:
                self.scroll_tree.heading(col, text=text)
            self.scroll_tree.column(col, width=width, minwidth=50, stretch=False)
        
        self.scroll_tree.grid(row=0, column=0, sticky='nsew')
        
        scroll_v = ttk.Scrollbar(main_frame, orient='vertical', command=self.scroll_tree.yview)
        scroll_v.grid(row=0, column=1, sticky='ns')
        scroll_h = ttk.Scrollbar(main_frame, orient='horizontal', command=self.scroll_tree.xview)
        scroll_h.grid(row=1, column=0, sticky='ew')
        self.scroll_tree.config(yscrollcommand=scroll_v.set, xscrollcommand=scroll_h.set)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)
        self.scroll_tree.bind('<Double-Button-1>', lambda e: self.show_scroll_details_dialog(pg_id))

        def scroll_table(event):
            delta = -1 if getattr(event, 'delta', 0) > 0 else 1
            if getattr(event, 'num', None) == 4:
                delta = -1
            elif getattr(event, 'num', None) == 5:
                delta = 1
            self.scroll_tree.yview_scroll(delta, "units")
            return "break"

        self.scroll_tree.bind("<MouseWheel>", scroll_table, add="+")
        self.scroll_tree.bind("<Button-4>", scroll_table, add="+")
        self.scroll_tree.bind("<Button-5>", scroll_table, add="+")
        
        self.refresh_scroll_list(pg_id)
        
        # Bottoni
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(btn_frame, text="➕ Aggiungi Pergamena", 
                  command=lambda: self.add_scroll_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Modifica", 
                  command=lambda: self.edit_scroll_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Elimina", 
                  command=lambda: self.delete_scroll(pg_id)).pack(side='left', padx=5)

    def delete_mount(self, pg_id, tree=None):
        """Elimina cavalcatura"""
        tree = tree or self.mount_tree
        selection = tree.selection()
        if not selection:
            return
        item = tree.item(selection[0])
        mount_id = item['tags'][0]
        if not messagebox.askyesno("Conferma", "Eliminare la cavalcatura selezionata?"):
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_cavalcature WHERE id = %s AND pg_id = %s", (mount_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_mount_list(pg_id, tree)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")

    def refresh_familiar_list(self, pg_id, tree=None):
        """Ricarica creature familiari - Con righe alternate"""
        try:
            tree = tree or self.familiar_tree
            tree.delete(*tree.get_children())
            tree.tag_configure('oddrow', background='white')
            tree.tag_configure('evenrow', background='#f0f0f0')
            
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_creature_familiari WHERE pg_id = %s", (pg_id,))
            familiars = cursor.fetchall()
            cursor.close()
            
            for i, fam in enumerate(familiars):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                tree.insert('', 'end', values=(
                    fam['nome'], fam['classe_armatura'], fam['dadi_vita'],
                    fam['movimento'], fam['attacchi'], fam['pf'], fam['ts']
                ), tags=(fam['id'], tag))
            tree.update_idletasks()
        except Exception as e:
            print(f"Errore refresh creature: {e}")
    
    def add_familiar_dialog(self, pg_id, tree=None):
        """Dialog aggiungi creatura familiare"""
        try:
            tree = tree or self.familiar_tree
            pg_id = int(pg_id)
            dialog = tk.Toplevel(self.root)
            dialog.title("Aggiungi Creatura Familiare")
            dialog.geometry("400x350")
            dialog.transient(self.root)
            dialog.grab_set()
            
            fields = {}
            row = 0
            
            for field, label in [('nome', 'Nome'), ('classe_armatura', 'CA'), ('dadi_vita', 'Dadi Vita'),
                                ('movimento', 'Movimento'), ('attacchi', 'Attacchi'), ('pf', 'PF'), ('ts', 'TS')]:
                ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
                if field in ['classe_armatura', 'movimento', 'attacchi', 'pf']:
                    fields[field] = ttk.Spinbox(dialog, from_=0, to=999, width=27)
                    fields[field].set(0)
                else:
                    fields[field] = ttk.Entry(dialog, width=30)
                fields[field].grid(row=row, column=1, padx=10, pady=5)
                row += 1
            
            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        INSERT INTO pc_creature_familiari 
                        (pg_id, nome, classe_armatura, dadi_vita, movimento, attacchi, pf, ts)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (pg_id, fields['nome'].get(), int(fields['classe_armatura'].get()),
                          fields['dadi_vita'].get(), int(fields['movimento'].get()),
                          int(fields['attacchi'].get()), int(fields['pf'].get()), fields['ts'].get()))
                    self.db.commit()
                    cursor.close()
                    self.refresh_familiar_list(pg_id, tree)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Creatura aggiunta!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")
            
            ttk.Button(dialog, text="Salva", command=save).grid(row=row, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=row, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def edit_familiar_dialog(self, pg_id, tree=None):
        """Dialog modifica creatura familiare"""
        tree = tree or self.familiar_tree
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona una creatura da modificare!")
            return
        item = tree.item(selection[0])
        fam_id = item['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_creature_familiari WHERE id = %s AND pg_id = %s", (fam_id, pg_id))
            fam = cursor.fetchone()
            cursor.close()
            if not fam:
                messagebox.showerror("Errore", "Creatura familiare non trovata.")
                return

            dialog = tk.Toplevel(self.root)
            dialog.title("Modifica Creatura Familiare")
            dialog.geometry("400x350")
            dialog.transient(self.root)
            dialog.grab_set()

            fields = {}
            row = 0
            for field, label in [('nome', 'Nome'), ('classe_armatura', 'CA'), ('dadi_vita', 'Dadi Vita'),
                                ('movimento', 'Movimento'), ('attacchi', 'Attacchi'), ('pf', 'PF'), ('ts', 'TS')] :
                ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
                if field in ['classe_armatura', 'movimento', 'attacchi', 'pf']:
                    fields[field] = ttk.Spinbox(dialog, from_=0, to=999, width=27)
                    fields[field].set(fam.get(field, 0) or 0)
                else:
                    fields[field] = ttk.Entry(dialog, width=30)
                    fields[field].insert(0, fam.get(field, '') or '')
                fields[field].grid(row=row, column=1, padx=10, pady=5)
                row += 1

            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        UPDATE pc_creature_familiari SET nome = %s, classe_armatura = %s, dadi_vita = %s,
                            movimento = %s, attacchi = %s, pf = %s, ts = %s
                        WHERE id = %s AND pg_id = %s
                    """, (
                        fields['nome'].get(), int(fields['classe_armatura'].get()), fields['dadi_vita'].get(),
                        int(fields['movimento'].get()), int(fields['attacchi'].get()), int(fields['pf'].get()),
                        fields['ts'].get(), fam_id, pg_id
                    ))
                    self.db.commit()
                    cursor.close()
                    self.refresh_familiar_list(pg_id, tree)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Creatura familiare aggiornata!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")

            ttk.Button(dialog, text="Salva", command=save).grid(row=row, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=row, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def delete_familiar(self, pg_id, tree=None):
        """Elimina creatura familiare"""
        tree = tree or self.familiar_tree
        selection = tree.selection()
        if not selection:
            return
        item = tree.item(selection[0])
        fam_id = item['tags'][0]
        if not messagebox.askyesno("Conferma", "Eliminare la creatura selezionata?"):
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_creature_familiari WHERE id = %s AND pg_id = %s", (fam_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_familiar_list(pg_id, tree)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")

    def refresh_language_list(self, pg_id):
        """Ricarica lista linguaggi"""
        try:
            self.language_tree.delete(*self.language_tree.get_children())
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_linguaggi WHERE pg_id = %s", (pg_id,))
            languages = cursor.fetchall()
            cursor.close()
            
            for lang in languages:
                self.language_tree.insert('', 'end', values=(lang['lingua'],), tags=(lang['id'],))
        except Exception as e:
            print(f"Errore refresh linguaggi: {e}")
    
    def add_language_dialog(self, pg_id):
        """Dialog aggiungi linguaggio"""
        try:
            pg_id = int(pg_id)
            dialog = tk.Toplevel(self.root)
            dialog.title("Aggiungi Linguaggio")
            dialog.geometry("350x120")
            dialog.transient(self.root)
            dialog.grab_set()
            
            ttk.Label(dialog, text="Lingua:").grid(row=0, column=0, sticky='w', padx=10, pady=10)
            lingua_var = ttk.Entry(dialog, width=30)
            lingua_var.grid(row=0, column=1, padx=10, pady=10)
            
            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("INSERT INTO pc_linguaggi (pg_id, lingua) VALUES (%s, %s)",
                                 (pg_id, lingua_var.get()))
                    self.db.commit()
                    cursor.close()
                    self.refresh_language_list(pg_id)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Linguaggio aggiunto!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")
            
            ttk.Button(dialog, text="Salva", command=save).grid(row=1, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=1, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def delete_language(self, pg_id):
        """Elimina linguaggio"""
        selection = self.language_tree.selection()
        if not selection:
            return
        item = self.language_tree.item(selection[0])
        lang_id = item['tags'][0]
        if not messagebox.askyesno("Conferma", "Eliminare il linguaggio selezionato?"):
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_linguaggi WHERE id = %s AND pg_id = %s", (lang_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_language_list(pg_id)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")

    def create_character_spells_tab(self, notebook, pg_id, character):
        """Tab Incantesimi basato su libro e preparazione strutturata."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Incantesimi")

        canvas = tk.Canvas(tab, highlightthickness=0)
        v_scroll = ttk.Scrollbar(tab, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        scrollable = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=scrollable, anchor='nw')
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(canvas_window, width=e.width))

        def scroll_spells_page(event):
            delta = -1 * int(event.delta / 120) if event.delta else 0
            canvas.yview_scroll(delta, "units")

        for widget in (tab, canvas, scrollable):
            widget.bind("<MouseWheel>", scroll_spells_page, add="+")

        self.create_magic_rules_frame(scrollable, pg_id, character)

        self.spell_limits_frame = ttk.LabelFrame(scrollable, text="Slot e preparazione", padding=8)
        self.spell_limits_frame.pack(fill='x', padx=10, pady=(0, 10))
        self.refresh_spell_limits_frame(pg_id)

        spellbook_frame = ttk.LabelFrame(scrollable, text="Libro Incantesimi/Preparazione", padding=10)
        spellbook_frame.pack(fill='both', expand=True, padx=10, pady=10)
        search_frame = ttk.Frame(spellbook_frame)
        search_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        ttk.Label(search_frame, text="Ricerca Nome:").pack(side='left', padx=(0, 6))
        self.spellbook_search_var = tk.StringVar(value=getattr(self, 'spellbook_search_text', ''))
        search_entry = ttk.Entry(search_frame, textvariable=self.spellbook_search_var, width=38)
        search_entry.pack(side='left', fill='x', expand=True)

        def on_spell_search(*_):
            self.spellbook_search_text = self.spellbook_search_var.get()
            self.refresh_spellbook_list(pg_id)

        self.spellbook_search_var.trace_add('write', on_spell_search)
        self.spellbook_sort_column = getattr(self, 'spellbook_sort_column', 'livello')
        self.spellbook_sort_reverse = getattr(self, 'spellbook_sort_reverse', False)
        columns_book = (
            'nome', 'livello', 'reversibile', 'raggio', 'durata',
            'effetto', 'preparati', 'lanciati', 'conosciuto', 'nel_libro'
        )
        self.spellbook_tree = ttk.Treeview(spellbook_frame, columns=columns_book, show='headings', height=8)
        for col, text, width in [
            ('nome', 'Nome', 170),
            ('livello', 'Livello', 60),
            ('reversibile', 'Reversibile', 80),
            ('raggio', 'Raggio', 130),
            ('durata', 'Durata', 130),
            ('effetto', 'Effetto', 180),
            ('preparati', 'Preparati', 80),
            ('lanciati', 'Lanciati', 70),
            ('conosciuto', 'Conosciuto', 80),
            ('nel_libro', 'Nel Libro', 80),
        ]:
            if col in ('nome', 'livello', 'preparati'):
                self.spellbook_tree.heading(col, text=text, command=lambda c=col: self.sort_spellbook_by(pg_id, c))
            else:
                self.spellbook_tree.heading(col, text=text)
            self.spellbook_tree.column(col, width=width, minwidth=50, stretch=False)
        self.spellbook_tree.grid(row=1, column=0, sticky='nsew')
        book_v_scroll = ttk.Scrollbar(spellbook_frame, orient='vertical', command=self.spellbook_tree.yview)
        book_v_scroll.grid(row=1, column=1, sticky='ns')
        book_h_scroll = ttk.Scrollbar(spellbook_frame, orient='horizontal', command=self.spellbook_tree.xview)
        book_h_scroll.grid(row=2, column=0, sticky='ew')
        self.spellbook_tree.config(yscrollcommand=book_v_scroll.set, xscrollcommand=book_h_scroll.set)
        spellbook_frame.columnconfigure(0, weight=1)
        spellbook_frame.rowconfigure(1, weight=1)
        self.spellbook_tree.bind('<Double-Button-1>', lambda e: self.show_spell_details_dialog(pg_id))

        book_btn_frame = ttk.Frame(scrollable)
        book_btn_frame.pack(fill='x', padx=10, pady=5)
        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        ttk.Button(book_btn_frame, text="Aggiungi da Catalogo", command=lambda: self.add_spell_from_catalog_dialog(pg_id)).pack(side='left', padx=5)
        if is_dm:
            ttk.Button(book_btn_frame, text="Aggiungi Incantesimo", command=lambda: self.add_spell_dialog(pg_id)).pack(side='left', padx=5)
            ttk.Button(book_btn_frame, text="Modifica Incantesimo", command=lambda: self.edit_spell_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(book_btn_frame, text="Modifica Note Libro", command=lambda: self.edit_spellbook_notes_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(book_btn_frame, text="Elimina Incantesimo", command=lambda: self.delete_spell(pg_id)).pack(side='left', padx=5)
        ttk.Button(book_btn_frame, text="Prepara +1", command=lambda: self.prepare_spell_from_book(pg_id)).pack(side='left', padx=5)
        ttk.Button(book_btn_frame, text="Segna lanciato +1", command=lambda: self.mark_prepared_spell_cast(pg_id)).pack(side='left', padx=5)
        ttk.Button(book_btn_frame, text="Azzera preparazione", command=lambda: self.reset_spell_preparation(pg_id)).pack(side='left', padx=5)

        self.refresh_spellbook_list(pg_id)
        self.bind_spell_page_mousewheel(scrollable, scroll_spells_page)

    def bind_spell_page_mousewheel(self, widget, callback):
        if not isinstance(widget, (ttk.Treeview, tk.Text, tk.Listbox)):
            widget.bind("<MouseWheel>", callback, add="+")
        for child in widget.winfo_children():
            self.bind_spell_page_mousewheel(child, callback)

    def blink_spell_limit_warnings(self):
        labels = [label for label in getattr(self, 'spell_limit_warning_labels', []) if label.winfo_exists()]
        if not labels:
            self.spell_limit_warning_blinking = False
            return
        self.spell_limit_warning_blinking = True
        next_yellow = not getattr(self, 'spell_limit_warning_yellow', True)
        self.spell_limit_warning_yellow = next_yellow
        for label in labels:
            label.configure(fg='red', bg='yellow' if next_yellow else 'SystemButtonFace')
        self.root.after(600, self.blink_spell_limit_warnings)

    def refresh_spell_limits_frame(self, pg_id):
        """Aggiorna localmente il riepilogo Slot e preparazione del TAB Incantesimi."""
        limits_frame = getattr(self, 'spell_limits_frame', None)
        if not limits_frame or not limits_frame.winfo_exists():
            return
        for child in limits_frame.winfo_children():
            child.destroy()
        limits = self.refresh_spell_preparation_limits(pg_id)
        self.spell_limit_warning_labels = []
        if limits:
            per_row = max(1, (len(limits) + 1) // 2)
            for idx, spell_level in enumerate(sorted(limits)):
                data = limits[spell_level]
                status = "oltre limite" if data.get('over_limit') else "ok"
                label_cls = tk.Label if data.get('over_limit') else ttk.Label
                label = label_cls(
                    limits_frame,
                    text=f"L{spell_level}: slot {data['slots']} | preparati {data['prepared']} | lanciati {data['casted']} | disponibili {data['available']} ({status})"
                )
                if data.get('over_limit'):
                    label.configure(fg='red', bg='yellow')
                    self.spell_limit_warning_labels.append(label)
                label.grid(row=idx // per_row, column=idx % per_row, sticky='w', padx=8, pady=3)
            if self.spell_limit_warning_labels and not getattr(self, 'spell_limit_warning_blinking', False):
                self.blink_spell_limit_warnings()
        else:
            ttk.Label(
                limits_frame,
                text="Nessuno slot o incantesimo preparato rilevato per classe/livello corrente."
            ).pack(anchor='w')

    def refresh_character_spells_tab_local(self, pg_id, selected_spell_id=None):
        """Aggiorna solo il TAB Incantesimi senza ricostruire la Scheda Personaggio."""
        tree = getattr(self, 'spellbook_tree', None)
        if selected_spell_id is None:
            selected_spell_id = self.get_selected_spellbook_spell_id()
        yview = tree.yview()[0] if tree else 0
        self.refresh_spellbook_list(pg_id)
        tree = getattr(self, 'spellbook_tree', None)
        if tree and selected_spell_id is not None:
            selected_key = str(selected_spell_id)
            for item_id in tree.get_children():
                tags = [str(tag) for tag in tree.item(item_id).get('tags', ())]
                if selected_key in tags:
                    tree.selection_set(item_id)
                    tree.focus(item_id)
                    break
            try:
                tree.yview_moveto(yview)
            except Exception:
                pass
        self.refresh_spell_limits_frame(pg_id)

    def sort_spellbook_by(self, pg_id, column):
        if getattr(self, 'spellbook_sort_column', None) == column:
            self.spellbook_sort_reverse = not getattr(self, 'spellbook_sort_reverse', False)
        else:
            self.spellbook_sort_column = column
            self.spellbook_sort_reverse = False
        self.refresh_spellbook_list(pg_id)

    def refresh_spell_preparation_limits(self, pg_id):
        """Riepiloga gli slot usando solo il libro/preparazione strutturati."""
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM player_characters WHERE id = %s", (pg_id,))
            character = cursor.fetchone()
            cursor.close()
            if not character:
                return {}
            class_code = self.get_character_class_code(character)
            level = int(character.get('livello') or 1)
            slots = self.get_effective_spell_slots(pg_id, class_code, level)
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT spell_level, COALESCE(SUM(prepared_count), 0) AS prepared,
                       COALESCE(SUM(cast_count), 0) AS casted
                FROM pc_spell_prepared
                WHERE pg_id = %s
                GROUP BY spell_level
            """, (pg_id,))
            structured = {int(r['spell_level']): r for r in cursor.fetchall()}
            cursor.close()
            result = {}
            for spell_level in sorted(set(slots) | set(structured)):
                prepared = int(structured.get(spell_level, {}).get('prepared') or 0)
                casted = int(structured.get(spell_level, {}).get('casted') or 0)
                available = max(0, int(slots.get(spell_level, 0)) - casted)
                result[spell_level] = {
                    'slots': int(slots.get(spell_level, 0)),
                    'prepared': prepared,
                    'casted': casted,
                    'available': available,
                    'over_limit': prepared > int(slots.get(spell_level, 0)),
                }
            return result
        except Exception:
            return {}

    def refresh_spellbook_list(self, pg_id):
        tree = getattr(self, 'spellbook_tree', None)
        if not tree:
            return
        try:
            tree.delete(*tree.get_children())
            cursor = self.db.cursor()
            search_text = (getattr(self, 'spellbook_search_text', '') or '').strip()
            direction = 'DESC' if getattr(self, 'spellbook_sort_reverse', False) else 'ASC'
            sort_column = getattr(self, 'spellbook_sort_column', 'livello')
            if sort_column == 'nome':
                order_sql = f"rs.spell_name {direction}, rs.spell_level ASC"
            elif sort_column == 'preparati':
                order_sql = f"prepared_count {direction}, rs.spell_level ASC, rs.spell_name ASC"
            else:
                order_sql = f"rs.spell_level {direction}, rs.spell_name ASC"
            query = f"""
                SELECT ps.id AS spellbook_id, ps.notes AS book_notes, rs.id AS spell_id,
                       rs.spell_name, rs.spell_level, rs.spell_list_type, rs.reversible,
                       rs.range_text, rs.duration_text, rs.effect_text, rs.description,
                       COALESCE(pp.prepared_count, 0) AS prepared_count,
                       COALESCE(pp.cast_count, 0) AS cast_count,
                       ps.known, ps.in_spellbook
                FROM pc_spellbook ps
                JOIN rule_spells rs ON ps.spell_id = rs.id
                LEFT JOIN pc_spell_prepared pp ON pp.pg_id = ps.pg_id AND pp.spell_id = rs.id
                WHERE ps.pg_id = %s
            """
            params = [pg_id]
            if search_text:
                query += " AND rs.spell_name LIKE %s"
                params.append(f"%{search_text}%")
            query += f" ORDER BY {order_sql}"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            dynamic_height = max(5, min(len(rows) if rows else 5, 14))
            tree.configure(height=dynamic_height)
            for row in rows:
                effect = row.get('effect_text') or ''
                if len(effect) > 60:
                    effect = effect[:57] + "..."
                tree.insert('', 'end', values=(
                    row.get('spell_name') or '',
                    row.get('spell_level') or '',
                    "Si" if row.get('reversible') else "No",
                    row.get('range_text') or '',
                    row.get('duration_text') or '',
                    effect,
                    row.get('prepared_count', 0) or 0,
                    row.get('cast_count', 0) or 0,
                    "Si" if row.get('known') else "No",
                    "Si" if row.get('in_spellbook') else "No",
                ), tags=(row['spell_id'],))
            cursor.close()
        except Exception as e:
            print(f"Errore refresh spellbook: {e}")

    def get_selected_spellbook_spell_id(self):
        tree = getattr(self, 'spellbook_tree', None)
        selection = tree.selection() if tree else ()
        if not selection:
            return None
        return tree.item(selection[0])['tags'][0]

    def get_spellbook_spell_details(self, pg_id, spell_id):
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT ps.id AS spellbook_id, ps.known, ps.in_spellbook, ps.notes AS book_notes,
                   rs.id AS spell_id, rs.spell_name, rs.spell_level, rs.spell_list_type,
                   rs.reversible, rs.range_text, rs.duration_text, rs.effect_text, rs.description,
                   COALESCE(pp.prepared_count, 0) AS prepared_count,
                   COALESCE(pp.cast_count, 0) AS cast_count,
                   pp.preparation_date
            FROM pc_spellbook ps
            JOIN rule_spells rs ON ps.spell_id = rs.id
            LEFT JOIN pc_spell_prepared pp ON pp.pg_id = ps.pg_id AND pp.spell_id = rs.id
            WHERE ps.pg_id = %s AND rs.id = %s
            LIMIT 1
        """, (pg_id, spell_id))
        row = cursor.fetchone()
        cursor.close()
        return row

    def get_spell_preparation_status_for_level(self, pg_id, spell_level):
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM player_characters WHERE id = %s", (pg_id,))
        character = cursor.fetchone()
        if not character:
            cursor.close()
            return {'slots': 0, 'prepared': 0, 'available': 0}
        class_code = self.get_character_class_code(character)
        level = int(character.get('livello') or 1)
        slots = self.get_effective_spell_slots(pg_id, class_code, level)
        cursor.execute("""
            SELECT COALESCE(SUM(prepared_count), 0) AS prepared
            FROM pc_spell_prepared
            WHERE pg_id = %s AND spell_level = %s
        """, (pg_id, spell_level))
        row = cursor.fetchone() or {}
        cursor.close()
        slot_count = int(slots.get(int(spell_level), 0) or 0)
        prepared = int(row.get('prepared') or 0)
        return {
            'slots': slot_count,
            'prepared': prepared,
            'available': max(0, slot_count - prepared),
        }

    def add_spell_from_catalog_dialog(self, pg_id):
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM player_characters WHERE id = %s", (pg_id,))
            character = cursor.fetchone()
            class_code = self.get_character_class_code(character)
            list_type = self.get_character_spell_list_type(class_code)
            if list_type:
                cursor.execute("""
                    SELECT id, spell_name, spell_level, spell_list_type, reversible,
                           range_text, duration_text, effect_text, description
                    FROM rule_spells
                    WHERE spell_list_type = %s
                    ORDER BY spell_level, spell_name
                """, (list_type,))
            else:
                cursor.execute("""
                    SELECT id, spell_name, spell_level, spell_list_type, reversible,
                           range_text, duration_text, effect_text, description
                    FROM rule_spells
                    ORDER BY spell_list_type, spell_level, spell_name
                """)
            spells = cursor.fetchall()
            cursor.close()
            if not spells:
                messagebox.showinfo("Catalogo vuoto", "Nessun incantesimo nel catalogo regole.")
                return

            dialog = tk.Toplevel(self.root)
            dialog.title("Aggiungi incantesimo da catalogo")
            dialog.geometry("620x460")
            dialog.transient(self.root)
            dialog.grab_set()

            list_frame = ttk.Frame(dialog)
            list_frame.pack(fill='both', expand=True, padx=10, pady=10)
            listbox = tk.Listbox(list_frame, height=18, width=86)
            listbox.pack(side='left', fill='both', expand=True)
            list_scroll = ttk.Scrollbar(list_frame, orient='vertical', command=listbox.yview)
            list_scroll.pack(side='right', fill='y')
            listbox.config(yscrollcommand=list_scroll.set)
            for spell in spells:
                reversible = " reversibile" if spell.get('reversible') else ""
                listbox.insert('end', f"L{spell['spell_level']} - {spell['spell_name']} ({spell['spell_list_type']}){reversible}")

            def add_selected():
                selection = listbox.curselection()
                if not selection:
                    return
                spell = spells[selection[0]]
                cursor = self.db.cursor()
                cursor.execute("""
                    INSERT INTO pc_spellbook (pg_id, spell_id, known, in_spellbook)
                    VALUES (%s, %s, 1, 1)
                    ON DUPLICATE KEY UPDATE known = 1, in_spellbook = 1
                """, (pg_id, spell['id']))
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_character_spells_tab_local(pg_id, spell['id'])

            ttk.Button(dialog, text="Aggiungi al libro", command=add_selected).pack(side='left', padx=10, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).pack(side='left', padx=10, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore catalogo incantesimi: {e}")

    def _spell_editor_dialog(self, pg_id, spell=None):
        if not (self.current_user and self.current_user.get('role') == 'DM'):
            messagebox.showerror(
                "Permesso negato",
                "Solo il DM puo' aggiungere o modificare gli incantesimi del catalogo globale."
            )
            return
        is_edit = spell is not None
        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Incantesimo" if is_edit else "Aggiungi Incantesimo")
        dialog.geometry("760x680")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)

        ttk.Label(dialog, text="Nome:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        name_entry = ttk.Entry(dialog, width=70)
        name_entry.grid(row=0, column=1, sticky='ew', padx=10, pady=5)
        ttk.Label(dialog, text="Livello:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        level_spin = ttk.Spinbox(dialog, from_=0, to=9, width=12)
        level_spin.grid(row=1, column=1, sticky='w', padx=10, pady=5)
        ttk.Label(dialog, text="Lista:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        list_combo = ttk.Combobox(dialog, values=['ARCANA', 'DIVINA', 'DRUIDICA', 'ALTRO'], width=24)
        list_combo.grid(row=2, column=1, sticky='w', padx=10, pady=5)
        reversible_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="Reversibile", variable=reversible_var).grid(row=3, column=1, sticky='w', padx=10, pady=5)
        ttk.Label(dialog, text="Raggio:").grid(row=4, column=0, sticky='w', padx=10, pady=5)
        range_entry = ttk.Entry(dialog, width=70)
        range_entry.grid(row=4, column=1, sticky='ew', padx=10, pady=5)
        ttk.Label(dialog, text="Durata:").grid(row=5, column=0, sticky='w', padx=10, pady=5)
        duration_entry = ttk.Entry(dialog, width=70)
        duration_entry.grid(row=5, column=1, sticky='ew', padx=10, pady=5)
        ttk.Label(dialog, text="Effetto:").grid(row=6, column=0, sticky='nw', padx=10, pady=5)
        effect_text = tk.Text(dialog, width=70, height=5)
        effect_text.grid(row=6, column=1, sticky='nsew', padx=10, pady=5)
        ttk.Label(dialog, text="Descrizione:").grid(row=7, column=0, sticky='nw', padx=10, pady=5)
        desc_text = tk.Text(dialog, width=70, height=9)
        desc_text.grid(row=7, column=1, sticky='nsew', padx=10, pady=5)
        ttk.Label(dialog, text="Note libro PG:").grid(row=8, column=0, sticky='nw', padx=10, pady=5)
        notes_text = tk.Text(dialog, width=70, height=4)
        notes_text.grid(row=8, column=1, sticky='nsew', padx=10, pady=5)
        known_var = tk.BooleanVar(value=True)
        in_book_var = tk.BooleanVar(value=True)
        flags_frame = ttk.Frame(dialog)
        flags_frame.grid(row=9, column=1, sticky='w', padx=10, pady=5)
        ttk.Checkbutton(flags_frame, text="Conosciuto", variable=known_var).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(flags_frame, text="Nel libro", variable=in_book_var).pack(side='left')

        if spell:
            name_entry.insert(0, spell.get('spell_name') or '')
            level_spin.set(spell.get('spell_level') or 1)
            list_combo.set(spell.get('spell_list_type') or 'ARCANA')
            reversible_var.set(bool(spell.get('reversible')))
            range_entry.insert(0, spell.get('range_text') or '')
            duration_entry.insert(0, spell.get('duration_text') or '')
            effect_text.insert('1.0', spell.get('effect_text') or '')
            desc_text.insert('1.0', spell.get('description') or '')
            notes_text.insert('1.0', spell.get('book_notes') or '')
            known_var.set(bool(spell.get('known', 1)))
            in_book_var.set(bool(spell.get('in_spellbook', 1)))
        else:
            level_spin.set(1)
            try:
                cursor = self.db.cursor()
                cursor.execute("SELECT * FROM player_characters WHERE id = %s", (pg_id,))
                character = cursor.fetchone()
                cursor.close()
                list_combo.set(self.get_character_spell_list_type(self.get_character_class_code(character)) or 'ARCANA')
            except Exception:
                list_combo.set('ARCANA')

        def save():
            spell_name = name_entry.get().strip()
            spell_list_type = list_combo.get().strip().upper()
            try:
                spell_level = int(level_spin.get())
            except Exception:
                messagebox.showerror("Errore", "Livello incantesimo non valido.")
                return
            if not spell_name or not spell_list_type:
                messagebox.showerror("Errore", "Nome e Lista sono obbligatori.")
                return
            data = {
                'spell_name': spell_name,
                'spell_level': spell_level,
                'spell_list_type': spell_list_type,
                'reversible': int(reversible_var.get()),
                'range_text': range_entry.get().strip(),
                'duration_text': duration_entry.get().strip(),
                'effect_text': effect_text.get('1.0', 'end-1c').strip(),
                'description': desc_text.get('1.0', 'end-1c').strip(),
                'pg_id': pg_id,
                'known': int(known_var.get()),
                'in_spellbook': int(in_book_var.get()),
                'book_notes': notes_text.get('1.0', 'end-1c').strip(),
            }
            cursor = self.db.cursor()
            try:
                if is_edit:
                    data['spell_id'] = spell['spell_id']
                    cursor.execute("""
                        UPDATE rule_spells
                        SET spell_name=%(spell_name)s, spell_level=%(spell_level)s,
                            spell_list_type=%(spell_list_type)s, reversible=%(reversible)s,
                            range_text=%(range_text)s, duration_text=%(duration_text)s,
                            effect_text=%(effect_text)s, description=%(description)s
                        WHERE id=%(spell_id)s
                    """, data)
                    cursor.execute("""
                        UPDATE pc_spellbook
                        SET known=%(known)s, in_spellbook=%(in_spellbook)s, notes=%(book_notes)s
                        WHERE pg_id=%(pg_id)s AND spell_id=%(spell_id)s
                    """, data)
                    cursor.execute("""
                        UPDATE pc_spell_prepared
                        SET spell_level=%(spell_level)s
                        WHERE pg_id=%(pg_id)s AND spell_id=%(spell_id)s
                    """, data)
                else:
                    cursor.execute("""
                        INSERT INTO rule_spells
                            (spell_name, spell_level, spell_list_type, reversible,
                             range_text, duration_text, effect_text, description)
                        VALUES
                            (%(spell_name)s, %(spell_level)s, %(spell_list_type)s, %(reversible)s,
                             %(range_text)s, %(duration_text)s, %(effect_text)s, %(description)s)
                        ON DUPLICATE KEY UPDATE
                            id = LAST_INSERT_ID(id),
                            reversible = VALUES(reversible),
                            range_text = VALUES(range_text),
                            duration_text = VALUES(duration_text),
                            effect_text = VALUES(effect_text),
                            description = VALUES(description)
                    """, data)
                    data['spell_id'] = cursor.lastrowid
                    cursor.execute("""
                        INSERT INTO pc_spellbook (pg_id, spell_id, known, in_spellbook, notes)
                        VALUES (%(pg_id)s, %(spell_id)s, %(known)s, %(in_spellbook)s, %(book_notes)s)
                        ON DUPLICATE KEY UPDATE
                            known=VALUES(known), in_spellbook=VALUES(in_spellbook), notes=VALUES(notes)
                    """, data)
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_character_spells_tab_local(pg_id, data.get('spell_id'))
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore salvataggio incantesimo: {e}")

        ttk.Button(dialog, text="Salva", command=save).grid(row=10, column=0, pady=12)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=10, column=1, sticky='w', pady=12)

    def add_spell_dialog(self, pg_id):
        if not (self.current_user and self.current_user.get('role') == 'DM'):
            messagebox.showerror("Permesso negato", "Solo il DM puo' aggiungere incantesimi al catalogo globale.")
            return
        self._spell_editor_dialog(pg_id)

    def edit_spell_dialog(self, pg_id):
        if not (self.current_user and self.current_user.get('role') == 'DM'):
            messagebox.showerror("Permesso negato", "Solo il DM puo' modificare gli incantesimi del catalogo globale.")
            return
        spell_id = self.get_selected_spellbook_spell_id()
        if not spell_id:
            messagebox.showwarning("Attenzione", "Seleziona un incantesimo dal libro.")
            return
        spell = self.get_spellbook_spell_details(pg_id, spell_id)
        if spell:
            self._spell_editor_dialog(pg_id, spell)

    def edit_spellbook_notes_dialog(self, pg_id):
        spell_id = self.get_selected_spellbook_spell_id()
        if not spell_id:
            messagebox.showwarning("Attenzione", "Seleziona un incantesimo dal libro.")
            return
        spell = self.get_spellbook_spell_details(pg_id, spell_id)
        if not spell:
            messagebox.showerror("Errore", "Incantesimo non trovato nel libro del PG.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Note Libro")
        dialog.geometry("620x380")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        header = f"{spell.get('spell_name') or 'Incantesimo'} - Note libro PG"
        ttk.Label(dialog, text=header).grid(row=0, column=0, sticky='w', padx=10, pady=(10, 5))
        notes_text = tk.Text(dialog, wrap='word', height=12)
        notes_text.grid(row=1, column=0, sticky='nsew', padx=10, pady=5)
        notes_scroll = ttk.Scrollbar(dialog, orient='vertical', command=notes_text.yview)
        notes_scroll.grid(row=1, column=1, sticky='ns', pady=5)
        notes_text.config(yscrollcommand=notes_scroll.set)
        notes_text.insert('1.0', spell.get('book_notes') or '')

        buttons = ttk.Frame(dialog)
        buttons.grid(row=2, column=0, columnspan=2, sticky='w', padx=10, pady=10)

        def save_notes():
            notes = notes_text.get('1.0', 'end-1c').strip()
            cursor = self.db.cursor()
            try:
                cursor.execute("""
                    UPDATE pc_spellbook
                    SET notes = %s
                    WHERE pg_id = %s AND spell_id = %s
                """, (notes, pg_id, spell_id))
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_character_spells_tab_local(pg_id, spell_id)
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore salvataggio note libro: {e}")

        ttk.Button(buttons, text="Salva", command=save_notes).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text="Annulla", command=dialog.destroy).pack(side='left')

    def delete_spell(self, pg_id):
        spell_id = self.get_selected_spellbook_spell_id()
        if not spell_id:
            messagebox.showwarning("Attenzione", "Seleziona un incantesimo dal libro.")
            return
        if not messagebox.askyesno("Conferma", "Rimuovere l'incantesimo selezionato dal libro del PG?"):
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_spell_prepared WHERE pg_id = %s AND spell_id = %s", (pg_id, spell_id))
            cursor.execute("DELETE FROM pc_spellbook WHERE pg_id = %s AND spell_id = %s", (pg_id, spell_id))
            self.db.commit()
            cursor.close()
            self.refresh_character_spells_tab_local(pg_id)
        except Exception as e:
            self.db.rollback()
            messagebox.showerror("Errore", f"Errore eliminazione incantesimo: {e}")

    def prepare_spell_from_book(self, pg_id):
        spell_id = self.get_selected_spellbook_spell_id()
        if not spell_id:
            messagebox.showwarning("Attenzione", "Seleziona un incantesimo dal libro.")
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT spell_level FROM rule_spells WHERE id = %s", (spell_id,))
            spell = cursor.fetchone()
            if not spell:
                cursor.close()
                return
            spell_level = int(spell['spell_level'])
            status = self.get_spell_preparation_status_for_level(pg_id, spell_level)
            if status['slots'] <= 0:
                cursor.close()
                messagebox.showwarning(
                    "Preparazione non consentita",
                    f"Il PG non ha slot disponibili per incantesimi di livello {spell_level}."
                )
                return
            if status['prepared'] >= status['slots']:
                cursor.close()
                messagebox.showwarning(
                    "Limite raggiunto",
                    f"Slot di livello {spell_level} gia' saturi: {status['prepared']} preparati su {status['slots']}."
                )
                return
            cursor.execute("""
                INSERT INTO pc_spell_prepared (pg_id, spell_id, spell_level, prepared_count, cast_count)
                VALUES (%s, %s, %s, 1, 0)
                ON DUPLICATE KEY UPDATE prepared_count = prepared_count + 1
            """, (pg_id, spell_id, spell_level))
            self.db.commit()
            cursor.close()
            self.refresh_character_spells_tab_local(pg_id, spell_id)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore preparazione incantesimo: {e}")

    def mark_prepared_spell_cast(self, pg_id):
        spell_id = self.get_selected_spellbook_spell_id()
        if not spell_id:
            messagebox.showwarning("Attenzione", "Seleziona un incantesimo dal libro.")
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE pc_spell_prepared
                SET cast_count = LEAST(prepared_count, cast_count + 1)
                WHERE pg_id = %s AND spell_id = %s
            """, (pg_id, spell_id))
            self.db.commit()
            cursor.close()
            self.refresh_character_spells_tab_local(pg_id, spell_id)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lancio incantesimo: {e}")

    def reset_spell_preparation(self, pg_id):
        spell_id = self.get_selected_spellbook_spell_id()
        if not spell_id:
            messagebox.showwarning("Attenzione", "Seleziona un incantesimo dal libro.")
            return
        if not messagebox.askyesno("Conferma", "Azzerare preparati e lanciati per l'incantesimo selezionato?"):
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE pc_spell_prepared
                SET prepared_count = 0, cast_count = 0
                WHERE pg_id = %s AND spell_id = %s
            """, (pg_id, spell_id))
            self.db.commit()
            cursor.close()
            self.refresh_character_spells_tab_local(pg_id, spell_id)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore azzeramento preparazione: {e}")

    def show_spell_details_dialog(self, pg_id):
        spell_id = self.get_selected_spellbook_spell_id()
        if not spell_id:
            return
        spell = self.get_spellbook_spell_details(pg_id, spell_id)
        if not spell:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title(spell.get('spell_name') or "Dettaglio incantesimo")
        dialog.geometry("760x620")
        dialog.transient(self.root)
        dialog.grab_set()

        info = ttk.LabelFrame(dialog, text="Dati Incantesimo", padding=10)
        info.pack(fill='x', padx=10, pady=10)
        rows = [
            ("Nome", spell.get('spell_name') or ''),
            ("Livello", spell.get('spell_level') or ''),
            ("Lista", spell.get('spell_list_type') or ''),
            ("Reversibile", "Si" if spell.get('reversible') else "No"),
            ("Raggio", spell.get('range_text') or ''),
            ("Durata", spell.get('duration_text') or ''),
            ("Preparati", spell.get('prepared_count') or 0),
            ("Lanciati", spell.get('cast_count') or 0),
        ]
        for i, (label, value) in enumerate(rows):
            ttk.Label(info, text=f"{label}:").grid(row=i // 2, column=(i % 2) * 2, sticky='w', padx=5, pady=3)
            ttk.Label(info, text=str(value), wraplength=240).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky='w', padx=5, pady=3)

        details = ttk.LabelFrame(dialog, text="Effetto e descrizione", padding=10)
        details.pack(fill='both', expand=True, padx=10, pady=5)
        text = tk.Text(details, wrap='word', height=18)
        text.pack(side='left', fill='both', expand=True)
        detail_scroll = ttk.Scrollbar(details, orient='vertical', command=text.yview)
        detail_scroll.pack(side='right', fill='y')
        text.config(yscrollcommand=detail_scroll.set)
        full_text = (
            f"Effetto:\n{spell.get('effect_text') or ''}\n\n"
            f"Descrizione:\n{spell.get('description') or ''}\n\n"
            f"Note libro PG:\n{spell.get('book_notes') or ''}"
        )
        text.insert('1.0', full_text)
        text.configure(state='disabled')
        ttk.Button(dialog, text="Chiudi", command=dialog.destroy).pack(pady=10)

    def refresh_mercenary_list(self, pg_id):
        """Ricarica mercenari - Con righe alternate"""
        try:
            self.mercenary_tree.delete(*self.mercenary_tree.get_children())
            self.mercenary_tree.tag_configure('oddrow', background='white')
            self.mercenary_tree.tag_configure('evenrow', background='#f0f0f0')
            
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_mercenari WHERE pg_id = %s", (pg_id,))
            mercenaries = cursor.fetchall()
            cursor.close()
            
            for i, merc in enumerate(mercenaries):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                self.mercenary_tree.insert('', 'end', values=(
                    merc['categoria'], merc['tipo_truppa'], merc['quantita']
                ), tags=(merc['id'], tag))
        except Exception as e:
            print(f"Errore refresh mercenari: {e}")
    
    def add_mercenary_dialog(self, pg_id):
        """Dialog aggiungi mercenari"""
        try:
            pg_id = int(pg_id)
            dialog = tk.Toplevel(self.root)
            dialog.title("Aggiungi Mercenari")
            dialog.geometry("400x200")
            dialog.transient(self.root)
            dialog.grab_set()
            
            ttk.Label(dialog, text="Categoria:").grid(row=0, column=0, sticky='w', padx=10, pady=10)
            cat_var = ttk.Combobox(dialog, values=["Fanteria", "Cavalleria", "Arcieri", "Assedio"], width=27)
            cat_var.grid(row=0, column=1, padx=10, pady=10)
            
            ttk.Label(dialog, text="Tipo Truppa:").grid(row=1, column=0, sticky='w', padx=10, pady=10)
            tipo_var = ttk.Entry(dialog, width=30)
            tipo_var.grid(row=1, column=1, padx=10, pady=10)
            
            ttk.Label(dialog, text="Quantità:").grid(row=2, column=0, sticky='w', padx=10, pady=10)
            qty_var = ttk.Spinbox(dialog, from_=1, to=9999, width=28)
            qty_var.set(10)
            qty_var.grid(row=2, column=1, padx=10, pady=10)
            
            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        INSERT INTO pc_mercenari (pg_id, categoria, tipo_truppa, quantita)
                        VALUES (%s, %s, %s, %s)
                    """, (pg_id, cat_var.get(), tipo_var.get(), int(qty_var.get())))
                    self.db.commit()
                    cursor.close()
                    self.refresh_mercenary_list(pg_id)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Mercenari aggiunti!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")
            
            ttk.Button(dialog, text="Salva", command=save).grid(row=3, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=3, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def edit_mercenary_dialog(self, pg_id):
        """Dialog modifica mercenari"""
        selection = self.mercenary_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un gruppo di mercenari!")
            return
        
        item = self.mercenary_tree.item(selection[0])
        merc_id = item['tags'][0]
        
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_mercenari WHERE id = %s AND pg_id = %s", (merc_id, pg_id))
            merc = cursor.fetchone()
            cursor.close()
            
            dialog = tk.Toplevel(self.root)
            dialog.title("Modifica Mercenari")
            dialog.geometry("400x200")
            dialog.transient(self.root)
            dialog.grab_set()
            
            ttk.Label(dialog, text="Categoria:").grid(row=0, column=0, sticky='w', padx=10, pady=10)
            cat_var = ttk.Combobox(dialog, values=["Fanteria", "Cavalleria", "Arcieri", "Assedio"], width=27)
            cat_var.set(merc['categoria'])
            cat_var.grid(row=0, column=1, padx=10, pady=10)
            
            ttk.Label(dialog, text="Tipo Truppa:").grid(row=1, column=0, sticky='w', padx=10, pady=10)
            tipo_var = ttk.Entry(dialog, width=30)
            tipo_var.insert(0, merc['tipo_truppa'])
            tipo_var.grid(row=1, column=1, padx=10, pady=10)
            
            ttk.Label(dialog, text="Quantità:").grid(row=2, column=0, sticky='w', padx=10, pady=10)
            qty_var = ttk.Spinbox(dialog, from_=0, to=9999, width=28)
            qty_var.set(merc['quantita'])
            qty_var.grid(row=2, column=1, padx=10, pady=10)
            
            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        UPDATE pc_mercenari 
                        SET categoria = %s, tipo_truppa = %s, quantita = %s
                        WHERE id = %s AND pg_id = %s
                    """, (cat_var.get(), tipo_var.get(), int(qty_var.get()), merc_id, pg_id))
                    self.db.commit()
                    cursor.close()
                    self.refresh_mercenary_list(pg_id)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Mercenari modificati!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")
            
            ttk.Button(dialog, text="Salva", command=save).grid(row=3, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=3, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def delete_mercenary(self, pg_id):
        """Elimina mercenari"""
        selection = self.mercenary_tree.selection()
        if not selection:
            return
        item = self.mercenary_tree.item(selection[0])
        merc_id = item['tags'][0]
        if not messagebox.askyesno("Conferma", "Eliminare i mercenari selezionati?"):
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_mercenari WHERE id = %s AND pg_id = %s", (merc_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_mercenary_list(pg_id)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")

    def create_character_mercenaries_tab(self, notebook, pg_id, character):
        """Tab Mercenari con integrazione spese fisse."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Mercenari")
        is_dm = self.current_user and self.current_user.get('role') == 'DM'

        main_frame = ttk.LabelFrame(tab, text="Truppe Mercenarie", padding=10)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        columns = ('categoria', 'tipo_truppa', 'quantita', 'costo_totale', 'frequenza', 'servizio')
        self.mercenary_tree = ttk.Treeview(main_frame, columns=columns, show='headings')
        headings = {
            'categoria': ('Categoria', 140),
            'tipo_truppa': ('Tipo Truppa', 220),
            'quantita': ('Quantita', 90),
            'costo_totale': ('Costo Totale', 110),
            'frequenza': ('Frequenza', 110),
            'servizio': ('In servizio', 90),
        }
        for col, (label, width) in headings.items():
            self.mercenary_tree.heading(col, text=label)
            self.mercenary_tree.column(col, width=width)

        self.mercenary_tree.pack(side='left', fill='both', expand=True)
        self.mercenary_tree.bind("<Double-1>", lambda e: self.show_mercenary_details_dialog(pg_id))

        merc_scroll = ttk.Scrollbar(main_frame, orient='vertical', command=self.mercenary_tree.yview)
        merc_scroll.pack(side='right', fill='y')
        self.mercenary_tree.config(yscrollcommand=merc_scroll.set)

        self.refresh_mercenary_list(pg_id)

        if not is_dm:
            return
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill='x', padx=10, pady=5)

        ttk.Button(btn_frame, text="Aggiungi Mercenari",
                  command=lambda: self.add_mercenary_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Modifica",
                  command=lambda: self.edit_mercenary_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Elimina",
                  command=lambda: self.delete_mercenary(pg_id)).pack(side='left', padx=5)

    def refresh_mercenary_list(self, pg_id):
        """Ricarica mercenari con dati economici e righe alternate."""
        try:
            self.mercenary_tree.delete(*self.mercenary_tree.get_children())
            self.mercenary_tree.tag_configure('oddrow', background='white')
            self.mercenary_tree.tag_configure('evenrow', background='#f0f0f0')

            cursor = self.db.cursor()
            cursor.execute("""
                SELECT *
                FROM pc_mercenari
                WHERE pg_id = %s
                ORDER BY categoria, tipo_truppa
            """, (pg_id,))
            mercenaries = cursor.fetchall()
            cursor.close()

            for i, merc in enumerate(mercenaries):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                self.mercenary_tree.insert('', 'end', values=(
                    merc.get('categoria') or '',
                    merc.get('tipo_truppa') or '',
                    merc.get('quantita') or 0,
                    f"{float(merc.get('costo_totale') or 0):.2f}",
                    merc.get('frequenza_pagamento') or '',
                    "Si" if merc.get('in_servizio', 1) else "No",
                ), tags=(merc['id'], tag))
        except Exception as e:
            print(f"Errore refresh mercenari: {e}")

    def add_mercenary_dialog(self, pg_id):
        """Dialog aggiungi mercenari."""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' aggiungere mercenari.")
            return
        self._mercenary_dialog(pg_id)

    def edit_mercenary_dialog(self, pg_id):
        """Dialog modifica mercenari."""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' modificare mercenari.")
            return
        selection = self.mercenary_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un gruppo di mercenari.")
            return
        merc_id = self.mercenary_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_mercenari WHERE id = %s AND pg_id = %s", (merc_id, pg_id))
            merc = cursor.fetchone()
            cursor.close()
            if not merc:
                messagebox.showwarning("Attenzione", "Gruppo mercenari non trovato.")
                return
            self._mercenary_dialog(pg_id, merc)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura mercenari: {e}")

    def delete_mercenary(self, pg_id):
        """Elimina mercenari e l'eventuale spesa fissa collegata."""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' eliminare mercenari.")
            return
        selection = self.mercenary_tree.selection()
        if not selection:
            return
        merc_id = self.mercenary_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_mercenari WHERE id = %s AND pg_id = %s", (merc_id, pg_id))
            merc = cursor.fetchone()
            cursor.close()
            if not merc:
                messagebox.showwarning("Attenzione", "Gruppo mercenari non trovato.")
                return
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura mercenari: {e}")
            return

        extra = "\n\nVerra' eliminata anche la spesa fissa collegata." if merc.get('fixed_expense_id') else ""
        if not messagebox.askyesno("Conferma", f"Eliminare i mercenari selezionati?{extra}"):
            return

        cursor = self.db.cursor()
        try:
            if merc.get('fixed_expense_id'):
                cursor.execute(
                    "DELETE FROM fixed_expenses WHERE id = %s AND pg_id = %s",
                    (merc.get('fixed_expense_id'), pg_id)
                )
            cursor.execute("DELETE FROM pc_mercenari WHERE id = %s AND pg_id = %s", (merc_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_mercenary_list(pg_id)
        except Exception as e:
            self.db.rollback()
            cursor.close()
            messagebox.showerror("Errore", f"Errore eliminazione mercenari: {e}")

    def _mercenary_dialog(self, pg_id, merc=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Mercenari" if merc else "Aggiungi Mercenari")
        dialog.geometry("620x430")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)

        ttk.Label(dialog, text="Categoria:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        cat_var = ttk.Combobox(dialog, values=["Fanteria", "Cavalleria", "Arcieri", "Assedio", "Altro"], width=38)
        cat_var.grid(row=0, column=1, sticky='ew', padx=10, pady=5)
        cat_var.set(merc.get('categoria') or '' if merc else '')

        ttk.Label(dialog, text="Tipo Truppa:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        tipo_var = ttk.Entry(dialog, width=40)
        tipo_var.grid(row=1, column=1, sticky='ew', padx=10, pady=5)
        tipo_var.insert(0, merc.get('tipo_truppa') or '' if merc else '')

        ttk.Label(dialog, text="Quantita:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        qty_var = ttk.Spinbox(dialog, from_=1, to=9999, width=38)
        qty_var.grid(row=2, column=1, sticky='ew', padx=10, pady=5)
        qty_var.set(merc.get('quantita') or 10 if merc else 10)

        ttk.Label(dialog, text="Costo totale gruppo (MO):").grid(row=3, column=0, sticky='w', padx=10, pady=5)
        costo_var = ttk.Entry(dialog, width=40)
        costo_var.grid(row=3, column=1, sticky='ew', padx=10, pady=5)
        costo_var.insert(0, str(float(merc.get('costo_totale') or 0)) if merc else "0")

        ttk.Label(dialog, text="Frequenza pagamento:").grid(row=4, column=0, sticky='w', padx=10, pady=5)
        freq_combo = ttk.Combobox(dialog, values=['giornaliera', 'settimanale', 'mensile'], state='readonly', width=38)
        freq_combo.grid(row=4, column=1, sticky='ew', padx=10, pady=5)
        freq_combo.set((merc.get('frequenza_pagamento') if merc else '') or 'mensile')

        ttk.Label(dialog, text="Banca collegata:").grid(row=5, column=0, sticky='w', padx=10, pady=5)
        bank_combo = ttk.Combobox(dialog, state='readonly', width=38)
        banks = self.get_property_banks(pg_id)
        bank_combo['values'] = [b['label'] for b in banks]
        bank_combo.grid(row=5, column=1, sticky='ew', padx=10, pady=5)
        current_bank_id = merc.get('banca_collegata') if merc else None
        if current_bank_id:
            for index, bank in enumerate(banks):
                if bank['id'] == current_bank_id:
                    bank_combo.current(index)
                    break

        servizio_var = tk.BooleanVar(value=bool(merc.get('in_servizio', 1)) if merc else True)
        ttk.Checkbutton(dialog, text="In servizio", variable=servizio_var).grid(row=6, column=1, sticky='w', padx=10, pady=5)

        def dec_value():
            raw = costo_var.get().strip()
            return Decimal(raw.replace(',', '.')) if raw else Decimal('0')

        def selected_bank_id():
            index = bank_combo.current()
            if index < 0 or index >= len(banks):
                return None
            return banks[index]['id']

        def save():
            try:
                quantity = int(qty_var.get())
                if quantity < 1:
                    raise ValueError()
            except Exception:
                messagebox.showerror("Errore", "Quantita non valida.")
                return
            try:
                costo = dec_value()
            except Exception:
                messagebox.showerror("Errore", "Costo totale gruppo non valido.")
                return
            data = {
                'pg_id': pg_id,
                'categoria': cat_var.get().strip(),
                'tipo_truppa': tipo_var.get().strip(),
                'quantita': quantity,
                'costo_totale': costo,
                'banca_collegata': selected_bank_id(),
                'frequenza_pagamento': freq_combo.get().strip() or None,
                'in_servizio': int(servizio_var.get()),
                'fixed_expense_id': merc.get('fixed_expense_id') if merc else None,
            }
            cursor = self.db.cursor()
            try:
                if merc:
                    data['id'] = merc['id']
                    cursor.execute("""
                        UPDATE pc_mercenari
                        SET categoria=%(categoria)s, tipo_truppa=%(tipo_truppa)s,
                            quantita=%(quantita)s, costo_totale=%(costo_totale)s,
                            banca_collegata=%(banca_collegata)s,
                            frequenza_pagamento=%(frequenza_pagamento)s,
                            in_servizio=%(in_servizio)s,
                            fixed_expense_id=%(fixed_expense_id)s
                        WHERE id=%(id)s AND pg_id=%(pg_id)s
                    """, data)
                    merc_id = merc['id']
                else:
                    cursor.execute("""
                        INSERT INTO pc_mercenari
                            (pg_id, categoria, tipo_truppa, quantita, costo_totale,
                             banca_collegata, frequenza_pagamento, in_servizio, fixed_expense_id)
                        VALUES
                            (%(pg_id)s, %(categoria)s, %(tipo_truppa)s, %(quantita)s, %(costo_totale)s,
                             %(banca_collegata)s, %(frequenza_pagamento)s, %(in_servizio)s, %(fixed_expense_id)s)
                    """, data)
                    merc_id = cursor.lastrowid
                data['fixed_expense_id'] = self.sync_mercenary_expense(cursor, pg_id, merc_id, data)
                cursor.execute(
                    "UPDATE pc_mercenari SET fixed_expense_id = %s WHERE id = %s AND pg_id = %s",
                    (data['fixed_expense_id'], merc_id, pg_id)
                )
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_mercenary_list(pg_id)
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore mercenari: {e}")

        ttk.Button(dialog, text="Salva", command=save).grid(row=7, column=0, pady=12)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=7, column=1, sticky='w', pady=12)

    def sync_mercenary_expense(self, cursor, pg_id, merc_id, data):
        fixed_expense_id = data.get('fixed_expense_id')
        active = bool(data.get('in_servizio'))
        cost = data.get('costo_totale') or Decimal('0')
        bank_id = data.get('banca_collegata')
        frequency = data.get('frequenza_pagamento')
        should_sync = active and cost > 0 and bank_id and frequency
        description = f"Mercenari: {data.get('categoria') or 'Mercenari'} - {data.get('tipo_truppa') or f'ID {merc_id}'}"
        if should_sync:
            if fixed_expense_id:
                cursor.execute("""
                    UPDATE fixed_expenses
                    SET pg_id = %s, description = %s, amount = %s,
                        frequency = %s, source_bank_id = %s
                    WHERE id = %s AND pg_id = %s
                """, (pg_id, description, cost, frequency, bank_id, fixed_expense_id, pg_id))
                if cursor.rowcount == 0:
                    cursor.execute(
                        "SELECT id FROM fixed_expenses WHERE id = %s AND pg_id = %s",
                        (fixed_expense_id, pg_id)
                    )
                    if not cursor.fetchone():
                        fixed_expense_id = None
            if not fixed_expense_id:
                cursor.execute("""
                    INSERT INTO fixed_expenses
                        (pg_id, description, amount, frequency, source_bank_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (pg_id, description, cost, frequency, bank_id))
                fixed_expense_id = cursor.lastrowid
        elif fixed_expense_id:
            cursor.execute("DELETE FROM fixed_expenses WHERE id = %s AND pg_id = %s", (fixed_expense_id, pg_id))
            fixed_expense_id = None
        return fixed_expense_id

    def show_mercenary_details_dialog(self, pg_id):
        selection = self.mercenary_tree.selection()
        if not selection:
            return
        merc_id = self.mercenary_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_mercenari WHERE id = %s AND pg_id = %s", (merc_id, pg_id))
            merc = cursor.fetchone()
            cursor.close()
            if not merc:
                return
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura mercenari: {e}")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(merc.get('tipo_truppa') or "Dettaglio mercenari")
        dialog.geometry("700x360")
        dialog.transient(self.root)
        dialog.grab_set()

        info = ttk.LabelFrame(dialog, text="Dati mercenari", padding=10)
        info.pack(fill='x', padx=10, pady=10)
        bank_text = self.get_property_bank_display(merc.get('banca_collegata'))
        rows = [
            ("Categoria", merc.get('categoria') or ''),
            ("Tipo truppa", merc.get('tipo_truppa') or ''),
            ("Quantita", merc.get('quantita') or 0),
            ("Costo totale gruppo", f"{float(merc.get('costo_totale') or 0):.2f}"),
            ("Frequenza pagamento", merc.get('frequenza_pagamento') or ''),
            ("Banca collegata", bank_text),
            ("In servizio", "Si" if merc.get('in_servizio', 1) else "No"),
        ]
        for i, (label, value) in enumerate(rows):
            ttk.Label(info, text=f"{label}:").grid(row=i // 2, column=(i % 2) * 2, sticky='w', padx=5, pady=3)
            ttk.Label(info, text=str(value), wraplength=260).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky='w', padx=5, pady=3)

        ttk.Button(dialog, text="Chiudi", command=dialog.destroy).pack(pady=10)

    def refresh_advisor_list(self, pg_id):
        """Ricarica consiglieri - Con righe alternate"""
        try:
            self.advisor_tree.delete(*self.advisor_tree.get_children())
            self.advisor_tree.tag_configure('oddrow', background='white')
            self.advisor_tree.tag_configure('evenrow', background='#f0f0f0')
            
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_consiglieri WHERE pg_id = %s", (pg_id,))
            advisors = cursor.fetchall()
            cursor.close()
            
            for i, adv in enumerate(advisors):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                self.advisor_tree.insert('', 'end', values=(
                    adv['mansione'], adv['nome'], adv['classe'], adv['livello'],
                    adv['fe'], adv['in_servizio'], adv['sa'], adv['de'], adv['co'], adv['ca']
                ), tags=(adv['id'], tag))
        except Exception as e:
            print(f"Errore refresh consiglieri: {e}")
    
    def add_advisor_dialog(self, pg_id):
        """Dialog aggiungi consigliere"""
        try:
            pg_id = int(pg_id)
            dialog = tk.Toplevel(self.root)
            dialog.title("Aggiungi Consigliere")
            dialog.geometry("550x500")  # Era 500x450, aumentato
            dialog.transient(self.root)
            dialog.grab_set()
            
            fields = {}
            row = 0
            
            for field, label in [('mansione', 'Mansione'), ('nome', 'Nome'), ('classe', 'Classe'),
                                ('livello', 'Livello'), ('fe', 'FE'), ('in_servizio', 'IN'),
                                ('sa', 'SA'), ('de', 'DE'), ('co', 'CO'), ('ca', 'CA')]:
                ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
                if field in ['livello', 'fe', 'in_servizio', 'sa', 'de', 'co', 'ca']:
                    fields[field] = ttk.Spinbox(dialog, from_=0, to=25, width=37)
                    fields[field].set(10 if field in ['fe', 'in_servizio', 'sa', 'de', 'co'] else 0)
                else:
                    fields[field] = ttk.Entry(dialog, width=40)
                fields[field].grid(row=row, column=1, padx=10, pady=5)
                row += 1
            
            ttk.Label(dialog, text="Note:").grid(row=row, column=0, sticky='nw', padx=10, pady=5)
            note_text = tk.Text(dialog, width=40, height=4)
            note_text.grid(row=row, column=1, padx=10, pady=5)
            row += 1
            
            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        INSERT INTO pc_consiglieri 
                        (pg_id, mansione, nome, classe, livello, fe, in_servizio, sa, de, co, ca, note)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (pg_id, fields['mansione'].get(), fields['nome'].get(), fields['classe'].get(),
                          int(fields['livello'].get()), int(fields['fe'].get()), int(fields['in_servizio'].get()),
                          int(fields['sa'].get()), int(fields['de'].get()), int(fields['co'].get()),
                          int(fields['ca'].get()), note_text.get('1.0', 'end-1c')))
                    self.db.commit()
                    cursor.close()
                    self.refresh_advisor_list(pg_id)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Consigliere aggiunto!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")
            
            ttk.Button(dialog, text="Salva", command=save).grid(row=row, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=row, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def edit_advisor_dialog(self, pg_id):
        """Dialog modifica consigliere"""
        selection = self.advisor_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un consigliere!")
            return
        item = self.advisor_tree.item(selection[0])
        adv_id = item['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_consiglieri WHERE id = %s AND pg_id = %s", (adv_id, pg_id))
            advisor = cursor.fetchone()
            cursor.close()
            if not advisor:
                messagebox.showerror("Errore", "Consigliere non trovato.")
                return

            dialog = tk.Toplevel(self.root)
            dialog.title("Modifica Consigliere")
            dialog.geometry("550x500")
            dialog.transient(self.root)
            dialog.grab_set()

            fields = {}
            row = 0
            field_defs = [
                ('mansione', 'Mansione'), ('nome', 'Nome'), ('classe', 'Classe'),
                ('livello', 'Livello'), ('fe', 'FE'), ('in_servizio', 'IN'),
                ('sa', 'SA'), ('de', 'DE'), ('co', 'CO'), ('ca', 'CA')
            ]
            for field, label in field_defs:
                ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
                if field in ['livello', 'fe', 'in_servizio', 'sa', 'de', 'co', 'ca']:
                    fields[field] = ttk.Spinbox(dialog, from_=0, to=25, width=37)
                    fields[field].set(advisor.get(field, 0) or 0)
                else:
                    fields[field] = ttk.Entry(dialog, width=40)
                    fields[field].insert(0, advisor.get(field, '') or '')
                fields[field].grid(row=row, column=1, padx=10, pady=5)
                row += 1

            ttk.Label(dialog, text="Note:").grid(row=row, column=0, sticky='nw', padx=10, pady=5)
            note_text = tk.Text(dialog, width=40, height=4)
            note_text.insert('1.0', advisor.get('note', '') or '')
            note_text.grid(row=row, column=1, padx=10, pady=5)
            row += 1

            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        UPDATE pc_consiglieri
                        SET mansione = %s, nome = %s, classe = %s, livello = %s,
                            fe = %s, in_servizio = %s, sa = %s, de = %s, co = %s, ca = %s, note = %s
                        WHERE id = %s AND pg_id = %s
                    """, (
                        fields['mansione'].get(), fields['nome'].get(), fields['classe'].get(),
                        int(fields['livello'].get()), int(fields['fe'].get()), int(fields['in_servizio'].get()),
                        int(fields['sa'].get()), int(fields['de'].get()), int(fields['co'].get()),
                        int(fields['ca'].get()), note_text.get('1.0', 'end-1c'), adv_id, pg_id
                    ))
                    self.db.commit()
                    cursor.close()
                    self.refresh_advisor_list(pg_id)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Consigliere modificato!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")

            ttk.Button(dialog, text="Salva", command=save).grid(row=row, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=row, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def delete_advisor(self, pg_id):
        """Elimina consigliere"""
        selection = self.advisor_tree.selection()
        if not selection:
            return
        item = self.advisor_tree.item(selection[0])
        adv_id = item['tags'][0]
        if not messagebox.askyesno("Conferma", "Eliminare il consigliere selezionato?"):
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_consiglieri WHERE id = %s AND pg_id = %s", (adv_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_advisor_list(pg_id)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")

    def create_character_advisors_tab(self, notebook, pg_id, character):
        """Tab Consiglieri con integrazione spese fisse."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Consiglieri")
        is_dm = self.current_user and self.current_user.get('role') == 'DM'

        main_frame = ttk.LabelFrame(tab, text="Consiglieri e Ufficiali", padding=10)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        columns = (
            'mansione', 'nome', 'classe', 'livello', 'fo', 'in_', 'sa',
            'de', 'co', 'ca', 'costo', 'frequenza', 'attivo_spesa'
        )
        self.advisor_tree = ttk.Treeview(main_frame, columns=columns, show='headings')
        headings = {
            'mansione': ('Mansione', 120),
            'nome': ('Nome', 120),
            'classe': ('Classe', 90),
            'livello': ('Liv', 55),
            'fo': ('FO', 50),
            'in_': ('IN', 50),
            'sa': ('SA', 50),
            'de': ('DE', 50),
            'co': ('CO', 50),
            'ca': ('CA', 50),
            'costo': ('Costo MO', 90),
            'frequenza': ('Frequenza', 105),
            'attivo_spesa': ('Attivo spesa', 95),
        }
        for col, (label, width) in headings.items():
            self.advisor_tree.heading(col, text=label)
            self.advisor_tree.column(col, width=width)

        self.advisor_tree.pack(side='left', fill='both', expand=True)
        self.advisor_tree.bind("<Double-1>", lambda e: self.show_advisor_details_dialog(pg_id))

        adv_scroll = ttk.Scrollbar(main_frame, orient='vertical', command=self.advisor_tree.yview)
        adv_scroll.pack(side='right', fill='y')
        self.advisor_tree.config(yscrollcommand=adv_scroll.set)

        self.refresh_advisor_list(pg_id)

        if not is_dm:
            return
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill='x', padx=10, pady=5)

        ttk.Button(btn_frame, text="Aggiungi Consigliere",
                  command=lambda: self.add_advisor_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Modifica",
                  command=lambda: self.edit_advisor_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Elimina",
                  command=lambda: self.delete_advisor(pg_id)).pack(side='left', padx=5)

    def refresh_advisor_list(self, pg_id):
        """Ricarica consiglieri con caratteristiche e dati economici."""
        try:
            self.advisor_tree.delete(*self.advisor_tree.get_children())
            self.advisor_tree.tag_configure('oddrow', background='white')
            self.advisor_tree.tag_configure('evenrow', background='#f0f0f0')

            cursor = self.db.cursor()
            cursor.execute("""
                SELECT *
                FROM pc_consiglieri
                WHERE pg_id = %s
                ORDER BY mansione, nome
            """, (pg_id,))
            advisors = cursor.fetchall()
            cursor.close()

            for i, adv in enumerate(advisors):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                self.advisor_tree.insert('', 'end', values=(
                    adv.get('mansione') or '',
                    adv.get('nome') or '',
                    adv.get('classe') or '',
                    adv.get('livello') or 0,
                    adv.get('fo') or 0,
                    adv.get('intelligenza') or 0,
                    adv.get('sa') or 0,
                    adv.get('de') or 0,
                    adv.get('co') or 0,
                    adv.get('ca') or 0,
                    f"{float(adv.get('costo') or 0):.2f}",
                    adv.get('frequenza_pagamento') or '',
                    "Si" if adv.get('attivo_spesa', 1) else "No",
                ), tags=(adv['id'], tag))
        except Exception as e:
            print(f"Errore refresh consiglieri: {e}")

    def add_advisor_dialog(self, pg_id):
        """Dialog aggiungi consigliere."""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' aggiungere consiglieri.")
            return
        self._advisor_dialog(pg_id)

    def edit_advisor_dialog(self, pg_id):
        """Dialog modifica consigliere."""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' modificare consiglieri.")
            return
        selection = self.advisor_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un consigliere.")
            return
        adv_id = self.advisor_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_consiglieri WHERE id = %s AND pg_id = %s", (adv_id, pg_id))
            advisor = cursor.fetchone()
            cursor.close()
            if not advisor:
                messagebox.showwarning("Attenzione", "Consigliere non trovato.")
                return
            self._advisor_dialog(pg_id, advisor)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura consigliere: {e}")

    def delete_advisor(self, pg_id):
        """Elimina consigliere e l'eventuale spesa fissa collegata."""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' eliminare consiglieri.")
            return
        selection = self.advisor_tree.selection()
        if not selection:
            return
        adv_id = self.advisor_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_consiglieri WHERE id = %s AND pg_id = %s", (adv_id, pg_id))
            advisor = cursor.fetchone()
            cursor.close()
            if not advisor:
                messagebox.showwarning("Attenzione", "Consigliere non trovato.")
                return
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura consigliere: {e}")
            return

        extra = "\n\nVerra' eliminata anche la spesa fissa collegata." if advisor.get('fixed_expense_id') else ""
        if not messagebox.askyesno("Conferma", f"Eliminare il consigliere selezionato?{extra}"):
            return

        cursor = self.db.cursor()
        try:
            if advisor.get('fixed_expense_id'):
                cursor.execute(
                    "DELETE FROM fixed_expenses WHERE id = %s AND pg_id = %s",
                    (advisor.get('fixed_expense_id'), pg_id)
                )
            cursor.execute("DELETE FROM pc_consiglieri WHERE id = %s AND pg_id = %s", (adv_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_advisor_list(pg_id)
        except Exception as e:
            self.db.rollback()
            cursor.close()
            messagebox.showerror("Errore", f"Errore eliminazione consigliere: {e}")

    def _advisor_dialog(self, pg_id, advisor=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Consigliere" if advisor else "Aggiungi Consigliere")
        dialog.geometry("680x660")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)

        text_fields = [
            ('mansione', 'Mansione'),
            ('nome', 'Nome'),
            ('classe', 'Classe'),
        ]
        widgets = {}
        row = 0
        for field, label in text_fields:
            ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=4)
            widget = ttk.Entry(dialog, width=42)
            widget.grid(row=row, column=1, sticky='ew', padx=10, pady=4)
            widget.insert(0, advisor.get(field) or '' if advisor else '')
            widgets[field] = widget
            row += 1

        numeric_fields = [
            ('livello', 'Livello', 0, 36, 0),
            ('fo', 'FO', 0, 25, 10),
            ('intelligenza', 'IN', 0, 25, 10),
            ('sa', 'SA', 0, 25, 10),
            ('de', 'DE', 0, 25, 10),
            ('co', 'CO', 0, 25, 10),
            ('ca', 'CA', -20, 30, 10),
        ]
        for field, label, min_value, max_value, default in numeric_fields:
            ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=4)
            widget = ttk.Spinbox(dialog, from_=min_value, to=max_value, width=39)
            widget.grid(row=row, column=1, sticky='ew', padx=10, pady=4)
            widget.set(advisor.get(field) if advisor and advisor.get(field) is not None else default)
            widgets[field] = widget
            row += 1

        ttk.Label(dialog, text="Costo MO:").grid(row=row, column=0, sticky='w', padx=10, pady=4)
        costo_var = ttk.Entry(dialog, width=42)
        costo_var.grid(row=row, column=1, sticky='ew', padx=10, pady=4)
        costo_var.insert(0, str(float(advisor.get('costo') or 0)) if advisor else "0")
        row += 1

        ttk.Label(dialog, text="Frequenza pagamento:").grid(row=row, column=0, sticky='w', padx=10, pady=4)
        freq_combo = ttk.Combobox(dialog, values=['giornaliera', 'settimanale', 'mensile'], state='readonly', width=39)
        freq_combo.grid(row=row, column=1, sticky='ew', padx=10, pady=4)
        freq_combo.set((advisor.get('frequenza_pagamento') if advisor else '') or 'mensile')
        row += 1

        ttk.Label(dialog, text="Banca collegata:").grid(row=row, column=0, sticky='w', padx=10, pady=4)
        bank_combo = ttk.Combobox(dialog, state='readonly', width=39)
        banks = self.get_property_banks(pg_id)
        bank_combo['values'] = [b['label'] for b in banks]
        bank_combo.grid(row=row, column=1, sticky='ew', padx=10, pady=4)
        current_bank_id = advisor.get('banca_collegata') if advisor else None
        if current_bank_id:
            for index, bank in enumerate(banks):
                if bank['id'] == current_bank_id:
                    bank_combo.current(index)
                    break
        row += 1

        attivo_spesa_var = tk.BooleanVar(value=bool(advisor.get('attivo_spesa', 1)) if advisor else True)
        ttk.Checkbutton(dialog, text="Attivo spesa", variable=attivo_spesa_var).grid(row=row, column=1, sticky='w', padx=10, pady=4)
        row += 1

        ttk.Label(dialog, text="Note:").grid(row=row, column=0, sticky='nw', padx=10, pady=4)
        note_text = tk.Text(dialog, width=44, height=5)
        note_text.grid(row=row, column=1, sticky='ew', padx=10, pady=4)
        note_text.insert('1.0', advisor.get('note') or '' if advisor else '')
        row += 1

        def int_value(field):
            return int(widgets[field].get())

        def dec_value():
            raw = costo_var.get().strip()
            return Decimal(raw.replace(',', '.')) if raw else Decimal('0')

        def selected_bank_id():
            index = bank_combo.current()
            if index < 0 or index >= len(banks):
                return None
            return banks[index]['id']

        def save():
            try:
                numeric_data = {field: int_value(field) for field, *_ in numeric_fields}
            except Exception:
                messagebox.showerror("Errore", "Uno dei valori numerici non e' valido.")
                return
            try:
                costo = dec_value()
            except Exception:
                messagebox.showerror("Errore", "Costo MO non valido.")
                return
            data = {
                'pg_id': pg_id,
                'mansione': widgets['mansione'].get().strip(),
                'nome': widgets['nome'].get().strip(),
                'classe': widgets['classe'].get().strip(),
                **numeric_data,
                'note': note_text.get('1.0', 'end-1c').strip(),
                'costo': costo,
                'banca_collegata': selected_bank_id(),
                'frequenza_pagamento': freq_combo.get().strip() or None,
                'attivo_spesa': int(attivo_spesa_var.get()),
                'fixed_expense_id': advisor.get('fixed_expense_id') if advisor else None,
            }
            cursor = self.db.cursor()
            try:
                if advisor:
                    data['id'] = advisor['id']
                    cursor.execute("""
                        UPDATE pc_consiglieri
                        SET mansione=%(mansione)s, nome=%(nome)s, classe=%(classe)s,
                            livello=%(livello)s, fo=%(fo)s, intelligenza=%(intelligenza)s,
                            sa=%(sa)s, de=%(de)s, co=%(co)s, ca=%(ca)s,
                            note=%(note)s, costo=%(costo)s, banca_collegata=%(banca_collegata)s,
                            frequenza_pagamento=%(frequenza_pagamento)s,
                            attivo_spesa=%(attivo_spesa)s,
                            fixed_expense_id=%(fixed_expense_id)s
                        WHERE id=%(id)s AND pg_id=%(pg_id)s
                    """, data)
                    adv_id = advisor['id']
                else:
                    cursor.execute("""
                        INSERT INTO pc_consiglieri
                            (pg_id, mansione, nome, classe, livello, fo, intelligenza, sa, de, co, ca,
                             note, costo, banca_collegata, frequenza_pagamento, attivo_spesa, fixed_expense_id)
                        VALUES
                            (%(pg_id)s, %(mansione)s, %(nome)s, %(classe)s, %(livello)s,
                             %(fo)s, %(intelligenza)s, %(sa)s, %(de)s, %(co)s, %(ca)s,
                             %(note)s, %(costo)s, %(banca_collegata)s, %(frequenza_pagamento)s,
                             %(attivo_spesa)s, %(fixed_expense_id)s)
                    """, data)
                    adv_id = cursor.lastrowid
                data['fixed_expense_id'] = self.sync_advisor_expense(cursor, pg_id, adv_id, data)
                cursor.execute(
                    "UPDATE pc_consiglieri SET fixed_expense_id = %s WHERE id = %s AND pg_id = %s",
                    (data['fixed_expense_id'], adv_id, pg_id)
                )
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_advisor_list(pg_id)
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore consigliere: {e}")

        ttk.Button(dialog, text="Salva", command=save).grid(row=row, column=0, pady=12)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=row, column=1, sticky='w', pady=12)

    def sync_advisor_expense(self, cursor, pg_id, adv_id, data):
        fixed_expense_id = data.get('fixed_expense_id')
        active = bool(data.get('attivo_spesa'))
        cost = data.get('costo') or Decimal('0')
        bank_id = data.get('banca_collegata')
        frequency = data.get('frequenza_pagamento')
        should_sync = active and cost > 0 and bank_id and frequency
        description = f"Consigliere: {data.get('mansione') or 'Consigliere'} - {data.get('nome') or f'ID {adv_id}'}"
        if should_sync:
            if fixed_expense_id:
                cursor.execute("""
                    UPDATE fixed_expenses
                    SET pg_id = %s, description = %s, amount = %s,
                        frequency = %s, source_bank_id = %s
                    WHERE id = %s AND pg_id = %s
                """, (pg_id, description, cost, frequency, bank_id, fixed_expense_id, pg_id))
                if cursor.rowcount == 0:
                    cursor.execute(
                        "SELECT id FROM fixed_expenses WHERE id = %s AND pg_id = %s",
                        (fixed_expense_id, pg_id)
                    )
                    if not cursor.fetchone():
                        fixed_expense_id = None
            if not fixed_expense_id:
                cursor.execute("""
                    INSERT INTO fixed_expenses
                        (pg_id, description, amount, frequency, source_bank_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (pg_id, description, cost, frequency, bank_id))
                fixed_expense_id = cursor.lastrowid
        elif fixed_expense_id:
            cursor.execute("DELETE FROM fixed_expenses WHERE id = %s AND pg_id = %s", (fixed_expense_id, pg_id))
            fixed_expense_id = None
        return fixed_expense_id

    def show_advisor_details_dialog(self, pg_id):
        selection = self.advisor_tree.selection()
        if not selection:
            return
        adv_id = self.advisor_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_consiglieri WHERE id = %s AND pg_id = %s", (adv_id, pg_id))
            advisor = cursor.fetchone()
            cursor.close()
            if not advisor:
                return
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura consigliere: {e}")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(advisor.get('nome') or "Dettaglio consigliere")
        dialog.geometry("740x560")
        dialog.transient(self.root)
        dialog.grab_set()

        info = ttk.LabelFrame(dialog, text="Dati consigliere", padding=10)
        info.pack(fill='x', padx=10, pady=10)
        bank_text = self.get_property_bank_display(advisor.get('banca_collegata'))
        rows = [
            ("Mansione", advisor.get('mansione') or ''),
            ("Nome", advisor.get('nome') or ''),
            ("Classe", advisor.get('classe') or ''),
            ("Livello", advisor.get('livello') or 0),
            ("FO", advisor.get('fo') or 0),
            ("IN", advisor.get('intelligenza') or 0),
            ("SA", advisor.get('sa') or 0),
            ("DE", advisor.get('de') or 0),
            ("CO", advisor.get('co') or 0),
            ("CA", advisor.get('ca') or 0),
            ("Costo MO", f"{float(advisor.get('costo') or 0):.2f}"),
            ("Frequenza pagamento", advisor.get('frequenza_pagamento') or ''),
            ("Banca collegata", bank_text),
            ("Attivo spesa", "Si" if advisor.get('attivo_spesa', 1) else "No"),
        ]
        for i, (label, value) in enumerate(rows):
            ttk.Label(info, text=f"{label}:").grid(row=i // 2, column=(i % 2) * 2, sticky='w', padx=5, pady=3)
            ttk.Label(info, text=str(value), wraplength=260).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky='w', padx=5, pady=3)

        notes_frame = ttk.LabelFrame(dialog, text="Note", padding=10)
        notes_frame.pack(fill='both', expand=True, padx=10, pady=5)
        text = tk.Text(notes_frame, wrap='word', height=10)
        text.pack(side='left', fill='both', expand=True)
        detail_scroll = ttk.Scrollbar(notes_frame, orient='vertical', command=text.yview)
        detail_scroll.pack(side='right', fill='y')
        text.config(yscrollcommand=detail_scroll.set)
        text.insert('1.0', advisor.get('note') or '')
        text.configure(state='disabled')

        ttk.Button(dialog, text="Chiudi", command=dialog.destroy).pack(pady=10)

    def refresh_specialist_list(self, pg_id):
        """Ricarica specialisti - Con righe alternate"""
        try:
            self.specialist_tree.delete(*self.specialist_tree.get_children())
            self.specialist_tree.tag_configure('oddrow', background='white')
            self.specialist_tree.tag_configure('evenrow', background='#f0f0f0')
            
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_specialisti WHERE pg_id = %s ORDER BY tipo, nome", (pg_id,))
            specialists = cursor.fetchall()
            cursor.close()
            
            for i, spec in enumerate(specialists):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                self.specialist_tree.insert('', 'end', values=(
                    spec.get('tipo') or '',
                    spec.get('nome') or '',
                    spec.get('localita') or '',
                    f"{float(spec.get('costo') or 0):.2f}",
                    spec.get('frequenza_pagamento') or '',
                    "Si" if spec.get('in_servizio', 1) else "No"
                ), tags=(spec['id'], tag))
        except Exception as e:
            print(f"Errore refresh specialisti: {e}")
    
    def add_specialist_dialog(self, pg_id):
        """Dialog aggiungi specialista"""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' aggiungere specialisti.")
            return
        self._specialist_dialog(pg_id)
        return
        try:
            pg_id = int(pg_id)
            dialog = tk.Toplevel(self.root)
            dialog.title("Aggiungi Specialista")
            dialog.geometry("450x300")
            dialog.transient(self.root)
            dialog.grab_set()
            
            ttk.Label(dialog, text="Tipo:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
            tipo_var = ttk.Combobox(dialog, values=[
                "Alchimista", "Armiere", "Addestratore", "Saggio", "Ingegnere",
                "Mercante", "Guaritore", "Altro"
            ], width=37)
            tipo_var.grid(row=0, column=1, padx=10, pady=5)
            
            ttk.Label(dialog, text="Nome:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
            nome_var = ttk.Entry(dialog, width=40)
            nome_var.grid(row=1, column=1, padx=10, pady=5)
            
            ttk.Label(dialog, text="Località:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
            loc_var = ttk.Entry(dialog, width=40)
            loc_var.grid(row=2, column=1, padx=10, pady=5)
            
            ttk.Label(dialog, text="Competenza:").grid(row=3, column=0, sticky='nw', padx=10, pady=5)
            comp_text = tk.Text(dialog, width=40, height=4)
            comp_text.grid(row=3, column=1, padx=10, pady=5)
            
            ttk.Label(dialog, text="Costo (MO):").grid(row=4, column=0, sticky='w', padx=10, pady=5)
            costo_var = ttk.Entry(dialog, width=40)
            costo_var.insert(0, "0")
            costo_var.grid(row=4, column=1, padx=10, pady=5)
            
            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        INSERT INTO pc_specialisti (pg_id, tipo, nome, localita, competenza, costo)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (pg_id, tipo_var.get(), nome_var.get(), loc_var.get(),
                          comp_text.get('1.0', 'end-1c'), float(costo_var.get())))
                    self.db.commit()
                    cursor.close()
                    self.refresh_specialist_list(pg_id)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Specialista aggiunto!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")
            
            ttk.Button(dialog, text="Salva", command=save).grid(row=5, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=5, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def edit_specialist_dialog(self, pg_id):
        """Dialog modifica specialista"""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' modificare specialisti.")
            return
        selection = self.specialist_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona uno specialista!")
            return
        spec_id = self.specialist_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_specialisti WHERE id = %s AND pg_id = %s", (spec_id, pg_id))
            spec = cursor.fetchone()
            cursor.close()
            if spec:
                self._specialist_dialog(pg_id, spec)
            return
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
            return
        
        item = self.specialist_tree.item(selection[0])
        spec_id = item['tags'][0]
        
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_specialisti WHERE id = %s AND pg_id = %s", (spec_id, pg_id))
            spec = cursor.fetchone()
            cursor.close()
            
            dialog = tk.Toplevel(self.root)
            dialog.title("Modifica Specialista")
            dialog.geometry("450x300")
            dialog.transient(self.root)
            dialog.grab_set()
            
            ttk.Label(dialog, text="Tipo:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
            tipo_var = ttk.Combobox(dialog, values=[
                "Alchimista", "Armiere", "Addestratore", "Saggio", "Ingegnere",
                "Mercante", "Guaritore", "Altro"
            ], width=37)
            tipo_var.set(spec['tipo'])
            tipo_var.grid(row=0, column=1, padx=10, pady=5)
            
            ttk.Label(dialog, text="Nome:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
            nome_var = ttk.Entry(dialog, width=40)
            nome_var.insert(0, spec['nome'])
            nome_var.grid(row=1, column=1, padx=10, pady=5)
            
            ttk.Label(dialog, text="Località:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
            loc_var = ttk.Entry(dialog, width=40)
            loc_var.insert(0, spec['localita'])
            loc_var.grid(row=2, column=1, padx=10, pady=5)
            
            ttk.Label(dialog, text="Competenza:").grid(row=3, column=0, sticky='nw', padx=10, pady=5)
            comp_text = tk.Text(dialog, width=40, height=4)
            comp_text.insert('1.0', spec['competenza'] or '')
            comp_text.grid(row=3, column=1, padx=10, pady=5)
            
            ttk.Label(dialog, text="Costo (MO):").grid(row=4, column=0, sticky='w', padx=10, pady=5)
            costo_var = ttk.Entry(dialog, width=40)
            costo_var.insert(0, str(float(spec['costo'])))
            costo_var.grid(row=4, column=1, padx=10, pady=5)
            
            def save():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        UPDATE pc_specialisti 
                        SET tipo = %s, nome = %s, localita = %s, competenza = %s, costo = %s
                        WHERE id = %s AND pg_id = %s
                    """, (tipo_var.get(), nome_var.get(), loc_var.get(),
                          comp_text.get('1.0', 'end-1c'), float(costo_var.get()), spec_id, pg_id))
                    self.db.commit()
                    cursor.close()
                    self.refresh_specialist_list(pg_id)
                    dialog.destroy()
                    messagebox.showinfo("Successo", "Specialista modificato!")
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore: {e}")
            
            ttk.Button(dialog, text="Salva", command=save).grid(row=5, column=0, pady=10)
            ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=5, column=1, pady=10)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")
    
    def delete_specialist(self, pg_id):
        """Elimina specialista"""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' eliminare specialisti.")
            return
        selection = self.specialist_tree.selection()
        if not selection:
            return
        spec_id = self.specialist_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_specialisti WHERE id = %s AND pg_id = %s", (spec_id, pg_id))
            spec = cursor.fetchone()
            cursor.close()
            if not spec:
                messagebox.showwarning("Attenzione", "Specialista non trovato.")
                return
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura specialista: {e}")
            return
        extra = "\n\nVerra' eliminata anche la spesa fissa collegata." if spec.get('fixed_expense_id') else ""
        if not messagebox.askyesno("Conferma", f"Eliminare lo specialista selezionato?{extra}"):
            return
        cursor = self.db.cursor()
        try:
            if spec.get('fixed_expense_id'):
                cursor.execute(
                    "DELETE FROM fixed_expenses WHERE id = %s AND pg_id = %s",
                    (spec.get('fixed_expense_id'), pg_id)
                )
            cursor.execute("DELETE FROM pc_specialisti WHERE id = %s AND pg_id = %s", (spec_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_specialist_list(pg_id)
        except Exception as e:
            self.db.rollback()
            cursor.close()
            messagebox.showerror("Errore", f"Errore eliminazione specialista: {e}")

    def get_specialist_type_values(self):
        base_types = ["Alchimista", "Armiere", "Addestratore", "Saggio", "Ingegnere", "Mercante", "Guaritore", "Altro"]
        values = list(base_types)
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT DISTINCT tipo
                FROM pc_specialisti
                WHERE tipo IS NOT NULL AND TRIM(tipo) <> ''
                ORDER BY tipo
            """)
            for row in cursor.fetchall():
                tipo = row.get('tipo')
                if tipo and tipo not in values:
                    values.append(tipo)
            cursor.close()
        except Exception as e:
            print(f"Errore caricamento tipi specialisti: {e}")
        return values

    def _specialist_dialog(self, pg_id, spec=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Specialista" if spec else "Aggiungi Specialista")
        dialog.geometry("620x520")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)

        ttk.Label(dialog, text="Tipo:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        tipo_var = ttk.Combobox(dialog, values=self.get_specialist_type_values(), width=38)
        tipo_var.grid(row=0, column=1, sticky='ew', padx=10, pady=5)
        tipo_var.set(spec.get('tipo') if spec else '')

        ttk.Label(dialog, text="Nome:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        nome_var = ttk.Entry(dialog, width=40)
        nome_var.grid(row=1, column=1, sticky='ew', padx=10, pady=5)
        nome_var.insert(0, spec.get('nome') or '' if spec else '')

        ttk.Label(dialog, text="Localita:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        loc_var = ttk.Entry(dialog, width=40)
        loc_var.grid(row=2, column=1, sticky='ew', padx=10, pady=5)
        loc_var.insert(0, spec.get('localita') or '' if spec else '')

        ttk.Label(dialog, text="Competenza:").grid(row=3, column=0, sticky='nw', padx=10, pady=5)
        comp_text = tk.Text(dialog, width=44, height=5)
        comp_text.grid(row=3, column=1, sticky='ew', padx=10, pady=5)
        comp_text.insert('1.0', spec.get('competenza') or '' if spec else '')

        ttk.Label(dialog, text="Costo (MO):").grid(row=4, column=0, sticky='w', padx=10, pady=5)
        costo_var = ttk.Entry(dialog, width=40)
        costo_var.grid(row=4, column=1, sticky='ew', padx=10, pady=5)
        costo_var.insert(0, str(float(spec.get('costo') or 0)) if spec else "0")

        ttk.Label(dialog, text="Frequenza pagamento:").grid(row=5, column=0, sticky='w', padx=10, pady=5)
        freq_combo = ttk.Combobox(dialog, values=['giornaliera', 'settimanale', 'mensile'], state='readonly', width=38)
        freq_combo.grid(row=5, column=1, sticky='ew', padx=10, pady=5)
        freq_combo.set((spec.get('frequenza_pagamento') if spec else '') or 'mensile')

        ttk.Label(dialog, text="Banca collegata:").grid(row=6, column=0, sticky='w', padx=10, pady=5)
        bank_combo = ttk.Combobox(dialog, state='readonly', width=38)
        banks = self.get_property_banks(pg_id)
        bank_combo['values'] = [b['label'] for b in banks]
        bank_combo.grid(row=6, column=1, sticky='ew', padx=10, pady=5)
        current_bank_id = spec.get('banca_collegata') if spec else None
        if current_bank_id:
            for index, bank in enumerate(banks):
                if bank['id'] == current_bank_id:
                    bank_combo.current(index)
                    break

        servizio_var = tk.BooleanVar(value=bool(spec.get('in_servizio', 1)) if spec else True)
        ttk.Checkbutton(dialog, text="In servizio", variable=servizio_var).grid(row=7, column=1, sticky='w', padx=10, pady=5)

        def dec_value():
            raw = costo_var.get().strip()
            return Decimal(raw.replace(',', '.')) if raw else Decimal('0')

        def selected_bank_id():
            index = bank_combo.current()
            if index < 0 or index >= len(banks):
                return None
            return banks[index]['id']

        def save():
            try:
                costo = dec_value()
            except Exception:
                messagebox.showerror("Errore", "Costo MO non valido.")
                return
            data = {
                'pg_id': pg_id,
                'tipo': tipo_var.get().strip(),
                'nome': nome_var.get().strip(),
                'localita': loc_var.get().strip(),
                'competenza': comp_text.get('1.0', 'end-1c').strip(),
                'costo': costo,
                'banca_collegata': selected_bank_id(),
                'frequenza_pagamento': freq_combo.get().strip() or None,
                'in_servizio': int(servizio_var.get()),
                'fixed_expense_id': spec.get('fixed_expense_id') if spec else None,
            }
            cursor = self.db.cursor()
            try:
                if spec:
                    data['id'] = spec['id']
                    cursor.execute("""
                        UPDATE pc_specialisti
                        SET tipo=%(tipo)s, nome=%(nome)s, localita=%(localita)s,
                            competenza=%(competenza)s, costo=%(costo)s,
                            banca_collegata=%(banca_collegata)s,
                            frequenza_pagamento=%(frequenza_pagamento)s,
                            in_servizio=%(in_servizio)s,
                            fixed_expense_id=%(fixed_expense_id)s
                        WHERE id=%(id)s AND pg_id=%(pg_id)s
                    """, data)
                    spec_id = spec['id']
                else:
                    cursor.execute("""
                        INSERT INTO pc_specialisti
                            (pg_id, tipo, nome, localita, competenza, costo,
                             banca_collegata, frequenza_pagamento, in_servizio, fixed_expense_id)
                        VALUES
                            (%(pg_id)s, %(tipo)s, %(nome)s, %(localita)s, %(competenza)s, %(costo)s,
                             %(banca_collegata)s, %(frequenza_pagamento)s, %(in_servizio)s, %(fixed_expense_id)s)
                    """, data)
                    spec_id = cursor.lastrowid
                data['fixed_expense_id'] = self.sync_specialist_expense(cursor, pg_id, spec_id, data)
                cursor.execute(
                    "UPDATE pc_specialisti SET fixed_expense_id = %s WHERE id = %s AND pg_id = %s",
                    (data['fixed_expense_id'], spec_id, pg_id)
                )
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_specialist_list(pg_id)
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore specialista: {e}")

        ttk.Button(dialog, text="Salva", command=save).grid(row=8, column=0, pady=12)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=8, column=1, sticky='w', pady=12)

    def sync_specialist_expense(self, cursor, pg_id, spec_id, data):
        fixed_expense_id = data.get('fixed_expense_id')
        active = bool(data.get('in_servizio'))
        cost = data.get('costo') or Decimal('0')
        bank_id = data.get('banca_collegata')
        frequency = data.get('frequenza_pagamento')
        should_sync = active and cost > 0 and bank_id and frequency
        description = f"Specialista: {data.get('tipo') or 'Specialista'} - {data.get('nome') or f'ID {spec_id}'}"
        if should_sync:
            if fixed_expense_id:
                cursor.execute("""
                    UPDATE fixed_expenses
                    SET pg_id = %s, description = %s, amount = %s,
                        frequency = %s, source_bank_id = %s
                    WHERE id = %s AND pg_id = %s
                """, (pg_id, description, cost, frequency, bank_id, fixed_expense_id, pg_id))
                if cursor.rowcount == 0:
                    cursor.execute(
                        "SELECT id FROM fixed_expenses WHERE id = %s AND pg_id = %s",
                        (fixed_expense_id, pg_id)
                    )
                    if not cursor.fetchone():
                        fixed_expense_id = None
            if not fixed_expense_id:
                cursor.execute("""
                    INSERT INTO fixed_expenses
                        (pg_id, description, amount, frequency, source_bank_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (pg_id, description, cost, frequency, bank_id))
                fixed_expense_id = cursor.lastrowid
        elif fixed_expense_id:
            cursor.execute("DELETE FROM fixed_expenses WHERE id = %s AND pg_id = %s", (fixed_expense_id, pg_id))
            fixed_expense_id = None
        return fixed_expense_id

    def show_specialist_details_dialog(self, pg_id):
        selection = self.specialist_tree.selection()
        if not selection:
            return
        spec_id = self.specialist_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_specialisti WHERE id = %s AND pg_id = %s", (spec_id, pg_id))
            spec = cursor.fetchone()
            cursor.close()
            if not spec:
                return
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura specialista: {e}")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(spec.get('nome') or "Dettaglio specialista")
        dialog.geometry("700x520")
        dialog.transient(self.root)
        dialog.grab_set()

        info = ttk.LabelFrame(dialog, text="Dati specialista", padding=10)
        info.pack(fill='x', padx=10, pady=10)
        bank_text = self.get_property_bank_display(spec.get('banca_collegata'))
        rows = [
            ("Tipo", spec.get('tipo') or ''),
            ("Nome", spec.get('nome') or ''),
            ("Localita", spec.get('localita') or ''),
            ("Costo MO", f"{float(spec.get('costo') or 0):.2f}"),
            ("Frequenza pagamento", spec.get('frequenza_pagamento') or ''),
            ("Banca collegata", bank_text),
            ("In servizio", "Si" if spec.get('in_servizio', 1) else "No"),
        ]
        for i, (label, value) in enumerate(rows):
            ttk.Label(info, text=f"{label}:").grid(row=i // 2, column=(i % 2) * 2, sticky='w', padx=5, pady=3)
            ttk.Label(info, text=str(value), wraplength=260).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky='w', padx=5, pady=3)

        details = ttk.LabelFrame(dialog, text="Competenza", padding=10)
        details.pack(fill='both', expand=True, padx=10, pady=5)
        text = tk.Text(details, wrap='word', height=12)
        text.pack(side='left', fill='both', expand=True)
        detail_scroll = ttk.Scrollbar(details, orient='vertical', command=text.yview)
        detail_scroll.pack(side='right', fill='y')
        text.config(yscrollcommand=detail_scroll.set)
        text.insert('1.0', spec.get('competenza') or '')
        text.configure(state='disabled')
        ttk.Button(dialog, text="Chiudi", command=dialog.destroy).pack(pady=10)

    def refresh_scroll_list(self, pg_id):
        """Ricarica pergamene strutturate."""
        tree = getattr(self, 'scroll_tree', None)
        if not tree:
            return
        try:
            tree.delete(*tree.get_children())
            tree.tag_configure('oddrow', background='white')
            tree.tag_configure('evenrow', background='#f0f0f0')
            
            cursor = self.db.cursor()
            direction = 'DESC' if getattr(self, 'scroll_sort_reverse', False) else 'ASC'
            sort_column = getattr(self, 'scroll_sort_column', 'nome')
            if sort_column == 'tipo':
                order_sql = f"COALESCE(tipo, '') {direction}, COALESCE(nome, '') ASC, id ASC"
            elif sort_column == 'trasportata':
                order_sql = f"trasportata {direction}, COALESCE(nome, '') ASC, id ASC"
            else:
                order_sql = f"COALESCE(nome, '') {direction}, id ASC"
            cursor.execute(f"""
                SELECT *
                FROM pc_pergamene
                WHERE pg_id = %s
                ORDER BY {order_sql}
            """, (pg_id,))
            scrolls = cursor.fetchall()
            cursor.close()
            
            for i, scroll in enumerate(scrolls):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                nome = scroll.get('nome') or self.get_legacy_scroll_name(scroll)
                tree.insert('', 'end', values=(
                    nome,
                    scroll.get('tipo') or 'Altro',
                    scroll.get('livello') if scroll.get('livello') is not None else '',
                    scroll.get('lista_magica') or '',
                    "Si" if scroll.get('identificata') else "No",
                    "Si" if scroll.get('consumata') else "No",
                    "Si" if scroll.get('trasportata', 1) else "No",
                    scroll.get('collocazione') or '',
                    scroll.get('quantita') or 1,
                    f"{float(scroll.get('valore_mo') or 0):.2f}",
                ), tags=(scroll['id'], tag))
        except Exception as e:
            print(f"Errore refresh pergamene: {e}")

    def sort_scrolls_by(self, pg_id, column):
        if getattr(self, 'scroll_sort_column', None) == column:
            self.scroll_sort_reverse = not getattr(self, 'scroll_sort_reverse', False)
        else:
            self.scroll_sort_column = column
            self.scroll_sort_reverse = False
        self.refresh_scroll_list(pg_id)

    def get_legacy_scroll_name(self, scroll):
        text = (scroll.get('descrizione') or '').strip()
        if not text:
            return ''
        return text[:60] + ('...' if len(text) > 60 else '')

    def get_scroll_type_values(self):
        base_types = ["Incantesimo", "Protezione", "Mappa", "Documento", "Contratto", "Ricetta", "Rituale", "Altro"]
        values = list(base_types)
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT DISTINCT tipo
                FROM pc_pergamene
                WHERE tipo IS NOT NULL AND TRIM(tipo) <> ''
                ORDER BY tipo
            """)
            for row in cursor.fetchall():
                tipo = row.get('tipo')
                if tipo and tipo not in values:
                    values.append(tipo)
            cursor.close()
        except Exception as e:
            print(f"Errore caricamento tipi pergamene: {e}")
        return values

    def get_scroll_spell_catalog(self):
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT id, spell_name, spell_level, spell_list_type,
                       reversible, range_text, duration_text, effect_text, description
                FROM rule_spells
                ORDER BY spell_list_type, spell_level, spell_name
            """)
            spells = cursor.fetchall()
            cursor.close()
            result = [{'id': None, 'label': 'Nessun incantesimo collegato'}]
            for spell in spells:
                result.append({
                    **spell,
                    'label': f"L{spell.get('spell_level')} - {spell.get('spell_name')} ({spell.get('spell_list_type')})"
                })
            return result
        except Exception as e:
            print(f"Errore caricamento catalogo incantesimi per pergamene: {e}")
            return [{'id': None, 'label': 'Nessun incantesimo collegato'}]

    def get_selected_scroll_id(self):
        tree = getattr(self, 'scroll_tree', None)
        selection = tree.selection() if tree else ()
        if not selection:
            return None
        return tree.item(selection[0])['tags'][0]

    def add_scroll_dialog(self, pg_id):
        """Dialog aggiungi pergamena"""
        self._scroll_editor_dialog(pg_id)

    def edit_scroll_dialog(self, pg_id):
        """Dialog modifica pergamena"""
        scroll_id = self.get_selected_scroll_id()
        if not scroll_id:
            messagebox.showwarning("Attenzione", "Seleziona una pergamena!")
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_pergamene WHERE id = %s AND pg_id = %s", (scroll_id, pg_id))
            scroll = cursor.fetchone()
            cursor.close()
            if not scroll:
                messagebox.showerror("Errore", "Pergamena non trovata.")
                return
            self._scroll_editor_dialog(pg_id, scroll)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")

    def _scroll_editor_dialog(self, pg_id, scroll=None):
        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        is_edit = scroll is not None
        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Pergamena" if is_edit else "Aggiungi Pergamena")
        dialog.geometry("760x720")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)

        spells = self.get_scroll_spell_catalog()

        ttk.Label(dialog, text="Nome:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        nome_var = ttk.Entry(dialog, width=62)
        nome_var.grid(row=0, column=1, sticky='ew', padx=10, pady=5)
        nome_var.insert(0, (scroll.get('nome') if scroll else '') or '')

        ttk.Label(dialog, text="Tipo:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        tipo_var = ttk.Combobox(dialog, values=self.get_scroll_type_values(), width=35)
        tipo_var.grid(row=1, column=1, sticky='w', padx=10, pady=5)
        tipo_var.set((scroll.get('tipo') if scroll else '') or ('Altro' if scroll else 'Incantesimo'))

        ttk.Label(dialog, text="Incantesimo collegato:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        spell_combo = ttk.Combobox(dialog, values=[s['label'] for s in spells], state='readonly', width=58)
        spell_combo.grid(row=2, column=1, sticky='ew', padx=10, pady=5)
        current_spell_id = scroll.get('spell_id') if scroll else None
        spell_combo.current(0)
        for index, spell in enumerate(spells):
            if spell['id'] == current_spell_id:
                spell_combo.current(index)
                break

        ttk.Label(dialog, text="Livello:").grid(row=3, column=0, sticky='w', padx=10, pady=5)
        level_var = ttk.Spinbox(dialog, from_=0, to=9, width=10)
        level_var.grid(row=3, column=1, sticky='w', padx=10, pady=5)
        level_var.set(scroll.get('livello') if scroll and scroll.get('livello') is not None else 0)

        ttk.Label(dialog, text="Lista magica:").grid(row=4, column=0, sticky='w', padx=10, pady=5)
        list_var = ttk.Combobox(dialog, values=['ARCANA', 'DIVINA', 'DRUIDICA', 'NON_MAGICA', 'ALTRO'], width=22)
        list_var.grid(row=4, column=1, sticky='w', padx=10, pady=5)
        list_var.set((scroll.get('lista_magica') if scroll else '') or ('NON_MAGICA' if scroll else 'ARCANA'))

        flags_frame = ttk.Frame(dialog)
        flags_frame.grid(row=5, column=1, sticky='w', padx=10, pady=5)
        identificata_var = tk.BooleanVar(value=bool(scroll.get('identificata')) if scroll else False)
        consumata_var = tk.BooleanVar(value=bool(scroll.get('consumata')) if scroll else False)
        trasportata_var = tk.BooleanVar(value=bool(scroll.get('trasportata', 1)) if scroll else True)
        ttk.Checkbutton(flags_frame, text="Identificata", variable=identificata_var).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(flags_frame, text="Consumata", variable=consumata_var).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(flags_frame, text="Trasportata", variable=trasportata_var).pack(side='left')

        ttk.Label(dialog, text="Collocazione:").grid(row=6, column=0, sticky='w', padx=10, pady=5)
        collocazione_var = ttk.Entry(dialog, width=62)
        collocazione_var.grid(row=6, column=1, sticky='ew', padx=10, pady=5)
        collocazione_var.insert(0, (scroll.get('collocazione') if scroll else '') or '')

        ttk.Label(dialog, text="Quantita:").grid(row=7, column=0, sticky='w', padx=10, pady=5)
        qty_var = ttk.Spinbox(dialog, from_=1, to=999, width=10)
        qty_var.grid(row=7, column=1, sticky='w', padx=10, pady=5)
        qty_var.set(scroll.get('quantita') if scroll and scroll.get('quantita') else 1)

        ttk.Label(dialog, text="Valore MO:").grid(row=8, column=0, sticky='w', padx=10, pady=5)
        value_var = ttk.Entry(dialog, width=16)
        value_var.grid(row=8, column=1, sticky='w', padx=10, pady=5)
        value_var.insert(0, str(float(scroll.get('valore_mo') or 0)) if scroll else "0")

        ttk.Label(dialog, text="Descrizione:").grid(row=9, column=0, sticky='nw', padx=10, pady=5)
        desc_text = tk.Text(dialog, width=68, height=8)
        desc_text.grid(row=9, column=1, sticky='nsew', padx=10, pady=5)
        desc_text.insert('1.0', (scroll.get('descrizione') if scroll else '') or '')

        dm_text = None
        if is_dm:
            ttk.Label(dialog, text="Note DM:").grid(row=10, column=0, sticky='nw', padx=10, pady=5)
            dm_text = tk.Text(dialog, width=68, height=5)
            dm_text.grid(row=10, column=1, sticky='nsew', padx=10, pady=5)
            dm_text.insert('1.0', (scroll.get('note_dm') if scroll else '') or '')

        def selected_spell():
            index = spell_combo.current()
            if index < 0 or index >= len(spells):
                return None
            spell = spells[index]
            return spell if spell.get('id') else None

        def autofill_spell_fields(event=None):
            spell = selected_spell()
            if not spell:
                return
            level_var.set(spell.get('spell_level') or 0)
            list_var.set(spell.get('spell_list_type') or 'ARCANA')
            if not nome_var.get().strip():
                nome_var.insert(0, spell.get('spell_name') or '')
            if not desc_text.get('1.0', 'end-1c').strip():
                desc_text.insert('1.0', spell.get('description') or spell.get('effect_text') or '')

        spell_combo.bind('<<ComboboxSelected>>', autofill_spell_fields)

        def decimal_value(raw):
            raw = (raw or '').strip()
            return Decimal(raw.replace(',', '.')) if raw else Decimal('0')

        def save():
            spell = selected_spell()
            nome = nome_var.get().strip()
            descrizione = desc_text.get('1.0', 'end-1c').strip()
            if not nome and not descrizione:
                messagebox.showerror("Errore", "Inserisci almeno Nome oppure Descrizione.")
                return
            try:
                data = {
                    'pg_id': pg_id,
                    'nome': nome,
                    'tipo': tipo_var.get().strip() or 'Altro',
                    'spell_id': spell.get('id') if spell else None,
                    'livello': int(level_var.get() or 0),
                    'lista_magica': (list_var.get().strip() or 'ALTRO').upper(),
                    'identificata': int(identificata_var.get()),
                    'consumata': int(consumata_var.get()),
                    'trasportata': int(trasportata_var.get()),
                    'collocazione': collocazione_var.get().strip(),
                    'quantita': max(1, int(qty_var.get() or 1)),
                    'valore_mo': decimal_value(value_var.get()),
                    'descrizione': descrizione,
                    'note_dm': dm_text.get('1.0', 'end-1c').strip() if is_dm and dm_text else (scroll.get('note_dm') if scroll else None),
                }
            except Exception:
                messagebox.showerror("Errore", "Quantita, livello o valore MO non validi.")
                return
            cursor = self.db.cursor()
            try:
                if is_edit:
                    data['id'] = scroll['id']
                    cursor.execute("""
                        UPDATE pc_pergamene
                        SET nome=%(nome)s, tipo=%(tipo)s, spell_id=%(spell_id)s,
                            livello=%(livello)s, lista_magica=%(lista_magica)s,
                            identificata=%(identificata)s, consumata=%(consumata)s,
                            trasportata=%(trasportata)s, collocazione=%(collocazione)s,
                            quantita=%(quantita)s, valore_mo=%(valore_mo)s,
                            descrizione=%(descrizione)s, note_dm=%(note_dm)s
                        WHERE id=%(id)s AND pg_id=%(pg_id)s
                    """, data)
                else:
                    cursor.execute("""
                        INSERT INTO pc_pergamene
                            (pg_id, nome, tipo, spell_id, livello, lista_magica,
                             identificata, consumata, trasportata, collocazione,
                             quantita, valore_mo, descrizione, note_dm)
                        VALUES
                            (%(pg_id)s, %(nome)s, %(tipo)s, %(spell_id)s, %(livello)s, %(lista_magica)s,
                             %(identificata)s, %(consumata)s, %(trasportata)s, %(collocazione)s,
                             %(quantita)s, %(valore_mo)s, %(descrizione)s, %(note_dm)s)
                    """, data)
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_scroll_list(pg_id)
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore salvataggio pergamena: {e}")

        button_row = 11 if is_dm else 10
        ttk.Button(dialog, text="Salva", command=save).grid(row=button_row, column=0, pady=12)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=button_row, column=1, sticky='w', pady=12)

    def show_scroll_details_dialog(self, pg_id):
        scroll_id = self.get_selected_scroll_id()
        if not scroll_id:
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT p.*, rs.spell_name, rs.spell_level, rs.spell_list_type,
                       rs.reversible, rs.range_text, rs.duration_text,
                       rs.effect_text, rs.description AS spell_description
                FROM pc_pergamene p
                LEFT JOIN rule_spells rs ON p.spell_id = rs.id
                WHERE p.id = %s AND p.pg_id = %s
            """, (scroll_id, pg_id))
            scroll = cursor.fetchone()
            cursor.close()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura pergamena: {e}")
            return
        if not scroll:
            return
        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        dialog = tk.Toplevel(self.root)
        dialog.title(scroll.get('nome') or self.get_legacy_scroll_name(scroll) or "Dettaglio pergamena")
        dialog.geometry("760x620")
        dialog.transient(self.root)
        dialog.grab_set()

        info = ttk.LabelFrame(dialog, text="Dati pergamena", padding=10)
        info.pack(fill='x', padx=10, pady=10)
        spell_label = ''
        if scroll.get('spell_id'):
            spell_label = f"L{scroll.get('spell_level')} - {scroll.get('spell_name')} ({scroll.get('spell_list_type')})"
        rows = [
            ("Nome", scroll.get('nome') or self.get_legacy_scroll_name(scroll)),
            ("Tipo", scroll.get('tipo') or 'Altro'),
            ("Incantesimo", spell_label),
            ("Livello", scroll.get('livello') if scroll.get('livello') is not None else ''),
            ("Lista magica", scroll.get('lista_magica') or ''),
            ("Identificata", "Si" if scroll.get('identificata') else "No"),
            ("Consumata", "Si" if scroll.get('consumata') else "No"),
            ("Trasportata", "Si" if scroll.get('trasportata', 1) else "No"),
            ("Collocazione", scroll.get('collocazione') or ''),
            ("Quantita", scroll.get('quantita') or 1),
            ("Valore MO", f"{float(scroll.get('valore_mo') or 0):.2f}"),
        ]
        for i, (label, value) in enumerate(rows):
            ttk.Label(info, text=f"{label}:").grid(row=i // 2, column=(i % 2) * 2, sticky='w', padx=5, pady=3)
            ttk.Label(info, text=str(value), wraplength=250).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky='w', padx=5, pady=3)

        details = ttk.LabelFrame(dialog, text="Descrizione e dettagli", padding=10)
        details.pack(fill='both', expand=True, padx=10, pady=5)
        text = tk.Text(details, wrap='word', height=18)
        text.pack(side='left', fill='both', expand=True)
        detail_scroll = ttk.Scrollbar(details, orient='vertical', command=text.yview)
        detail_scroll.pack(side='right', fill='y')
        text.config(yscrollcommand=detail_scroll.set)
        full_text = f"Descrizione:\n{scroll.get('descrizione') or ''}"
        if scroll.get('spell_id'):
            full_text += (
                f"\n\nDati incantesimo:\n"
                f"Raggio: {scroll.get('range_text') or ''}\n"
                f"Durata: {scroll.get('duration_text') or ''}\n"
                f"Reversibile: {'Si' if scroll.get('reversible') else 'No'}\n\n"
                f"Effetto:\n{scroll.get('effect_text') or ''}\n\n"
                f"Descrizione incantesimo:\n{scroll.get('spell_description') or ''}"
            )
        if is_dm:
            full_text += f"\n\nNote DM:\n{scroll.get('note_dm') or ''}"
        text.insert('1.0', full_text)
        text.configure(state='disabled')
        ttk.Button(dialog, text="Chiudi", command=dialog.destroy).pack(pady=10)

    def delete_scroll(self, pg_id):
        """Elimina pergamena"""
        scroll_id = self.get_selected_scroll_id()
        if not scroll_id:
            return
        if not messagebox.askyesno("Conferma", "Eliminare la pergamena selezionata?"):
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_pergamene WHERE id = %s AND pg_id = %s", (scroll_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_scroll_list(pg_id)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")

    def create_character_special_actions_tab(self, notebook, pg_id, character):
        """Tab Azioni Speciali strutturato."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Azioni Speciali")
        is_dm = self.current_user and self.current_user.get('role') == 'DM'

        main_frame = ttk.LabelFrame(tab, text="Azioni e Capacita Speciali", padding=10)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.action_sort_column = getattr(self, 'action_sort_column', 'azione')
        self.action_sort_reverse = getattr(self, 'action_sort_reverse', False)
        columns = ('azione', 'tipo', 'origine', 'stato', 'usi_limite', 'visibile') if is_dm else ('azione', 'tipo', 'origine', 'stato', 'usi_limite')
        self.action_tree = ttk.Treeview(main_frame, columns=columns, show='headings', height=12)
        specs = {
            'azione': ('Azione/Capacita', 220),
            'tipo': ('Tipo', 140),
            'origine': ('Origine', 150),
            'stato': ('Stato', 110),
            'usi_limite': ('Usi/Limite', 160),
            'visibile': ('Visibile', 80),
        }
        for col, (label, width) in specs.items():
            if col not in columns:
                continue
            if col in ('azione', 'tipo', 'stato'):
                self.action_tree.heading(col, text=label, command=lambda c=col: self.sort_actions_by(pg_id, c))
            else:
                self.action_tree.heading(col, text=label)
            self.action_tree.column(col, width=width, minwidth=50, stretch=False)
        self.action_tree.grid(row=0, column=0, sticky='nsew')

        action_v = ttk.Scrollbar(main_frame, orient='vertical', command=self.action_tree.yview)
        action_v.grid(row=0, column=1, sticky='ns')
        action_h = ttk.Scrollbar(main_frame, orient='horizontal', command=self.action_tree.xview)
        action_h.grid(row=1, column=0, sticky='ew')
        self.action_tree.config(yscrollcommand=action_v.set, xscrollcommand=action_h.set)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)
        self.action_tree.bind('<Double-Button-1>', lambda e: self.show_action_details_dialog(pg_id))

        def scroll_action_table(event):
            delta = -1 if getattr(event, 'delta', 0) > 0 else 1
            if getattr(event, 'num', None) == 4:
                delta = -1
            elif getattr(event, 'num', None) == 5:
                delta = 1
            self.action_tree.yview_scroll(delta, "units")
            return "break"

        self.action_tree.bind("<MouseWheel>", scroll_action_table, add="+")
        self.action_tree.bind("<Button-4>", scroll_action_table, add="+")
        self.action_tree.bind("<Button-5>", scroll_action_table, add="+")

        self.refresh_action_list(pg_id)

        if not is_dm:
            return

        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill='x', padx=10, pady=5)
        ttk.Button(btn_frame, text="Aggiungi", command=lambda: self.add_action_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Modifica", command=lambda: self.edit_action_dialog(pg_id)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Elimina", command=lambda: self.delete_action(pg_id)).pack(side='left', padx=5)

    def sort_actions_by(self, pg_id, column):
        if getattr(self, 'action_sort_column', None) == column:
            self.action_sort_reverse = not getattr(self, 'action_sort_reverse', False)
        else:
            self.action_sort_column = column
            self.action_sort_reverse = False
        self.refresh_action_list(pg_id)

    def get_selected_action_id(self):
        tree = getattr(self, 'action_tree', None)
        selection = tree.selection() if tree else ()
        if not selection:
            return None
        return tree.item(selection[0])['tags'][0]

    def get_action_type_values(self):
        base_types = [
            "Dote", "Skill", "Tecnica", "Privilegio di classe",
            "Dono magico", "Retaggio", "Maledizione", "Addestramento", "Altro"
        ]
        values = list(base_types)
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT DISTINCT tipo
                FROM pc_azioni_speciali
                WHERE tipo IS NOT NULL AND TRIM(tipo) <> ''
                ORDER BY tipo
            """)
            for row in cursor.fetchall():
                tipo = row.get('tipo')
                if tipo and tipo not in values:
                    values.append(tipo)
            cursor.close()
        except Exception as e:
            print(f"Errore caricamento tipi azioni speciali: {e}")
        return values

    def refresh_action_list(self, pg_id):
        """Ricarica azioni/capacita speciali strutturate."""
        tree = getattr(self, 'action_tree', None)
        if not tree:
            return
        try:
            tree.delete(*tree.get_children())
            tree.tag_configure('oddrow', background='white')
            tree.tag_configure('evenrow', background='#f0f0f0')
            is_dm = self.current_user and self.current_user.get('role') == 'DM'
            direction = 'DESC' if getattr(self, 'action_sort_reverse', False) else 'ASC'
            sort_column = getattr(self, 'action_sort_column', 'azione')
            if sort_column == 'tipo':
                order_sql = f"COALESCE(tipo, '') {direction}, COALESCE(azione, '') ASC, id ASC"
            elif sort_column == 'stato':
                order_sql = f"COALESCE(stato, '') {direction}, COALESCE(azione, '') ASC, id ASC"
            else:
                order_sql = f"COALESCE(azione, '') {direction}, id ASC"
            query = f"SELECT * FROM pc_azioni_speciali WHERE pg_id = %s"
            params = [pg_id]
            if not is_dm:
                query += " AND visible_to_player = 1"
            query += f" ORDER BY {order_sql}"
            cursor = self.db.cursor()
            cursor.execute(query, params)
            actions = cursor.fetchall()
            cursor.close()

            for i, action in enumerate(actions):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                values = [
                    action.get('azione') or '',
                    action.get('tipo') or 'Altro',
                    action.get('origine') or '',
                    action.get('stato') or 'Attiva',
                    action.get('usi_limite') or '',
                ]
                if is_dm:
                    values.append("Si" if action.get('visible_to_player', 1) else "No")
                tree.insert('', 'end', values=values, tags=(action['id'], tag))
        except Exception as e:
            print(f"Errore refresh azioni: {e}")

    def add_action_dialog(self, pg_id):
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' aggiungere azioni speciali.")
            return
        self._action_editor_dialog(pg_id)

    def edit_action_dialog(self, pg_id):
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' modificare azioni speciali.")
            return
        action_id = self.get_selected_action_id()
        if not action_id:
            messagebox.showwarning("Attenzione", "Seleziona un'azione speciale.")
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_azioni_speciali WHERE id = %s AND pg_id = %s", (action_id, pg_id))
            action = cursor.fetchone()
            cursor.close()
            if not action:
                messagebox.showerror("Errore", "Azione speciale non trovata.")
                return
            self._action_editor_dialog(pg_id, action)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura azione speciale: {e}")

    def _action_editor_dialog(self, pg_id, action=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Azione Speciale" if action else "Aggiungi Azione Speciale")
        dialog.geometry("760x650")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)

        ttk.Label(dialog, text="Azione/Capacita:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        action_entry = ttk.Entry(dialog, width=62)
        action_entry.grid(row=0, column=1, sticky='ew', padx=10, pady=5)
        action_entry.insert(0, action.get('azione') or '' if action else '')

        ttk.Label(dialog, text="Tipo:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        type_combo = ttk.Combobox(dialog, values=self.get_action_type_values(), width=35)
        type_combo.grid(row=1, column=1, sticky='w', padx=10, pady=5)
        type_combo.set((action.get('tipo') if action else '') or 'Altro')

        ttk.Label(dialog, text="Origine:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        origin_combo = ttk.Combobox(dialog, values=[
            'Classe', 'Razza', 'Addestramento', 'Maestro', 'Oggetto',
            'Evento di campagna', 'Ricompensa DM', 'Retaggio', 'Altro'
        ], width=35)
        origin_combo.grid(row=2, column=1, sticky='w', padx=10, pady=5)
        origin_combo.set((action.get('origine') if action else '') or '')

        ttk.Label(dialog, text="Stato:").grid(row=3, column=0, sticky='w', padx=10, pady=5)
        state_combo = ttk.Combobox(dialog, values=['Attiva', 'Dormiente', 'Temporanea', 'Persa', 'Da confermare'], state='readonly', width=33)
        state_combo.grid(row=3, column=1, sticky='w', padx=10, pady=5)
        state_combo.set((action.get('stato') if action else '') or 'Attiva')

        ttk.Label(dialog, text="Usi/Limite:").grid(row=4, column=0, sticky='w', padx=10, pady=5)
        uses_entry = ttk.Entry(dialog, width=62)
        uses_entry.grid(row=4, column=1, sticky='ew', padx=10, pady=5)
        uses_entry.insert(0, action.get('usi_limite') or '' if action else '')

        visible_var = tk.BooleanVar(value=bool(action.get('visible_to_player', 1)) if action else True)
        ttk.Checkbutton(dialog, text="Visibile al giocatore", variable=visible_var).grid(row=5, column=1, sticky='w', padx=10, pady=5)

        ttk.Label(dialog, text="Effetto:").grid(row=6, column=0, sticky='nw', padx=10, pady=5)
        effect_text = tk.Text(dialog, width=68, height=8)
        effect_text.grid(row=6, column=1, sticky='nsew', padx=10, pady=5)
        effect_text.insert('1.0', action.get('effetto') or '' if action else '')

        ttk.Label(dialog, text="Note:").grid(row=7, column=0, sticky='nw', padx=10, pady=5)
        notes_text = tk.Text(dialog, width=68, height=5)
        notes_text.grid(row=7, column=1, sticky='nsew', padx=10, pady=5)
        notes_text.insert('1.0', action.get('note') or '' if action else '')

        ttk.Label(dialog, text="Note DM:").grid(row=8, column=0, sticky='nw', padx=10, pady=5)
        dm_text = tk.Text(dialog, width=68, height=5)
        dm_text.grid(row=8, column=1, sticky='nsew', padx=10, pady=5)
        dm_text.insert('1.0', action.get('note_dm') or '' if action else '')

        def save():
            name = action_entry.get().strip()
            if not name:
                messagebox.showerror("Errore", "Azione/Capacita obbligatoria.")
                return
            data = {
                'pg_id': pg_id,
                'azione': name,
                'tipo': type_combo.get().strip() or 'Altro',
                'origine': origin_combo.get().strip(),
                'stato': state_combo.get().strip() or 'Attiva',
                'effetto': effect_text.get('1.0', 'end-1c').strip(),
                'usi_limite': uses_entry.get().strip(),
                'visible_to_player': int(visible_var.get()),
                'note': notes_text.get('1.0', 'end-1c').strip(),
                'note_dm': dm_text.get('1.0', 'end-1c').strip(),
            }
            cursor = self.db.cursor()
            try:
                if action:
                    data['id'] = action['id']
                    cursor.execute("""
                        UPDATE pc_azioni_speciali
                        SET azione=%(azione)s, tipo=%(tipo)s, origine=%(origine)s,
                            stato=%(stato)s, effetto=%(effetto)s, usi_limite=%(usi_limite)s,
                            visible_to_player=%(visible_to_player)s, note=%(note)s, note_dm=%(note_dm)s
                        WHERE id=%(id)s AND pg_id=%(pg_id)s
                    """, data)
                else:
                    cursor.execute("""
                        INSERT INTO pc_azioni_speciali
                            (pg_id, azione, tipo, origine, stato, effetto,
                             usi_limite, visible_to_player, note, note_dm)
                        VALUES
                            (%(pg_id)s, %(azione)s, %(tipo)s, %(origine)s, %(stato)s, %(effetto)s,
                             %(usi_limite)s, %(visible_to_player)s, %(note)s, %(note_dm)s)
                    """, data)
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_action_list(pg_id)
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore salvataggio azione speciale: {e}")

        ttk.Button(dialog, text="Salva", command=save).grid(row=9, column=0, pady=12)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=9, column=1, sticky='w', pady=12)

    def show_action_details_dialog(self, pg_id):
        action_id = self.get_selected_action_id()
        if not action_id:
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_azioni_speciali WHERE id = %s AND pg_id = %s", (action_id, pg_id))
            action = cursor.fetchone()
            cursor.close()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura azione speciale: {e}")
            return
        if not action:
            return
        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        if not is_dm and not action.get('visible_to_player', 1):
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(action.get('azione') or "Dettaglio azione speciale")
        dialog.geometry("740x560")
        dialog.transient(self.root)
        dialog.grab_set()

        info = ttk.LabelFrame(dialog, text="Dati", padding=10)
        info.pack(fill='x', padx=10, pady=10)
        rows = [
            ("Azione/Capacita", action.get('azione') or ''),
            ("Tipo", action.get('tipo') or 'Altro'),
            ("Origine", action.get('origine') or ''),
            ("Stato", action.get('stato') or 'Attiva'),
            ("Usi/Limite", action.get('usi_limite') or ''),
            ("Visibile al giocatore", "Si" if action.get('visible_to_player', 1) else "No"),
        ]
        for i, (label, value) in enumerate(rows):
            ttk.Label(info, text=f"{label}:").grid(row=i // 2, column=(i % 2) * 2, sticky='w', padx=5, pady=3)
            ttk.Label(info, text=str(value), wraplength=250).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky='w', padx=5, pady=3)

        details = ttk.LabelFrame(dialog, text="Effetto e note", padding=10)
        details.pack(fill='both', expand=True, padx=10, pady=5)
        text = tk.Text(details, wrap='word', height=16)
        text.pack(side='left', fill='both', expand=True)
        detail_scroll = ttk.Scrollbar(details, orient='vertical', command=text.yview)
        detail_scroll.pack(side='right', fill='y')
        text.config(yscrollcommand=detail_scroll.set)
        full_text = f"Effetto:\n{action.get('effetto') or ''}\n\nNote:\n{action.get('note') or ''}"
        if is_dm:
            full_text += f"\n\nNote DM:\n{action.get('note_dm') or ''}"
        text.insert('1.0', full_text)
        text.configure(state='disabled')
        ttk.Button(dialog, text="Chiudi", command=dialog.destroy).pack(pady=10)

    def delete_action(self, pg_id):
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' eliminare azioni speciali.")
            return
        action_id = self.get_selected_action_id()
        if not action_id:
            return
        if not messagebox.askyesno("Conferma", "Eliminare l'azione/capacita selezionata?"):
            return
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM pc_azioni_speciali WHERE id = %s AND pg_id = %s", (action_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_action_list(pg_id)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore eliminazione azione speciale: {e}")

    def check_nuovo_diario(self):
        """Controlla se esiste una nuova versione del diario su GitHub."""
        VERSION_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/diario_version.txt"
        try:
            versione_locale = self.current_user.get('diario_version', "0.0.0")

            response = requests.get(VERSION_URL, timeout=3)
            response.raise_for_status()
            ultima_versione_online = response.text.strip()

            return self._is_remote_version_newer(ultima_versione_online, versione_locale)

        except Exception:
            return False

    def _parse_version_tuple(self, version):
        """Converte una versione tipo 0.2.4 in tupla numerica confrontabile."""
        try:
            parts = re.findall(r"\d+", str(version or "0.0.0"))
            return tuple(int(part) for part in parts) if parts else (0,)
        except Exception:
            return (0,)

    def _is_remote_version_newer(self, remote_version, local_version):
        """True solo se la versione remota e' maggiore della locale."""
        remote = self._parse_version_tuple(remote_version)
        local = self._parse_version_tuple(local_version)
        max_len = max(len(remote), len(local))
        remote += (0,) * (max_len - len(remote))
        local += (0,) * (max_len - len(local))
        return remote > local
    
    def download_diary(self):
        """Scarica il diario della campagna"""
        try:
            VERSION_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/diario_version.txt"
            PDF_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/Diario_Campagna.pdf"
            
            versione_locale = self.current_user.get('diario_version', '0.0.0')
            
            response = requests.get(VERSION_URL, timeout=5)
            response.raise_for_status()
            ultima_versione = response.text.strip()
            
            if not self._is_remote_version_newer(ultima_versione, versione_locale):
                messagebox.showinfo("Diario Aggiornato", 
                                  f"Hai già l'ultima versione del diario ({versione_locale})")
                return
            
            if not messagebox.askyesno("Nuovo Diario Disponibile", 
                                      f"Nuova versione disponibile: {ultima_versione}\n"
                                      f"Versione attuale: {versione_locale}\n\n"
                                      f"Scaricare il diario?"):
                return  # L'utente ha cliccato "No"
            
            # Scarica PDF
            r = requests.get(PDF_URL, stream=True, timeout=30)
            r.raise_for_status()
            
            filename = "Diario_Campagna.pdf"
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Aggiorna versione nel DB
            cursor = self.db.cursor()
            cursor.execute("UPDATE users SET diario_version = %s WHERE id = %s",
                         (ultima_versione, self.current_user['id']))
            self.db.commit()
            
            self.current_user['diario_version'] = ultima_versione
            
            # Aggiorna interfaccia
            self.stop_diario_blink()
            if hasattr(self, 'diario_button') and self.diario_button.winfo_exists():
                self.diario_button.configure(text="📘 Diario")
            
            print("Diario scaricato con successo!")
            messagebox.showinfo("Successo", f"Diario scaricato: {filename}")
            
        except Exception as e:
            print(f"Errore nel download del diario: {e}")
            messagebox.showerror("Errore", f"Errore download diario: {e}")


    def start_diario_blink(self):
        """Avvia l'effetto lampeggio per il pulsante del diario"""
        self.blink_state = True
        self.blink_counter = 0
        self.blink_max = 100  # Numero molto alto per lampeggiare a lungo
        self.blink_diario()

    def blink_diario(self):
        """Gestisce l'animazione di lampeggio - versione con tk.Button"""
        if not hasattr(self, 'diario_button') or not self.diario_button.winfo_exists():
            return
        
        try:
            if self.blink_state:
                # Stato "acceso" - sfondo giallo, testo rosso in grassetto
                self.diario_button.configure(
                    bg='yellow', 
                    fg='red', 
                    font=('Arial', 9, 'bold')
                )
            else:
                # Stato "spento" - colori normali
                self.diario_button.configure(
                    bg='SystemButtonFace', 
                    fg='black', 
                    font=('Arial', 9)
                )
            
            self.blink_state = not self.blink_state
            self.blink_counter += 1
            
            # Continua il lampeggio finché c'è nuova versione
            if self.blink_counter < self.blink_max and self.diario_has_new_version:
                self.root.after(500, self.blink_diario)  # Lampeggio ogni 500ms
        except Exception as e:
            print(f"Errore nel lampeggio: {e}")

    def stop_diario_blink(self):
        """Ferma l'effetto lampeggio e ripristina il testo normale"""
        self.diario_has_new_version = False
        if hasattr(self, 'diario_button') and self.diario_button.winfo_exists():
            try:
                # Ripristina lo stile normale
                self.diario_button.configure(
                    bg='SystemButtonFace', 
                    fg='black', 
                    font=('Arial', 9)
                )
            except Exception as e:
                print(f"Errore nel fermare il lampeggio: {e}")
    
    def show_welcome_content(self):
        """Mostra il contenuto di benvenuto con banner notifiche - VERSIONE MODIFICATA"""
        self.clear_content()
        
        welcome = ttk.Label(self.content_frame, 
                           text="🎲 Benvenuto nel D&D Tool", 
                           style='Title.TLabel')
        welcome.pack(pady=10)
        
        # 🔥 BANNER NOTIFICHE SEMPLICE
        cursor = self.db.cursor()
        
        if self.current_user['role'] == 'DM':
            # Conta richieste di vendita
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM bank_items 
                WHERE status = 'IN_VALUTAZIONE' AND dm_notified = FALSE
            """)
            result = cursor.fetchone()
            
            if result and result['count'] > 0:
                notification_frame = ttk.Frame(self.content_frame, relief='raised', borderwidth=2)
                notification_frame.pack(fill='x', padx=20, pady=10)
                
                ttk.Label(notification_frame, 
                         text=f"⭐ Hai {result['count']} richiesta(e) di vendita in attesa!",
                         font=('Arial', 10, 'bold'),
                         foreground='red').pack(pady=5)
                
                ttk.Button(notification_frame, 
                          text="📋 Vedi tutte le richieste",
                          command=self.show_all_sale_requests,
                          width=25).pack(pady=5)
        else:
            # Conta notifiche giocatore
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM bank_items bi
                JOIN player_characters pc ON bi.pg_id = pc.id
                WHERE pc.user_id = %s 
                AND (
                    (bi.status = 'RIFIUTATO' AND bi.player_notified = FALSE) OR
                    (bi.status = 'IN_VALUTAZIONE' AND EXISTS (
                        SELECT 1 FROM bank_item_evaluations 
                        WHERE item_id = bi.id AND evaluator_role = 'DM'
                    ) AND bi.player_notified = FALSE)
                )
            """, (self.current_user['id'],))
            
            result = cursor.fetchone()
            
            if result and result['count'] > 0:
                notification_frame = ttk.Frame(self.content_frame, relief='raised', borderwidth=2)
                notification_frame.pack(fill='x', padx=20, pady=10)
                
                ttk.Label(notification_frame, 
                         text=f"⭐ Hai {result['count']} notifica(e) non lette!",
                         font=('Arial', 10, 'bold'),
                         foreground='blue').pack(pady=5)
                
                ttk.Button(notification_frame, 
                          text="📋 Vedi le tue notifiche",
                          command=self.show_player_notifications_simple,
                          width=25).pack(pady=5)
        
        cursor.close()
        
        # Versione del software
        version_label = ttk.Label(self.content_frame,
                                 text=f"Versione {__VERSION__}",
                                 style='Info.TLabel',
                                 font=('Arial', 10, 'italic'))
        version_label.pack(pady=(0, 10))
        
        info = ttk.Label(self.content_frame,
                        text=f"Utente: {self.current_user['username']}\n"
                             f"Ruolo: {self.current_user['role']}\n\n"
                             f"Data di Gioco: {self.convert_date_to_ded_format(self.game_date)}",
                        style='Info.TLabel')
        info.pack(pady=20)
        
        # Container per le due colonne
        columns_container = ttk.Frame(self.content_frame)
        columns_container.pack(pady=10, padx=20, fill='both', expand=True)
        
        try:
            cursor = self.db.cursor()
            
            # 🔹 COLONNA SINISTRA - BANCHE
            banks_frame = ttk.LabelFrame(columns_container, text="🏦 Dettaglio Banche", padding=10)
            banks_frame.pack(side='left', fill='both', expand=True, padx=(0, 10))
            
            if self.current_user['role'] == 'DM':
                cursor.execute("""
                    SELECT name, current_balance 
                    FROM banks 
                    ORDER BY name ASC
                """)
            else:
                cursor.execute("""
                    SELECT b.name, b.current_balance 
                    FROM banks b
                    LEFT JOIN player_characters pc ON b.pg_id = pc.id
                    WHERE pc.user_id = %s
                    ORDER BY b.name ASC
                """, (self.current_user['id'],))
            
            banks = cursor.fetchall()
            
            if banks:
                # Frame scrollabile per le banche
                banks_canvas = tk.Canvas(banks_frame, height=200)
                banks_scrollbar = ttk.Scrollbar(banks_frame, orient="vertical", command=banks_canvas.yview)
                banks_scrollable_frame = ttk.Frame(banks_canvas)
                
                banks_scrollable_frame.bind(
                    "<Configure>",
                    lambda e: banks_canvas.configure(scrollregion=banks_canvas.bbox("all"))
                )
                
                banks_canvas.create_window((0, 0), window=banks_scrollable_frame, anchor="nw")
                banks_canvas.configure(yscrollcommand=banks_scrollbar.set)
                
                for bank in banks:
                    bank_name = bank['name']
                    bank_balance = float(bank['current_balance'])
                    ttk.Label(banks_scrollable_frame, 
                             text=f"• {bank_name}: {bank_balance:.2f} MO",
                             font=('Arial', 9)).pack(anchor='w', padx=5, pady=2)
                
                banks_canvas.pack(side="left", fill="both", expand=True)
                banks_scrollbar.pack(side="right", fill="y")
            else:
                ttk.Label(banks_frame, text="Nessuna banca disponibile").pack(pady=5)
            
            # 🔹 COLONNA DESTRA - SEGUACI
            followers_frame = ttk.LabelFrame(columns_container, text="🛡️ Elenco Seguaci", padding=10)
            followers_frame.pack(side='right', fill='both', expand=True, padx=(10, 0))
            
            if self.current_user['role'] == 'DM':
                cursor.execute("""
                    SELECT f.name, f.class, f.level, pc.name as pg_name
                    FROM followers f
                    LEFT JOIN player_characters pc ON f.pg_id = pc.id
                    ORDER BY f.name ASC
                """)
            else:
                cursor.execute("""
                    SELECT f.name, f.class, f.level, pc.name as pg_name
                    FROM followers f
                    LEFT JOIN player_characters pc ON f.pg_id = pc.id
                    WHERE pc.user_id = %s
                    ORDER BY f.name ASC
                """, (self.current_user['id'],))
            
            followers = cursor.fetchall()
            
            if followers:
                # Frame scrollabile per i seguaci
                followers_canvas = tk.Canvas(followers_frame, height=200)
                followers_scrollbar = ttk.Scrollbar(followers_frame, orient="vertical", command=followers_canvas.yview)
                followers_scrollable_frame = ttk.Frame(followers_canvas)
                
                followers_scrollable_frame.bind(
                    "<Configure>",
                    lambda e: followers_canvas.configure(scrollregion=followers_canvas.bbox("all"))
                )
                
                followers_canvas.create_window((0, 0), window=followers_scrollable_frame, anchor="nw")
                followers_canvas.configure(yscrollcommand=followers_scrollbar.set)
                
                for follower in followers:
                    follower_info = f"• {follower['name']} ({follower['class']} Lvl {follower['level']})"
                    if follower['pg_name']:
                        follower_info += f" - PG: {follower['pg_name']}"
                    
                    ttk.Label(followers_scrollable_frame, 
                             text=follower_info,
                             font=('Arial', 9)).pack(anchor='w', padx=5, pady=2)
                
                followers_canvas.pack(side="left", fill="both", expand=True)
                followers_scrollbar.pack(side="right", fill="y")
            else:
                ttk.Label(followers_frame, text="Nessun seguace disponibile").pack(pady=5)
            
            cursor.close()
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento dettagli: {e}")

    def clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # 🔥 Invalida SOLO ciò che esiste davvero
        for attr in (
            "tree_imprevisti",
            "imprevisti_listbox",
            "objectives_tree",
            "tree_users",
            "tree_characters",
        ):
            if hasattr(self, attr):
                setattr(self, attr, None)

    def send_email_notification(self, to_email, subject, body):
        smtp_server = "smtp.gmail.com"
        smtp_port = 465  # SSL

        sender_email = self.SMTP_EMAIL
        app_password = self.SMTP_PASSWORD

        if not sender_email or not app_password:
            print("❌ Email o password non trovate nel file .env_sec")
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

    def treeview_sort_column(self, tree, col, reverse):
        """Ordina le colonne di una Treeview cliccando sull’intestazione"""
        try:
            # Recupera i valori dalla colonna selezionata
            data = [(tree.set(k, col), k) for k in tree.get_children('')]

            # Provo a convertire in numero, se fallisce ordino come testo
            try:
                data.sort(key=lambda t: float(t[0].replace('MO', '').replace('%', '').strip()), reverse=reverse)
            except ValueError:
                data.sort(key=lambda t: t[0].lower(), reverse=reverse)

            # Riordina la TreeView
            for index, (val, k) in enumerate(data):
                tree.move(k, '', index)

            # Aggiorna la funzione del click per invertire l’ordine la prossima volta
            tree.heading(col, command=lambda: self.treeview_sort_column(tree, col, not reverse))
        except Exception as e:
            print(f"[Errore ordinamento colonna '{col}']: {e}")

    def show_characters_menu(self):
        """Mostra il menu personaggi"""
        self.clear_content()
        
        title = ttk.Label(self.content_frame, text="🧙 Gestione Personaggi", style='Title.TLabel')
        title.pack(pady=10)
        
        # Frame pulsanti
        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(pady=10)
        
        if self.current_user['role'] == 'DM':
            ttk.Button(btn_frame, text="➕ Aggiungi PG", 
                      command=self.add_character_dialog).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Modifica", 
                  command=self.edit_character_dialog).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Elimina", 
                  command=self.remove_character_action).pack(side='left', padx=5)
        # Il pulsante "🔄 Aggiorna" è stato rimosso come richiesto.
       
        # Lista personaggi
        self.show_characters_list()
    
    def show_characters_list(self):
        """Mostra la lista dei personaggi senza ID e con ordinamento colonne"""
        list_frame = ttk.Frame(self.content_frame)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Colonne principali (senza ID)
        columns = ('Nome', 'Giocatore', 'Ruolo')
        self.tree_characters = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        for col in columns:
            # Attiva ordinamento cliccando sull'intestazione
            self.tree_characters.heading(col, text=col, command=lambda c=col: self.treeview_sort_column(self.tree_characters, c, False))
            self.tree_characters.column(col, width=180, anchor='center')

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree_characters.yview)
        self.tree_characters.configure(yscrollcommand=scrollbar.set)
        self.tree_characters.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        try:
            cursor = self.db.cursor()
            if self.current_user['role'] == 'DM':
                # DM vede tutti i personaggi e i loro proprietari
                cursor.execute("""
                    SELECT pc.id, pc.name, u.username, u.role
                    FROM player_characters pc
                    LEFT JOIN users u ON pc.user_id = u.id
                    ORDER BY u.username ASC, pc.name ASC
                """)
            else:
                # Giocatore vede solo i propri personaggi
                cursor.execute("""
                    SELECT pc.id, pc.name, u.username, u.role
                    FROM player_characters pc
                    LEFT JOIN users u ON pc.user_id = u.id
                    WHERE pc.user_id = %s
                    ORDER BY pc.name ASC
                """, (self.current_user['id'],))

            characters = cursor.fetchall()

            for char in characters:
                iid = str(char['id'])
                self.tree_characters.insert('', 'end', iid=iid, values=(
                    char.get('name', 'N/A'),
                    char.get('username', 'N/A'),
                    char.get('role', 'N/A')
                ))

        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento personaggi: {e}")

    def add_character_dialog(self):
        """Aggiunge un nuovo personaggio (il ruolo è ereditato dal giocatore)"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Aggiungi Personaggio")
        dialog.geometry("400x300")

        ttk.Label(dialog, text="Nome Personaggio:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=30)
        name_entry.pack(pady=5)

        ttk.Label(dialog, text="Giocatore (proprietario):").pack(pady=5)
        cursor = self.db.cursor()
        cursor.execute("SELECT id, username, role FROM users")
        users = cursor.fetchall()

        player_combo = ttk.Combobox(dialog, width=28, state='readonly')
        player_combo['values'] = [f"{u['username']} ({u['role']})" for u in users]
        player_combo.pack(pady=5)

        def save_character():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Errore", "Inserisci un nome valido")
                return

            if player_combo.current() < 0:
                messagebox.showerror("Errore", "Seleziona un giocatore")
                return

            user_id = users[player_combo.current()]['id']

            try:
                cursor.execute("""
                    INSERT INTO player_characters (name, user_id)
                    VALUES (%s, %s)
                """, (name, user_id))
                self.db.commit()
                messagebox.showinfo("Successo", "Personaggio creato con successo!")
                dialog.destroy()
                self.show_characters_menu()
            except Exception as e:
                messagebox.showerror("Errore", f"Errore creazione personaggio: {e}")

        ttk.Button(dialog, text="💾 Salva", command=save_character).pack(pady=20)

    def edit_character_dialog(self):
        """Dialog per modificare un personaggio"""
        tree = getattr(self, 'tree_characters', None)
        if tree is None:
            messagebox.showerror("Errore", "Lista personaggi non inizializzata")
            return

        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un personaggio da modificare")
            return

        char_id = int(selection[0])

        # Carica dati personaggio
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT pc.*, u.username 
            FROM player_characters pc
            LEFT JOIN users u ON pc.user_id = u.id
            WHERE pc.id = %s
        """, (char_id,))
        char = cursor.fetchone()
        
        if not char:
            messagebox.showerror("Errore", "Personaggio non trovato")
            return
        
        # Crea dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Personaggio")
        dialog.geometry("400x250")
        
        # Nome
        ttk.Label(dialog, text="Nome Personaggio:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=30)
        name_entry.insert(0, char['name'])
        name_entry.pack(pady=5)
        
        # Seleziona proprietario
        ttk.Label(dialog, text="Proprietario:").pack(pady=5)
        
        cursor.execute("SELECT id, username FROM users WHERE role = 'GIOCATORE'")
        players = cursor.fetchall()
        
        player_combo = ttk.Combobox(dialog, width=28, state='readonly')
        player_combo['values'] = [p['username'] for p in players]
        
        # Trova indice attuale
        current_idx = next((i for i, p in enumerate(players) if p['id'] == char['user_id']), -1)
        if current_idx >= 0:
            player_combo.current(current_idx)
        
        player_combo.pack(pady=5)
        
        def save_changes():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Errore", "Inserisci un nome valido")
                return
            
            if player_combo.current() < 0:
                messagebox.showerror("Errore", "Seleziona un proprietario")
                return
            
            player_id = players[player_combo.current()]['id']
            
            try:
                cursor = self.db.cursor()
                cursor.execute("""
                    UPDATE player_characters 
                    SET name=%s, user_id=%s 
                    WHERE id=%s
                """, (name, player_id, char_id))
                self.db.commit()
                
                messagebox.showinfo("Successo", "Personaggio aggiornato!")
                dialog.destroy()
                self.show_characters_menu()
                
            except Exception as e:
                messagebox.showerror("Errore", f"Errore aggiornamento: {e}")
        
        ttk.Button(dialog, text="💾 Salva", command=save_changes).pack(pady=20)

    def remove_character_action(self):
        tree = getattr(self, 'tree_characters', None)
        if tree is None:
            messagebox.showerror("Errore", "Lista personaggi non inizializzata")
            return

        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un personaggio da eliminare")
            return

        char_id = int(selection[0])  # ID dall'iid
        char_name = tree.item(selection[0])['values'][0]  # Nome rimane nel primo valore visibile

        if not messagebox.askyesno("Conferma", f"Vuoi eliminare il personaggio '{char_name}'?"):
            return

        try:
            cursor = self.db.cursor()
            linked_checks = [
                ("banche", "banks"),
                ("seguaci", "followers"),
                ("attività economiche", "economic_activities"),
                ("spese fisse", "fixed_expenses"),
                ("oggetti in banca", "bank_items"),
            ]
            linked_rows = []

            for label, table in linked_checks:
                cursor.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE pg_id = %s", (char_id,))
                count = cursor.fetchone().get('count', 0)
                if count:
                    linked_rows.append(f"- {label}: {count}")

            if linked_rows:
                messagebox.showwarning(
                    "Eliminazione bloccata",
                    "Non puoi eliminare questo PG perché ha dati collegati:\n\n"
                    + "\n".join(linked_rows)
                    + "\n\nSposta o rimuovi prima questi dati dalle rispettive sezioni."
                )
                return

            cursor.execute("DELETE FROM player_characters WHERE id = %s", (char_id,))
            self.db.commit()
            messagebox.showinfo("Successo", f"Personaggio '{char_name}' eliminato!")
            self.show_characters_menu()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore eliminazione: {e}")
    
    def show_banks_menu(self):
        """Mostra la gestione delle banche"""
        self.clear_content()

        title = ttk.Label(
            self.content_frame,
            text="🏦 Gestione Banche",
            style='Title.TLabel'
        )
        title.pack(pady=10)

        # PRIMA RIGA di pulsanti
        btn_frame_row1 = ttk.Frame(self.content_frame)
        btn_frame_row1.pack(pady=10)

        # --- Pulsanti visibili SOLO al DM ---
        if self.current_user['role'] == 'DM':
            ttk.Button(
                btn_frame_row1,
                text="➕ Aggiungi Banca",
                command=self.add_bank_dialog
            ).pack(side='left', padx=5)

            ttk.Button(
                btn_frame_row1,
                text="✏️ Modifica",
                command=self.edit_bank_dialog
            ).pack(side='left', padx=5)

            ttk.Button(
                btn_frame_row1,
                text="🗑️ Rimuovi",
                command=self.remove_bank_action
            ).pack(side='left', padx=5)

        # --- Pulsanti visibili a tutti ---
        ttk.Button(
            btn_frame_row1,
            text="💰 Deposita",
            command=self.deposit_dialog
        ).pack(side='left', padx=5)

        ttk.Button(
            btn_frame_row1,
            text="💸 Preleva",
            command=self.withdraw_dialog
        ).pack(side='left', padx=5)

        ttk.Button(
            btn_frame_row1,
            text="💱 Trasferisci Fondi",
            command=self.transfer_funds_dialog
        ).pack(side='left', padx=5)

        ttk.Button(
            btn_frame_row1,
            text="📦 Oggetti in Banca",
            command=self.show_bank_items_dialog
        ).pack(side='left', padx=5)

        ttk.Button(
            btn_frame_row1,
            text="📜 Storico Operazioni",
            command=self.show_bank_history_dialog
        ).pack(side='left', padx=5)

        # SECONDA RIGA di pulsanti (solo per DM)
        if self.current_user['role'] == 'DM':
            btn_frame_row2 = ttk.Frame(self.content_frame)
            btn_frame_row2.pack(pady=(0, 10))  # Margine solo in basso
            
            ttk.Button(
                btn_frame_row2,
                text="📊 Esporta Excel",
                command=self.export_to_excel
            ).pack(side='left', padx=5)

        # Lista banche
        self.show_banks_list()
    
    def show_banks_list(self):
        """Mostra la lista delle banche (ID nascosto come iid); include location e PG associato; supporta ordinamento colonne"""

        list_frame = ttk.Frame(self.content_frame)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)

        columns = ('Nome', 'Luogo', 'PG associato', 'Saldo', 'Interesse %')
        self.tree_banks = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        for col in columns:
            self.tree_banks.heading(col, text=col, command=lambda c=col: self.treeview_sort_column(self.tree_banks, c, False))
            self.tree_banks.column(col, width=140, anchor='center')

        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree_banks.yview)
        self.tree_banks.configure(yscrollcommand=scrollbar.set)
        self.tree_banks.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        try:
            cursor = self.db.cursor()

            # --- DM: vede tutte le banche ---
            if self.current_user['role'] == 'DM':
                cursor.execute("""
                    SELECT b.id, b.name, b.location, pc.name AS pg_name, 
                           b.current_balance, b.annual_interest
                    FROM banks b
                    LEFT JOIN player_characters pc ON b.pg_id = pc.id
                    ORDER BY b.name ASC
                """)

            # --- GIOCATORE: vede solo le banche dei suoi PG ---
            else:
                cursor.execute("""
                    SELECT b.id, b.name, b.location, pc.name AS pg_name, 
                           b.current_balance, b.annual_interest
                    FROM banks b
                    LEFT JOIN player_characters pc ON b.pg_id = pc.id
                    WHERE pc.user_id = %s
                    ORDER BY b.name ASC
                """, (self.current_user['id'],))

            rows = cursor.fetchall()

            for b in rows:
                iid = str(b['id'])
                vals = (
                    b['name'],
                    b.get('location', ''),
                    b.get('pg_name') or '',
                    f"{float(b.get('current_balance', 0)):.2f} MO",
                    f"{b.get('annual_interest', 0)} %"
                )
                self.tree_banks.insert('', 'end', iid=iid, values=vals)

        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento banche: {e}")

    def add_bank_dialog(self):
        """Aggiungi una nuova banca (inserisce initial_balance -> current_balance)"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Nuova Banca")
        dialog.geometry("420x360")

        ttk.Label(dialog, text="Nome Banca:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=40); name_entry.pack(pady=5)

        ttk.Label(dialog, text="Luogo (location):").pack(pady=5)
        location_entry = ttk.Entry(dialog, width=40); location_entry.pack(pady=5)

        ttk.Label(dialog, text="Interesse annuale (%):").pack(pady=5)
        interest_entry = ttk.Entry(dialog, width=12); interest_entry.insert(0, "2.0"); interest_entry.pack(pady=5)

        ttk.Label(dialog, text="Fondi iniziali (initial_balance):").pack(pady=5)
        init_entry = ttk.Entry(dialog, width=16); init_entry.insert(0, "0"); init_entry.pack(pady=5)

        ttk.Label(dialog, text="Associare a PG (opzionale):").pack(pady=5)
        cursor = self.db.cursor()
        cursor.execute("SELECT id, name FROM player_characters ORDER BY name ASC")
        pgs = cursor.fetchall()
        pg_values = [pg['name'] for pg in pgs]
        pg_combo = ttk.Combobox(dialog, values=pg_values, state='readonly', width=36)
        pg_combo.pack(pady=5)

        def save_bank():
            name = name_entry.get().strip()
            location = location_entry.get().strip()
            try:
                annual_interest = float(interest_entry.get().strip() or 0)
            except ValueError:
                messagebox.showerror("Errore", "Interesse non valido")
                return
            try:
                initial_balance = float(init_entry.get().strip() or 0)
            except ValueError:
                messagebox.showerror("Errore", "Saldo iniziale non valido")
                return

            if not name:
                messagebox.showerror("Errore", "Inserisci il nome della banca")
                return

            pg_id = None
            if pg_combo.current() >= 0:
                pg_id = pgs[pg_combo.current()]['id']

            try:
                # user_id è chi crea la banca (il DM)
                cursor = self.db.cursor()
                insert_query = """
                    INSERT INTO banks (user_id, name, location, annual_interest,
                                       initial_balance, current_balance, pg_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_query, (
                    self.current_user['id'],
                    name,
                    location,
                    annual_interest,
                    initial_balance,
                    initial_balance,   # current_balance inizializzato uguale a initial_balance
                    pg_id
                ))
                self.db.commit()
                messagebox.showinfo("Successo", f"Banca '{name}' creata.")
                dialog.destroy()
                self.show_banks_menu()
            except Exception as e:
                messagebox.showerror("Errore", f"Errore creazione banca: {e}")

        ttk.Button(dialog, text="💾 Salva", command=save_bank).pack(pady=12)

    def edit_bank_dialog(self, tree=None):
        """Modifica una banca selezionata (usa iid come id)"""
        tree = tree or getattr(self, 'tree_banks', None)
        if not tree or not tree.selection():
            messagebox.showwarning("Avviso", "Seleziona una banca da modificare")
            return

        bank_id = int(tree.selection()[0])
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM banks WHERE id=%s", (bank_id,))
        bank = cursor.fetchone()
        if not bank:
            messagebox.showerror("Errore", "Banca non trovata")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Banca")
        dialog.geometry("420x420")

        ttk.Label(dialog, text="Nome Banca:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=40); name_entry.insert(0, bank.get('name','')); name_entry.pack(pady=5)

        ttk.Label(dialog, text="Luogo (location):").pack(pady=5)
        location_entry = ttk.Entry(dialog, width=40); location_entry.insert(0, bank.get('location','')); location_entry.pack(pady=5)

        ttk.Label(dialog, text="Interesse annuale (%):").pack(pady=5)
        interest_entry = ttk.Entry(dialog, width=12); interest_entry.insert(0, str(bank.get('annual_interest',0))); interest_entry.pack(pady=5)

        ttk.Label(dialog, text="Saldo attuale (current_balance):").pack(pady=5)
        current_entry = ttk.Entry(dialog, width=16); current_entry.insert(0, str(bank.get('current_balance', bank.get('initial_balance',0)))); current_entry.pack(pady=5)

        ttk.Label(dialog, text="Associare a PG (opzionale):").pack(pady=5)
        cursor.execute("SELECT id, name FROM player_characters ORDER BY name ASC")
        pgs = cursor.fetchall()
        pg_values = [pg['name'] for pg in pgs]
        pg_combo = ttk.Combobox(dialog, values=pg_values, state='readonly', width=36)
        # imposta il valore corrente se presente
        if bank.get('pg_id'):
            idx = next((i for i,p in enumerate(pgs) if p['id']==bank['pg_id']), None)
            if idx is not None:
                pg_combo.current(idx)
        pg_combo.pack(pady=5)

        def save_changes():
            new_name = name_entry.get().strip()
            new_location = location_entry.get().strip()
            try:
                new_interest = float(interest_entry.get().strip() or 0)
                new_current = float(current_entry.get().strip() or 0)
            except ValueError:
                messagebox.showerror("Errore", "Valori numerici non validi")
                return

            new_pg_id = None
            if pg_combo.current() >= 0:
                new_pg_id = pgs[pg_combo.current()]['id']

            try:
                cursor.execute("""
                    UPDATE banks SET name=%s, location=%s, annual_interest=%s, current_balance=%s, pg_id=%s
                    WHERE id=%s
                """, (new_name, new_location, new_interest, new_current, new_pg_id, bank_id))
                self.db.commit()
                messagebox.showinfo("Successo", "Banca aggiornata")
                dialog.destroy()
                self.show_banks_menu()
            except Exception as e:
                messagebox.showerror("Errore", f"Errore aggiornamento banca: {e}")

        ttk.Button(dialog, text="💾 Salva", command=save_changes).pack(pady=12)

    def remove_bank_action(self, tree=None):
        tree = tree or getattr(self, 'tree_banks', None)
        if not tree or not tree.selection():
            messagebox.showwarning("Avviso", "Seleziona una banca da eliminare")
            return

        bank_id = int(tree.selection()[0])
        # leggo il nome per conferma
        name = tree.item(str(bank_id))['values'][0]
        if not messagebox.askyesno("Conferma", f"Vuoi eliminare la banca '{name}'?"):
            return

        try:
            cursor = self.db.cursor()
            linked_checks = [
                ("transazioni sorgente", "bank_transactions", "bank_id"),
                ("transazioni destinazione", "bank_transactions", "target_bank_id"),
                ("oggetti in banca", "bank_items", "bank_id"),
                ("costi seguaci", "followers", "bank_destination_cost"),
                ("obiettivi", "follower_objectives", "bank_id"),
                ("attività economiche", "economic_activities", "destination_bank_id"),
                ("spese fisse", "fixed_expenses", "source_bank_id"),
            ]
            linked_rows = []

            for label, table, column in linked_checks:
                cursor.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {column} = %s", (bank_id,))
                count = cursor.fetchone().get('count', 0)
                if count:
                    linked_rows.append(f"- {label}: {count}")

            if linked_rows:
                messagebox.showwarning(
                    "Eliminazione bloccata",
                    "Non puoi eliminare questa banca perché ha dati collegati:\n\n"
                    + "\n".join(linked_rows)
                    + "\n\nSposta o rimuovi prima questi dati dalle rispettive sezioni."
                )
                return

            cursor.execute("DELETE FROM banks WHERE id=%s", (bank_id,))
            self.db.commit()
            messagebox.showinfo("Successo", "Banca eliminata")
            self.show_banks_menu()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore eliminazione banca: {e}")

    def transfer_funds_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Trasferisci Fondi")
        dialog.geometry("460x320")

        cursor = self.db.cursor()
        if self.current_user['role'] == 'DM':
            cursor.execute("""
                SELECT b.id, b.name, b.current_balance, b.pg_id, b.user_id, pc.user_id AS owner_user_id
                FROM banks b
                LEFT JOIN player_characters pc ON b.pg_id = pc.id
                ORDER BY b.name ASC
            """)
        else:
            cursor.execute("""
                SELECT b.id, b.name, b.current_balance, b.pg_id, b.user_id, pc.user_id AS owner_user_id
                FROM banks b
                JOIN player_characters pc ON b.pg_id = pc.id
                WHERE pc.user_id = %s
                ORDER BY b.name ASC
            """, (self.current_user['id'],))
        banks = cursor.fetchall()

        if len(banks) < 2:
            messagebox.showwarning("Avviso", "Servono almeno due banche disponibili per trasferire fondi.")
            dialog.destroy()
            return

        ttk.Label(dialog, text="Banca sorgente:").pack(pady=5)
        from_combo = ttk.Combobox(dialog, values=[b['name'] for b in banks], state='readonly', width=36); from_combo.pack(pady=5)

        ttk.Label(dialog, text="Banca destinazione:").pack(pady=5)
        to_combo = ttk.Combobox(dialog, values=[b['name'] for b in banks], state='readonly', width=36); to_combo.pack(pady=5)

        ttk.Label(dialog, text="Importo (MO):").pack(pady=5)
        amount_entry = ttk.Entry(dialog, width=18); amount_entry.pack(pady=5)

        def do_transfer():
            if from_combo.current()<0 or to_combo.current()<0:
                messagebox.showerror("Errore", "Seleziona entrambe le banche")
                return
            try:
                amount = float(amount_entry.get().strip())
            except ValueError:
                messagebox.showerror("Errore", "Importo non valido")
                return
            if amount <= 0:
                messagebox.showerror("Errore", "Importo deve essere positivo")
                return

            from_bank = banks[from_combo.current()]
            to_bank = banks[to_combo.current()]
            if from_bank['id'] == to_bank['id']:
                messagebox.showerror("Errore", "Seleziona banche diverse")
                return
            source_pg_id = from_bank.get('pg_id')
            source_user_id = from_bank.get('owner_user_id') or from_bank.get('user_id') or self.current_user['id']
            target_pg_id = to_bank.get('pg_id')
            target_user_id = to_bank.get('owner_user_id') or to_bank.get('user_id') or self.current_user['id']

            # controllo saldo
            if float(from_bank.get('current_balance',0)) < amount:
                if not messagebox.askyesno("Conferma", "Saldo insufficiente. Vuoi procedere lo stesso?"):
                    return

            try:
                cursor.execute("START TRANSACTION")
                cursor.execute("UPDATE banks SET current_balance = current_balance - %s WHERE id=%s", (amount, from_bank['id']))
                cursor.execute("UPDATE banks SET current_balance = current_balance + %s WHERE id=%s", (amount, to_bank['id']))
                cursor.execute("""
                    INSERT INTO bank_transactions
                    (pg_id, user_id, bank_id, target_bank_id, operation_type, amount, reason, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    source_pg_id,
                    source_user_id,
                    from_bank['id'],
                    to_bank['id'],
                    'TRASFERIMENTO_OUT',
                    amount,
                    f"Trasferito a {to_bank['name']}"
                ))
                cursor.execute("""
                    INSERT INTO bank_transactions
                    (pg_id, user_id, bank_id, target_bank_id, operation_type, amount, reason, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    target_pg_id,
                    target_user_id,
                    to_bank['id'],
                    from_bank['id'],
                    'TRASFERIMENTO_IN',
                    amount,
                    f"Ricevuto da {from_bank['name']}"
                ))
                self.db.commit()
                messagebox.showinfo("Successo", "Trasferimento completato")
                dialog.destroy()
                self.show_banks_menu()
            except Exception as e:
                try:
                    self.db.rollback()
                except:
                    pass
                messagebox.showerror("Errore", f"Errore durante il trasferimento: {e}")

        ttk.Button(dialog, text="💸 Trasferisci", command=do_transfer).pack(pady=12)

    def show_bank_history_dialog(self):
        """Visualizza lo storico delle operazioni bancarie (compatibile con lo schema originale)"""
        # Proviamo prima a ottenere la banca selezionata nella tree (se presente)
        tree = getattr(self, 'tree_banks', None)
        bank_id = None
        bank_name = None

        if tree and tree.selection():
            try:
                bank_id = int(tree.selection()[0])  # usiamo iid = id
                # nome visibile nella row (colonna 0)
                bank_name = tree.item(str(bank_id))['values'][0]
            except Exception:
                bank_id = None

        cursor = self.db.cursor()

        # Se non c'è una banca selezionata nella UI, apriamo una finestra di selezione
        if bank_id is None:
            # Recupera elenco banche accessibili (come nel codice console)
            try:
                if self.current_user['role'] == 'DM':
                    cursor.execute("SELECT id, name FROM banks ORDER BY name ASC")
                    banks = cursor.fetchall()
                else:
                    # prendo i pg dell'utente e poi le banche con pg_id in (...)
                    cursor.execute("SELECT id FROM player_characters WHERE user_id = %s", (self.current_user['id'],))
                    user_pg_ids = [row['id'] for row in cursor.fetchall()]

                    if not user_pg_ids:
                        messagebox.showwarning("Avviso", "Nessun personaggio associato al tuo account.")
                        return

                    placeholders = ','.join(['%s'] * len(user_pg_ids))
                    query = f"SELECT id, name FROM banks WHERE pg_id IN ({placeholders}) ORDER BY name ASC"
                    cursor.execute(query, tuple(user_pg_ids))
                    banks = cursor.fetchall()

                if not banks:
                    messagebox.showinfo("Informazione", "Nessuna banca disponibile.")
                    return

                # Dialog di selezione semplice
                sel_dialog = tk.Toplevel(self.root)
                sel_dialog.title("Seleziona Banca")
                sel_dialog.geometry("360x320")

                ttk.Label(sel_dialog, text="Seleziona una banca:").pack(pady=8)
                listbox = tk.Listbox(sel_dialog, height=10)
                listbox.pack(fill='both', expand=True, padx=10, pady=5)
                for b in banks:
                    listbox.insert(tk.END, b['name'])

                def choose():
                    idx = listbox.curselection()
                    if not idx:
                        messagebox.showwarning("Avviso", "Seleziona una banca")
                        return
                    sel = idx[0]
                    sel_bank = banks[sel]
                    nonlocal bank_id, bank_name
                    bank_id = sel_bank['id']
                    bank_name = sel_bank['name']
                    sel_dialog.destroy()
                ttk.Button(sel_dialog, text="Seleziona", command=choose).pack(pady=8)
                sel_dialog.transient(self.root)
                sel_dialog.grab_set()
                self.root.wait_window(sel_dialog)

            except Exception as e:
                messagebox.showerror("Errore", f"Errore caricamento banche: {e}")
                return

        if bank_id is None:
            # utente ha chiuso il dialog o non ha selezionato nulla
            return

        # Ora carichiamo le transazioni con le JOIN come nel tuo script originale
        try:
            cursor.execute("""
                SELECT 
                    t.operation_type, t.amount, t.reason, t.timestamp,
                    pc.name AS pg_name,
                    u.username AS user_name,
                    b2.name AS target_bank_name
                FROM bank_transactions t
                LEFT JOIN player_characters pc ON t.pg_id = pc.id
                LEFT JOIN users u ON t.user_id = u.id
                LEFT JOIN banks b2 ON t.target_bank_id = b2.id
                WHERE t.bank_id = %s
                ORDER BY t.timestamp DESC
            """, (bank_id,))
            transactions = cursor.fetchall()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore query transazioni: {e}")
            return

        # Costruisco la finestra con Treeview per mostrare lo storico
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Storico - {bank_name or ''}")
        dialog.geometry("900x420")

        cols = ('Data/Time', 'Operazione', 'Importo', 'PG', 'Giocatore', 'Motivo', 'Destinazione')
        hist_tree = ttk.Treeview(dialog, columns=cols, show='headings', height=18)
        for c in cols:
            hist_tree.heading(c, text=c)
            hist_tree.column(c, width=120 if c != 'Motivo' and c != 'Destinazione' else 220)
        hist_tree.pack(fill='both', expand=True, padx=10, pady=10)

        if not transactions:
            # messaggio vuoto ma mostriamo la finestra per coerenza
            messagebox.showinfo("Informazione", "Nessuna transazione trovata per la banca selezionata.")
        else:
            for tx in transactions:
                ts = tx.get('timestamp')
                # formatto timestamp in stringa leggibile
                try:
                    ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if hasattr(ts, 'strftime') else str(ts)
                except Exception:
                    ts_str = str(ts)
                oper = (tx.get('operation_type') or '').capitalize()
                amount = float(tx.get('amount') or 0.0)
                amt_str = f"{amount:.2f} MO"
                pg = tx.get('pg_name') or 'N/A'
                usern = tx.get('user_name') or 'Sconosciuto'
                motivo = tx.get('reason') or ''
                dest = tx.get('target_bank_name') or ''
                hist_tree.insert('', 'end', values=(ts_str, oper, amt_str, pg, usern, motivo, dest))

        ttk.Button(dialog, text="Chiudi", command=dialog.destroy).pack(pady=6)
    
    def deposit_dialog(self):
        """Dialog per depositare denaro"""
        self.transaction_dialog("Deposito", "deposito")
    
    def withdraw_dialog(self):
        """Dialog per prelevare denaro"""
        self.transaction_dialog("Prelievo", "prelievo")
    
    def transaction_dialog(self, title, transaction_type):
        """Dialog generico per transazioni bancarie"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("400x300")
        
        # Carica banche
        cursor = self.db.cursor()
        if self.current_user['role'] == 'DM':
            cursor.execute("SELECT id, name, current_balance FROM banks")
        else:
            cursor.execute("""
                SELECT b.id, b.name, b.current_balance 
                FROM banks b
                JOIN player_characters pc ON b.pg_id = pc.id
                WHERE pc.user_id = %s
            """, (self.current_user['id'],))
        
        banks = cursor.fetchall()
        
        if not banks:
            messagebox.showwarning("Avviso", "Nessuna banca disponibile")
            dialog.destroy()
            return
        
        ttk.Label(dialog, text="Seleziona Banca:").pack(pady=5)
        bank_combo = ttk.Combobox(dialog, width=35, state='readonly')
        bank_combo['values'] = [f"{b['name']} (Saldo: {float(b['current_balance']):.2f})" 
                                for b in banks]
        bank_combo.pack(pady=5)
        
        ttk.Label(dialog, text="Importo:").pack(pady=5)
        amount_entry = ttk.Entry(dialog, width=30)
        amount_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Motivo:").pack(pady=5)
        reason_entry = ttk.Entry(dialog, width=30)
        reason_entry.pack(pady=5)
        
        def execute_transaction():
            if bank_combo.current() < 0:
                messagebox.showerror("Errore", "Seleziona una banca")
                return
            
            try:
                amount = float(amount_entry.get())
                reason = reason_entry.get().strip()
                
                if amount <= 0:
                    messagebox.showerror("Errore", "Importo deve essere positivo")
                    return
                
                bank = banks[bank_combo.current()]
                current_balance = float(bank['current_balance'])
                
                if transaction_type == "prelievo" and amount > current_balance:
                    messagebox.showerror("Errore", "Fondi insufficienti")
                    return
                
                new_balance = current_balance + amount if transaction_type == "deposito" else current_balance - amount
                
                cursor = self.db.cursor()
                cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s",
                             (new_balance, bank['id']))
                
                cursor.execute("""
                    INSERT INTO bank_transactions 
                    (bank_id, user_id, operation_type, amount, reason, timestamp)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (bank['id'], self.current_user['id'], transaction_type, amount, reason))
                
                self.db.commit()
                
                messagebox.showinfo("Successo", f"{title} completato!")
                dialog.destroy()
                self.show_banks_menu()
                
            except ValueError:
                messagebox.showerror("Errore", "Importo non valido")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore transazione: {e}")
        
        ttk.Button(dialog, text=f"💰 Esegui {title}", command=execute_transaction).pack(pady=20)

    def apply_annual_bank_interest(self):
        """Applica interessi annuali su tutte le banche con current_balance > 0 (uso tasso annuale)."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT b.id, b.name, b.current_balance, b.annual_interest,
                       b.pg_id, COALESCE(pc.user_id, b.user_id) AS owner_user_id
                FROM banks b
                LEFT JOIN player_characters pc ON b.pg_id = pc.id
            """)
            banks = cursor.fetchall() or []
            if not banks:
                self.append_time_log("Nessuna banca trovata per il calcolo interessi annuali.")
                try:
                    cursor.close()
                except:
                    pass
                return

            self.append_time_log("📅 Fine anno Mystara → Calcolo interessi annuali:")
            for bank in banks:
                bank_id = bank.get('id')
                name = bank.get('name', 'N/A')
                balance = float(bank.get('current_balance') or 0.0)
                rate = float(bank.get('annual_interest') or 0.0)
                if balance <= 0 or rate <= 0:
                    self.append_time_log(f" - Banca '{name}': saldo {balance:.2f} → nessun interesse (saldo negativo o tasso nullo).")
                    continue
                interest = balance * (rate / 100.0)
                try:
                    cursor.execute("START TRANSACTION")
                    cursor.execute(
                        "UPDATE banks SET current_balance = current_balance + %s WHERE id = %s",
                        (interest, bank_id)
                    )
                    cursor.execute("""
                        INSERT INTO bank_transactions
                        (pg_id, user_id, bank_id, operation_type, amount, reason, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """, (
                        bank.get('pg_id'),
                        bank.get('owner_user_id'),
                        bank_id,
                        'INTERESSE_ANNUALE',
                        interest,
                        f"Interesse annuale {rate:.2f}% su saldo {balance:.2f} MO"
                    ))
                    self.db.commit()
                    new_balance = balance + interest
                    self.append_time_log(f" - 💰 '{name}': {balance:.2f} → {new_balance:.2f} (interessi {interest:.2f})")
                except Exception as e:
                    try:
                        self.db.rollback()
                    except:
                        pass
                    self.append_time_log(f" - Errore aggiornamento banca '{name}': {e}")
            try:
                cursor.close()
            except:
                pass

            # ricarica GUI banche se presente
            try:
                if hasattr(self, 'tree_banks'):
                    self.load_banks(self.tree_banks)
            except Exception as e:
                self.append_time_log(f"Impossibile ricaricare GUI banche: {e}")

        except Exception as e:
            self.append_time_log(f"Errore apply_annual_bank_interest: {e}")

    def show_bank_items_dialog(self):
        bank_id = None
        pg_id = None

        # CASO 1: banca selezionata da Treeview (DM)
        if hasattr(self, "tree_banks") and self.tree_banks is not None:
            sel = self.tree_banks.selection()
            if sel:
                bank_id = int(sel[0])  # iid = id banca
                
                # Recupera l'ID del PG associato alla banca
                try:
                    cursor = self.db.cursor()
                    cursor.execute("SELECT pg_id FROM banks WHERE id = %s", (bank_id,))
                    result = cursor.fetchone()
                    if result and result['pg_id']:
                        pg_id = result['pg_id']
                    cursor.close()
                except Exception as e:
                    print(f"Errore nel recupero del PG associato alla banca: {e}")

        # CASO 2: giocatore → banca già nota
        if bank_id is None:
            bank_id = getattr(self, "current_bank_id", None)

        if bank_id is None:
            messagebox.showwarning(
                "Attenzione",
                "Nessuna banca selezionata o disponibile."
            )
            return

        # Se pg_id non è stato trovato, prova a recuperarlo da self.current_user
        if pg_id is None and hasattr(self, 'current_user'):
            try:
                cursor = self.db.cursor()
                # Cerca il primo PG dell'utente corrente
                cursor.execute("SELECT id FROM player_characters WHERE user_id = %s LIMIT 1", 
                             (self.current_user['id'],))
                result = cursor.fetchone()
                if result:
                    pg_id = result['id']
                cursor.close()
            except Exception as e:
                print(f"Errore nel recupero del PG dell'utente: {e}")

        if pg_id is None:
            messagebox.showwarning(
                "Attenzione",
                "Impossibile determinare il personaggio associato."
            )
            return

        # salva contesto
        self.current_bank_id = bank_id
        self.current_pg_id = pg_id

        win = tk.Toplevel(self.root)
        win.title("📦 Oggetti in Banca")
        
        # MISURE DELLA FINESTRA:
        win.geometry("1000x500")
        
        # Imposta dimensione minima
        win.minsize(750, 450)
        
        # Imposta per rimanere sempre in primo piano
        win.transient(self.root)  # Rende la finestra figlia della principale
        win.grab_set()  # Blocca l'interazione con la finestra principale

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.build_bank_items_tab(notebook, bank_id, pg_id)
        self.mark_bank_notifications_read(bank_id)

    def get_pg_name(self, pg_id):
        """Recupera il nome del PG dato l'ID"""
        cursor = self.db.cursor()
        cursor.execute("SELECT name FROM player_characters WHERE id = %s", (pg_id,))
        result = cursor.fetchone()
        cursor.close()
        return result['name'] if result else "Sconosciuto"

    def build_bank_items_tab(self, notebook, bank_id, pg_id):
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="📦 Oggetti")

        columns = ("id", "item", "qty", "declared", "status", "dm_proposal")
        tree = ttk.Treeview(frame, columns=columns, show="headings")

        tree.heading("item", text="Oggetto")
        tree.heading("qty", text="Qtà")
        tree.heading("declared", text="Prezzo giocatore (MO)")
        tree.heading("status", text="Stato / Motivo rifiuto")
        tree.heading("dm_proposal", text="Proposta DM (MO)")

        # ALLARGA LE COLONNE
        tree.column("id", width=0, stretch=False)
        tree.column("item", width=200)  # Da 150 a 200
        tree.column("qty", width=80)    # Da 60 a 80
        tree.column("declared", width=180)  # Da 160 a 180
        tree.column("status", width=300)  # Da 250 a 300
        tree.column("dm_proposal", width=180)  # Da 150 a 180
        
        tree.pack(fill="both", expand=True, padx=5, pady=5)

        self.bank_items_tree = tree
        self.load_bank_items(bank_id, pg_id)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x")

        # Pulsanti per giocatore
        if self.current_user['role'] == 'GIOCATORE':
            ttk.Button(
                btn_frame,
                text="➕ Deposita oggetto",
                command=lambda: self.open_deposit_item_dialog(bank_id, pg_id)
            ).pack(side="left", padx=5)
            
            ttk.Button(
                btn_frame,
                text="↪️ Ritira oggetto",
                command=self.withdraw_selected_item
            ).pack(side="left", padx=5)
            
            ttk.Button(
                btn_frame,
                text="💰 Richiedi vendita",
                command=self.request_sale_dialog
            ).pack(side="left", padx=5)
            
            ttk.Button(
                btn_frame,
                text="💲 Modifica prezzo",
                command=self.modify_price_dialog
            ).pack(side="left", padx=5)

        # Pulsanti per DM
        if self.current_user['role'] == 'DM':
            ttk.Button(
                btn_frame,
                text="💲 Propone prezzo",
                command=self.dm_propose_price_dialog
            ).pack(side="left", padx=5)
            
            ttk.Button(
                btn_frame,
                text="✅ Accetta prezzo giocatore",
                command=self.dm_accept_player_price
            ).pack(side="left", padx=5)
            
            ttk.Button(
                btn_frame,
                text="✅ Accetta prezzo DM",
                command=self.dm_accept_dm_price
            ).pack(side="left", padx=5)
            
            ttk.Button(
                btn_frame,
                text="❌ Rifiuta vendita",
                command=self.dm_reject_sale
            ).pack(side="left", padx=5)
            
            # NUOVO PULSANTE: Elimina oggetto venduto/ritirato
            ttk.Button(
                btn_frame,
                text="🗑️ Elimina oggetto",
                command=self.dm_delete_item
            ).pack(side="left", padx=5)

        # Bind per doppio click
        tree.bind("<Double-1>", lambda e: self.show_item_details(tree))

    def load_bank_items(self, bank_id, pg_id):
        tree = self.bank_items_tree
        tree.delete(*tree.get_children())

        cursor = self.db.cursor()

        if self.current_user['role'] == 'DM':
            cursor.execute("""
                SELECT bi.*, ev.value AS dm_proposal
                FROM bank_items bi
                LEFT JOIN (
                    SELECT item_id, value 
                    FROM bank_item_evaluations 
                    WHERE evaluator_role = 'DM'
                    ORDER BY created_at DESC
                ) ev ON bi.id = ev.item_id
                WHERE bi.bank_id = %s
            """, (bank_id,))
        else:
            cursor.execute("""
                SELECT bi.*, ev.value AS dm_proposal
                FROM bank_items bi
                LEFT JOIN (
                    SELECT item_id, value 
                    FROM bank_item_evaluations 
                    WHERE evaluator_role = 'DM'
                    ORDER BY created_at DESC
                ) ev ON bi.id = ev.item_id
                WHERE bi.bank_id = %s AND bi.pg_id = %s
            """, (bank_id, pg_id))

        for row in cursor.fetchall():
            status = row["status"]
            status_text = ""
            
            if status == "DEPOSITATO":
                status_text = "Depositato"
            elif status == "IN_VALUTAZIONE":
                status_text = "In valutazione"
            elif status == "VENDUTO":
                status_text = "Venduto"
            elif status == "RIFIUTATO":
                status_text = "Rifiutato"
            elif status == "RITIRATO":
                status_text = "Ritirato"
            else:
                status_text = status
            
            # Ottieni l'ultima proposta del DM se esiste
            dm_proposal_value = row.get("dm_proposal")
            dm_proposal_text = f"{dm_proposal_value:.2f} MO" if dm_proposal_value else "—"
            
            # Se è RIFIUTATO, mostra il motivo
            if status == "RIFIUTATO" and row.get("rejection_reason"):
                status_text = f"Rifiutato: {row['rejection_reason']}"
            
            declared_value = row["declared_value"] or 0
            
            tree.insert("", "end", values=(
                row["id"],
                row["item_name"],
                row["quantity"],
                f"{declared_value:.2f} MO",
                status_text,
                dm_proposal_text
            ))

        cursor.close()

    def open_deposit_item_dialog(self, bank_id, pg_id):
        """Finestra per depositare un oggetto in banca - VERSIONE CORRETTA CON FOCUS"""
        # Ottieni la finestra padre (quella degli oggetti in banca)
        parent_window = self.bank_items_tree.winfo_toplevel()
        
        win = tk.Toplevel(parent_window)  # Specifica la finestra padre
        win.title("Deposita oggetto in banca")
        win.geometry("400x250")
        
        # ⭐⭐ AGGIUNGI QUESTE DUE RIGHE PER TENERE LA FINESTRA IN PRIMO PIANO
        win.transient(parent_window)  # Rende la finestra figlia
        win.grab_set()  # Blocca l'interazione con la finestra padre

        tk.Label(win, text="Nome oggetto").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        tk.Label(win, text="Quantità").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        tk.Label(win, text="Valore stimato (MO)").grid(row=2, column=0, padx=5, pady=5, sticky='w')

        name_e = tk.Entry(win, width=30)
        qty_e = tk.Entry(win, width=10)
        val_e = tk.Entry(win, width=15)
        
        name_e.grid(row=0, column=1, padx=5, pady=5)
        qty_e.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        val_e.grid(row=2, column=1, padx=5, pady=5, sticky='w')
        
        # Focus sul primo campo
        name_e.focus_set()

        def submit():
            try:
                item_name = name_e.get().strip()
                if not item_name:
                    messagebox.showerror("Errore", "Inserisci il nome dell'oggetto")
                    name_e.focus_set()
                    return
                    
                quantity = int(qty_e.get())
                if quantity <= 0:
                    messagebox.showerror("Errore", "La quantità deve essere maggiore di 0")
                    qty_e.focus_set()
                    qty_e.select_range(0, tk.END)
                    return
                    
                declared_value = float(val_e.get())
                if declared_value < 0:
                    messagebox.showerror("Errore", "Il valore non può essere negativo")
                    val_e.focus_set()
                    val_e.select_range(0, tk.END)
                    return

                abs_day = self.date_to_absolute_day(self.game_date)

                cursor = self.db.cursor()
                cursor.execute("""
                    INSERT INTO bank_items
                    (pg_id, bank_id, item_name, quantity, declared_value, 
                     status, request_sale, absolute_day)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (pg_id, bank_id, item_name, quantity, declared_value, 
                      "DEPOSITATO", 0, abs_day))

                self.db.commit()
                cursor.close()

                self.append_time_log(
                    f"{self.get_pg_name(pg_id)} deposita {quantity}x {item_name} in banca (valore: {declared_value:.2f} MO)."
                )
                
                win.destroy()
                self.load_bank_items(self.current_bank_id, self.current_pg_id)
                messagebox.showinfo("Successo", f"Oggetto '{item_name}' depositato con successo!")
                
            except ValueError as e:
                messagebox.showerror("Errore", f"Valore non valido: {e}")
                # Ripristina il focus sul campo errato
                if "quantity" in str(e).lower():
                    qty_e.focus_set()
                    qty_e.select_range(0, tk.END)
                else:
                    val_e.focus_set()
                    val_e.select_range(0, tk.END)
            except Exception as e:
                messagebox.showerror("Errore", f"Errore nel deposito: {e}")

        def on_closing():
            win.destroy()
            parent_window.focus_set()
        
        # Bind per Enter e Escape
        win.bind('<Return>', lambda e: submit())
        win.bind('<Escape>', lambda e: on_closing())
        
        # Pulsante centrato
        btn_frame = tk.Frame(win)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=20)
        
        tk.Button(btn_frame, text="Deposita", command=submit).pack()
        
        # Bind per la chiusura della finestra
        win.protocol("WM_DELETE_WINDOW", on_closing)

    def withdraw_selected_item(self):
        """Ritira l'oggetto selezionato dalla banca"""
        sel = self.bank_items_tree.selection()
        if not sel:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto da ritirare")
            return

        item_id = self.bank_items_tree.item(sel[0])["values"][0]
        item_name = self.bank_items_tree.item(sel[0])["values"][1]
        quantity = self.bank_items_tree.item(sel[0])["values"][2]
        status = self.bank_items_tree.item(sel[0])["values"][4]

        # Non permettere il ritiro se l'oggetto è già venduto
        if status == "Venduto":
            messagebox.showerror("Errore", "Questo oggetto è già stato venduto e non può essere ritirato")
            return

        if not messagebox.askyesno("Conferma ritiro", 
                                  f"Vuoi davvero ritirare {quantity}x {item_name} dalla banca?\n"
                                  f"L'oggetto verrà rimosso dall'inventario della banca."):
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE bank_items
                SET status = 'RITIRATO', request_sale = 0
                WHERE id = %s
            """, (item_id,))
            self.db.commit()
            cursor.close()

            self.append_time_log(
                f"Oggetto {item_name} ritirato dalla banca."
            )
            
            messagebox.showinfo("Successo", f"Oggetto '{item_name}' ritirato con successo!")
            self.load_bank_items(self.current_bank_id, self.current_pg_id)
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante il ritiro: {e}")

    def request_sale_dialog(self):
        """Richiede la vendita di un oggetto depositato"""
        sel = self.bank_items_tree.selection()
        if not sel:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto da mettere in vendita")
            return

        item_id = self.bank_items_tree.item(sel[0])["values"][0]
        item_name = self.bank_items_tree.item(sel[0])["values"][1]
        current_price = float(self.bank_items_tree.item(sel[0])["values"][3].replace(" MO", ""))
        status = self.bank_items_tree.item(sel[0])["values"][4]

        # Non permettere la vendita se l'oggetto è già stato venduto o ritirato
        if status in ["Venduto", "Ritirato"]:
            messagebox.showerror("Errore", "Questo oggetto non può essere messo in vendita")
            return

        # Ottieni la finestra padre (quella degli oggetti in banca)
        parent_window = self.bank_items_tree.winfo_toplevel()
        
        win = tk.Toplevel(parent_window)  # Specifica la finestra padre
        win.title("Richiedi vendita oggetto")
        win.geometry("400x200")
        
        # ⭐⭐ AGGIUNGI QUESTE DUE RIGHE PER TENERE LA FINESTRA IN PRIMO PIANO
        win.transient(parent_window)  # Rende la finestra figlia
        win.grab_set()  # Blocca l'interazione con la finestra padre
        
        tk.Label(win, text=f"Oggetto: {item_name}").pack(pady=5)
        tk.Label(win, text=f"Prezzo attuale: {current_price:.2f} MO").pack(pady=5)
        
        tk.Label(win, text="Nuovo prezzo di vendita (MO):").pack(pady=5)
        price_entry = tk.Entry(win, width=15)
        price_entry.insert(0, str(current_price))
        price_entry.pack(pady=5)
        
        # Focus sul campo prezzo
        price_entry.focus_set()

        def submit():
            try:
                new_price = float(price_entry.get())
                if new_price <= 0:
                    messagebox.showerror("Errore", "Il prezzo deve essere maggiore di 0")
                    return

                cursor = self.db.cursor()
                cursor.execute("""
                    UPDATE bank_items
                    SET declared_value = %s, status = 'IN_VALUTAZIONE', request_sale = 1
                    WHERE id = %s
                """, (new_price, item_id))
                
                # AGGIUNTA PER NOTIFICHE: segna che c'è una nuova notifica per il DM
                cursor.execute("UPDATE bank_items SET dm_notified = FALSE WHERE id = %s", (item_id,))
                
                self.db.commit()
                cursor.close()

                self.append_time_log(
                    f"Richiesta vendita per {item_name} a {new_price:.2f} MO."
                )
                
                win.destroy()
                self.load_bank_items(self.current_bank_id, self.current_pg_id)
                messagebox.showinfo("Successo", f"Richiesta di vendita inviata al DM!")
                
            except ValueError:
                messagebox.showerror("Errore", "Inserisci un prezzo valido")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore nella richiesta: {e}")

        def on_closing():
            win.destroy()
            parent_window.focus_set()
        
        # Bind per Enter e Escape
        win.bind('<Return>', lambda e: submit())
        win.bind('<Escape>', lambda e: on_closing())
        
        tk.Button(win, text="Invia richiesta", command=submit).pack(pady=15)
        
        # Bind per la chiusura della finestra
        win.protocol("WM_DELETE_WINDOW", on_closing)

    def modify_price_dialog(self):
        """Modifica il prezzo di un oggetto in vendita"""
        sel = self.bank_items_tree.selection()
        if not sel:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto")
            return

        item_id = self.bank_items_tree.item(sel[0])["values"][0]
        item_name = self.bank_items_tree.item(sel[0])["values"][1]
        current_price = float(self.bank_items_tree.item(sel[0])["values"][3].replace(" MO", ""))
        status = self.bank_items_tree.item(sel[0])["values"][4]

        # Solo per oggetti in valutazione o depositati
        if status not in ["In valutazione", "Depositato"]:
            messagebox.showerror("Errore", "Puoi modificare il prezzo solo per oggetti depositati o in valutazione")
            return

        win = tk.Toplevel(self.root)
        win.title("Modifica prezzo oggetto")
        win.geometry("400x200")

        tk.Label(win, text=f"Oggetto: {item_name}").pack(pady=5)
        
        tk.Label(win, text="Nuovo prezzo (MO):").pack(pady=5)
        price_entry = tk.Entry(win, width=15)
        price_entry.insert(0, str(current_price))
        price_entry.pack(pady=5)

        def submit():
            try:
                new_price = float(price_entry.get())
                if new_price <= 0:
                    messagebox.showerror("Errore", "Il prezzo deve essere maggiore di 0")
                    return

                cursor = self.db.cursor()
                
                # Se l'oggetto era in valutazione, rimuovi le vecchie valutazioni DM
                if status == "In valutazione":
                    cursor.execute("""
                        DELETE FROM bank_item_evaluations 
                        WHERE item_id = %s
                    """, (item_id,))
                
                cursor.execute("""
                    UPDATE bank_items
                    SET declared_value = %s
                    WHERE id = %s
                """, (new_price, item_id))
                
                self.db.commit()
                cursor.close()

                self.append_time_log(
                    f"Prezzo modificato per {item_name}: {new_price:.2f} MO."
                )
                
                win.destroy()
                self.load_bank_items(self.current_bank_id, self.current_pg_id)
                messagebox.showinfo("Successo", f"Prezzo aggiornato a {new_price:.2f} MO")
                
            except ValueError:
                messagebox.showerror("Errore", "Inserisci un prezzo valido")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore nella modifica: {e}")

        tk.Button(win, text="Modifica prezzo", command=submit).pack(pady=15)

    def dm_delete_item(self):
        """DM elimina un oggetto venduto o ritirato dal database"""
        sel = self.bank_items_tree.selection()
        if not sel:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto da eliminare")
            return

        item_id = self.bank_items_tree.item(sel[0])["values"][0]
        item_name = self.bank_items_tree.item(sel[0])["values"][1]
        status_text = self.bank_items_tree.item(sel[0])["values"][4]
        
        # Determina lo stato effettivo dal testo visualizzato
        status = "UNKNOWN"
        if "Depositato" in status_text:
            status = "DEPOSITATO"
        elif "In valutazione" in status_text:
            status = "IN_VALUTAZIONE"
        elif "Venduto" in status_text:
            status = "VENDUTO"
        elif "Rifiutato" in status_text:
            status = "RIFIUTATO"
        elif "Ritirato" in status_text:
            status = "RITIRATO"
        
        # Permetti eliminazione solo per oggetti VENDUTI o RITIRATI
        if status not in ["VENDUTO", "RITIRATO"]:
            messagebox.showwarning("Attenzione", 
                                  f"Puoi eliminare solo oggetti VENDUTI o RITIRATI.\n"
                                  f"Stato attuale: {status_text}")
            return
        
        # Ottieni la finestra Toplevel padre
        parent_window = self.bank_items_tree.winfo_toplevel()
        
        # Crea una messagebox personalizzata che mantiene il focus
        confirm = tk.messagebox.askyesno(
            "Conferma eliminazione",
            f"Sei sicuro di voler ELIMINARE PERMANENTEMENTE "
            f"l'oggetto '{item_name}'?\n\n"
            f"Questa azione non può essere annullata!\n"
            f"Verranno eliminati anche tutti i dati correlati.",
            parent=parent_window  # Specifica la finestra padre
        )
        
        if not confirm:
            return
        
        try:
            cursor = self.db.cursor()
            
            # Prima elimina le valutazioni correlate (se presenti)
            cursor.execute("DELETE FROM bank_item_evaluations WHERE item_id = %s", (item_id,))
            
            # Poi elimina l'oggetto stesso
            cursor.execute("DELETE FROM bank_items WHERE id = %s", (item_id,))
            
            self.db.commit()
            cursor.close()

            self.append_time_log(
                f"Oggetto eliminato: {item_name} (ID: {item_id})"
            )
            
            # Messagebox di conferma che mantiene il focus
            tk.messagebox.showinfo(
                "Eliminato", 
                f"Oggetto '{item_name}' eliminato permanentemente.",
                parent=parent_window  # Specifica la finestra padre
            )
            
            self.load_bank_items(self.current_bank_id, self.current_pg_id)
            
        except Exception as e:
            tk.messagebox.showerror(
                "Errore", 
                f"Errore durante l'eliminazione: {e}",
                parent=parent_window  # Specifica la finestra padre
            )

    def dm_propose_price_dialog(self):
        """DM propone un prezzo alternativo per un oggetto in valutazione"""
        sel = self.bank_items_tree.selection()
        if not sel:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto in valutazione")
            return

        item_id = self.bank_items_tree.item(sel[0])["values"][0]
        item_name = self.bank_items_tree.item(sel[0])["values"][1]
        player_price = float(self.bank_items_tree.item(sel[0])["values"][3].replace(" MO", ""))
        status = self.bank_items_tree.item(sel[0])["values"][4]
        
        if status != "In valutazione":
            messagebox.showwarning("Attenzione", "Puoi proporre un prezzo solo per oggetti in valutazione")
            return

        # Ottieni la finestra padre (quella degli oggetti in banca)
        parent_window = self.bank_items_tree.winfo_toplevel()
        
        win = tk.Toplevel(parent_window)  # Specifica la finestra padre
        win.title("Propone prezzo banca")
        win.geometry("400x250")
        
        # ⭐⭐ AGGIUNGI QUESTE DUE RIGHE PER TENERE LA FINESTRA IN PRIMO PIANO
        win.transient(parent_window)  # Rende la finestra figlia
        win.grab_set()  # Blocca l'interazione con la finestra padre

        tk.Label(win, text=f"Oggetto: {item_name}").pack(pady=5)
        tk.Label(win, text=f"Prezzo richiesto dal giocatore: {player_price:.2f} MO").pack(pady=5)
        
        tk.Label(win, text="Prezzo proposto dalla banca (MO):").pack(pady=5)
        price_entry = tk.Entry(win, width=15)
        price_entry.insert(0, str(player_price * 0.8))  # Offerta iniziale: 80% del prezzo giocatore
        price_entry.pack(pady=5)
        
        # Focus sul campo prezzo
        price_entry.focus_set()
        price_entry.select_range(0, tk.END)  # Seleziona tutto il testo

        def submit():
            try:
                proposed_price = float(price_entry.get())
                if proposed_price <= 0:
                    messagebox.showerror("Errore", "Il prezzo deve essere maggiore di 0")
                    return

                cursor = self.db.cursor()
                
                # Registra la proposta del DM
                cursor.execute("""
                    INSERT INTO bank_item_evaluations 
                    (item_id, evaluator_role, value, created_at)
                    VALUES (%s, %s, %s, NOW())
                """, (item_id, 'DM', proposed_price))
                
                # AGGIUNTA PER NOTIFICHE: segna che c'è una nuova notifica per il giocatore
                cursor.execute("UPDATE bank_items SET player_notified = FALSE WHERE id = %s", (item_id,))
                
                self.db.commit()
                cursor.close()

                self.append_time_log(
                    f"Banca propone {proposed_price:.2f} MO per {item_name} (giocatore chiede {player_price:.2f} MO)."
                )
                
                win.destroy()
                self.load_bank_items(self.current_bank_id, self.current_pg_id)
                messagebox.showinfo("Successo", f"Prezzo proposto: {proposed_price:.2f} MO")
                
            except ValueError:
                messagebox.showerror("Errore", "Inserisci un prezzo valido")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore nella proposta: {e}")

        def on_closing():
            win.destroy()
            parent_window.focus_set()
        
        # Bind per Enter e Escape
        win.bind('<Return>', lambda e: submit())
        win.bind('<Escape>', lambda e: on_closing())
        
        # Pulsante centrato
        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Propone prezzo", command=submit).pack()
        
        # Bind per la chiusura della finestra
        win.protocol("WM_DELETE_WINDOW", on_closing)

    def dm_accept_player_price(self):
        """DM accetta il prezzo proposto dal giocatore"""
        sel = self.bank_items_tree.selection()
        if not sel:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto in valutazione")
            return

        item_id = self.bank_items_tree.item(sel[0])["values"][0]
        item_name = self.bank_items_tree.item(sel[0])["values"][1]
        quantity = self.bank_items_tree.item(sel[0])["values"][2]
        sale_price = float(self.bank_items_tree.item(sel[0])["values"][3].replace(" MO", ""))
        status = self.bank_items_tree.item(sel[0])["values"][4]
        
        if status != "In valutazione":
            messagebox.showwarning("Attenzione", "Puoi accettare solo oggetti in valutazione")
            return

        if not messagebox.askyesno("Conferma vendita",
                                  f"Accettare la vendita di {quantity}x {item_name} "
                                  f"per {sale_price:.2f} MO (prezzo del giocatore)?\n"
                                  f"Il denaro verrà accreditato sul conto bancario."):
            return

        try:
            cursor = self.db.cursor()
            
            # Ottieni bank_id per accreditare il denaro
            cursor.execute("SELECT bank_id FROM bank_items WHERE id = %s", (item_id,))
            result = cursor.fetchone()
            bank_id = result['bank_id']
            
            # Accredita il denaro
            cursor.execute("""
                UPDATE banks
                SET current_balance = current_balance + %s
                WHERE id = %s
            """, (sale_price, bank_id))
            
            # Aggiorna lo stato dell'oggetto
            cursor.execute("""
                UPDATE bank_items
                SET status = 'VENDUTO', evaluated_value = %s, request_sale = 0
                WHERE id = %s
            """, (sale_price, item_id))
            
            self.db.commit()
            cursor.close()

            self.append_time_log(
                f"Vendita accettata al prezzo del giocatore: {quantity}x {item_name} venduto per {sale_price:.2f} MO."
            )
            
            messagebox.showinfo("Successo", f"Vendita completata! {sale_price:.2f} MO accreditati.")
            self.load_bank_items(self.current_bank_id, self.current_pg_id)
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore nell'accettare la vendita: {e}")

    def dm_accept_dm_price(self):
        """DM accetta la propria proposta di prezzo"""
        sel = self.bank_items_tree.selection()
        if not sel:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto in valutazione")
            return

        item_id = self.bank_items_tree.item(sel[0])["values"][0]
        item_name = self.bank_items_tree.item(sel[0])["values"][1]
        quantity = self.bank_items_tree.item(sel[0])["values"][2]
        dm_price_text = self.bank_items_tree.item(sel[0])["values"][5]
        status = self.bank_items_tree.item(sel[0])["values"][4]
        
        if status != "In valutazione":
            messagebox.showwarning("Attenzione", "Puoi accettare solo oggetti in valutazione")
            return
        
        if dm_price_text == "—":
            messagebox.showwarning("Attenzione", "Prima propone un prezzo come DM")
            return
            
        dm_price = float(dm_price_text.replace(" MO", ""))

        if not messagebox.askyesno("Conferma vendita",
                                  f"Accettare la vendita di {quantity}x {item_name} "
                                  f"per {dm_price:.2f} MO (prezzo della banca)?\n"
                                  f"Il denaro verrà accreditato sul conto bancario."):
            return

        try:
            cursor = self.db.cursor()
            
            # Ottieni bank_id per accreditare il denaro
            cursor.execute("SELECT bank_id FROM bank_items WHERE id = %s", (item_id,))
            result = cursor.fetchone()
            bank_id = result['bank_id']
            
            # Accredita il denaro
            cursor.execute("""
                UPDATE banks
                SET current_balance = current_balance + %s
                WHERE id = %s
            """, (dm_price, bank_id))
            
            # Aggiorna lo stato dell'oggetto
            cursor.execute("""
                UPDATE bank_items
                SET status = 'VENDUTO', evaluated_value = %s, request_sale = 0
                WHERE id = %s
            """, (dm_price, item_id))
            
            self.db.commit()
            cursor.close()

            self.append_time_log(
                f"Vendita accettata al prezzo della banca: {quantity}x {item_name} venduto per {dm_price:.2f} MO."
            )
            
            messagebox.showinfo("Successo", f"Vendita completata! {dm_price:.2f} MO accreditati.")
            self.load_bank_items(self.current_bank_id, self.current_pg_id)
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore nell'accettare la vendita: {e}")

    def dm_reject_sale(self):
        """DM rifiuta la vendita e imposta lo stato a RIFIUTATO"""
        sel = self.bank_items_tree.selection()
        if not sel:
            messagebox.showwarning("Attenzione", "Seleziona un oggetto")
            return

        item_id = self.bank_items_tree.item(sel[0])["values"][0]
        item_name = self.bank_items_tree.item(sel[0])["values"][1]
        status = self.bank_items_tree.item(sel[0])["values"][4]

        if status != "In valutazione":
            messagebox.showwarning("Attenzione", "Puoi rifiutare solo oggetti in valutazione")
            return

        reason = tk.simpledialog.askstring("Motivo rifiuto",
                                          f"Motivo del rifiuto per {item_name}:",
                                          parent=self.root)
        
        if reason is None:  # L'utente ha cliccato Cancel
            return

        try:
            cursor = self.db.cursor()
            
            # Rimuovi eventuali valutazioni DM
            cursor.execute("""
                DELETE FROM bank_item_evaluations 
                WHERE item_id = %s
            """, (item_id,))
            
            # Imposta lo stato a RIFIUTATO e salva il motivo
            cursor.execute("""
                UPDATE bank_items
                SET status = 'RIFIUTATO', request_sale = 0, rejection_reason = %s
                WHERE id = %s
            """, (reason, item_id))

            cursor.execute("UPDATE bank_items SET player_notified = FALSE WHERE id = %s", (item_id,))

            self.db.commit()
            cursor.close()

            self.append_time_log(
                f"Vendita rifiutata per {item_name}. Motivo: {reason}"
            )
            
            messagebox.showinfo("Rifiutato", f"Vendita rifiutata. Oggetto marcato come 'Rifiutato'.")
            self.load_bank_items(self.current_bank_id, self.current_pg_id)
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore nel rifiutare la vendita: {e}")

    def show_item_details(self, tree):
        """Mostra dettagli completi dell'oggetto selezionato"""
        sel = tree.selection()
        if not sel:
            return
        
        item_id = tree.item(sel[0])["values"][0]
        
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT bi.*, ev.value AS dm_proposal, ev.created_at AS proposal_date
            FROM bank_items bi
            LEFT JOIN (
                SELECT item_id, value, created_at 
                FROM bank_item_evaluations 
                WHERE evaluator_role = 'DM'
                ORDER BY created_at DESC
                LIMIT 1
            ) ev ON bi.id = ev.item_id
            WHERE bi.id = %s
        """, (item_id,))
        
        item = cursor.fetchone()
        cursor.close()
        
        if not item:
            return
        
        # Ottieni la finestra padre (quella degli oggetti in banca)
        parent_window = tree.winfo_toplevel()
        
        win = tk.Toplevel(parent_window)  # Specifica esplicitamente la finestra padre
        win.title(f"Dettagli oggetto: {item['item_name']}")
        win.geometry("500x450")
        
        # Rendi questa finestra modale rispetto alla sua padre
        win.transient(parent_window)
        
        # NON USARE grab_set() per questa finestra secondaria
        # Invece, imposta il focus e rendila modale in modo più leggero
        win.focus_set()
        
        # Mostra tutti i dettagli in un Text widget
        text = tk.Text(win, wrap="word", height=20, width=60)
        text.pack(fill="both", expand=True, padx=10, pady=10)
        
        details = f"""OGGETTO: {item['item_name']}
    Quantità: {item['quantity']}
    Valore stimato: {item['declared_value'] or 0:.2f} MO
    Stato: {item['status']}
    """
        
        if item['status'] == 'RIFIUTATO' and item.get('rejection_reason'):
            details += f"Motivo rifiuto: {item['rejection_reason']}\n"
        
        if item['dm_proposal']:
            details += f"Proposta DM: {item['dm_proposal']:.2f} MO\n"
            if item['proposal_date']:
                try:
                    proposal_date = item['proposal_date']
                    mystara_date = self.convert_date_to_ded_format(proposal_date)
                    details += f"Data proposta: {mystara_date}\n"
                except Exception as e:
                    proposal_str = proposal_date.strftime("%Y-%m-%d %H:%M") if hasattr(proposal_date, 'strftime') else str(proposal_date)
                    details += f"Data proposta: {proposal_str}\n"
        
        if item['evaluated_value']:
            details += f"Valore finale vendita: {item['evaluated_value']:.2f} MO\n"
        
        try:
            abs_day = item['absolute_day']
            if abs_day is not None:
                date_from_abs = self.absolute_day_to_date(abs_day)
                mystara_deposit_date = self.convert_date_to_ded_format(date_from_abs)
                details += f"\nData deposito: {mystara_deposit_date}"
            else:
                details += f"\nData deposito: N/A"
        except Exception as e:
            details += f"\nData deposito: Errore conversione"
        
        text.insert("1.0", details)
        text.config(state="disabled")
        
        # Pulsante Chiudi con gestione corretta
        def close_window():
            win.destroy()
            # Ripristina il focus sulla finestra padre
            parent_window.focus_set()
        
        tk.Button(win, text="Chiudi", command=close_window).pack(pady=10)
        
        # Bind per chiudere con ESC
        win.bind('<Escape>', lambda e: close_window())
        
        # Bind per chiudere cliccando fuori (solo se non in modalità grab)
        def on_focus_out(event):
            if event.widget == win:
                # Permetti di chiudere cliccando fuori
                close_window()
        
        win.bind('<FocusOut>', on_focus_out)

    def show_all_sale_requests(self):
        """Mostra tutte le richieste di vendita per il DM (versione semplice)"""
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT bi.*, pc.name as pg_name, b.name as bank_name, b.id as bank_id
            FROM bank_items bi
            JOIN player_characters pc ON bi.pg_id = pc.id
            JOIN banks b ON bi.bank_id = b.id
            WHERE bi.status = 'IN_VALUTAZIONE'
            ORDER BY bi.id DESC
        """)
        
        items = cursor.fetchall()
        cursor.close()
        
        if not items:
            messagebox.showinfo("Nessuna richiesta", "Non ci sono richieste di vendita in attesa.")
            return
        
        # Finestra semplice con lista
        win = tk.Toplevel(self.root)
        win.title("📋 Richieste di Vendita")
        win.geometry("500x400")
        
        ttk.Label(win, text=f"Hai {len(items)} richiesta(e) di vendita:", 
                 font=('Arial', 11, 'bold')).pack(pady=10)
        
        # Frame scrollabile
        frame = ttk.Frame(win)
        frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(frame)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        for item in items:
            item_frame = ttk.Frame(scrollable_frame, relief='groove', borderwidth=1)
            item_frame.pack(fill='x', pady=2, padx=5)
            
            # Mostra tutte le informazioni, incluso il nome della banca
            info = f"• {item['item_name']} (x{item['quantity']}) - PG: {item['pg_name']}"
            info += f" - Banca: {item['bank_name']} - Prezzo: {item['declared_value']:.2f} MO"
            
            ttk.Label(item_frame, text=info, font=('Arial', 9)).pack(side='left', padx=5, pady=3)
            
            # Pulsante con nome banca
            ttk.Button(item_frame, text=f"Vai a {item['bank_name']}",
                      command=lambda b=item['bank_id'], bn=item['bank_name']: self.open_bank_and_close(b, bn, win),
                      width=20).pack(side='right', padx=5)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        ttk.Button(win, text="Chiudi", command=win.destroy).pack(pady=10)

    def open_bank_and_close(self, bank_id, bank_name, parent_window):
        """Apre la banca specifica e chiude la finestra delle richieste"""
        parent_window.destroy()
        self.show_banks_menu()
        messagebox.showinfo("Info", 
                           f"Vai al menu Banche e seleziona la banca:\n"
                           f"'{bank_name}' (ID: {bank_id})\n\n"
                           f"Poi clicca su 'Oggetti in Banca' per gestire la richiesta.")

    def show_player_notifications_simple(self):
        """Mostra notifiche giocatore (versione semplice)"""
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT bi.*, b.name as bank_name, ev.value as dm_proposal
            FROM bank_items bi
            JOIN banks b ON bi.bank_id = b.id
            LEFT JOIN (
                SELECT item_id, value 
                FROM bank_item_evaluations 
                WHERE evaluator_role = 'DM'
                ORDER BY created_at DESC
                LIMIT 1
            ) ev ON bi.id = ev.item_id
            WHERE bi.pg_id IN (
                SELECT id FROM player_characters WHERE user_id = %s
            )
            AND (
                (bi.status = 'RIFIUTATO' AND bi.player_notified = FALSE) OR
                (bi.status = 'IN_VALUTAZIONE' AND ev.value IS NOT NULL AND bi.player_notified = FALSE)
            )
            ORDER BY bi.id DESC
        """, (self.current_user['id'],))
        
        items = cursor.fetchall()
        cursor.close()
        
        if not items:
            messagebox.showinfo("Nessuna notifica", "Non hai notifiche non lette.")
            return
        
        # Finestra semplice con lista
        win = tk.Toplevel(self.root)
        win.title("📬 Le tue notifiche")
        win.geometry("400x500")
        
        ttk.Label(win, text=f"Hai {len(items)} notifica(e):", 
                 font=('Arial', 11, 'bold')).pack(pady=10)
        
        # Frame scrollabile
        frame = ttk.Frame(win)
        frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(frame)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        for item in items:
            item_frame = ttk.Frame(scrollable_frame, relief='groove', borderwidth=1)
            item_frame.pack(fill='x', pady=2, padx=5)
            
            if item['dm_proposal']:
                message = f"⭐ OFFERTA: {item['item_name']} - La banca offre {item['dm_proposal']:.2f} MO"
                color = 'green'
            else:
                reason = item.get('rejection_reason', 'Vendita rifiutata')
                message = f"⚠️ RIFIUTO: {item['item_name']} - {reason[:50]}{'...' if len(reason) > 50 else ''}"
                color = 'red'
            
            ttk.Label(item_frame, text=message, 
                     font=('Arial', 9),
                     foreground=color).pack(padx=5, pady=3)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Segna come lette
        def mark_as_read():
            for item in items:
                cursor = self.db.cursor()
                cursor.execute("UPDATE bank_items SET player_notified = TRUE WHERE id = %s", 
                              (item['id'],))
                self.db.commit()
                cursor.close()
            
            win.destroy()
            messagebox.showinfo("Lette", "Tutte le notifiche segnate come lette!")
            # Ricarica la schermata principale per rimuovere il banner
            self.show_main_menu()
        
        ttk.Button(win, text="Segna tutte come lette", command=mark_as_read).pack(pady=10)
        ttk.Button(win, text="Chiudi", command=win.destroy).pack(pady=5)

    def mark_bank_notifications_read(self, bank_id):
        """Segna le notifiche come lette quando l'utente accede alla banca"""
        cursor = self.db.cursor()
        
        if self.current_user['role'] == 'DM':
            # Per DM: segna tutte le notifiche di questa banca
            cursor.execute("""
                UPDATE bank_items 
                SET dm_notified = TRUE 
                WHERE bank_id = %s AND status = 'IN_VALUTAZIONE'
            """, (bank_id,))
        else:
            # Per giocatore: segna le sue notifiche in questa banca
            cursor.execute("""
                UPDATE bank_items 
                SET player_notified = TRUE 
                WHERE bank_id = %s AND pg_id IN (
                    SELECT id FROM player_characters WHERE user_id = %s
                )
            """, (bank_id, self.current_user['id']))
        
        self.db.commit()
        cursor.close()

    def show_followers_menu(self):
        """Mostra il menu seguaci, obiettivi e imprevisti"""
        self.clear_content()
        
        title = ttk.Label(self.content_frame, text="🛡️ Gestione Seguaci", style='Title.TLabel')
        title.pack(pady=10)
        
        # Notebook principale
        notebook = ttk.Notebook(self.content_frame)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # --- Tab Seguaci ---
        followers_frame = ttk.Frame(notebook)
        notebook.add(followers_frame, text="🛡️ Seguaci")
        self.create_followers_tab(followers_frame)
        
        # --- Tab Obiettivi ---
        objectives_frame = ttk.Frame(notebook)
        notebook.add(objectives_frame, text="🎯 Obiettivi")
        self.create_objectives_tab(objectives_frame)
        
        # --- Nuovo Tab Imprevisti ---
        events_frame = ttk.Frame(notebook)
        notebook.add(events_frame, text="🌀 Imprevisti")
        self.create_events_tab(events_frame)

    def load_followers_list(self, tree):
        """Carica la lista dei seguaci (senza ID) con banca e note, supporta ordinamento colonne"""
        if not tree:
            return  # sicurezza se il tree non è ancora creato

        # Pulisce la tabella
        for item in tree.get_children():
            tree.delete(item)
        
        try:
            cursor = self.db.cursor()

            if self.current_user['role'] == 'DM':
                query = """
                    SELECT f.id, f.name, f.class, f.level, f.annual_cost, 
                           f.notes, f.description, 
                           pc.name AS pg_name, 
                           u.username AS owner_name,
                           b.name AS bank_name
                    FROM followers f
                    LEFT JOIN player_characters pc ON f.pg_id = pc.id
                    LEFT JOIN users u ON pc.user_id = u.id
                    LEFT JOIN banks b ON f.bank_destination_cost = b.id
                    ORDER BY pc.name ASC, f.name ASC
                """
                cursor.execute(query)
            else:
                query = """
                    SELECT f.id, f.name, f.class, f.level, f.annual_cost, 
                           f.notes, f.description,
                           pc.name AS pg_name, 
                           u.username AS owner_name,
                           b.name AS bank_name
                    FROM followers f
                    LEFT JOIN player_characters pc ON f.pg_id = pc.id
                    LEFT JOIN users u ON pc.user_id = u.id
                    LEFT JOIN banks b ON f.bank_destination_cost = b.id
                    WHERE pc.user_id = %s
                    ORDER BY pc.name ASC, f.name ASC
                """
                cursor.execute(query, (self.current_user['id'],))
            
            followers = cursor.fetchall()

            for f in followers:
                iid = str(f['id'])
                vals = (
                    f.get('name', 'N/A'),
                    f.get('class', 'N/A'),
                    f.get('level', 0),
                    f"{float(f.get('annual_cost', 0)):.2f} MO",
                    f.get('bank_name', 'N/A'),
                    f.get('notes', ''),
                    f.get('description', ''),
                    f.get('pg_name', 'N/A'),
                    f.get('owner_name', 'N/A')
                )
                tree.insert('', 'end', iid=iid, values=vals)

        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento seguaci: {e}")

    def add_follower_dialog(self):
        """Dialog per aggiungere un seguace"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Aggiungi Seguace")
        dialog.geometry("450x650")

        # Nome
        ttk.Label(dialog, text="Nome Seguace:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=35)
        name_entry.pack(pady=5)

        # Classe
        ttk.Label(dialog, text="Classe:").pack(pady=5)
        class_entry = ttk.Entry(dialog, width=35)
        class_entry.pack(pady=5)

        # Livello
        ttk.Label(dialog, text="Livello:").pack(pady=5)
        level_spinbox = ttk.Spinbox(dialog, from_=1, to=36, width=33)
        level_spinbox.set(1)
        level_spinbox.pack(pady=5)

        # Costo annuale
        ttk.Label(dialog, text="Costo Annuale:").pack(pady=5)
        cost_entry = ttk.Entry(dialog, width=35)
        cost_entry.insert(0, "0")
        cost_entry.pack(pady=5)

        # Note
        ttk.Label(dialog, text="Note:").pack(pady=5)
        notes_text = tk.Text(dialog, width=35, height=4)
        notes_text.pack(pady=5)

        # Razza / descrizione
        ttk.Label(dialog, text="Razza (es. Umano, Elfo):").pack(pady=5)
        desc_entry = ttk.Entry(dialog, width=35)
        desc_entry.pack(pady=5)

        # PG associato
        ttk.Label(dialog, text="Seleziona PG:").pack(pady=5)

        cursor = self.db.cursor()
        if self.current_user['role'] == 'DM':
            cursor.execute("SELECT id, name FROM player_characters")
        else:
            cursor.execute("SELECT id, name FROM player_characters WHERE user_id = %s",
                           (self.current_user['id'],))
        pgs = cursor.fetchall()

        if not pgs:
            messagebox.showerror("Errore", "Nessun PG disponibile")
            dialog.destroy()
            return

        pg_combo = ttk.Combobox(dialog, width=33, state='readonly')
        pg_combo['values'] = [p['name'] for p in pgs]
        pg_combo.pack(pady=5)

        # ▼▼ BANCHE ▼▼
        ttk.Label(dialog, text="Banca da cui prelevare il costo annuale:").pack(pady=5)
        bank_combo = ttk.Combobox(dialog, width=33, state='readonly')
        bank_combo.pack(pady=5)

        def update_banks_for_pg(event=None):
            """Aggiorna la lista delle banche in base al PG selezionato"""
            selected_index = pg_combo.current()
            if selected_index < 0:
                return

            cursor = self.db.cursor()
            pg_id = pgs[selected_index]['id']
            cursor.execute("SELECT id, name FROM banks WHERE pg_id = %s ORDER BY name", (pg_id,))
            banks = cursor.fetchall()

            if banks:
                bank_combo['values'] = [f"{b['id']} - {b['name']}" for b in banks]
                bank_combo.current(0)
            else:
                bank_combo['values'] = []
                bank_combo.set("")

        pg_combo.bind("<<ComboboxSelected>>", update_banks_for_pg)
        pg_combo.current(0)
        update_banks_for_pg()  # inizializza

        def save_new_follower():
            try:
                name = name_entry.get().strip()
                f_class = class_entry.get().strip()
                level = int(level_spinbox.get())
                cost = float(cost_entry.get())
                notes = notes_text.get("1.0", "end").strip()
                race = desc_entry.get().strip()
                pg_index = pg_combo.current()
                bank_value = bank_combo.get().strip()

                if not name or pg_index < 0:
                    messagebox.showerror("Errore", "Nome e PG obbligatori")
                    return

                pg_id = pgs[pg_index]['id']
                bank_id = None
                if bank_value:
                    bank_id = int(bank_value.split(" - ")[0])

                cursor = self.db.cursor()
                cursor.execute("""
                    INSERT INTO followers (
                        pg_id, name, class, level, annual_cost, notes, bank_destination_cost, description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (pg_id, name, f_class, level, cost, notes, bank_id, race))

                self.db.commit()
                messagebox.showinfo("Successo", f"Seguace '{name}' aggiunto!")
                dialog.destroy()
                if self.tree_followers:
                    self.load_followers_list(self.tree_followers)
            except ValueError:
                messagebox.showerror("Errore", "Livello o costo annuale non valido")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore inserimento seguace: {e}")

        ttk.Button(dialog, text="💾 Salva", command=save_new_follower).pack(pady=15)

    def edit_follower_dialog(self, tree):
        if not tree:
            return

        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un seguace da modificare")
            return

        follower_id = selection[0]

        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM followers WHERE id = %s", (follower_id,))
        follower = cursor.fetchone()

        if not follower:
            messagebox.showerror("Errore", "Seguace non trovato")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Seguace")
        dialog.geometry("450x650")

        # Nome
        ttk.Label(dialog, text="Nome Seguace:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=35)
        name_entry.insert(0, follower['name'])
        name_entry.pack(pady=5)

        # Classe
        ttk.Label(dialog, text="Classe:").pack(pady=5)
        class_entry = ttk.Entry(dialog, width=35)
        class_entry.insert(0, follower.get('class', ''))
        class_entry.pack(pady=5)

        # Livello
        ttk.Label(dialog, text="Livello:").pack(pady=5)
        level_spinbox = ttk.Spinbox(dialog, from_=1, to=36, width=33)
        level_spinbox.set(follower.get('level', 1))
        level_spinbox.pack(pady=5)

        # Costo
        ttk.Label(dialog, text="Costo Annuale:").pack(pady=5)
        cost_entry = ttk.Entry(dialog, width=35)
        cost_entry.insert(0, str(follower.get('annual_cost', 0)))
        cost_entry.pack(pady=5)

        # Razza
        ttk.Label(dialog, text="Razza:").pack(pady=5)
        desc_entry = ttk.Entry(dialog, width=35)
        desc_entry.insert(0, follower.get('description', ''))
        desc_entry.pack(pady=5)

        # Note
        ttk.Label(dialog, text="Note:").pack(pady=5)
        notes_text = tk.Text(dialog, width=35, height=4)
        notes_text.insert(1.0, follower.get('notes', ''))
        notes_text.pack(pady=5)

        # ▼▼ Banca ▼▼
        ttk.Label(dialog, text="Banca per il costo annuale:").pack(pady=5)

        cursor.execute("SELECT id, name FROM banks WHERE pg_id = %s", (follower['pg_id'],))
        banks = cursor.fetchall()

        bank_combo = ttk.Combobox(dialog, width=33, state='readonly')
        bank_combo['values'] = [f"{b['id']} - {b['name']}" for b in banks]
        bank_combo.pack(pady=5)

        # seleziona banca attuale
        current_bank = follower.get('bank_destination_cost')
        if current_bank:
            for i, b in enumerate(banks):
                if b['id'] == current_bank:
                    bank_combo.current(i)
                    break

        def save_changes():
            name = name_entry.get().strip()
            f_class = class_entry.get().strip()
            level = int(level_spinbox.get())
            cost = float(cost_entry.get())
            desc = desc_entry.get().strip()
            notes = notes_text.get("1.0", "end").strip()
            bank_val = bank_combo.get().strip()

            bank_id = None
            if bank_val:
                bank_id = int(bank_val.split(" - ")[0])

            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE followers
                SET name=%s, class=%s, level=%s, annual_cost=%s,
                    description=%s, notes=%s, bank_destination_cost=%s
                WHERE id=%s
            """, (name, f_class, level, cost, desc, notes, bank_id, follower['id']))

            self.db.commit()
            messagebox.showinfo("Successo", "Seguace aggiornato!")
            dialog.destroy()
            if self.tree_followers:
                self.load_followers_list(self.tree_followers)

        ttk.Button(dialog, text="💾 Salva", command=save_changes).pack(pady=15)

    def remove_follower_action(self, tree):
        """Rimuove un seguace selezionato usando l'ID invisibile"""
        if not tree:
            return

        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un seguace da rimuovere")
            return

        follower_id = selection[0]

        confirm = messagebox.askyesno("Conferma", "Sei sicuro di voler eliminare questo seguace?")
        if not confirm:
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT COUNT(*) AS count
                FROM follower_objectives
                WHERE follower_id = %s
            """, (follower_id,))
            linked_objectives = cursor.fetchone().get('count', 0)
            if linked_objectives:
                messagebox.showwarning(
                    "Eliminazione bloccata",
                    "Non puoi eliminare questo seguace perché ha obiettivi collegati.\n\n"
                    f"- obiettivi: {linked_objectives}\n\n"
                    "Rimuovi o riassegna prima gli obiettivi del seguace."
                )
                return

            cursor.execute("DELETE FROM followers WHERE id = %s", (follower_id,))
            self.db.commit()
            messagebox.showinfo("Successo", "Seguace eliminato con successo!")
            if self.tree_followers:
                self.load_followers_list(self.tree_followers)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante l'eliminazione: {e}")

    def create_followers_tab(self, parent):
        """Crea il tab per la gestione dei seguaci con colonne adattive"""
        
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(pady=10)

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)

        columns = ('Nome', 'Classe', 'Liv', 'Costo', 'Banca', 'Note', 'Razza', 'PG', 'Giocatore')

        tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        self.tree_followers = tree
        
        # 🔹 MODIFICA: Larghezze proporzionali basate sul contenuto
        column_widths = {
            'Nome': 120,      # Più largo per nomi lunghi
            'Classe': 90,     # Classe può essere media
            'Liv': 60,        # Solo numeri
            'Costo': 80,      # Numeri
            'Banca': 110,     # Nome banca
            'Note': 200,      # Più largo per le note
            'Razza': 90,      # Razza media
            'PG': 120,        # Nome PG
            'Giocatore': 100  # Nome giocatore
        }
        
        for col in columns:
            tree.heading(col, text=col, command=lambda c=col: self.treeview_sort_column(tree, c, False))
            tree.column(col, width=column_widths.get(col, 100), anchor='center')

        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 🔹 AGGIUNTA: Bind per doppio click per aprire popup dettagli
        tree.bind("<Double-1>", lambda e: self.show_follower_details_popup(tree))

        # Pulsanti solo per DM
        if self.current_user['role'] == 'DM':
            ttk.Button(btn_frame, text="➕ Aggiungi Seguace", 
                       command=self.add_follower_dialog).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="✏️ Modifica", 
                       command=lambda: self.edit_follower_dialog(self.tree_followers)).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="🗑️ Rimuovi", 
                       command=lambda: self.remove_follower_action(self.tree_followers)).pack(side='left', padx=5)

        self.load_followers_list(tree)
  
    def create_objectives_tab(self, parent):
        """Crea il tab per la gestione degli obiettivi"""
        # Frame pulsanti in alto
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(pady=10)

        if self.current_user['role'] == 'DM':
            ttk.Button(btn_frame, text="➕ Aggiungi Obiettivo", 
                       command=lambda: self.add_objective_dialog()).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="✏️ Modifica", 
                       command=lambda: self.edit_objective_dialog(tree)).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="🗑️ Rimuovi", 
                       command=lambda: self.remove_objective_action(tree)).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="▶ Inizia", 
                       command=lambda: self.start_objective_action(tree)).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="📜 Cronologia Imprevisti", 
                       command=lambda: self.show_objective_events_dialog(tree)).pack(side='left', padx=5)

        # Frame lista
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Colonne (senza ID visibile)
        columns = ('Nome', 'Seguace', 'Stato', 'Progresso %', 'Durata (mesi)', 'Costo (MO)', 'Banca', 'Note')
        tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        for col in columns:
            tree.heading(col, text=col, command=lambda c=col: self.treeview_sort_column(tree, c, False))
            tree.column(col, width=130, anchor='center')

        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 🔹 AGGIUNTA: Bind per doppio click per aprire popup dettagli
        tree.bind("<Double-1>", lambda e: self.show_objective_details_popup(tree))

        # Carica lista
        self.load_objectives_list(tree)

    def create_events_tab(self, parent):
        """Crea il tab per la gestione degli imprevisti (solo DM)"""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(pady=10)

        if self.current_user['role'] == 'DM':
            ttk.Button(btn_frame, text="➕ Aggiungi Imprevisto",
                       command=self.add_objective_event_dialog).pack(side='left', padx=5)

            ttk.Button(btn_frame, text="✉️ Registra Scelta Giocatore",
                       command=self.register_objective_choice).pack(side='left', padx=5)

            ttk.Button(btn_frame, text="🗑 Rimuovi Imprevisto",
                       command=self.remove_objective_event).pack(side='left', padx=5)

        # --- Tabella elenco imprevisti ---
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)

        columns = ('Data', 'Descrizione', 'Obiettivo', 'Scelta Giocatore')
        self.tree_imprevisti = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        # Colonne
        for col in columns:
            self.tree_imprevisti.heading(
                col, text=col,
                command=lambda c=col: self.treeview_sort_column(self.tree_imprevisti, c, False)
            )
            width = 60 if col == 'ID' else 160
            self.tree_imprevisti.column(col, width=width, anchor='center')

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree_imprevisti.yview)
        self.tree_imprevisti.configure(yscrollcommand=scrollbar.set)
        self.tree_imprevisti.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Carica inizialmente i dati
        self.load_events_list(self.tree_imprevisti)

    def load_objectives_list(self, tree):
        """Carica la lista degli obiettivi (senza ID visibile)"""
        for item in tree.get_children():
            tree.delete(item)
        
        try:
            cursor = self.db.cursor()

            query = """
                SELECT fo.id, fo.name, fo.status, fo.progress_percentage, fo.estimated_months,
                       fo.total_cost, fo.notes, fo.start_date,
                       f.name AS follower_name, b.name AS bank_name
                FROM follower_objectives fo
                LEFT JOIN followers f ON fo.follower_id = f.id
                LEFT JOIN banks b ON fo.bank_id = b.id
            """
            if self.current_user['role'] != 'DM':
                query += """
                    JOIN player_characters pc ON f.pg_id = pc.id
                    WHERE pc.user_id = %s
                """
                cursor.execute(query, (self.current_user['id'],))
            else:
                cursor.execute(query)

            rows = cursor.fetchall()

            for r in rows:
                iid = str(r['id'])
                vals = (
                    r.get('name', 'N/A'),
                    r.get('follower_name', 'N/A'),
                    self.OBJECTIVE_STATUS_REV.get(r.get('status'), 'Sconosciuto'),
                    f"{float(r.get('progress_percentage', 0)):.1f}%",
                    r.get('estimated_months', 0),
                    f"{float(r.get('total_cost', 0)):.2f}",
                    r.get('bank_name', 'N/A'),
                    (r.get('notes', '') or '')[:40] + '...' if r.get('notes') else ''
                )
                tree.insert('', 'end', iid=iid, values=vals)

        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento obiettivi: {e}")

    def add_objective_dialog(self):
        """Dialog per aggiungere un nuovo obiettivo (solo DM)"""
        if self.current_user['role'] != 'DM':
            messagebox.showwarning("Permesso negato", "Solo il DM può aggiungere obiettivi.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Aggiungi Obiettivo")
        dialog.geometry("450x520")

        ttk.Label(dialog, text="Nome Obiettivo:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=35)
        name_entry.pack(pady=5)

        ttk.Label(dialog, text="Mesi Stimati:").pack(pady=5)
        months_spin = ttk.Spinbox(dialog, from_=1, to=120, width=33)
        months_spin.set(6)
        months_spin.pack(pady=5)

        ttk.Label(dialog, text="Costo Totale (MO):").pack(pady=5)
        cost_entry = ttk.Entry(dialog, width=35)
        cost_entry.insert(0, "0.0")
        cost_entry.pack(pady=5)

        ttk.Label(dialog, text="Note:").pack(pady=5)
        notes_text = tk.Text(dialog, width=35, height=3)
        notes_text.pack(pady=5)

        # Selezione seguace
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT f.id, f.name, f.pg_id, pc.name AS pg_name
            FROM followers f
            JOIN player_characters pc ON f.pg_id = pc.id
            ORDER BY pc.name, f.name
        """)
        followers = cursor.fetchall()
        if not followers:
            messagebox.showerror("Errore", "Nessun seguace trovato.")
            dialog.destroy()
            return

        ttk.Label(dialog, text="Seguace:").pack(pady=5)
        follower_combo = ttk.Combobox(dialog, width=33, state='readonly')
        follower_combo['values'] = [f"{f['name']} (PG: {f['pg_name']})" for f in followers]
        follower_combo.pack(pady=5)

        # Selezione banca
        ttk.Label(dialog, text="Banca per i costi:").pack(pady=5)
        banks = []
        bank_combo = ttk.Combobox(dialog, width=33, state='readonly')
        bank_combo.pack(pady=5)

        def update_objective_banks(_event=None):
            nonlocal banks
            follower_index = follower_combo.current()
            if follower_index < 0:
                banks = []
                bank_combo['values'] = []
                bank_combo.set("")
                return

            pg_id = followers[follower_index]['pg_id']
            cursor.execute("SELECT id, name FROM banks WHERE pg_id = %s ORDER BY name", (pg_id,))
            banks = cursor.fetchall()
            bank_combo['values'] = [b['name'] for b in banks]
            if banks:
                bank_combo.current(0)
            else:
                bank_combo.set("")

        follower_combo.bind("<<ComboboxSelected>>", update_objective_banks)
        follower_combo.current(0)
        update_objective_banks()

        def save_objective():
            try:
                name = name_entry.get().strip()
                months = int(months_spin.get())
                cost = float(cost_entry.get())
                notes = notes_text.get("1.0", tk.END).strip()
                if follower_combo.current() < 0:
                    messagebox.showwarning("Dati mancanti", "Seleziona un seguace.")
                    return
                if bank_combo.current() < 0:
                    messagebox.showwarning("Dati mancanti", "Il PG del seguace non ha banche disponibili per questo obiettivo.")
                    return

                follower_id = followers[follower_combo.current()]['id']
                bank_id = banks[bank_combo.current()]['id']

                cursor.execute("""
                    INSERT INTO follower_objectives
                    (follower_id, name, estimated_months, total_cost, notes, bank_id,
                     status, progress_percentage, base_estimated_months, base_total_cost)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    follower_id, name, months, cost, notes, bank_id,
                    self.OBJECTIVE_STATUS['NON_INIZIATO'], 0.0, months, cost
                ))
                self.db.commit()

                messagebox.showinfo("Successo", f"Obiettivo '{name}' aggiunto.")
                dialog.destroy()
                self.show_followers_menu()
            except Exception as e:
                messagebox.showerror("Errore", f"Errore inserimento: {e}")

        ttk.Button(dialog, text="✅ Salva Obiettivo", command=save_objective).pack(pady=10)

    def edit_objective_dialog(self, tree):
        """Modifica un obiettivo esistente (solo DM)"""
        if self.current_user['role'] != 'DM':
            messagebox.showwarning("Permesso negato", "Solo il DM può modificare obiettivi dei seguaci.")
            return

        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un obiettivo da modificare")
            return

        obj_id = selection[0]

        cursor = self.db.cursor()
        cursor.execute("""
            SELECT fo.*, f.name AS follower_name, b.name AS bank_name, pc.name AS pg_name
            FROM follower_objectives fo
            JOIN followers f ON fo.follower_id = f.id
            JOIN player_characters pc ON f.pg_id = pc.id
            LEFT JOIN banks b ON fo.bank_id = b.id
            WHERE fo.id = %s
        """, (obj_id,))
        objective = cursor.fetchone()
        if not objective:
            messagebox.showerror("Errore", "Obiettivo non trovato nel database.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Modifica Obiettivo - {objective['name']}")
        dialog.geometry("500x600")

        # Nome
        ttk.Label(dialog, text="Nome Obiettivo:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.insert(0, objective['name'])
        name_entry.pack(pady=5)

        # Mesi stimati
        ttk.Label(dialog, text="Mesi Stimati:").pack(pady=5)
        months_spin = ttk.Spinbox(dialog, from_=1, to=120, width=38)
        months_spin.set(objective.get('estimated_months', 1))
        months_spin.pack(pady=5)

        # Costo totale
        ttk.Label(dialog, text="Costo Totale (MO):").pack(pady=5)
        cost_entry = ttk.Entry(dialog, width=40)
        cost_entry.insert(0, str(objective.get('total_cost', 0)))
        cost_entry.pack(pady=5)

        # Note
        ttk.Label(dialog, text="Note:").pack(pady=5)
        notes_text = tk.Text(dialog, width=40, height=4)
        notes_text.insert(1.0, objective.get('notes', ''))
        notes_text.pack(pady=5)

        # Stato
        ttk.Label(dialog, text="Stato:").pack(pady=5)
        status_combo = ttk.Combobox(dialog, width=38, state='readonly')
        status_combo['values'] = list(self.OBJECTIVE_STATUS.keys())
        rev_map = {v: k for k, v in self.OBJECTIVE_STATUS.items()}
        current_status = self.OBJECTIVE_STATUS_REV.get(objective['status'], 'Sconosciuto')
        if current_status in status_combo['values']:
            status_combo.set(current_status)
        else:
            status_combo.current(0)
        status_combo.pack(pady=5)

        # Progresso
        ttk.Label(dialog, text="Progresso (%):").pack(pady=5)
        progress_spin = ttk.Spinbox(dialog, from_=0, to=100, width=38, increment=1)
        progress_spin.set(objective.get('progress_percentage', 0))
        progress_spin.pack(pady=5)

        # Seleziona nuovo seguace
        ttk.Label(dialog, text="Seguace:").pack(pady=5)
        cursor.execute("""
            SELECT f.id, f.name, f.pg_id, pc.name AS pg_name
            FROM followers f
            JOIN player_characters pc ON f.pg_id = pc.id
            ORDER BY pc.name, f.name
        """)
        followers = cursor.fetchall()
        follower_combo = ttk.Combobox(dialog, width=38, state='readonly')
        follower_combo['values'] = [f"{f['name']} (PG: {f['pg_name']})" for f in followers]
        for i, f in enumerate(followers):
            if f['id'] == objective['follower_id']:
                follower_combo.current(i)
                break
        follower_combo.pack(pady=5)

        # Seleziona banca
        ttk.Label(dialog, text="Banca:").pack(pady=5)
        banks = []
        bank_combo = ttk.Combobox(dialog, width=38, state='readonly')
        bank_combo.pack(pady=5)

        def update_banks_for_objective_follower(_event=None):
            nonlocal banks
            follower_index = follower_combo.current()
            if follower_index < 0:
                banks = []
                bank_combo['values'] = []
                bank_combo.set("")
                return

            pg_id = followers[follower_index]['pg_id']
            cursor.execute("SELECT id, name FROM banks WHERE pg_id = %s ORDER BY name", (pg_id,))
            banks = cursor.fetchall()
            bank_combo['values'] = [b['name'] for b in banks]
            bank_combo.set("")
            for i, b in enumerate(banks):
                if b['id'] == objective.get('bank_id'):
                    bank_combo.current(i)
                    break
            if banks and bank_combo.current() < 0:
                bank_combo.current(0)

        follower_combo.bind("<<ComboboxSelected>>", update_banks_for_objective_follower)
        update_banks_for_objective_follower()

        def save_changes():
            try:
                name = name_entry.get().strip()
                months = int(months_spin.get())
                cost = float(cost_entry.get())
                notes = notes_text.get("1.0", tk.END).strip()
                status_name = status_combo.get()
                status_value = self.OBJECTIVE_STATUS[status_name]
                progress = float(progress_spin.get())

                if follower_combo.current() < 0:
                    messagebox.showwarning("Dati mancanti", "Seleziona un seguace.")
                    return
                if bank_combo.current() < 0:
                    messagebox.showwarning("Dati mancanti", "Il PG del seguace non ha banche disponibili per questo obiettivo.")
                    return

                follower_id = followers[follower_combo.current()]['id']
                bank_id = banks[bank_combo.current()]['id']

                # Aggiorna start_date se cambia stato
                start_date = objective.get('start_date')
                if status_value == self.OBJECTIVE_STATUS['IN_CORSO'] and not start_date:
                    start_date = self.game_date.strftime('%Y-%m-%d')
                elif status_value != self.OBJECTIVE_STATUS['IN_CORSO'] and start_date:
                    start_date = None

                cursor.execute("""
                    UPDATE follower_objectives
                    SET name=%s, estimated_months=%s, total_cost=%s, notes=%s,
                        status=%s, progress_percentage=%s, follower_id=%s, bank_id=%s, start_date=%s
                    WHERE id=%s
                """, (name, months, cost, notes, status_value, progress, follower_id, bank_id, start_date, obj_id))
                self.db.commit()

                messagebox.showinfo("Successo", "Obiettivo aggiornato con successo.")
                dialog.destroy()
                self.show_followers_menu()

            except Exception as e:
                messagebox.showerror("Errore", f"Errore durante l'aggiornamento: {e}")

        ttk.Button(dialog, text="💾 Salva Modifiche", command=save_changes).pack(pady=10)

    def remove_objective_action(self, tree):
        """Rimuove un obiettivo selezionato"""
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un obiettivo da rimuovere")
            return

        obj_id = tree.item(selection[0])['iid']

        if not messagebox.askyesno("Conferma", "Eliminare definitivamente l'obiettivo selezionato?"):
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM follower_objectives WHERE id = %s", (obj_id,))
            self.db.commit()
            messagebox.showinfo("Successo", "Obiettivo eliminato con successo!")
            self.show_followers_menu()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante l'eliminazione: {e}")

    def show_follower_details_popup(self, tree):
        """Mostra popup con dettagli completi del seguace (versione senza doppia scrollbar)."""
        selected = tree.focus()
        if not selected:
            return
        
        try:
            follower_id = int(selected)
        except Exception:
            messagebox.showerror("Errore", "Impossibile leggere l'ID del seguace selezionato.")
            return
        
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT f.*, pc.name as pg_name, u.username as player_name,
                       b.name as bank_name
                FROM followers f
                LEFT JOIN player_characters pc ON f.pg_id = pc.id
                LEFT JOIN users u ON pc.user_id = u.id
                LEFT JOIN banks b ON f.bank_destination_cost = b.id
                WHERE f.id = %s
            """, (follower_id,))
            
            follower = cursor.fetchone()
            cursor.close()
            
            if not follower:
                messagebox.showwarning("Attenzione", "Seguace non trovato nel database.")
                return

            # --- Finestra popup con dimensioni automatiche ---
            win = tk.Toplevel(self.root)
            win.title(f"Dettagli Seguace: {follower.get('name', 'N/A')}")
            
            # Rende la finestra modale e sopra la principale
            win.transient(self.root)
            win.grab_set()
            
            # Calcola dimensioni in base al contenuto
            notes_text = follower.get('notes', '') or 'Nessuna nota'
            
            # Determina l'altezza in base alla lunghezza delle note
            note_lines = len(notes_text.split('\n'))
            
            if note_lines <= 5:
                text_height = 8
            elif note_lines <= 10:
                text_height = 12
            elif note_lines <= 20:
                text_height = 15
            else:
                text_height = 20
            
            # Imposta dimensioni fisse ma sufficienti
            win.geometry(f"750x550")  # Dimensioni generose per evitare scroll
            win.minsize(700, 450)

            # Frame principale SENZA scrollbar globale
            main_frame = ttk.Frame(win)
            main_frame.pack(fill='both', expand=True, padx=15, pady=15)
            
            # 🔸 Titolo
            ttk.Label(main_frame, text=f"👤 {follower.get('name', 'N/A')}", 
                     font=('Arial', 14, 'bold')).pack(pady=10)
            
            # 🔸 Informazioni base
            info_frame = ttk.LabelFrame(main_frame, text="Informazioni Base", padding=10)
            info_frame.pack(fill='x', pady=10)
            
            info_text = f"""Classe: {follower.get('class', 'N/A')}
    Livello: {follower.get('level', 'N/A')}
    Razza: {follower.get('description', 'N/A')}
    Costo Annuale: {float(follower.get('annual_cost', 0)):.2f} MO
    Banca: {follower.get('bank_name', 'N/A')}
    PG Proprietario: {follower.get('pg_name', 'N/A')}
    Giocatore: {follower.get('player_name', 'N/A')}"""
            
            ttk.Label(info_frame, text=info_text, justify='left').pack(anchor='w')
            
            # 🔸 Note complete - CON SOLO LA SCROLLBAR DELL'AREA TESTO
            notes_frame = ttk.LabelFrame(main_frame, text="Note Complete", padding=10)
            notes_frame.pack(fill='both', expand=True, pady=10)
            
            # Area testo con scrollbar integrata
            txt_notes = scrolledtext.ScrolledText(
                notes_frame, 
                wrap='word', 
                height=text_height,
                width=70,
                font=('Arial', 10)
            )
            txt_notes.insert('1.0', notes_text)
            txt_notes.config(state='disabled')
            txt_notes.pack(fill='both', expand=True, padx=5, pady=5)
            
            # 🔹 Pulsante di chiusura
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill='x', pady=10)
            
            ttk.Button(button_frame, text="Chiudi", 
                      command=win.destroy).pack(side='right')
            
            # 🔹 Focus sulla finestra popup
            win.focus_set()
            
            # 🔹 Bind per chiudere con ESC
            win.bind('<Escape>', lambda e: win.destroy())

            # Forza l'aggiornamento per calcolare le dimensioni corrette
            win.update_idletasks()
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore apertura dettagli seguace: {e}")

    def show_objective_details_popup(self, tree):
        """Mostra popup con dettagli completi dell'obiettivo (versione senza doppia scrollbar)."""
        selected = tree.focus()
        if not selected:
            return
        
        try:
            objective_id = int(selected)
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT fo.*, f.name as follower_name, pc.name as pg_name,
                       b.name as bank_name, u.username as player_name,
                       fo.start_date, fo.estimated_months, fo.total_cost,
                       fo.progress_percentage, fo.status, fo.notes
                FROM follower_objectives fo
                LEFT JOIN followers f ON fo.follower_id = f.id
                LEFT JOIN player_characters pc ON f.pg_id = pc.id
                LEFT JOIN users u ON pc.user_id = u.id
                LEFT JOIN banks b ON fo.bank_id = b.id
                WHERE fo.id = %s
            """, (objective_id,))
            
            objective = cursor.fetchone()
            cursor.close()
            
            if not objective:
                messagebox.showwarning("Attenzione", "Obiettivo non trovato nel database.")
                return

            # --- Finestra popup migliorata ---
            win = tk.Toplevel(self.root)
            win.title(f"Obiettivo: {objective.get('name', 'N/A')}")
            
            # Rende la finestra modale
            win.transient(self.root)
            win.grab_set()
            
            # Calcola dimensioni in base al contenuto
            notes_text = objective.get('notes', '') or 'Nessuna descrizione'
            note_lines = len(notes_text.split('\n'))
            
            if note_lines <= 5:
                text_height = 8
            elif note_lines <= 10:
                text_height = 12
            elif note_lines <= 20:
                text_height = 15
            else:
                text_height = 20
            
            # Imposta dimensioni fisse ma sufficienti
            win.geometry("700x550")
            win.minsize(650, 450)

            # Frame principale SENZA scrollbar globale
            main_frame = ttk.Frame(win)
            main_frame.pack(fill='both', expand=True, padx=15, pady=15)
            
            # 🔸 Titolo
            ttk.Label(main_frame, text=f"🎯 {objective.get('name', 'N/A')}", 
                     font=('Arial', 14, 'bold')).pack(pady=10)
            
            # 🔸 Informazioni base
            info_frame = ttk.LabelFrame(main_frame, text="Informazioni Obiettivo", padding=10)
            info_frame.pack(fill='x', pady=10)
            
            status_name = self.OBJECTIVE_STATUS_REV.get(objective.get('status'), 'Sconosciuto')
            start_date_raw = objective.get('start_date')

            if start_date_raw:
                try:
                    if isinstance(start_date_raw, datetime):
                        start_date_raw = start_date_raw.date()
                    start_date = self.convert_date_to_ded_format(start_date_raw)
                except Exception:
                    start_date = str(start_date_raw)
            else:
                start_date = "Non iniziato"
            
            info_text = f"""Seguace: {objective.get('follower_name', 'N/A')}
    PG Proprietario: {objective.get('pg_name', 'N/A')}
    Giocatore: {objective.get('player_name', 'N/A')}
    Stato: {status_name}
    Progresso: {float(objective.get('progress_percentage', 0)):.1f}%
    Data Inizio: {start_date}
    Durata Stimata: {objective.get('estimated_months', 0)} mesi
    Costo Totale: {float(objective.get('total_cost', 0)):.2f} MO
    Banca: {objective.get('bank_name', 'N/A')}"""
            
            ttk.Label(info_frame, text=info_text, justify='left').pack(anchor='w')
            
            # 🔸 Note complete - CON SOLO LA SCROLLBAR DELL'AREA TESTO
            notes_frame = ttk.LabelFrame(main_frame, text="Descrizione e Note", padding=10)
            notes_frame.pack(fill='both', expand=True, pady=10)
            
            # Area testo con scrollbar integrata
            txt_notes = scrolledtext.ScrolledText(
                notes_frame, 
                wrap='word', 
                height=text_height,
                width=70,
                font=('Arial', 10)
            )
            txt_notes.insert('1.0', notes_text)
            txt_notes.config(state='disabled')
            txt_notes.pack(fill='both', expand=True, padx=5, pady=5)
            
            # 🔹 Pulsante di chiusura
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill='x', pady=10)
            
            ttk.Button(button_frame, text="Chiudi", 
                      command=win.destroy).pack(side='right')
            
            # 🔹 Focus sulla finestra popup
            win.focus_set()
            
            # 🔹 Bind per chiudere con ESC
            win.bind('<Escape>', lambda e: win.destroy())

            # Forza l'aggiornamento per calcolare le dimensioni corrette
            win.update_idletasks()
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore apertura dettagli obiettivo: {e}")

    def show_event_details_popup(self, tree):
        """Mostra una finestra popup con i dettagli completi dell'imprevisto selezionato (versione senza doppia scrollbar)."""

        selected = tree.focus()
        if not selected:
            return

        try:
            event_id = int(selected)
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT e.event_date, e.description, 
                       fo.name AS objective_name, 
                       e.player_choice
                FROM follower_objective_events e
                LEFT JOIN follower_objectives fo ON e.objective_id = fo.id
                WHERE e.id = %s
            """, (event_id,))
            ev = cursor.fetchone()

            if not ev:
                messagebox.showwarning("Attenzione", "Evento non trovato nel database.")
                return

            # 🔹 Converti la data in formato Mystara
            event_date = ev.get('event_date')
            if event_date:
                if isinstance(event_date, datetime):
                    mystara_date = self.convert_date_to_ded_format(event_date)
                else:
                    try:
                        date_obj = datetime.strptime(str(event_date), "%Y-%m-%d").date()
                        mystara_date = self.convert_date_to_ded_format(date_obj)
                    except:
                        mystara_date = str(event_date)
            else:
                mystara_date = "Data sconosciuta"

            # --- Prepara i testi ---
            desc_text = ev.get('description', '') or '—'
            choice_raw = ev.get('player_choice', '') or '—'

            # 🔹 Se il campo "player_choice" è in formato JSON, estrai i dati
            try:
                choice_data = json.loads(choice_raw)
                if isinstance(choice_data, dict) and "option" in choice_data:
                    choice_text = choice_data["option"]
                    extra_cost = choice_data.get("extra_cost", 0)
                    extra_months = choice_data.get("extra_months", 0)
                    choice_formatted = f"{choice_text}\n\nCosto Extra: {extra_cost} MO\nMesi Extra: {extra_months}"
                else:
                    # Se è già solo testo
                    choice_formatted = str(choice_data)
            except json.JSONDecodeError:
                # Se non è JSON valido, lo mostriamo com'è
                choice_formatted = choice_raw

            # --- Finestra popup migliorata ---
            win = tk.Toplevel(self.root)
            win.title("Dettagli Imprevisto")
            
            # Rende la finestra modale
            win.transient(self.root)
            win.grab_set()
            
            # Dimensioni ottimali
            win.geometry("650x550")
            win.minsize(600, 450)

            # Frame principale SENZA scrollbar globale
            main_frame = ttk.Frame(win)
            main_frame.pack(fill='both', expand=True, padx=15, pady=15)
            
            # 🔸 Titolo e informazioni base
            ttk.Label(main_frame, text=f"Obiettivo: {ev.get('objective_name', 'N/A')}", 
                     font=('Arial', 12, 'bold')).pack(pady=5)
            ttk.Label(main_frame, text=f"📅 Data Evento: {mystara_date}", 
                     font=('Arial', 10)).pack(pady=5)

            # 🔸 Descrizione
            desc_frame = ttk.LabelFrame(main_frame, text="Descrizione", padding=10)
            desc_frame.pack(fill='both', expand=True, pady=10)
            
            txt_desc = scrolledtext.ScrolledText(
                desc_frame, 
                wrap='word', 
                height=8,
                width=70,
                font=('Arial', 10)
            )
            txt_desc.insert('1.0', desc_text)
            txt_desc.config(state='disabled')
            txt_desc.pack(fill='both', expand=True, padx=5, pady=5)

            # 🔸 Scelta del Giocatore
            choice_frame = ttk.LabelFrame(main_frame, text="Scelta del Giocatore", padding=10)
            choice_frame.pack(fill='both', expand=True, pady=10)
            
            txt_choice = scrolledtext.ScrolledText(
                choice_frame, 
                wrap='word', 
                height=6,
                width=70,
                font=('Arial', 10)
            )
            txt_choice.insert('1.0', choice_formatted)
            txt_choice.config(state='disabled')
            txt_choice.pack(fill='both', expand=True, padx=5, pady=5)
            
            # 🔹 Pulsante di chiusura
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill='x', pady=10)
            
            ttk.Button(button_frame, text="Chiudi", 
                      command=win.destroy).pack(side='right')
            
            # 🔹 Focus sulla finestra popup
            win.focus_set()
            
            # 🔹 Bind per chiudere con ESC
            win.bind('<Escape>', lambda e: win.destroy())

        except Exception as e:
            messagebox.showerror("Errore", f"Errore apertura dettagli: {e}")

    def load_events_list(self, tree):
        """Carica e aggiorna la lista degli imprevisti con testo pulito e popup dettagli."""

        # 🔹 Svuota tabella
        for i in tree.get_children():
            tree.delete(i)

        try:
            cursor = self.db.cursor()
            
            # 🔹 MODIFICA: Query con filtraggio per GIOCATORE/DM
            if self.current_user['role'] == 'GIOCATORE':
                query = """
                    SELECT e.id, e.event_date, e.description, 
                           fo.name AS objective_name, 
                           e.player_choice
                    FROM follower_objective_events e
                    LEFT JOIN follower_objectives fo ON e.objective_id = fo.id
                    LEFT JOIN followers f ON fo.follower_id = f.id  
                    LEFT JOIN player_characters pc ON f.pg_id = pc.id
                    WHERE pc.user_id = %s
                    ORDER BY e.event_date DESC
                """
                cursor.execute(query, (self.current_user['id'],))
            else:
                # DM vede tutto
                query = """
                    SELECT e.id, e.event_date, e.description, 
                           fo.name AS objective_name, 
                           e.player_choice
                    FROM follower_objective_events e
                    LEFT JOIN follower_objectives fo ON e.objective_id = fo.id
                    ORDER BY e.event_date DESC
                """
                cursor.execute(query)
                
            events = cursor.fetchall()

            for ev in events:
                # 🔹 MODIFICA: Converti la data in formato Mystara
                event_date = ev.get('event_date')
                if event_date:
                    # Se event_date è già un oggetto date, usa direttamente
                    if isinstance(event_date, datetime):
                        mystara_date = self.convert_date_to_ded_format(event_date)
                    else:
                        # Se è stringa, converti prima in date
                        try:
                            date_obj = datetime.strptime(str(event_date), "%Y-%m-%d").date()
                            mystara_date = self.convert_date_to_ded_format(date_obj)
                        except:
                            mystara_date = str(event_date)  # Fallback
                else:
                    mystara_date = "Data sconosciuta"

                # --- Pulisci descrizione ---
                desc_full = ev.get('description', '') or ''
                desc_clean = re.sub(r'["{}]', '', desc_full).strip()
                desc_short = (desc_clean[:80] + '...') if len(desc_clean) > 80 else desc_clean

                # --- Pulisci scelta ---
                choice_full = ev.get('player_choice', '') or '—'
                choice_clean = re.sub(r'["{}]|option:|option', '', choice_full, flags=re.IGNORECASE).strip()
                choice_short = (choice_clean[:60] + '...') if len(choice_clean) > 60 else choice_clean

                # 🔹 MODIFICA: Usa mystara_date invece di event_date
                vals = (
                    mystara_date,  # Data in formato Mystara
                    desc_short,
                    ev.get('objective_name', 'N/A'),
                    choice_short
                )

                # L'ID serve per modificare e rimuovere → lo mettiamo come iid
                tree.insert('', 'end', iid=str(ev['id']), values=vals)

            # 🔹 Associa popup dettagliato
            tree.bind("<Double-1>", lambda e: self.show_event_details_popup(tree))

        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento imprevisti: {e}")

    def show_objective_events_dialog(self, tree):
        """Visualizza la cronologia imprevisti per un obiettivo"""
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un obiettivo per vedere gli imprevisti.")
            return

        obj_id = selection[0]  # <-- usa direttamente l'iid della riga

        dialog = tk.Toplevel(self.root)
        dialog.title("📜 Cronologia Imprevisti")
        dialog.geometry("700x400")

        frame = ttk.Frame(dialog)
        frame.pack(fill='both', expand=True, padx=10, pady=10)

        tree_events = ttk.Treeview(frame, columns=('Data', 'Descrizione', 'Scelta'), show='headings', height=15)
        for c in ('Data', 'Descrizione', 'Scelta'):
            tree_events.heading(c, text=c)
            tree_events.column(c, width=220, anchor='center')
        tree_events.pack(fill='both', expand=True)

        try:
            cursor = self.db.cursor()
            
            # 🔹 MODIFICA: Query con filtraggio per GIOCATORE/DM
            if self.current_user['role'] == 'GIOCATORE':
                cursor.execute("""
                    SELECT e.event_date, e.description, e.player_choice
                    FROM follower_objective_events e
                    LEFT JOIN follower_objectives fo ON e.objective_id = fo.id
                    LEFT JOIN followers f ON fo.follower_id = f.id  
                    LEFT JOIN player_characters pc ON f.pg_id = pc.id
                    WHERE e.objective_id = %s AND pc.user_id = %s
                    ORDER BY e.event_date DESC
                """, (obj_id, self.current_user['id']))
            else:
                cursor.execute("""
                    SELECT event_date, description, player_choice
                    FROM follower_objective_events
                    WHERE objective_id = %s
                    ORDER BY event_date DESC
                """, (obj_id,))

            events = cursor.fetchall()
            for ev in events:
                # 🔹 MODIFICA: Converti la data in formato Mystara
                event_date = ev.get('event_date')
                if event_date:
                    if isinstance(event_date, datetime):
                        mystara_date = self.convert_date_to_ded_format(event_date)
                    else:
                        try:
                            date_obj = datetime.strptime(str(event_date), "%Y-%m-%d").date()
                            mystara_date = self.convert_date_to_ded_format(date_obj)
                        except:
                            mystara_date = str(event_date)
                else:
                    mystara_date = "Data sconosciuta"
                
                description = ev.get('description', '')
                player_choice = ev.get('player_choice', '')

                tree_events.insert('', 'end', values=(mystara_date, description, player_choice))

        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento cronologia: {e}")

    def register_objective_choice(self):
        """Finestra grafica per registrare la scelta del giocatore in un evento imprevisto"""
        if not self.current_user or self.current_user['role'] != 'DM':
            messagebox.showwarning("Permesso negato", "Solo un DM può registrare le scelte dei giocatori.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("📨 Registra Scelta del Giocatore")
        dialog.geometry("650x500")

        ttk.Label(dialog, text="Eventi in attesa di risposta:").pack(pady=5)

        frame = ttk.Frame(dialog)
        frame.pack(fill='both', expand=True, padx=10, pady=5)

        # Treeview eventi non gestiti
        tree = ttk.Treeview(frame, columns=("Descrizione", "Obiettivo"), show='headings', height=10)
        tree.heading("Descrizione", text="Descrizione")
        tree.heading("Obiettivo", text="Obiettivo")
        tree.column("Descrizione", width=400)
        tree.column("Obiettivo", width=200)
        tree.pack(fill='both', expand=True)

        # Carica eventi non gestiti
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT e.id, e.description, fo.name AS objective_name, e.response_options
            FROM follower_objective_events e
            JOIN follower_objectives fo ON e.objective_id = fo.id
            WHERE e.handled = FALSE AND (e.player_choice IS NULL OR e.player_choice = '')
            ORDER BY e.event_date DESC
        """)
        events = cursor.fetchall()

        if not events:
            messagebox.showinfo("Nessun evento", "Non ci sono eventi in attesa di scelta.")
            dialog.destroy()
            return

        for ev in events:
            tree.insert('', 'end', iid=str(ev['id']), values=(ev['description'], ev['objective_name']))

        # Area per opzioni e scelta
        ttk.Label(dialog, text="Opzioni disponibili:").pack(pady=5)
        options_box = tk.Listbox(dialog, height=6)
        options_box.pack(fill='both', expand=True, padx=10)

        ttk.Label(dialog, text="Scelta del giocatore:").pack(pady=5)
        choice_entry = ttk.Entry(dialog, width=60)
        choice_entry.pack(pady=5)

        def load_options_for_selected_event(_event):
            """Carica le opzioni quando selezioni un evento"""
            options_box.delete(0, tk.END)
            selection = tree.selection()
            if not selection:
                return

            ev_id = int(selection[0])
            selected = next((e for e in events if e['id'] == ev_id), None)
            if not selected:
                return

            options_raw = selected.get('response_options')
            if isinstance(options_raw, bytes):
                try:
                    options_raw = options_raw.decode("utf-8")
                except Exception:
                    pass

            try:
                options = json.loads(options_raw) if isinstance(options_raw, str) else options_raw
            except Exception:
                options = []

            if not options:
                options_box.insert(tk.END, "⚠️ Nessuna opzione disponibile.")
                return

            for i, opt in enumerate(options, 1):
                if isinstance(opt, dict):
                    text = f"{i}. {opt.get('option','')} (+{opt.get('extra_months',0)} mesi, +{opt.get('extra_cost',0)} MO)"
                    if opt.get('fail'):
                        text += " ❌ Fallimento"
                else:
                    text = f"{i}. {opt}"
                options_box.insert(tk.END, text)

        tree.bind("<<TreeviewSelect>>", load_options_for_selected_event)

        def save_choice():
            """Registra la scelta del giocatore nel DB"""
            try:
                selection = tree.selection()
                if not selection:
                    raise Exception("Seleziona un evento da aggiornare.")
                ev_id = int(selection[0])
                selected = next((e for e in events if e['id'] == ev_id), None)
                if not selected:
                    raise Exception("Evento non trovato.")

                options_raw = selected.get('response_options')
                if isinstance(options_raw, bytes):
                    options_raw = options_raw.decode("utf-8")

                options = json.loads(options_raw) if isinstance(options_raw, str) else []
                if not options:
                    raise Exception("Nessuna opzione valida per questo evento.")

                try:
                    idx = int(choice_entry.get().strip()) - 1
                    if not (0 <= idx < len(options)):
                        raise Exception("Numero scelta non valido.")
                except ValueError:
                    raise Exception("Inserisci un numero di scelta valido.")

                chosen = options[idx]
                extra_cost = chosen.get("extra_cost", 0) if isinstance(chosen, dict) else 0
                extra_months = chosen.get("extra_months", 0) if isinstance(chosen, dict) else 0

                cursor.execute("""
                    UPDATE follower_objective_events
                    SET player_choice = %s,
                        handled = FALSE,
                        extra_cost = %s,
                        extra_months = %s
                    WHERE id = %s
                """, (json.dumps(chosen, ensure_ascii=False), extra_cost, extra_months, ev_id))
                self.db.commit()
                
                # ✅ Aggiorna la lista degli imprevisti dopo la registrazione della scelta
                if hasattr(self, "tree_imprevisti"):
                    self.root.after(200, lambda: self.load_events_list(self.tree_imprevisti))

                messagebox.showinfo("Successo", "Scelta registrata correttamente.")
                dialog.destroy()

            except Exception as e:
                messagebox.showerror("Errore", str(e))

        ttk.Button(dialog, text="💾 Salva Scelta", command=save_choice).pack(pady=10)

    def start_objective_action(self, tree):
        """Inizia un obiettivo"""
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un obiettivo da iniziare")
            return

        obj_id = selection[0]  # <-- usa l'iid reale
        obj_name = tree.item(selection[0])['values'][1]  # il nome rimane values[1]

        if not messagebox.askyesno("Conferma", f"Iniziare l'obiettivo '{obj_name}'?"):
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE follower_objectives
                SET status = %s,
                    start_date = %s,
                    progress_percentage = 0.0,
                    base_estimated_months = COALESCE(base_estimated_months, estimated_months),
                    base_total_cost = COALESCE(base_total_cost, total_cost)
                WHERE id = %s
            """, (self.OBJECTIVE_STATUS['IN_CORSO'], self.game_date.strftime('%Y-%m-%d'), obj_id))
            self.db.commit()

            if cursor.rowcount == 0:
                messagebox.showwarning("Attenzione", "Nessun obiettivo aggiornato. Controlla l'ID.")
            else:
                messagebox.showinfo("Successo", "Obiettivo iniziato!")

            self.load_objectives_list(tree)

        except Exception as e:
            messagebox.showerror("Errore", f"Errore: {e}")

    def add_objective_event_dialog(self):
        """Dialog completo che crea un imprevisto, permette di modificare le opzioni e invia mail al giocatore"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Aggiungi Imprevisto (AI)")
        dialog.geometry("650x600")

        # --- Selezione Obiettivo ---
        ttk.Label(dialog, text="Seleziona Obiettivo:").pack(pady=5)
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT fo.id, fo.name, fo.follower_id, f.name AS follower_name
            FROM follower_objectives fo
            LEFT JOIN followers f ON fo.follower_id = f.id
            WHERE fo.status=%s
        """, (self.OBJECTIVE_STATUS['IN_CORSO'],))
        objs = cursor.fetchall()

        if not objs:
            messagebox.showwarning("Avviso", "Nessun obiettivo in corso")
            dialog.destroy()
            return

        combo = ttk.Combobox(dialog, values=[f"{o['name']} ({o['follower_name']})" for o in objs], state='readonly')
        combo.pack(pady=5)

        # --- Descrizione imprevisto ---
        ttk.Label(dialog, text="Descrizione Imprevisto:").pack(pady=5)
        desc = tk.Text(dialog, width=75, height=8)
        desc.pack(pady=5)

        # --- Opzioni AI ---
        ttk.Label(dialog, text="Opzioni generate (scegli una per default):").pack(pady=5)
        options_box = tk.Listbox(dialog, height=8)
        options_box.pack(fill='both', expand=False, padx=10, pady=5)

        # --- Funzione per generare opzioni ---
        def generate_options():
            text = desc.get('1.0', 'end').strip()
            if not text:
                messagebox.showwarning("Attenzione", "Inserisci una descrizione dell'imprevisto.")
                return

            options_box.delete(0, tk.END)

            try:
                if self.client:
                    self.generate_ai_options_for_event(text, options_box)
                else:
                    raise Exception("LM Studio non disponibile, uso fallback locale.")

            except Exception as e:
                print(f"⚠️ {e}")
                messagebox.showinfo("Info", "Generazione AI non disponibile — verranno usate opzioni di esempio.")

                fallback_options = [
                    {"option": "Il seguace trova un alleato imprevisto ma deve pagare un tributo.", "extra_months": 1, "extra_cost": 50.0},
                    {"option": "Il seguace affronta un ostacolo naturale e perde tempo prezioso.", "extra_months": 2, "extra_cost": 0.0},
                    {"option": "L’imprevisto si rivela fatale: il compito fallisce.", "extra_months": 0, "extra_cost": 0.0, "fail": True}
                ]

                for idx, opt in enumerate(fallback_options, 1):
                    display = f"{idx}. {opt['option']} (+{opt.get('extra_months',0)} mesi, +{opt.get('extra_cost',0):.2f} MO)"
                    if opt.get("fail"):
                        display += " ⚠️ Fallimento"
                    options_box.insert(tk.END, display)

                options_box.ai_options = fallback_options

        # --- Pulsante per generare le opzioni AI ---
        ttk.Button(dialog, text="✨ Genera Opzioni (AI)", command=generate_options).pack(pady=5)

        # --- Modifica Opzioni ---
        def edit_options():
            if not hasattr(options_box, "ai_options") or not options_box.ai_options:
                messagebox.showwarning("Avviso", "Prima genera le opzioni AI.")
                return

            edit_dialog = tk.Toplevel(dialog)
            edit_dialog.title("Modifica Opzioni")
            edit_dialog.geometry("600x400")

            entries = []

            for i, opt in enumerate(options_box.ai_options):
                frame = ttk.LabelFrame(edit_dialog, text=f"Opzione {i+1}")
                frame.pack(fill='x', padx=10, pady=5)

                ttk.Label(frame, text="Descrizione:").grid(row=0, column=0, sticky='w')
                txt = tk.Entry(frame, width=70)
                txt.insert(0, opt['option'])
                txt.grid(row=0, column=1, padx=5, pady=2)

                ttk.Label(frame, text="Mesi aggiuntivi:").grid(row=1, column=0, sticky='w')
                months = tk.Entry(frame, width=10)
                months.insert(0, str(opt.get('extra_months',0)))
                months.grid(row=1, column=1, sticky='w', padx=5, pady=2)

                ttk.Label(frame, text="Costo aggiuntivo MO:").grid(row=2, column=0, sticky='w')
                cost = tk.Entry(frame, width=10)
                cost.insert(0, str(opt.get('extra_cost',0)))
                cost.grid(row=2, column=1, sticky='w', padx=5, pady=2)

                ttk.Label(frame, text="Fallimento?").grid(row=3, column=0, sticky='w')
                fail_var = tk.BooleanVar(value=opt.get('fail', False))
                fail_chk = ttk.Checkbutton(frame, variable=fail_var)
                fail_chk.grid(row=3, column=1, sticky='w')

                entries.append((txt, months, cost, fail_var))

            def save_edits():
                for i, (txt, months, cost, fail_var) in enumerate(entries):
                    options_box.ai_options[i]['option'] = txt.get()
                    try:
                        options_box.ai_options[i]['extra_months'] = int(months.get())
                    except:
                        options_box.ai_options[i]['extra_months'] = 0
                    try:
                        options_box.ai_options[i]['extra_cost'] = float(cost.get())
                    except:
                        options_box.ai_options[i]['extra_cost'] = 0.0
                    options_box.ai_options[i]['fail'] = fail_var.get()

                # Aggiorna Listbox
                options_box.delete(0, tk.END)
                for idx, opt in enumerate(options_box.ai_options, 1):
                    display = f"{idx}. {opt['option']} (+{opt.get('extra_months',0)} mesi, +{opt.get('extra_cost',0):.2f} MO)"
                    if opt.get("fail"):
                        display += " ⚠️ Fallimento"
                    options_box.insert(tk.END, display)

                edit_dialog.destroy()

            ttk.Button(edit_dialog, text="💾 Salva Modifiche", command=save_edits).pack(pady=10)

        ttk.Button(dialog, text="✏️ Modifica Opzioni", command=edit_options).pack(pady=5)

        # --- Salva Evento ---
        def save_event():
            try:
                idx = combo.current()
                if idx < 0:
                    raise Exception("Seleziona un obiettivo valido")
                obj = objs[idx]

                description = desc.get('1.0','end').strip()
                if not description:
                    raise Exception("Inserisci la descrizione dell'imprevisto")

                if not hasattr(options_box, "ai_options") or not options_box.ai_options:
                    raise Exception("Genera prima le opzioni AI")

                ai_options = options_box.ai_options

                # Inserimento nel DB
                cursor.execute("""
                    INSERT INTO follower_objective_events 
                    (objective_id, description, type, response_options, event_date)
                    VALUES (%s,%s,%s,%s,%s)
                """, (
                    obj['id'], description, "IMPREVISTO", json.dumps(ai_options), self.game_date
                ))
                self.db.commit()
                
                # ✅ Aggiorna la lista degli imprevisti dopo il salvataggio
                if hasattr(self, "tree_imprevisti"):
                    self.root.after(200, lambda: self.load_events_list(self.tree_imprevisti))

                # Invio email al giocatore
                cursor.execute("SELECT id, name, pg_id FROM followers WHERE id=%s", (obj['follower_id'],))
                follower_data = cursor.fetchone()
                if follower_data:
                    pg_id = follower_data['pg_id']
                    follower_name = follower_data['name']

                    cursor.execute("SELECT user_id, name FROM player_characters WHERE id=%s", (pg_id,))
                    pg_data = cursor.fetchone()
                    if pg_data:
                        user_id = pg_data['user_id']
                        pg_name = pg_data['name']

                        cursor.execute("SELECT mail FROM users WHERE id=%s", (user_id,))
                        email_data = cursor.fetchone()
                        email = email_data['mail'] if email_data else None

                        if email:
                            subject = f"Imprevisto per {follower_name} nell'obiettivo '{obj['name']}'"
                            mystara_date = self.convert_date_to_ded_format(self.game_date)
                            body = f"Ciao {pg_name},\n\nIl tuo seguace **{follower_name}** ha incontrato un imprevisto durante l'obiettivo **{obj['name']}** in data {mystara_date}:\n\n➡️ {description}\n\nScegli una delle seguenti opzioni:\n"

                            for idx,opt in enumerate(ai_options,1):
                                body += f"{idx}. {opt['option']} (+{opt.get('extra_months',0)} mesi, +{opt.get('extra_cost',0):.2f} MO)"
                                if opt.get("fail"):
                                    body += " ⚠️ Fallimento"
                                body += "\n"

                            body += "\nRispondi a questa email scrivendo solo ad esempio: SCELTA: 2\n\nBuon gioco!"
                            self.send_email_notification(email, subject, body)
                            messagebox.showinfo("Successo", f"📧 Email inviata al giocatore {pg_name}")

                messagebox.showinfo("Successo", "Imprevisto salvato correttamente.")
                dialog.destroy()

            except Exception as e:
                messagebox.showerror("Errore", f"{e}")

        ttk.Button(dialog, text="💾 Salva Imprevisto", command=save_event).pack(pady=10)

    def generate_ai_options_for_event(self, description, listbox):
        """
        Genera opzioni AI in formato JSON (option, extra_months, extra_cost, fail)
        e le popola nella ListBox.
        """
        listbox.delete(0, tk.END)

        if not description:
            messagebox.showwarning("Attenzione", "Inserisci una descrizione dell'imprevisto.")
            return

        try:
            # ✅ Usa self.client invece di client
            if not self.client:
                raise Exception("Client AI (LM Studio) non inizializzato o non disponibile.")

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

            # ✅ Richiesta al modello AI
            response = self.client.chat.completions.create(
                model="mistral",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=400
            )

            content = response.choices[0].message.content

            # 🔹 Rimuove eventuali blocchi markdown come ```json ... ```
            cleaned = re.sub(r"```(?:json)?(.*?)```", r"\1", content, flags=re.DOTALL).strip()

            # 🔹 Parsing del JSON
            data = json.loads(cleaned)

            # 🔹 Validazione struttura
            if isinstance(data, list) and all("option" in o for o in data):
                for idx, opt in enumerate(data, 1):
                    display = f"{idx}. {opt['option']} (+{opt.get('extra_months',0)} mesi, +{opt.get('extra_cost',0):.2f} MO)"
                    if opt.get("fail"):
                        display += " ⚠️ Fallimento"
                    listbox.insert(tk.END, display)
                listbox.ai_options = data
            else:
                messagebox.showwarning("Attenzione", "Formato JSON non valido generato dall'AI.")
                listbox.ai_options = []

        except json.JSONDecodeError:
            messagebox.showerror("Errore", f"Impossibile interpretare il JSON generato dall'AI:\n{content}")
            listbox.ai_options = []

        except Exception as e:
            messagebox.showerror("Errore generazione AI", str(e))
            listbox.ai_options = []

    def remove_objective_event(self):
        """Rimuove un imprevisto selezionato nella tabella."""
        try:
            sel = self.tree_imprevisti.selection()
            if not sel:
                messagebox.showwarning("Avviso", "Seleziona un imprevisto da rimuovere.")
                return

            event_id = sel[0]  # L'IID È l'ID dell'imprevisto

            if not str(event_id).isdigit():
                messagebox.showerror("Errore", f"ID imprevisto non valido: {event_id}")
                return

            # Conferma
            if not messagebox.askyesno("Conferma", "Sei sicuro di voler eliminare questo imprevisto?"):
                return

            cursor = self.db.cursor()
            cursor.execute("DELETE FROM follower_objective_events WHERE id = %s", (event_id,))
            self.db.commit()

            # Rimuovi dalla GUI
            self.tree_imprevisti.delete(event_id)

            messagebox.showinfo("Successo", "Imprevisto rimosso con successo.")

        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante la rimozione: {e}")

    def show_economic_menu(self):
        """Mostra il menu attività economiche"""
        self.clear_content()
        
        title = ttk.Label(self.content_frame, text="⚒️ Attività Economiche", style='Title.TLabel')
        title.pack(pady=10)
        
        # Pulsanti azione
        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(pady=10)
        
        if self.current_user['role'] == 'DM':
            ttk.Button(btn_frame, text="➕ Aggiungi Attività", 
                      command=self.add_economic_activity_dialog).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="✏️ Modifica", 
                      command=lambda: self.edit_economic_activity(tree)).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="🗑️ Rimuovi", 
                      command=lambda: self.remove_economic_activity(tree)).pack(side='left', padx=5)
        
        # Lista attività
        list_frame = ttk.Frame(self.content_frame)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        columns = ('Descrizione', 'Guadagno', 'Frequenza', 'PG', 'Banca Dest.')
        tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            tree.heading(col, text=col, command=lambda _col=col: self.treeview_sort_column(tree, _col, False))
            if col == 'Descrizione':
                tree.column(col, width=250)
            else:
                tree.column(col, width=140)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 🔹 AGGIUNTA: Bind per doppio click per aprire popup dettagli attività economiche
        tree.bind("<Double-1>", lambda e: self.show_economic_activity_details_popup(tree))
        
        self.load_economic_activities(tree)
        self.tree_economic = tree

    def load_economic_activities(self, tree):
        """Carica le attività economiche nella tabella"""
        for item in tree.get_children():
            tree.delete(item)
        
        try:
            cursor = self.db.cursor()
            query = """
                SELECT ea.id, ea.description, ea.income, ea.frequency, 
                       pc.name AS pg_name, b.name AS bank_name
                FROM economic_activities ea
                LEFT JOIN player_characters pc ON ea.pg_id = pc.id
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
            """
            if self.current_user['role'] != 'DM':
                query += " WHERE pc.user_id = %s"
                cursor.execute(query, (self.current_user['id'],))
            else:
                cursor.execute(query)
            
            activities = cursor.fetchall()
            
            for act in activities:
                # Inserisci ID come "iid" nascosto ma non visibile
                tree.insert('', 'end', iid=str(act['id']), values=(
                    act['description'],
                    f"{float(act['income']):.2f} MO",
                    act['frequency'],
                    act.get('pg_name', 'N/A'),
                    act.get('bank_name', 'N/A')
                ))
                
        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento attività: {e}")

    def show_economic_activity_details_popup(self, tree):
        """Mostra popup con dettagli completi dell'attività economica (versione migliorata con auto-resize)."""
        selected = tree.focus()
        if not selected:
            return

        try:
            activity_id = int(selected)
        except Exception:
            messagebox.showerror("Errore", "Impossibile leggere l'ID dell'attività selezionata.")
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT ea.*, pc.name AS pg_name, b.name AS bank_name
                FROM economic_activities ea
                LEFT JOIN player_characters pc ON ea.pg_id = pc.id
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
                WHERE ea.id = %s
            """, (activity_id,))
            act = cursor.fetchone()
            cursor.close()

            if not act:
                messagebox.showwarning("Attenzione", "Attività economica non trovata.")
                return

            # Titolo abbreviato
            title_short = act["description"][:45] + ("..." if len(act["description"]) > 45 else "")

            win = tk.Toplevel(self.root)
            win.title(f"Dettagli Attività: {title_short}")

            # Finestra più grande come richiesto
            win.geometry("730x520")
            win.minsize(650, 480)

            main_frame = ttk.Frame(win)
            main_frame.pack(fill='both', expand=True, padx=10, pady=10)

            canvas = tk.Canvas(main_frame)
            scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
            scrollable = ttk.Frame(canvas)

            scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scrollable, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            # ★ INFO BASE
            info_frame = ttk.LabelFrame(scrollable, text="Informazioni", padding=10)
            info_frame.pack(fill='x', pady=5)

            info_text = f"""Entrata: {float(act['income']):.2f} MO
    Frequenza: {act['frequency']}
    PG Associato: {act.get('pg_name', 'N/A')}
    Banca Accredito: {act.get('bank_name', 'N/A')}"""

            ttk.Label(info_frame, text=info_text, justify='left').pack(anchor='w')

            # ★ DESCRIZIONE COMPLETA
            desc_frame = ttk.LabelFrame(scrollable, text="Descrizione Completa", padding=10)
            desc_frame.pack(fill='both', pady=5, expand=True)

            txt = scrolledtext.ScrolledText(desc_frame, wrap='word', height=10)
            txt.insert('1.0', act["description"])
            txt.config(state='disabled')
            txt.pack(fill='both', expand=True)

            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

        except Exception as e:
            messagebox.showerror("Errore", f"Errore apertura dettagli attività economica: {e}")

    def add_economic_activity_dialog(self):
        """Dialog per aggiungere attività economica"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Aggiungi Attività Economica")
        dialog.geometry("450x420")
        
        ttk.Label(dialog, text="Descrizione Attività:").pack(pady=5)
        desc_entry = ttk.Entry(dialog, width=35)
        desc_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Guadagno per periodo (MO):").pack(pady=5)
        income_entry = ttk.Entry(dialog, width=35)
        income_entry.insert(0, "0")
        income_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Frequenza:").pack(pady=5)
        freq_combo = ttk.Combobox(dialog, width=33, state='readonly')
        freq_combo['values'] = ['giornaliera', 'settimanale', 'mensile']
        freq_combo.current(2)
        freq_combo.pack(pady=5)
        
        ttk.Label(dialog, text="Seleziona PG:").pack(pady=5)
        cursor = self.db.cursor()
        cursor.execute("SELECT id, name FROM player_characters ORDER BY name")
        pgs = cursor.fetchall()
        
        pg_combo = ttk.Combobox(dialog, width=33, state='readonly')
        pg_combo['values'] = [p['name'] for p in pgs]
        pg_combo.pack(pady=5)
        
        ttk.Label(dialog, text="Banca Destinazione:").pack(pady=5)
        bank_combo = ttk.Combobox(dialog, width=33, state='readonly')
        bank_combo.pack(pady=5)
        
        def update_banks(*args):
            if pg_combo.current() < 0:
                return
            pg_id = pgs[pg_combo.current()]['id']
            cursor.execute("SELECT id, name FROM banks WHERE pg_id = %s ORDER BY name", (pg_id,))
            banks = cursor.fetchall()
            bank_combo['values'] = [b['name'] for b in banks]
            bank_combo.set('')
            bank_combo.bank_data = banks
        
        pg_combo.bind('<<ComboboxSelected>>', update_banks)
        
        def save_activity():
            try:
                description = desc_entry.get().strip()
                income = float(income_entry.get())
                frequency = freq_combo.get()
                
                if pg_combo.current() < 0:
                    messagebox.showerror("Errore", "Seleziona un PG")
                    return
                pg_id = pgs[pg_combo.current()]['id']
                
                bank_id = None
                if hasattr(bank_combo, "bank_data") and bank_combo.current() >= 0:
                    bank_id = bank_combo.bank_data[bank_combo.current()]['id']
                
                cursor.execute("""
                    INSERT INTO economic_activities (pg_id, description, income, frequency, destination_bank_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (pg_id, description, income, frequency, bank_id))
                self.db.commit()
                
                messagebox.showinfo("Successo", "Attività economica aggiunta!")
                dialog.destroy()
                self.load_economic_activities(self.tree_economic)
                
            except ValueError:
                messagebox.showerror("Errore", "Guadagno non valido")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore: {e}")
        
        ttk.Button(dialog, text="💾 Salva", command=save_activity).pack(pady=20)

    def edit_economic_activity(self, tree):
        """Modifica attività economica esistente (ora con selezione banca destinazione)"""
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Avviso", "Seleziona un'attività da modificare")
            return

        aid = sel[0]  # usa iid nascosto (ID)
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM economic_activities WHERE id=%s", (aid,))
        act = cursor.fetchone()
        if not act:
            messagebox.showerror("Errore", "Attività non trovata")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Attività Economica")
        dialog.geometry("480x440")

        ttk.Label(dialog, text="Descrizione:").pack(pady=5)
        desc = ttk.Entry(dialog, width=50)
        desc.insert(0, act.get('description', ''))
        desc.pack(pady=5)

        ttk.Label(dialog, text="Guadagno (MO):").pack(pady=5)
        inc = ttk.Entry(dialog, width=50)
        inc.insert(0, str(act.get('income', 0)))
        inc.pack(pady=5)

        ttk.Label(dialog, text="Frequenza:").pack(pady=5)
        freq = ttk.Combobox(dialog, values=['giornaliera', 'settimanale', 'mensile'], state='readonly')
        freq.set(act.get('frequency', 'mensile'))
        freq.pack(pady=5)

        # Selezione PG (mostro nome e uso pg_id per query banche)
        pg_id = act.get('pg_id')
        pg_name = ''
        try:
            if pg_id:
                cursor.execute("SELECT name FROM player_characters WHERE id = %s", (pg_id,))
                row = cursor.fetchone()
                pg_name = row.get('name') if row else ''
        except Exception:
            pg_name = ''

        ttk.Label(dialog, text=f"PG associato: {pg_name if pg_name else 'N/D'}").pack(pady=8)

        # Combobox per banche del PG
        ttk.Label(dialog, text="Banca Destinazione:").pack(pady=5)
        bank_combo = ttk.Combobox(dialog, width=40, state='readonly')
        bank_combo.pack(pady=5)

        # Carica banche del PG
        banks = []
        try:
            if pg_id:
                cursor.execute("SELECT id, name FROM banks WHERE pg_id = %s", (pg_id,))
                banks = cursor.fetchall()
        except Exception as e:
            # non blocco l'operazione, ma mostro comunque error nel combobox se serve
            print("Errore caricamento banche:", e)
            banks = []

        bank_names = [b['name'] for b in banks] if banks else []
        bank_combo['values'] = bank_names

        # Preseleziona la banca corrente se presente
        current_bank_id = act.get('destination_bank_id') or act.get('destination_bank_id', None)
        if current_bank_id and banks:
            for idx, b in enumerate(banks):
                if b['id'] == current_bank_id:
                    bank_combo.current(idx)
                    break
        else:
            bank_combo.set('')  # nessuna selezione

        def save_action():
            try:
                # calcola bank_id selezionata
                selected_bank_id = None
                if bank_combo.current() >= 0 and banks:
                    selected_bank_id = banks[bank_combo.current()]['id']

                cursor.execute("""
                    UPDATE economic_activities 
                    SET description=%s, income=%s, frequency=%s, destination_bank_id=%s
                    WHERE id=%s
                """, (desc.get().strip(), float(inc.get()), freq.get(), selected_bank_id, aid))
                self.db.commit()
                messagebox.showinfo("Successo", "Attività aggiornata!")
                dialog.destroy()
                self.load_economic_activities(tree)
            except ValueError:
                messagebox.showerror("Errore", "Guadagno non valido (usare un numero).")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore salvataggio: {e}")

        ttk.Button(dialog, text="💾 Salva", command=save_action).pack(pady=15)

    def remove_economic_activity(self, tree):
        """Rimuove attività economica selezionata"""
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Avviso", "Seleziona un'attività da rimuovere")
            return
        
        aid = sel[0]  # iid = ID attività
        if not messagebox.askyesno("Conferma", "Vuoi davvero eliminare l'attività selezionata?"):
            return
        
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM economic_activities WHERE id=%s", (aid,))
            self.db.commit()
            messagebox.showinfo("Rimosso", "Attività economica rimossa.")
            self.load_economic_activities(tree)
        except Exception as e:
            messagebox.showerror("Errore", f"Errore rimozione: {e}")

    def show_expenses_menu(self):
        """Mostra il menu spese fisse"""
        self.clear_content()
        
        title = ttk.Label(self.content_frame, text="💰 Spese Fisse", style='Title.TLabel')
        title.pack(pady=10)
        
        # Pulsanti azione
        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(pady=10)
        
        if self.current_user['role'] == 'DM':
            ttk.Button(btn_frame, text="➕ Aggiungi Spesa", 
                      command=self.add_fixed_expense_dialog).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="✏️ Modifica", 
                      command=lambda: self.edit_fixed_expense(tree)).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="🗑️ Rimuovi", 
                      command=lambda: self.remove_fixed_expense(tree)).pack(side='left', padx=5)
        
        list_frame = ttk.Frame(self.content_frame)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        columns = ('Descrizione', 'Ammontare', 'Frequenza', 'PG', 'Banca Origine')
        tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        for col in columns:
            tree.heading(col, text=col, command=lambda c=col: self.treeview_sort_column(tree, c, False))
            tree.column(col, width=160 if col != 'Descrizione' else 250)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        # 🔹 AGGIUNTA: Bind per doppio click per aprire popup dettagli spese fisse
        tree.bind("<Double-1>", lambda e: self.show_fixed_expense_details_popup(tree))
        
        tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        self.load_fixed_expenses(tree)

    def load_fixed_expenses(self, tree):
        """Carica le spese fisse"""
        for item in tree.get_children():
            tree.delete(item)
        
        try:
            cursor = self.db.cursor()
            query = """
                SELECT fe.*, pc.name AS pg_name, b.name AS bank_name
                FROM fixed_expenses fe
                LEFT JOIN player_characters pc ON fe.pg_id = pc.id
                LEFT JOIN banks b ON fe.source_bank_id = b.id
            """
            
            if self.current_user['role'] != 'DM':
                query += " WHERE pc.user_id = %s"
                cursor.execute(query, (self.current_user['id'],))
            else:
                cursor.execute(query)
            
            expenses = cursor.fetchall()
            for exp in expenses:
                tree.insert(
                    '',
                    'end',
                    iid=str(exp['id']),       # ← ID VERO DEL DB
                    values=(
                        exp['description'],
                        f"{float(exp['amount']):.2f} MO",
                        exp['frequency'],
                        exp.get('pg_name', 'N/A'),
                        exp.get('bank_name', 'N/A')
                    ))
                
        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento spese fisse: {e}")

    def show_fixed_expense_details_popup(self, tree):
        """Mostra popup con dettagli completi della spesa fissa (versione migliorata con resize automatico)."""
        selected = tree.focus()
        if not selected:
            return

        try:
            expense_id = int(selected)
        except Exception:
            messagebox.showerror("Errore", "Impossibile leggere la spesa selezionata.")
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT fe.*, pc.name AS pg_name, b.name AS bank_name
                FROM fixed_expenses fe
                LEFT JOIN player_characters pc ON fe.pg_id = pc.id
                LEFT JOIN banks b ON fe.source_bank_id = b.id
                WHERE fe.id = %s
            """, (expense_id,))
            exp = cursor.fetchone()
            cursor.close()

            if not exp:
                messagebox.showwarning("Attenzione", "Spesa non trovata.")
                return

            # Titolo abbreviato
            title_short = exp["description"][:45] + ("..." if len(exp["description"]) > 45 else "")

            win = tk.Toplevel(self.root)
            win.title(f"Dettagli Spesa: {title_short}")

            # 🔥 finestra più larga e più alta (si adatta meglio)
            win.geometry("730x520")  
            win.minsize(650, 480)

            main_frame = ttk.Frame(win)
            main_frame.pack(fill='both', expand=True, padx=10, pady=10)

            canvas = tk.Canvas(main_frame)
            scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
            scrollable = ttk.Frame(canvas)

            scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scrollable, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            # ★ INFO BASE
            info_frame = ttk.LabelFrame(scrollable, text="Informazioni", padding=10)
            info_frame.pack(fill='x', pady=5)

            info_text = f"""Ammontare: {float(exp['amount']):.2f} MO
    Frequenza: {exp['frequency']}
    PG Associato: {exp.get('pg_name', 'N/A')}
    Banca Origine: {exp.get('bank_name', 'N/A')}"""

            ttk.Label(info_frame, text=info_text, justify='left').pack(anchor='w')

            # ★ DESCRIZIONE COMPLETA — più stretta e ben leggibile
            desc_frame = ttk.LabelFrame(scrollable, text="Descrizione Completa", padding=10)
            desc_frame.pack(fill='both', pady=5, expand=True)

            txt = scrolledtext.ScrolledText(desc_frame, wrap='word', height=10)
            txt.insert('1.0', exp["description"])
            txt.config(state='disabled')
            txt.pack(fill='both', expand=True)

            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

        except Exception as e:
            messagebox.showerror("Errore", f"Errore apertura dettagli spesa: {e}")

    def add_fixed_expense_dialog(self):
        """Dialog per aggiungere una spesa fissa"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Aggiungi Spesa Fissa")
        dialog.geometry("450x420")
        
        ttk.Label(dialog, text="Descrizione Spesa:").pack(pady=5)
        desc_entry = ttk.Entry(dialog, width=35)
        desc_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Ammontare per periodo:").pack(pady=5)
        amount_entry = ttk.Entry(dialog, width=35)
        amount_entry.insert(0, "0")
        amount_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Frequenza:").pack(pady=5)
        freq_combo = ttk.Combobox(dialog, width=33, state='readonly')
        freq_combo['values'] = ['giornaliera', 'settimanale', 'mensile']
        freq_combo.current(2)
        freq_combo.pack(pady=5)
        
        # Seleziona PG
        ttk.Label(dialog, text="Seleziona PG:").pack(pady=5)
        cursor = self.db.cursor()
        cursor.execute("SELECT id, name FROM player_characters ORDER BY name")
        pgs = cursor.fetchall()
        
        pg_combo = ttk.Combobox(dialog, width=33, state='readonly')
        pg_combo['values'] = [p['name'] for p in pgs]
        pg_combo.pack(pady=5)
        
        # Seleziona banca
        ttk.Label(dialog, text="Banca Origine:").pack(pady=5)
        bank_combo = ttk.Combobox(dialog, width=33, state='readonly')
        bank_combo.pack(pady=5)

        def update_banks(*args):
            if pg_combo.current() < 0:
                return
            pg_id = pgs[pg_combo.current()]['id']
            cursor.execute("SELECT id, name FROM banks WHERE pg_id = %s", (pg_id,))
            banks = cursor.fetchall()
            bank_combo['values'] = [b['name'] for b in banks]
            bank_combo.bank_data = banks
            if banks:
                bank_combo.current(0)
            else:
                bank_combo.set("")

        pg_combo.bind('<<ComboboxSelected>>', update_banks)

        def save_expense():
            try:
                description = desc_entry.get().strip()
                amount = float(amount_entry.get())
                frequency = freq_combo.get()

                if not description:
                    messagebox.showerror("Errore", "Inserisci una descrizione valida.")
                    return
                if pg_combo.current() < 0:
                    messagebox.showerror("Errore", "Seleziona un personaggio.")
                    return

                pg_id = pgs[pg_combo.current()]['id']

                if bank_combo.current() < 0:
                    messagebox.showerror("Errore", "Seleziona una banca di origine.")
                    return

                bank_data = getattr(bank_combo, 'bank_data', [])
                bank_id = bank_data[bank_combo.current()]['id'] if bank_combo.current() >= 0 and bank_data else None

                cursor.execute("""
                    INSERT INTO fixed_expenses (pg_id, description, amount, frequency, source_bank_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (pg_id, description, amount, frequency, bank_id))
                self.db.commit()

                messagebox.showinfo("Successo", "Spesa fissa aggiunta!")
                dialog.destroy()
                self.show_expenses_menu()

            except Exception as e:
                messagebox.showerror("Errore", f"Errore salvataggio: {e}")

        ttk.Button(dialog, text="💾 Salva", command=save_expense).pack(pady=15)

    def edit_fixed_expense(self, tree):
        """Modifica una spesa fissa esistente usando l'ID nascosto della Treeview."""
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Avviso", "Seleziona una spesa da modificare.")
            return

        expense_id = sel[0]

        cursor = self.db.cursor()
        try:
            cursor.execute("SELECT * FROM fixed_expenses WHERE id = %s", (expense_id,))
            exp = cursor.fetchone()
            if not exp:
                messagebox.showerror("Errore", "Spesa non trovata nel database")
                return
        except Exception as e:
            messagebox.showerror("Errore", f"Errore nel caricamento della spesa: {e}")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Spesa Fissa")
        dialog.geometry("480x460")

        ttk.Label(dialog, text="Descrizione:").pack(pady=5)
        desc_entry = ttk.Entry(dialog, width=50)
        desc_entry.insert(0, exp.get('description', ''))
        desc_entry.pack(pady=5)

        ttk.Label(dialog, text="Ammontare (MO):").pack(pady=5)
        amount_entry = ttk.Entry(dialog, width=50)
        amount_entry.insert(0, str(exp.get('amount', 0)))
        amount_entry.pack(pady=5)

        ttk.Label(dialog, text="Frequenza:").pack(pady=5)
        freq_combo = ttk.Combobox(dialog, values=['giornaliera', 'settimanale', 'mensile'], state='readonly')
        freq_combo.set(exp.get('frequency', 'mensile'))
        freq_combo.pack(pady=5)

        # Selezione PG (personaggio)
        ttk.Label(dialog, text="Personaggio (PG):").pack(pady=5)
        try:
            cursor.execute("SELECT id, name FROM player_characters ORDER BY name")
            pgs = cursor.fetchall()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore recupero PG: {e}")
            dialog.destroy()
            return

        pg_combo = ttk.Combobox(dialog, width=45, state='readonly')
        pg_names = [p['name'] for p in pgs]
        pg_combo['values'] = pg_names
        pg_combo.pack(pady=5)

        # Preseleziona PG corrente se presente
        current_pg_id = exp.get('pg_id')
        if current_pg_id:
            for idx, p in enumerate(pgs):
                if p['id'] == current_pg_id:
                    pg_combo.current(idx)
                    break

        # Combobox banca
        ttk.Label(dialog, text="Banca Origine:").pack(pady=5)
        bank_combo = ttk.Combobox(dialog, width=45, state='readonly')
        bank_combo.pack(pady=5)
        bank_combo.banks = []

        def load_banks_for_pg(event=None):
            """Carica le banche relative al PG selezionato e preseleziona la corrente"""
            sel_idx = pg_combo.current()
            if sel_idx < 0:
                bank_combo['values'] = []
                bank_combo.set('')
                bank_combo.banks = []
                return
            selected_pg_id = pgs[sel_idx]['id']
            try:
                cursor.execute("SELECT id, name FROM banks WHERE pg_id = %s ORDER BY name", (selected_pg_id,))
                banks = cursor.fetchall()
            except Exception as e:
                messagebox.showerror("Errore", f"Errore recupero banche: {e}")
                banks = []

            bank_combo.banks = banks
            bank_combo['values'] = [b['name'] for b in banks]
            bank_combo.set('')

            # Preseleziona la banca corrente se corrisponde al PG
            current_bank_id = exp.get('source_bank_id')
            if current_bank_id and banks:
                for idx, b in enumerate(banks):
                    if b['id'] == current_bank_id:
                        bank_combo.current(idx)
                        break

        # Carica banche iniziali (in base al PG corrente)
        load_banks_for_pg()
        pg_combo.bind("<<ComboboxSelected>>", load_banks_for_pg)

        def save_changes():
            try:
                new_desc = desc_entry.get().strip()
                new_amount = float(amount_entry.get())
                new_freq = freq_combo.get()

                sel_pg_idx = pg_combo.current()
                new_pg_id = pgs[sel_pg_idx]['id'] if sel_pg_idx >= 0 else None

                sel_bank_idx = bank_combo.current()
                banks = getattr(bank_combo, 'banks', [])
                new_bank_id = banks[sel_bank_idx]['id'] if sel_bank_idx >= 0 and banks else None

                cursor.execute("""
                    UPDATE fixed_expenses
                    SET description=%s, amount=%s, frequency=%s, pg_id=%s, source_bank_id=%s
                    WHERE id=%s
                """, (new_desc, new_amount, new_freq, new_pg_id, new_bank_id, exp['id']))
                self.db.commit()

                messagebox.showinfo("Successo", "Spesa aggiornata con successo.")
                dialog.destroy()

                # ricarica la vista (usa la funzione che mostra il menu spese)
                try:
                    self.show_expenses_menu()
                except Exception:
                    # Se preferisci ricaricare solo la lista:
                    try:
                        self.load_fixed_expenses(tree)
                    except Exception:
                        pass

            except ValueError:
                messagebox.showerror("Errore", "Ammontare non valido (usa un numero).")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore aggiornamento: {e}")

        ttk.Button(dialog, text="💾 Salva", command=save_changes).pack(pady=15)

    def remove_fixed_expense(self, tree):
        """Rimuove una spesa fissa"""
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona una spesa da rimuovere.")
            return

        expense_id = selection[0]
        desc = tree.item(selection[0])['values'][0]
        if not messagebox.askyesno("Conferma", f"Eliminare la spesa '{desc}'?"):
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM fixed_expenses WHERE id = %s", (expense_id,))
            self.db.commit()
            messagebox.showinfo("Successo", "Spesa rimossa.")
            self.show_expenses_menu()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore eliminazione: {e}")

    def show_users_menu(self):
        """Mostra il menu gestione utenti"""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Accesso negato", "Solo il DM puo' gestire gli utenti.")
            return

        self.clear_content()
        
        title = ttk.Label(self.content_frame, text="👥 Gestione Utenti", style='Title.TLabel')
        title.pack(pady=10)
        
        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="➕ Aggiungi Utente", command=self.add_user_dialog).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Modifica", command=self.edit_user_dialog).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Elimina", command=self.remove_user_action).pack(side='left', padx=5)
        # 🔄 Pulsante "Aggiorna" rimosso, non necessario
        
        # Lista utenti
        self.show_users_list()

    def show_users_list(self):
        """Mostra la lista utenti (senza mostrare l'ID, ma lo mantiene per operazioni)"""
        list_frame = ttk.Frame(self.content_frame)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)

        columns = ('Username', 'Mail', 'Ruolo')  # ID non incluso nelle colonne
        self.tree_users = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        for col in columns:
            self.tree_users.heading(col, text=col, command=lambda c=col: self.treeview_sort_column(self.tree_users, c, False))
            self.tree_users.column(col, width=180, anchor='center')

        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree_users.yview)
        self.tree_users.configure(yscrollcommand=scrollbar.set)
        self.tree_users.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT id, username, mail, role
                FROM users
                ORDER BY username ASC
            """)
            users = cursor.fetchall()

            for u in users:
                iid = str(u['id'])  # L'ID resta invisibile ma identificabile
                self.tree_users.insert('', 'end', iid=iid, values=(
                    u.get('username', 'N/A'),
                    u.get('mail', 'N/A'),
                    u.get('role', 'N/A')
                ))

        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento utenti: {e}")
        
    def add_user_dialog(self):
        """Aggiunge un nuovo utente"""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Accesso negato", "Solo il DM puo' creare utenti.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Nuovo Utente")
        dialog.geometry("400x350")

        ttk.Label(dialog, text="Username:").pack(pady=5)
        username_entry = ttk.Entry(dialog, width=30)
        username_entry.pack(pady=5)

        ttk.Label(dialog, text="Mail:").pack(pady=5)
        mail_entry = ttk.Entry(dialog, width=30)
        mail_entry.pack(pady=5)

        ttk.Label(dialog, text="Password:").pack(pady=5)
        password_entry = ttk.Entry(dialog, width=30, show="*")
        password_entry.pack(pady=5)

        ttk.Label(dialog, text="Ruolo:").pack(pady=5)
        role_combo = ttk.Combobox(dialog, width=28, state='readonly')
        role_combo['values'] = ['GIOCATORE', 'DM']
        role_combo.current(0)
        role_combo.pack(pady=5)

        def save_user():
            username = username_entry.get().strip()
            mail = mail_entry.get().strip()
            password = password_entry.get().strip()
            role = role_combo.get().strip()

            if not username or not mail or not password:
                messagebox.showerror("Errore", "Compila tutti i campi obbligatori")
                return

            try:
                cursor = self.db.cursor()
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                if cursor.fetchone():
                    messagebox.showerror("Errore", "Esiste gia' un utente con questo username.")
                    return

                cursor.execute("""
                    INSERT INTO users (username, mail, password, role)
                    VALUES (%s, %s, %s, %s)
                """, (username, mail, password, role))
                self.db.commit()
                messagebox.showinfo("Successo", "Utente creato correttamente!")
                dialog.destroy()
                self.show_users_menu()
            except Exception as e:
                messagebox.showerror("Errore", f"Errore creazione utente: {e}")

        ttk.Button(dialog, text="💾 Salva", command=save_user).pack(pady=20)

    def edit_user_dialog(self, tree=None):
        """Modifica un utente esistente usando l'ID invisibile"""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Accesso negato", "Solo il DM puo' modificare gli utenti.")
            return

        tree = tree or getattr(self, 'tree_users', None)
        if tree is None:
            messagebox.showerror("Errore", "Lista utenti non inizializzata")
            return

        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un utente da modificare")
            return

        user_id = selection[0]  # usa l'iid invisibile
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            messagebox.showerror("Errore", "Utente non trovato")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Modifica Utente")
        dialog.geometry("400x350")

        ttk.Label(dialog, text="Username:").pack(pady=5)
        username_entry = ttk.Entry(dialog, width=30)
        username_entry.insert(0, user.get('username', ''))
        username_entry.pack(pady=5)

        ttk.Label(dialog, text="Mail:").pack(pady=5)
        mail_entry = ttk.Entry(dialog, width=30)
        mail_entry.insert(0, user.get('mail', ''))
        mail_entry.pack(pady=5)

        ttk.Label(dialog, text="Ruolo:").pack(pady=5)
        role_combo = ttk.Combobox(dialog, width=28, state='readonly')
        role_combo['values'] = ['GIOCATORE', 'DM']
        role_combo.set(user.get('role', 'GIOCATORE'))
        role_combo.pack(pady=5)

        ttk.Label(dialog, text="Nuova Password (opzionale):").pack(pady=5)
        password_entry = ttk.Entry(dialog, width=30, show='*')
        password_entry.pack(pady=5)

        def save_changes():
            username = username_entry.get().strip()
            mail = mail_entry.get().strip()
            role = role_combo.get().strip()
            password = password_entry.get().strip()

            if not username or not mail:
                messagebox.showerror("Errore", "Compila tutti i campi obbligatori")
                return

            try:
                cursor.execute(
                    "SELECT id FROM users WHERE username = %s AND id <> %s",
                    (username, user_id)
                )
                if cursor.fetchone():
                    messagebox.showerror("Errore", "Esiste gia' un altro utente con questo username.")
                    return

                if password:
                    cursor.execute("""
                        UPDATE users SET username=%s, mail=%s, role=%s, password=%s WHERE id=%s
                    """, (username, mail, role, password, user_id))
                else:
                    cursor.execute("""
                        UPDATE users SET username=%s, mail=%s, role=%s WHERE id=%s
                    """, (username, mail, role, user_id))
                self.db.commit()
                messagebox.showinfo("Successo", "Utente aggiornato correttamente!")
                dialog.destroy()
                self.show_users_menu()
            except Exception as e:
                messagebox.showerror("Errore", f"Errore aggiornamento utente: {e}")

        ttk.Button(dialog, text="💾 Salva", command=save_changes).pack(pady=20)

    def remove_user_action(self, tree=None):
        """Elimina un utente usando l'ID invisibile"""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Accesso negato", "Solo il DM puo' eliminare gli utenti.")
            return

        tree = tree or getattr(self, 'tree_users', None)
        if tree is None:
            messagebox.showerror("Errore", "Lista utenti non inizializzata")
            return

        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un utente da eliminare")
            return

        user_id = selection[0]  # usa l'iid invisibile
        username = tree.item(selection[0])['values'][0]  # prende username dalla colonna visibile

        if not messagebox.askyesno("Conferma", f"Vuoi eliminare l'utente '{username}'?"):
            return

        try:
            cursor = self.db.cursor()
            checks = [
                ("personaggi", "SELECT COUNT(*) AS count FROM player_characters WHERE user_id = %s", (user_id,)),
                ("banche", "SELECT COUNT(*) AS count FROM banks WHERE user_id = %s", (user_id,)),
                ("movimenti bancari", "SELECT COUNT(*) AS count FROM bank_transactions WHERE user_id = %s", (user_id,)),
                ("messaggi inviati", "SELECT COUNT(*) AS count FROM chat_messages WHERE sender_id = %s", (user_id,)),
                ("messaggi ricevuti", "SELECT COUNT(*) AS count FROM chat_messages WHERE receiver_id = %s", (user_id,)),
                ("letture chat", "SELECT COUNT(*) AS count FROM chat_reads WHERE user_id = %s", (user_id,)),
            ]
            linked_data = []
            for label, sql, params in checks:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                count = row.get('count', 0) if row else 0
                if count:
                    linked_data.append(f"{label}: {count}")

            if linked_data:
                messagebox.showerror(
                    "Eliminazione bloccata",
                    "Impossibile eliminare questo utente perche' ha dati collegati:\n\n"
                    + "\n".join(linked_data)
                    + "\n\nRiassegna o rimuovi prima questi dati."
                )
                return

            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            self.db.commit()
            messagebox.showinfo("Successo", f"Utente '{username}' eliminato!")
            self.show_users_menu()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore eliminazione utente: {e}")

    def show_backup_menu(self):
        """Mostra il menu backup"""
        self.clear_content()
        
        title = ttk.Label(self.content_frame, text="💾 Backup Database", style='Title.TLabel')
        title.pack(pady=10)
        
        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text="💾 Crea Backup", 
                  command=self.create_backup_action, 
                  width=20).pack(pady=10)
        ttk.Button(btn_frame, text="♻️ Ripristina Backup", 
                  command=self.restore_backup_action, 
                  width=20).pack(pady=10)
    
    def create_backup_action(self):
        """Crea un backup del database"""
        if not messagebox.askyesno("Conferma", "Creare un backup del database?"):
            return
        
        try:
            backup_dir = "backups"
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            tables = self.get_backup_table_names()
            
            cursor = self.db.cursor()
            
            for table in tables:
                cursor.execute(f"SELECT * FROM {table}")
                data = cursor.fetchall()
                
                # Conversione sicura per JSON
                converted_data = []
                for row in data:
                    converted_row = {}
                    for k, v in row.items():
                        if isinstance(v, Decimal):
                            converted_row[k] = float(v)
                        elif isinstance(v, (date, datetime)):
                            converted_row[k] = v.isoformat()
                        elif isinstance(v, bytes):
                            try:
                                converted_row[k] = v.decode("utf-8")
                            except:
                                converted_row[k] = v.hex()
                        else:
                            converted_row[k] = v
                    converted_data.append(converted_row)
                
                filename = os.path.join(backup_dir, f"{table}_backup_{timestamp}.json")
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(converted_data, f, ensure_ascii=False, indent=4)
            
            messagebox.showinfo("Successo", f"Backup creato nella cartella '{backup_dir}'")
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante il backup: {e}")
    
    def restore_backup_action(self):
        """Ripristina un backup"""
        messagebox.showinfo("In Sviluppo", 
                          "Funzionalità ripristino backup in fase di implementazione GUI.\n"
                          "Utilizzare lo script Python originale per il restore.")
    
    def show_status(self):
        """Mostra lo stato della campagna come nel vecchio sistema"""
        self.clear_content()
        
        # Header con titolo e pulsante stampa
        header_frame = ttk.Frame(self.content_frame)
        header_frame.pack(fill='x', pady=10)
        
        title = ttk.Label(header_frame, text="📊 Stato Campagna", style='Title.TLabel')
        title.pack(side='left', padx=10)
        
        print_btn = ttk.Button(header_frame, text="🖨️ Esporta TXT",
                              command=lambda: self.export_status_to_txt(scrollable_frame))
        print_btn.pack(side='right', padx=10)
        
        # Container principale con scrollbar
        container = ttk.Frame(self.content_frame)
        container.pack(fill='both', expand=True)
        
        # Canvas e scrollbar con larghezza ridotta (usa tk.Scrollbar invece di ttk.Scrollbar)
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview, width=12)
        scrollable_frame = ttk.Frame(canvas)
        
        # Configura il canvas per espandersi correttamente
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=canvas.winfo_width())
        
        def on_canvas_configure(event):
            # Aggiorna la larghezza del frame interno quando il canvas viene ridimensionato
            canvas.itemconfig(canvas.find_withtag("all")[0], width=event.width)
        
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        canvas.bind("<Configure>", on_canvas_configure)
        scrollable_frame.bind("<Configure>", on_frame_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        try:
            cursor = self.db.cursor()

            # Data di gioco
            date_frame = ttk.LabelFrame(scrollable_frame, text="📅 Data di Gioco", padding=10)
            date_frame.pack(fill='x', padx=10, pady=5)
            ttk.Label(date_frame, text=self.convert_date_to_ded_format(self.game_date),
                     font=('Arial', 12, 'bold')).pack()

            # 1. PGs e utente associato
            if self.current_user and self.current_user['role'] == 'GIOCATORE':
                cursor.execute("""
                    SELECT pc.id, pc.name, pc.user_id, pc.pf_attuali, pc.pf_massimi, u.username
                    FROM player_characters pc
                    LEFT JOIN users u ON pc.user_id = u.id
                    WHERE pc.user_id = %s
                """, (self.current_user['id'],))
            else:
                cursor.execute("""
                    SELECT pc.id, pc.name, pc.user_id, pc.pf_attuali, pc.pf_massimi, u.username
                    FROM player_characters pc
                    LEFT JOIN users u ON pc.user_id = u.id
                """)
            all_pgs = cursor.fetchall()
            num_pgs = len(all_pgs)

            if not all_pgs:
                ttk.Label(scrollable_frame, text="Nessun PG, fondo, seguace, attività o spesa trovata.").pack(pady=10)
                canvas.pack(side="left", fill="both", expand=True)
                scrollbar.pack(side="right", fill="y")
                return

            pgs_to_display = all_pgs

            # Recupera tutte le altre tabelle
            pg_ids = [pg['id'] for pg in pgs_to_display]
            placeholders = ",".join(["%s"] * len(pg_ids))

            cursor.execute(f"SELECT * FROM banks WHERE pg_id IN ({placeholders})", pg_ids)
            all_banks = cursor.fetchall()

            cursor.execute(f"SELECT * FROM followers WHERE pg_id IN ({placeholders})", pg_ids)
            all_followers = cursor.fetchall()

            cursor.execute(f"SELECT * FROM economic_activities WHERE pg_id IN ({placeholders})", pg_ids)
            all_activities = cursor.fetchall()

            cursor.execute(f"SELECT * FROM fixed_expenses WHERE pg_id IN ({placeholders})", pg_ids)
            all_expenses = cursor.fetchall()

            cursor.execute(f"SELECT * FROM bank_items WHERE pg_id IN ({placeholders})", pg_ids)
            all_bank_items = cursor.fetchall()

            cursor.execute("""
                SELECT fo.*, b.name AS bank_name, f.pg_id
                FROM follower_objectives fo
                LEFT JOIN followers f ON fo.follower_id = f.id
                LEFT JOIN banks b ON fo.bank_id = b.id
                WHERE f.pg_id IN ({})
            """.format(placeholders), pg_ids)
            all_objectives = cursor.fetchall()

            objective_ids = [obj['id'] for obj in all_objectives]
            if objective_ids:
                obj_placeholders = ",".join(["%s"] * len(objective_ids))
                cursor.execute(f"""
                    SELECT *
                    FROM follower_objective_events
                    WHERE objective_id IN ({obj_placeholders})
                    ORDER BY event_date DESC, id DESC
                """, objective_ids)
                all_events = cursor.fetchall()
            else:
                all_events = []

            try:
                cursor.execute(f"""
                    SELECT *
                    FROM pc_status_effects
                    WHERE pg_id IN ({placeholders}) AND is_active = 1
                    ORDER BY pg_id, end_absolute_day, effect_name
                """, pg_ids)
                all_status_effects = cursor.fetchall()
            except Exception:
                all_status_effects = []

            try:
                cursor.execute(f"""
                    SELECT *
                    FROM pc_journal_entries
                    WHERE pg_id IN ({placeholders})
                      AND entry_type IN ('MISSIONE','INDIZIO','OGGETTO_MISSIONE')
                      AND COALESCE(status, 'APERTO') IN ('APERTO','IN_CORSO')
                    ORDER BY pg_id, updated_at DESC
                """, pg_ids)
                all_open_journal = cursor.fetchall()
            except Exception:
                all_open_journal = []

            try:
                cursor.execute(f"""
                    SELECT *
                    FROM pc_possedimenti
                    WHERE pg_id IN ({placeholders})
                    ORDER BY pg_id, tipo, possedimento
                """, pg_ids)
                all_properties = cursor.fetchall()
            except Exception:
                all_properties = []

            try:
                cursor.execute(f"""
                    SELECT *
                    FROM pc_rule_overrides
                    WHERE pg_id IN ({placeholders}) AND is_active = 1
                    ORDER BY pg_id, override_scope, field_name
                """, pg_ids)
                all_rule_overrides = cursor.fetchall()
            except Exception:
                all_rule_overrides = []

            # Info generale
            general_frame = ttk.LabelFrame(scrollable_frame, text="📈 Informazioni Generali", padding=10)
            general_frame.pack(fill='x', padx=10, pady=5)
            ttk.Label(general_frame, text=f"Numero totale di Personaggi Giocanti (PG): {num_pgs}").pack(anchor='w')

            # 2. Stato per ogni PG
            for pg in pgs_to_display:
                pg_frame = ttk.LabelFrame(scrollable_frame, 
                                        text=f"🧙 {pg['name']} (Utente: {pg['username'] if pg['username'] else 'N/A'})", 
                                        padding=10)
                pg_frame.pack(fill='x', padx=10, pady=5)

                # Fondi
                pg_banks = [b for b in all_banks if b['pg_id'] == pg['id']]
                total_funds = sum(float(b['current_balance']) for b in pg_banks)
                
                funds_label = ttk.Label(pg_frame, text=f"💰 Fondi totali: {total_funds:.2f} MO (suddivisi in {len(pg_banks)} conti)")
                funds_label.pack(anchor='w')
                
                if pg_banks:
                    for bank in pg_banks:
                        ttk.Label(pg_frame, text=f"   • {bank['name']}: {float(bank['current_balance']):.2f} MO").pack(anchor='w')
                else:
                    ttk.Label(pg_frame, text="   Nessun conto bancario.").pack(anchor='w')

                pg_bank_items = [item for item in all_bank_items if item['pg_id'] == pg['id']]
                items_label = ttk.Label(pg_frame, text=f"📦 Oggetti in banca ({len(pg_bank_items)})")
                items_label.pack(anchor='w', pady=(10, 0))
                if pg_bank_items:
                    for item in pg_bank_items:
                        value = item.get('evaluated_value') or item.get('declared_value') or 0
                        item_text = (
                            f"   • {item.get('item_name', 'Oggetto')}: "
                            f"q.ta {item.get('quantity', 1)}, "
                            f"stato {item.get('status', 'N/A')}, "
                            f"valore {float(value):.2f} MO"
                        )
                        ttk.Label(pg_frame, text=item_text).pack(anchor='w')
                else:
                    ttk.Label(pg_frame, text="   Nessun oggetto in banca.").pack(anchor='w')

                # Seguaci e obiettivi
                pg_followers = [f for f in all_followers if f['pg_id'] == pg['id']]
                followers_label = ttk.Label(pg_frame, text=f"🛡️ Seguaci totali: {len(pg_followers)}")
                followers_label.pack(anchor='w', pady=(10, 0))
                
                if pg_followers:
                    for follower in pg_followers:
                        ttk.Label(pg_frame, text=f"   • {follower['name']} ({follower['description']})", 
                                 font=('Arial', 9, 'bold')).pack(anchor='w')
                        
                        follower_objectives = [obj for obj in all_objectives if obj['follower_id'] == follower['id']]
                        if follower_objectives:
                            ttk.Label(pg_frame, text="     Obiettivi:").pack(anchor='w')
                            for obj in follower_objectives:
                                status_name = self.OBJECTIVE_STATUS_REV.get(obj['status'], 'Sconosciuto')
                                bank_name = obj['bank_name'] if obj['bank_name'] else 'N/A'
                                obj_text = (f"       - '{obj['name']}': Stato: {status_name}, "
                                          f"Progresso: {float(obj['progress_percentage']):.1f}%, "
                                          f"Costo: {float(obj['total_cost']):.2f} MO (Banca: {bank_name})")
                                ttk.Label(pg_frame, text=obj_text, font=('Arial', 8)).pack(anchor='w')
                                objective_events = [event for event in all_events if event['objective_id'] == obj['id']]
                                if objective_events:
                                    ttk.Label(pg_frame, text=f"         Imprevisti: {len(objective_events)}").pack(anchor='w')
                                    for event in objective_events:
                                        handled = "gestito" if event.get('handled') else "da gestire"
                                        event_date = event.get('event_date') or 'N/A'
                                        event_text = (
                                            f"           • {event_date} - {event.get('type', 'N/A')} "
                                            f"({handled}): {event.get('description', '')}"
                                        )
                                        ttk.Label(pg_frame, text=event_text, font=('Arial', 8)).pack(anchor='w')
                        else:
                            ttk.Label(pg_frame, text="     Nessun obiettivo.").pack(anchor='w')
                else:
                    ttk.Label(pg_frame, text="   Nessun seguace.").pack(anchor='w')

                pg_effects = [e for e in all_status_effects if e['pg_id'] == pg['id']]
                if pg_effects:
                    ttk.Label(pg_frame, text=f"Stati attivi: {len(pg_effects)}", font=('Arial', 9, 'bold')).pack(anchor='w', pady=(10, 0))
                    for effect in pg_effects:
                        hidden = "" if effect.get('visible_to_player') else " (nascosto)"
                        ttk.Label(pg_frame, text=f"   - {effect.get('effect_name')}{hidden}: {effect.get('bonus_malus') or ''}", font=('Arial', 8)).pack(anchor='w')

                try:
                    low_hp = pg.get('pf_attuali') is not None and pg.get('pf_massimi') and int(pg.get('pf_attuali') or 0) <= max(1, int(pg.get('pf_massimi') or 0) // 4)
                except Exception:
                    low_hp = False
                if low_hp:
                    ttk.Label(pg_frame, text=f"Avviso PF bassi: {pg.get('pf_attuali')}/{pg.get('pf_massimi')}", foreground='darkred').pack(anchor='w')

                pg_journal = [j for j in all_open_journal if j['pg_id'] == pg['id']]
                if pg_journal:
                    ttk.Label(pg_frame, text=f"Missioni/indizi aperti: {len(pg_journal)}", font=('Arial', 9, 'bold')).pack(anchor='w', pady=(10, 0))
                    for entry in pg_journal[:5]:
                        ttk.Label(pg_frame, text=f"   - {entry.get('entry_type')}: {entry.get('title')} [{entry.get('status') or 'APERTO'}]", font=('Arial', 8)).pack(anchor='w')

                pg_properties = [p for p in all_properties if p['pg_id'] == pg['id']]
                if pg_properties:
                    ttk.Label(pg_frame, text=f"Possedimenti logistici: {len(pg_properties)}", font=('Arial', 9, 'bold')).pack(anchor='w', pady=(10, 0))
                    for prop in pg_properties[:5]:
                        money_bits = []
                        if prop.get('rendita') is not None:
                            money_bits.append(f"rendita {float(prop.get('rendita') or 0):.2f}")
                        if prop.get('costo_manutenzione') is not None:
                            money_bits.append(f"manut. {float(prop.get('costo_manutenzione') or 0):.2f}")
                        suffix = f" ({', '.join(money_bits)})" if money_bits else ""
                        ttk.Label(pg_frame, text=f"   - {prop.get('possedimento')} - {prop.get('stato') or 'stato n/d'}{suffix}", font=('Arial', 8)).pack(anchor='w')

                pg_overrides = [o for o in all_rule_overrides if o['pg_id'] == pg['id']]
                if pg_overrides:
                    ttk.Label(pg_frame, text=f"Override DM attivi: {len(pg_overrides)}", foreground='darkorange').pack(anchor='w', pady=(10, 0))

                # Attività Economiche
                pg_activities = [a for a in all_activities if a['pg_id'] == pg['id']]
                activities_label = ttk.Label(pg_frame, text=f"⚒️ Attività Economiche ({len(pg_activities)} attive)")
                activities_label.pack(anchor='w', pady=(10, 0))
                
                if pg_activities:
                    for activity in pg_activities:
                        bank_id = activity.get('destination_bank_id')
                        if not bank_id:
                            ttk.Label(pg_frame, text=f"   ⚠️ Attività '{activity.get('description', 'Sconosciuta')}' senza banca associata.").pack(anchor='w')
                            continue
                        bank = next((b for b in all_banks if b['id'] == bank_id), None)
                        bank_name = bank['name'] if bank else 'N/A'
                        activity_text = f"   • {activity['description']} → {float(activity['income']):.2f} MO ({activity['frequency']}) → Banca: {bank_name}"
                        ttk.Label(pg_frame, text=activity_text).pack(anchor='w')
                else:
                    ttk.Label(pg_frame, text="   Nessuna attività economica.").pack(anchor='w')

                # Spese Fisse
                pg_expenses = [e for e in all_expenses if e['pg_id'] == pg['id']]
                expenses_label = ttk.Label(pg_frame, text=f"💰 Spese Fisse ({len(pg_expenses)} attive)")
                expenses_label.pack(anchor='w', pady=(10, 0))
                
                if pg_expenses:
                    for expense in pg_expenses:
                        bank_name = next((b['name'] for b in all_banks if b['id'] == expense['source_bank_id']), 'N/A')
                        expense_text = f"   • '{expense['description']}' (-{float(expense['amount']):.2f} MO {expense['frequency']}, da: {bank_name})"
                        ttk.Label(pg_frame, text=expense_text).pack(anchor='w')
                else:
                    ttk.Label(pg_frame, text="   Nessuna spesa fissa.").pack(anchor='w')

            cursor.close()

        except Exception as e:
            error_label = ttk.Label(scrollable_frame, text=f"Si è verificato un errore durante la visualizzazione dello stato: {e}")
            error_label.pack(pady=10)
        
        # Pack finale - IMPORTANTE: prima canvas poi scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def export_status_to_txt(self, frame_widget):
        """Esporta lo stato della campagna in un file di testo"""
        
        try:
            # Chiedi dove salvare il file
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("File di testo", "*.txt"), ("Tutti i file", "*.*")],
                initialfile=f"stato_campagna_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            
            if not filename:
                return
            
            cursor = self.db.cursor()
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("STATO CAMPAGNA D&D\n")
                f.write("=" * 80 + "\n\n")
                
                # Data di gioco
                f.write(f"📅 Data di Gioco: {self.convert_date_to_ded_format(self.game_date)}\n")
                f.write(f"Data esportazione: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n")
                
                # PGs e utente associato
                if self.current_user and self.current_user['role'] == 'GIOCATORE':
                    cursor.execute("""
                        SELECT pc.id, pc.name, pc.user_id, u.username
                        FROM player_characters pc
                        LEFT JOIN users u ON pc.user_id = u.id
                        WHERE pc.user_id = %s
                    """, (self.current_user['id'],))
                else:
                    cursor.execute("""
                        SELECT pc.id, pc.name, pc.user_id, u.username
                        FROM player_characters pc
                        LEFT JOIN users u ON pc.user_id = u.id
                    """)
                all_pgs = cursor.fetchall()
                num_pgs = len(all_pgs)
                
                if not all_pgs:
                    f.write("Nessun PG, fondo, seguace, attività o spesa trovata.\n")
                    cursor.close()
                    messagebox.showinfo("Successo", f"File esportato con successo in:\n{filename}")
                    return
                
                pgs_to_display = all_pgs
                
                # Recupera tutte le altre tabelle
                pg_ids = [pg['id'] for pg in pgs_to_display]
                placeholders = ",".join(["%s"] * len(pg_ids))

                cursor.execute(f"SELECT * FROM banks WHERE pg_id IN ({placeholders})", pg_ids)
                all_banks = cursor.fetchall()
                
                cursor.execute(f"SELECT * FROM followers WHERE pg_id IN ({placeholders})", pg_ids)
                all_followers = cursor.fetchall()
                
                cursor.execute(f"SELECT * FROM economic_activities WHERE pg_id IN ({placeholders})", pg_ids)
                all_activities = cursor.fetchall()
                
                cursor.execute(f"SELECT * FROM fixed_expenses WHERE pg_id IN ({placeholders})", pg_ids)
                all_expenses = cursor.fetchall()

                cursor.execute(f"SELECT * FROM bank_items WHERE pg_id IN ({placeholders})", pg_ids)
                all_bank_items = cursor.fetchall()
                
                cursor.execute("""
                    SELECT fo.*, b.name AS bank_name, f.pg_id
                    FROM follower_objectives fo
                    LEFT JOIN followers f ON fo.follower_id = f.id
                    LEFT JOIN banks b ON fo.bank_id = b.id
                    WHERE f.pg_id IN ({})
                """.format(placeholders), pg_ids)
                all_objectives = cursor.fetchall()

                objective_ids = [obj['id'] for obj in all_objectives]
                if objective_ids:
                    obj_placeholders = ",".join(["%s"] * len(objective_ids))
                    cursor.execute(f"""
                        SELECT *
                        FROM follower_objective_events
                        WHERE objective_id IN ({obj_placeholders})
                        ORDER BY event_date DESC, id DESC
                    """, objective_ids)
                    all_events = cursor.fetchall()
                else:
                    all_events = []
                
                # Info generale
                f.write("-" * 80 + "\n")
                f.write("📈 INFORMAZIONI GENERALI\n")
                f.write("-" * 80 + "\n")
                f.write(f"Numero totale di Personaggi Giocanti (PG): {num_pgs}\n\n")
                
                # Stato per ogni PG
                for pg in pgs_to_display:
                    f.write("=" * 80 + "\n")
                    f.write(f"🧙 {pg['name']} (Utente: {pg['username'] if pg['username'] else 'N/A'})\n")
                    f.write("=" * 80 + "\n\n")
                    
                    # Fondi
                    pg_banks = [b for b in all_banks if b['pg_id'] == pg['id']]
                    total_funds = sum(float(b['current_balance']) for b in pg_banks)
                    
                    f.write(f"💰 FONDI TOTALI: {total_funds:.2f} MO (suddivisi in {len(pg_banks)} conti)\n")
                    if pg_banks:
                        for bank in pg_banks:
                            f.write(f"   • {bank['name']}: {float(bank['current_balance']):.2f} MO\n")
                    else:
                        f.write("   Nessun conto bancario.\n")
                    f.write("\n")

                    pg_bank_items = [item for item in all_bank_items if item['pg_id'] == pg['id']]
                    f.write(f"📦 OGGETTI IN BANCA ({len(pg_bank_items)})\n")
                    if pg_bank_items:
                        for item in pg_bank_items:
                            value = item.get('evaluated_value') or item.get('declared_value') or 0
                            f.write(
                                f"   • {item.get('item_name', 'Oggetto')}: "
                                f"q.ta {item.get('quantity', 1)}, "
                                f"stato {item.get('status', 'N/A')}, "
                                f"valore {float(value):.2f} MO\n"
                            )
                    else:
                        f.write("   Nessun oggetto in banca.\n")
                    f.write("\n")
                    
                    # Seguaci e obiettivi
                    pg_followers = [f for f in all_followers if f['pg_id'] == pg['id']]
                    f.write(f"🛡️ SEGUACI TOTALI: {len(pg_followers)}\n")
                    
                    if pg_followers:
                        for follower in pg_followers:
                            f.write(f"   • {follower['name']} ({follower['description']})\n")
                            
                            follower_objectives = [obj for obj in all_objectives if obj['follower_id'] == follower['id']]
                            if follower_objectives:
                                f.write("     Obiettivi:\n")
                                for obj in follower_objectives:
                                    status_name = self.OBJECTIVE_STATUS_REV.get(obj['status'], 'Sconosciuto')
                                    bank_name = obj['bank_name'] if obj['bank_name'] else 'N/A'
                                    f.write(f"       - '{obj['name']}': Stato: {status_name}, "
                                           f"Progresso: {float(obj['progress_percentage']):.1f}%, "
                                           f"Costo: {float(obj['total_cost']):.2f} MO (Banca: {bank_name})\n")
                                    objective_events = [event for event in all_events if event['objective_id'] == obj['id']]
                                    if objective_events:
                                        f.write(f"         Imprevisti: {len(objective_events)}\n")
                                        for event in objective_events:
                                            handled = "gestito" if event.get('handled') else "da gestire"
                                            event_date = event.get('event_date') or 'N/A'
                                            f.write(
                                                f"           • {event_date} - {event.get('type', 'N/A')} "
                                                f"({handled}): {event.get('description', '')}\n"
                                            )
                            else:
                                f.write("     Nessun obiettivo.\n")
                    else:
                        f.write("   Nessun seguace.\n")
                    f.write("\n")
                    
                    # Attività Economiche
                    pg_activities = [a for a in all_activities if a['pg_id'] == pg['id']]
                    f.write(f"⚒️ ATTIVITÀ ECONOMICHE ({len(pg_activities)} attive)\n")
                    
                    if pg_activities:
                        for activity in pg_activities:
                            bank_id = activity.get('destination_bank_id')
                            if not bank_id:
                                f.write(f"   ⚠️ Attività '{activity.get('description', 'Sconosciuta')}' senza banca associata.\n")
                                continue
                            bank = next((b for b in all_banks if b['id'] == bank_id), None)
                            bank_name = bank['name'] if bank else 'N/A'
                            f.write(f"   • {activity['description']} → {float(activity['income']):.2f} MO "
                                   f"({activity['frequency']}) → Banca: {bank_name}\n")
                    else:
                        f.write("   Nessuna attività economica.\n")
                    f.write("\n")
                    
                    # Spese Fisse
                    pg_expenses = [e for e in all_expenses if e['pg_id'] == pg['id']]
                    f.write(f"💰 SPESE FISSE ({len(pg_expenses)} attive)\n")
                    
                    if pg_expenses:
                        for expense in pg_expenses:
                            bank_name = next((b['name'] for b in all_banks if b['id'] == expense['source_bank_id']), 'N/A')
                            f.write(f"   • '{expense['description']}' (-{float(expense['amount']):.2f} MO "
                                   f"{expense['frequency']}, da: {bank_name})\n")
                    else:
                        f.write("   Nessuna spesa fissa.\n")
                    f.write("\n")
                
                cursor.close()
            
            messagebox.showinfo("Successo", f"File esportato con successo in:\n{filename}")
            
            # Chiedi se vuoi aprire il file
            if messagebox.askyesno("Apri file", "Vuoi aprire il file esportato?"):
                os.startfile(filename)
        
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante l'esportazione: {e}")

    def get_backup_table_names(self):
        """Elenco unico delle tabelle incluse nel backup/restore JSON."""
        return [
            'users', 'player_characters', 'banks', 'bank_transactions',
            'bank_items', 'bank_item_evaluations',
            'followers', 'economic_activities', 'fixed_expenses',
            'game_state', 'follower_objectives', 'follower_objective_events',
            'chat_messages', 'chat_reads',
            'pc_abilita_ladro', 'pc_armature', 'pc_armi', 'pc_azioni_speciali',
            'pc_cavalcature', 'pc_consiglieri', 'pc_creature_familiari',
            'pc_inventario', 'pc_linguaggi', 'pc_mercenari', 'pc_oggetti_magici',
            'pc_pergamene', 'pc_possedimenti', 'pc_specialisti',
            'rule_classes', 'rule_ability_modifiers', 'rule_primary_requisite_xp_bonus',
            'rule_xp_progression', 'rule_saving_throws', 'rule_thac0',
            'pc_rule_overrides', 'rule_thief_abilities', 'rule_turn_undead',
            'rule_spell_slots', 'rule_spells', 'pc_spellbook', 'pc_spell_prepared',
            'rule_weapons', 'rule_armor', 'rule_equipment', 'pc_containers',
            'pc_status_effects', 'pc_journal_entries'
        ]

    def restore_backup_action(self):
        """Ripristina un backup JSON creato dal menu Backup."""
        if not messagebox.askyesno(
            "Conferma ripristino",
            "Il ripristino sostituisce i dati delle tabelle trovate nel backup selezionato.\n\n"
            "Eseguire solo dopo un backup a freddo/WAMP. Procedere?"
        ):
            return
        backup_dir = filedialog.askdirectory(title="Seleziona cartella backup")
        if not backup_dir:
            return
        cursor = None
        try:
            cursor = self.db.cursor()
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            restored = []
            for table in reversed(self.get_backup_table_names()):
                files = [
                    os.path.join(backup_dir, name)
                    for name in os.listdir(backup_dir)
                    if name.startswith(f"{table}_backup_") and name.endswith(".json")
                ]
                if not files:
                    continue
                latest_file = max(files, key=os.path.getmtime)
                with open(latest_file, "r", encoding="utf-8") as f:
                    rows = json.load(f)
                cursor.execute(f"DELETE FROM {table}")
                if rows:
                    columns = list(rows[0].keys())
                    column_clause = ", ".join(f"`{col}`" for col in columns)
                    value_clause = ", ".join([f"%({col})s" for col in columns])
                    cursor.executemany(
                        f"INSERT INTO {table} ({column_clause}) VALUES ({value_clause})",
                        rows
                    )
                restored.append(table)
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
            self.db.commit()
            messagebox.showinfo("Successo", f"Ripristino completato.\nTabelle ripristinate: {len(restored)}")
        except Exception as e:
            try:
                self.db.rollback()
                if cursor:
                    cursor.execute("SET FOREIGN_KEY_CHECKS=1")
            except Exception:
                pass
            messagebox.showerror("Errore", f"Errore durante il ripristino: {e}")
        finally:
            if cursor:
                cursor.close()

    def get_current_absolute_day(self):
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT absolute_day FROM game_state ORDER BY id LIMIT 1")
            row = cursor.fetchone()
            cursor.close()
            return int(row.get('absolute_day') or 0) if row else 0
        except Exception:
            return 0

    def get_active_status_effects(self, pg_id, include_hidden=False):
        """Restituisce gli effetti attivi del PG, filtrando quelli nascosti per i giocatori."""
        try:
            cursor = self.db.cursor()
            query = """
                SELECT *
                FROM pc_status_effects
                WHERE pg_id = %s AND is_active = 1
            """
            params = [pg_id]
            if not include_hidden:
                query += " AND visible_to_player = 1"
            query += " ORDER BY end_absolute_day IS NULL, end_absolute_day, effect_name"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Exception:
            return []

    def calculate_follower_limits(self, pg_id):
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT carisma FROM player_characters WHERE id = %s", (pg_id,))
            pg = cursor.fetchone() or {}
            cursor.execute("SELECT COUNT(*) AS total FROM followers WHERE pg_id = %s", (pg_id,))
            count = cursor.fetchone().get('total', 0)
            cursor.close()
            charisma = int(pg.get('carisma') or 10)
        except Exception:
            charisma, count = 10, 0
        if charisma <= 3:
            max_followers, morale, reaction = 1, 4, -2
        elif charisma <= 5:
            max_followers, morale, reaction = 2, 5, -1
        elif charisma <= 8:
            max_followers, morale, reaction = 3, 6, -1
        elif charisma <= 12:
            max_followers, morale, reaction = 4, 7, 0
        elif charisma <= 15:
            max_followers, morale, reaction = 5, 8, 1
        elif charisma <= 17:
            max_followers, morale, reaction = 6, 9, 1
        else:
            max_followers, morale, reaction = 7, 10, 2
        max_rule = self.get_rule_value(pg_id, 'followers', 'max_followers', max_followers)
        morale_rule = self.get_rule_value(pg_id, 'followers', 'base_morale', morale)
        return {
            'charisma': charisma,
            'max_followers': int(max_rule.get('effective') or max_followers),
            'base_morale': int(morale_rule.get('effective') or morale),
            'reaction_modifier': reaction,
            'current_followers': int(count or 0),
            'max_override': bool(max_rule.get('is_override')),
            'morale_override': bool(morale_rule.get('is_override')),
        }

    def create_character_adventure_tab(self, notebook, pg_id, character):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Avventura")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        adv_notebook = ttk.Notebook(tab)
        adv_notebook.grid(row=0, column=0, sticky='nsew', padx=8, pady=8)

        status_frame = ttk.Frame(adv_notebook)
        adv_notebook.add(status_frame, text="Stati")
        self.status_effects_tree = ttk.Treeview(
            status_frame,
            columns=('nome', 'tipo', 'fonte', 'durata', 'fine', 'visibile'),
            show='headings',
            height=12
        )
        for col, label, width in [
            ('nome', 'Effetto', 150), ('tipo', 'Tipo', 90), ('fonte', 'Fonte', 140),
            ('durata', 'Durata', 100), ('fine', 'Fine giorno', 90), ('visibile', 'Visibile', 70)
        ]:
            self.status_effects_tree.heading(col, text=label)
            self.status_effects_tree.column(col, width=width)
        self.status_effects_tree.pack(fill='both', expand=True, padx=8, pady=8)
        status_buttons = ttk.Frame(status_frame)
        status_buttons.pack(fill='x', padx=8, pady=4)
        ttk.Button(status_buttons, text="Aggiungi", command=lambda: self.add_status_effect_dialog(pg_id)).pack(side='left', padx=4)
        ttk.Button(status_buttons, text="Modifica", command=lambda: self.edit_status_effect_dialog(pg_id)).pack(side='left', padx=4)
        ttk.Button(status_buttons, text="Disattiva", command=lambda: self.deactivate_status_effect(pg_id)).pack(side='left', padx=4)
        if self.current_user and self.current_user.get('role') == 'DM':
            ttk.Button(status_buttons, text="Elimina", command=lambda: self.delete_status_effect(pg_id)).pack(side='left', padx=4)

        journal_frame = ttk.Frame(adv_notebook)
        adv_notebook.add(journal_frame, text="Diario e missioni")
        self.journal_tree = ttk.Treeview(
            journal_frame,
            columns=('titolo', 'tipo', 'stato', 'data', 'visibile'),
            show='headings',
            height=12
        )
        for col, label, width in [
            ('titolo', 'Titolo', 220), ('tipo', 'Tipo', 120),
            ('stato', 'Stato', 100), ('data', 'Data', 120), ('visibile', 'Visibile', 70)
        ]:
            self.journal_tree.heading(col, text=label)
            self.journal_tree.column(col, width=width)
        self.journal_tree.pack(fill='both', expand=True, padx=8, pady=8)
        journal_buttons = ttk.Frame(journal_frame)
        journal_buttons.pack(fill='x', padx=8, pady=4)
        ttk.Button(journal_buttons, text="Aggiungi", command=lambda: self.add_journal_entry_dialog(pg_id)).pack(side='left', padx=4)
        ttk.Button(journal_buttons, text="Modifica/Dettaglio", command=lambda: self.edit_journal_entry_dialog(pg_id)).pack(side='left', padx=4)
        ttk.Button(journal_buttons, text="Elimina", command=lambda: self.delete_journal_entry(pg_id)).pack(side='left', padx=4)

        self.refresh_status_effects_list(pg_id)
        self.refresh_journal_entries_list(pg_id)

    def refresh_status_effects_list(self, pg_id):
        tree = getattr(self, 'status_effects_tree', None)
        if not tree:
            return
        tree.delete(*tree.get_children())
        include_hidden = self.current_user and self.current_user.get('role') == 'DM'
        try:
            rows = self.get_active_status_effects(pg_id, include_hidden=include_hidden)
            for row in rows:
                duration = ""
                if row.get('duration_unit'):
                    duration = f"{row.get('duration_value') or ''} {row.get('duration_unit')}".strip()
                tree.insert('', 'end', values=(
                    row.get('effect_name') or '',
                    row.get('effect_type') or '',
                    row.get('source') or '',
                    duration,
                    row.get('end_absolute_day') or '',
                    "Si" if row.get('visible_to_player') else "No",
                ), tags=(row['id'],))
        except Exception as e:
            print(f"Errore stati avventura: {e}")

    def _status_effect_dialog(self, pg_id, effect=None):
        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        dialog = tk.Toplevel(self.root)
        dialog.title("Effetto temporaneo")
        dialog.geometry("560x560")
        dialog.transient(self.root)
        dialog.grab_set()
        fields = {}
        rows = [
            ('effect_name', 'Nome'), ('effect_type', 'Tipo'), ('source', 'Fonte'),
            ('duration_value', 'Durata'), ('duration_unit', 'Unita'),
            ('start_absolute_day', 'Giorno inizio'), ('end_absolute_day', 'Giorno fine'),
        ]
        for row, (field, label) in enumerate(rows):
            ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=4)
            if field == 'duration_unit':
                widget = ttk.Combobox(dialog, values=['ROUND', 'TURNO', 'ORA', 'GIORNO', 'MESE', 'PERMANENTE', 'SPECIALE'], width=36)
            else:
                widget = ttk.Entry(dialog, width=39)
            widget.grid(row=row, column=1, sticky='ew', padx=10, pady=4)
            widget.insert(0, '' if not effect or effect.get(field) is None else str(effect.get(field)))
            fields[field] = widget
        active_var = tk.BooleanVar(value=bool(effect.get('is_active', 1)) if effect else True)
        visible_var = tk.BooleanVar(value=bool(effect.get('visible_to_player', 1)) if effect else True)
        ttk.Checkbutton(dialog, text="Attivo", variable=active_var).grid(row=7, column=0, sticky='w', padx=10, pady=4)
        ttk.Checkbutton(dialog, text="Visibile al giocatore", variable=visible_var, state='normal' if is_dm else 'disabled').grid(row=7, column=1, sticky='w', padx=10, pady=4)
        ttk.Label(dialog, text="Bonus/Malus:").grid(row=8, column=0, sticky='nw', padx=10, pady=4)
        bonus_text = tk.Text(dialog, width=40, height=4)
        bonus_text.grid(row=8, column=1, sticky='ew', padx=10, pady=4)
        bonus_text.insert('1.0', effect.get('bonus_malus') or '' if effect else '')
        ttk.Label(dialog, text="Note giocatore:").grid(row=9, column=0, sticky='nw', padx=10, pady=4)
        player_text = tk.Text(dialog, width=40, height=4)
        player_text.grid(row=9, column=1, sticky='ew', padx=10, pady=4)
        player_text.insert('1.0', effect.get('player_notes') or '' if effect else '')
        ttk.Label(dialog, text="Note DM:").grid(row=10, column=0, sticky='nw', padx=10, pady=4)
        dm_text = tk.Text(dialog, width=40, height=4)
        dm_text.grid(row=10, column=1, sticky='ew', padx=10, pady=4)
        dm_text.insert('1.0', effect.get('dm_notes') or '' if effect and is_dm else '')
        if not is_dm:
            dm_text.configure(state='disabled')

        def save():
            data = {
                'pg_id': pg_id,
                'effect_name': fields['effect_name'].get().strip(),
                'effect_type': fields['effect_type'].get().strip(),
                'source': fields['source'].get().strip(),
                'bonus_malus': bonus_text.get('1.0', 'end-1c').strip(),
                'duration_value': int(fields['duration_value'].get() or 0) if fields['duration_value'].get().strip() else None,
                'duration_unit': fields['duration_unit'].get().strip() or None,
                'start_absolute_day': int(fields['start_absolute_day'].get() or 0) if fields['start_absolute_day'].get().strip() else None,
                'end_absolute_day': int(fields['end_absolute_day'].get() or 0) if fields['end_absolute_day'].get().strip() else None,
                'is_active': int(active_var.get()),
                'visible_to_player': int(visible_var.get()) if is_dm else 1,
                'dm_notes': dm_text.get('1.0', 'end-1c').strip() if is_dm else (effect.get('dm_notes') if effect else ''),
                'player_notes': player_text.get('1.0', 'end-1c').strip(),
            }
            if not data['effect_name']:
                messagebox.showerror("Errore", "Nome effetto obbligatorio.")
                return
            cursor = self.db.cursor()
            try:
                if effect:
                    data['id'] = effect['id']
                    cursor.execute("""
                        UPDATE pc_status_effects
                        SET effect_name=%(effect_name)s, effect_type=%(effect_type)s, source=%(source)s,
                            bonus_malus=%(bonus_malus)s, duration_value=%(duration_value)s,
                            duration_unit=%(duration_unit)s, start_absolute_day=%(start_absolute_day)s,
                            end_absolute_day=%(end_absolute_day)s, is_active=%(is_active)s,
                            visible_to_player=%(visible_to_player)s, dm_notes=%(dm_notes)s,
                            player_notes=%(player_notes)s
                        WHERE id=%(id)s AND pg_id=%(pg_id)s
                    """, data)
                else:
                    cursor.execute("""
                        INSERT INTO pc_status_effects
                            (pg_id, effect_name, effect_type, source, bonus_malus, duration_value,
                             duration_unit, start_absolute_day, end_absolute_day, is_active,
                             visible_to_player, dm_notes, player_notes)
                        VALUES
                            (%(pg_id)s, %(effect_name)s, %(effect_type)s, %(source)s, %(bonus_malus)s,
                             %(duration_value)s, %(duration_unit)s, %(start_absolute_day)s,
                             %(end_absolute_day)s, %(is_active)s, %(visible_to_player)s,
                             %(dm_notes)s, %(player_notes)s)
                    """, data)
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_status_effects_list(pg_id)
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore salvataggio effetto: {e}")

        ttk.Button(dialog, text="Salva", command=save).grid(row=11, column=0, pady=10)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=11, column=1, pady=10)

    def add_status_effect_dialog(self, pg_id):
        self._status_effect_dialog(pg_id)

    def edit_status_effect_dialog(self, pg_id):
        selection = getattr(self, 'status_effects_tree', None).selection() if getattr(self, 'status_effects_tree', None) else ()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona un effetto.")
            return
        effect_id = self.status_effects_tree.item(selection[0])['tags'][0]
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM pc_status_effects WHERE id = %s AND pg_id = %s", (effect_id, pg_id))
        effect = cursor.fetchone()
        cursor.close()
        if effect:
            self._status_effect_dialog(pg_id, effect)

    def deactivate_status_effect(self, pg_id):
        selection = getattr(self, 'status_effects_tree', None).selection() if getattr(self, 'status_effects_tree', None) else ()
        if not selection:
            return
        effect_id = self.status_effects_tree.item(selection[0])['tags'][0]
        cursor = self.db.cursor()
        cursor.execute("UPDATE pc_status_effects SET is_active = 0 WHERE id = %s AND pg_id = %s", (effect_id, pg_id))
        self.db.commit()
        cursor.close()
        self.refresh_status_effects_list(pg_id)

    def delete_status_effect(self, pg_id):
        selection = getattr(self, 'status_effects_tree', None).selection() if getattr(self, 'status_effects_tree', None) else ()
        if not selection or not messagebox.askyesno("Conferma", "Eliminare definitivamente l'effetto?"):
            return
        effect_id = self.status_effects_tree.item(selection[0])['tags'][0]
        cursor = self.db.cursor()
        cursor.execute("DELETE FROM pc_status_effects WHERE id = %s AND pg_id = %s", (effect_id, pg_id))
        self.db.commit()
        cursor.close()
        self.refresh_status_effects_list(pg_id)

    def refresh_journal_entries_list(self, pg_id):
        tree = getattr(self, 'journal_tree', None)
        if not tree:
            return
        tree.delete(*tree.get_children())
        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        try:
            cursor = self.db.cursor()
            query = "SELECT * FROM pc_journal_entries WHERE pg_id = %s"
            params = [pg_id]
            if not is_dm:
                query += " AND visible_to_player = 1"
            query += " ORDER BY updated_at DESC, id DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close()
            for row in rows:
                tree.insert('', 'end', values=(
                    row.get('title') or '',
                    row.get('entry_type') or '',
                    row.get('status') or '',
                    row.get('mystara_date') or '',
                    "Si" if row.get('visible_to_player') else "No",
                ), tags=(row['id'],))
        except Exception as e:
            print(f"Errore diario avventura: {e}")

    def _journal_entry_dialog(self, pg_id, entry=None):
        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        dialog = tk.Toplevel(self.root)
        dialog.title("Diario / Missione")
        dialog.geometry("620x560")
        dialog.minsize(560, 460)
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)
        dialog.rowconfigure(4, weight=4)
        dialog.rowconfigure(5, weight=2)
        title_entry = ttk.Entry(dialog, width=55)
        type_combo = ttk.Combobox(dialog, values=['DIARIO', 'MISSIONE', 'INDIZIO', 'PNG', 'LUOGO', 'OGGETTO_MISSIONE', 'NOTA'], width=52)
        status_combo = ttk.Combobox(dialog, values=['APERTO', 'IN_CORSO', 'COMPLETATO', 'FALLITO', 'ARCHIVIATO'], width=52)
        date_entry = ttk.Entry(dialog, width=55)
        fields = [('Titolo', title_entry), ('Tipo', type_combo), ('Stato', status_combo), ('Data Mystara', date_entry)]
        for row, (label, widget) in enumerate(fields):
            ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
            widget.grid(row=row, column=1, sticky='ew', padx=10, pady=5)
        content_text = scrolledtext.ScrolledText(dialog, width=58, height=12, wrap='word')
        ttk.Label(dialog, text="Contenuto:").grid(row=4, column=0, sticky='nw', padx=10, pady=5)
        content_text.grid(row=4, column=1, sticky='nsew', padx=10, pady=5)
        dm_text = scrolledtext.ScrolledText(dialog, width=58, height=5, wrap='word')
        ttk.Label(dialog, text="Note DM:").grid(row=5, column=0, sticky='nw', padx=10, pady=5)
        dm_text.grid(row=5, column=1, sticky='nsew', padx=10, pady=5)
        visible_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dialog, text="Visibile al giocatore", variable=visible_var, state='normal' if is_dm else 'disabled').grid(row=6, column=1, sticky='w', padx=10, pady=5)
        if entry:
            title_entry.insert(0, entry.get('title') or '')
            type_combo.set(entry.get('entry_type') or 'DIARIO')
            status_combo.set(entry.get('status') or '')
            date_entry.insert(0, entry.get('mystara_date') or '')
            content_text.insert('1.0', entry.get('content') or '')
            dm_text.insert('1.0', entry.get('dm_notes') or '' if is_dm else '')
            visible_var.set(bool(entry.get('visible_to_player', 1)))
        else:
            type_combo.set('DIARIO')
            status_combo.set('APERTO')
            date_entry.insert(0, self.convert_date_to_ded_format(self.game_date))
        if not is_dm:
            dm_text.configure(state='disabled')

        def save():
            data = {
                'pg_id': pg_id,
                'title': title_entry.get().strip(),
                'entry_type': type_combo.get().strip() or 'DIARIO',
                'content': content_text.get('1.0', 'end-1c').strip(),
                'mystara_date': date_entry.get().strip(),
                'absolute_day': self.get_current_absolute_day(),
                'status': status_combo.get().strip() or None,
                'visible_to_player': int(visible_var.get()) if is_dm else 1,
                'dm_notes': dm_text.get('1.0', 'end-1c').strip() if is_dm else (entry.get('dm_notes') if entry else ''),
            }
            if not data['title'] or not data['content']:
                messagebox.showerror("Errore", "Titolo e contenuto sono obbligatori.")
                return
            cursor = self.db.cursor()
            try:
                if entry:
                    data['id'] = entry['id']
                    cursor.execute("""
                        UPDATE pc_journal_entries
                        SET title=%(title)s, entry_type=%(entry_type)s, content=%(content)s,
                            mystara_date=%(mystara_date)s, absolute_day=%(absolute_day)s,
                            status=%(status)s, visible_to_player=%(visible_to_player)s,
                            dm_notes=%(dm_notes)s
                        WHERE id=%(id)s AND pg_id=%(pg_id)s
                    """, data)
                else:
                    cursor.execute("""
                        INSERT INTO pc_journal_entries
                            (pg_id, title, entry_type, content, mystara_date, absolute_day,
                             status, visible_to_player, dm_notes)
                        VALUES
                            (%(pg_id)s, %(title)s, %(entry_type)s, %(content)s,
                             %(mystara_date)s, %(absolute_day)s, %(status)s,
                             %(visible_to_player)s, %(dm_notes)s)
                    """, data)
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_journal_entries_list(pg_id)
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore salvataggio diario: {e}")

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=7, column=0, columnspan=2, sticky='ew', padx=10, pady=10)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        ttk.Button(button_frame, text="Salva", command=save).grid(row=0, column=0, padx=10)
        ttk.Button(button_frame, text="Annulla", command=dialog.destroy).grid(row=0, column=1, padx=10)

    def add_journal_entry_dialog(self, pg_id):
        self._journal_entry_dialog(pg_id)

    def edit_journal_entry_dialog(self, pg_id):
        selection = getattr(self, 'journal_tree', None).selection() if getattr(self, 'journal_tree', None) else ()
        if not selection:
            messagebox.showwarning("Avviso", "Seleziona una voce.")
            return
        entry_id = self.journal_tree.item(selection[0])['tags'][0]
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM pc_journal_entries WHERE id = %s AND pg_id = %s", (entry_id, pg_id))
        entry = cursor.fetchone()
        cursor.close()
        if entry:
            self._journal_entry_dialog(pg_id, entry)

    def delete_journal_entry(self, pg_id):
        selection = getattr(self, 'journal_tree', None).selection() if getattr(self, 'journal_tree', None) else ()
        if not selection or not messagebox.askyesno("Conferma", "Eliminare la voce selezionata?"):
            return
        entry_id = self.journal_tree.item(selection[0])['tags'][0]
        cursor = self.db.cursor()
        cursor.execute("DELETE FROM pc_journal_entries WHERE id = %s AND pg_id = %s", (entry_id, pg_id))
        self.db.commit()
        cursor.close()
        self.refresh_journal_entries_list(pg_id)

    def show_time_menu(self):
        """Mostra il menu gestione tempo con riquadro log e imprevisti (GUI)."""
        self.clear_content()

        title = ttk.Label(self.content_frame, text="⏳ Gestione Tempo", style='Title.TLabel')
        title.pack(pady=10)

        # Frame con pulsanti tempo
        time_frame = ttk.LabelFrame(self.content_frame, text="Avanza Tempo", padding=10)
        time_frame.pack(pady=10, padx=10, fill='x')

        btn_frame = ttk.Frame(time_frame)
        btn_frame.pack(pady=6)

        ttk.Button(btn_frame, text="➕ 1 Giorno", command=lambda: self.advance_days_dialog(1)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="➕ 1 Settimana", command=lambda: self.advance_weeks_dialog(1)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="➕ 1 Mese", command=lambda: self.advance_months_dialog(1)).pack(side='left', padx=5)

        # Imposta data manualmente
        ttk.Button(time_frame, text="📅 Imposta Data Manualmente", command=self.set_date_manually_dialog).pack(pady=6)

        # Frame eventi / azioni (solo DM)
        if self.current_user and self.current_user.get('role') == 'DM':
            events_frame = ttk.LabelFrame(self.content_frame, text="Azioni Tempo (DM)", padding=10)
            events_frame.pack(pady=10, padx=10, fill='x')
            # rimango minimale: pulsanti informativi (non necessari per l'applicazione automatica)
            ttk.Label(events_frame, text="Gli eventi vengono applicati automaticamente durante l'avanzamento del tempo.",
                      font=('Arial', 9, 'italic')).pack(pady=4)

        # Frame principale con log a sinistra e lista imprevisti a destra
        main_frame = ttk.Frame(self.content_frame)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Log testuale (scrollabile)
        log_frame = ttk.LabelFrame(main_frame, text="Log Eventi", padding=6)
        log_frame.pack(side='left', fill='both', expand=True, padx=(0,10))

        self.time_log_text = tk.Text(log_frame, wrap='word', height=20)
        self.time_log_text.configure(state='disabled')
        log_scroll = ttk.Scrollbar(log_frame, command=self.time_log_text.yview)
        self.time_log_text.configure(yscrollcommand=log_scroll.set)
        self.time_log_text.pack(side='left', fill='both', expand=True)
        log_scroll.pack(side='right', fill='y')

        # Lista imprevisti pendenti
        right_frame = ttk.LabelFrame(main_frame, text="Imprevisti in Sospeso", padding=6)
        right_frame.pack(side='right', fill='y', ipadx=10)

        self.imprevisti_listbox = tk.Listbox(right_frame, width=50, height=20)
        self.imprevisti_listbox.pack(side='left', fill='y')
        imprevisti_scroll = ttk.Scrollbar(right_frame, orient='vertical', command=self.imprevisti_listbox.yview)
        self.imprevisti_listbox.configure(yscrollcommand=imprevisti_scroll.set)
        imprevisti_scroll.pack(side='right', fill='y')

        # Carica la lista imprevisti e un breve log iniziale
        self.append_time_log("Apertura Gestione Tempo.")
        self.load_pending_events()

    def advance_days_dialog(self, days):
        """Chiede conferma e avvia advance_days (GUI wrapper)."""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showwarning("Avviso", "Solo un DM può avanzare il tempo.")
            return

        if not messagebox.askyesno("Conferma", f"Avanzare di {days} giorno/i?"):
            return

        self.advance_days(days)

    def advance_weeks_dialog(self, weeks):
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showwarning("Avviso", "Solo un DM può avanzare il tempo.")
            return
        if not messagebox.askyesno("Conferma", f"Avanzare di {weeks} settimana/e?"):
            return
        self.advance_weeks(weeks)

    def advance_months_dialog(self, months):
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showwarning("Avviso", "Solo un DM può avanzare il tempo.")
            return
        if not messagebox.askyesno("Conferma", f"Avanzare di {months} mese/i?"):
            return
        self.advance_months(months)

    def _check_year_change(self, old_date, new_date):
        """
        Controlla il cambio di ANNO Mystara (non l'anno gregoriano).
        Se l'anno Mystara cambia chiama apply_annual_bank_interest().
        Usa il calcolo anno coerente con absolute_day ed EPOCH_DATE.
        """
        try:
            # validazione input
            if not old_date or not new_date:
                return

            # normalizza date
            if isinstance(old_date, datetime):
                old_date = old_date.date()
            if isinstance(new_date, datetime):
                new_date = new_date.date()

            # calcolo anni Mystara in modo coerente
            old_abs = self.date_to_absolute_day(old_date)
            new_abs = self.date_to_absolute_day(new_date)

            base_year = getattr(self, "EPOCH_DATE", date(1, 1, 1)).year
            old_y = base_year + (old_abs // self.DAYS_PER_YEAR)
            new_y = base_year + (new_abs // self.DAYS_PER_YEAR)

            # confronto
            if new_y != old_y:
                self.append_time_log(
                    f"🔄 Cambio anno Mystara rilevato: {old_y} → {new_y}"
                )
                try:
                    self.apply_annual_bank_interest()
                except Exception as e:
                    self.append_time_log(
                        f"Errore apply_annual_bank_interest: {e}"
                    )

        except Exception as e:
            self.append_time_log(f"Errore _check_year_change: {e}")

    def advance_days(self, days=1):
        """
        Avanza il tempo di N giorni secondo Mystara (mantiene game_date come date).
        Aggiorna game_state (game_date + absolute_day) via _update_game_state_date.
        Applica gli eventi giornalieri e gli imprevisti ogni giorno.
        """
        try:
            for i in range(days):
                # salva data precedente coerente come date
                old_date = self.game_date
                if isinstance(old_date, datetime):
                    old_date = old_date.date()

                # incrementa di un giorno (mantieni self.game_date come date)
                if isinstance(self.game_date, datetime):
                    self.game_date = (self.game_date + timedelta(days=1)).date()
                elif isinstance(self.game_date, date):
                    self.game_date = self.game_date + timedelta(days=1)
                else:
                    self.game_date = datetime.strptime(str(self.game_date), "%Y-%m-%d").date() + timedelta(days=1)

                # AGGIORNAMENTO CRITICO: Salva immediatamente nel database
                self._update_game_state_date(self.game_date)

                # controllo cambio anno Mystara (usa absolute_day -> anno Mystara)
                try:
                    self._check_year_change(old_date, self.game_date)
                except Exception as e:
                    self.append_time_log(f"Errore controllo cambio anno: {e}")

                self.append_time_log(f"Data avanzata a {self.convert_date_to_ded_format(self.game_date)} (giorno {i+1}/{days})")

                # Applica eventi giornalieri
                try:
                    self._apply_daily_events()
                except Exception as e:
                    self.append_time_log(f"Errore applicazione eventi giornalieri: {e}")

            # Applica imprevisti SOLO UNA VOLTA alla fine di tutti i giorni
            try:
                self.apply_unhandled_objective_events()
            except Exception as e:
                self.append_time_log(f"Errore apply_unhandled_objective_events dopo daily: {e}")

            # Aggiorna grafica (data nel menu principale, ecc.)
            if hasattr(self, 'date_label'):
                try:
                    self.date_label.config(text=self.convert_date_to_ded_format(self.game_date))
                except:
                    pass

            # ricarica tab obiettivi se presente
            try:
                if hasattr(self, 'objectives_tree') and hasattr(self, 'load_objectives_list'):
                    self.load_objectives_list(self.objectives_tree)
            except Exception as e:
                self.append_time_log(f"Impossibile aggiornare lista obiettivi GUI: {e}")

            # aggiorna lista imprevisti
            try:
                self.load_pending_events()
            except Exception as e:
                self.append_time_log(f"Errore aggiornamento imprevisti GUI: {e}")

            messagebox.showinfo("Successo", f"Avanzati {days} giorni. Data: {self.convert_date_to_ded_format(self.game_date)}")

        except Exception as e:
            messagebox.showerror("Errore", f"Errore avanzamento giorni: {e}")
            self.append_time_log(f"Errore avanzamento giorni: {e}")

    def advance_weeks(self, weeks=1):
        """Avanza settimane Mystara (7 giorni ogni settimana)."""
        try:
            for w in range(weeks):
                self.append_time_log(f"📅 Settimana {w+1}/{weeks} — avanzamento 7 giorni")

                # Avanza 7 giorni in una volta sola
                self.advance_days(7)

                # EVENTI SETTIMANALI
                try:
                    self._apply_weekly_events()
                except Exception as e:
                    self.append_time_log(f"Errore eventi settimanali: {e}")

            # Aggiorna GUI
            if hasattr(self, "date_label"):
                self.date_label.config(text=self.convert_date_to_ded_format(self.game_date))

            messagebox.showinfo(
                "Successo",
                f"Avanzate {weeks} settimane. Data: {self.convert_date_to_ded_format(self.game_date)}"
            )

        except Exception as e:
            messagebox.showerror("Errore", f"Errore avanzamento settimane: {e}")
            self.append_time_log(f"Errore advance_weeks: {e}")

    def advance_months(self, months=1):
        """Avanza mesi Mystara, 28 giorni ciascuno."""
        try:
            total_days = months * self.DAYS_PER_MONTH
            self.append_time_log(f"📆 Avanzamento Mystara: {months} mese/i → {total_days} giorni")

            # Avanza tutti i giorni in una volta
            self.advance_days(total_days)

            for month_index in range(months):
                self.append_time_log(f"→ Applico eventi mensili Mystara ({month_index + 1}/{months})")
                try:
                    self._apply_monthly_events()
                except Exception as e:
                    self.append_time_log(f"Errore eventi mensili mese {month_index + 1}: {e}")

            messagebox.showinfo(
                "Successo",
                f"Avanzati {months} mesi Mystara. Data: {self.convert_date_to_ded_format(self.game_date)}"
            )

        except Exception as e:
            messagebox.showerror("Errore", f"Errore avanzamento mesi: {e}")
            self.append_time_log(f"Errore advance_months: {e}")

    def _apply_daily_events(self):
        """Applica eventi giornalieri (attività, spese, progress obiettivi 1/30)."""
        self.append_time_log("Applicazione eventi giornalieri...")
        try:
            cursor = self.db.cursor()

            # Attività economiche giornaliere
            cursor.execute("""
                SELECT ea.*, pc.user_id
                FROM economic_activities ea
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
                LEFT JOIN player_characters pc ON ea.pg_id = pc.id
            """)
            activities = cursor.fetchall() or []
            for activity in activities:
                if str(activity.get('frequency', '')).lower() != 'giornaliera':
                    continue
                dest_bank_id = activity.get('destination_bank_id')
                if not dest_bank_id:
                    self.append_time_log(f"  Attività '{activity.get('description','?')}' senza banca: guadagno non applicato")
                    continue
                income = float(activity.get('income') or 0.0)
                try:
                    cursor.execute("START TRANSACTION")
                    cursor.execute("UPDATE banks SET current_balance = current_balance + %s WHERE id = %s", (income, dest_bank_id))
                    cursor.execute("""
                        INSERT INTO bank_transactions
                        (pg_id, user_id, bank_id, operation_type, amount, reason, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """, (
                        activity.get('pg_id'),
                        activity.get('user_id'),
                        dest_bank_id,
                        'ATTIVITA_ECONOMICA',
                        income,
                        f"Attività giornaliera: {activity.get('description', '')}"
                    ))
                    self.db.commit()
                    self.append_time_log(f"  Guadagno giornaliero {income:.2f} MO -> banca id {dest_bank_id}")
                except Exception as e:
                    try:
                        self.db.rollback()
                    except:
                        pass
                    self.append_time_log(f"  Errore aggiornamento banca per attività {activity.get('description')}: {e}")

            # Spese fisse giornaliere
            cursor.execute("""
                SELECT fe.*, pc.user_id
                FROM fixed_expenses fe
                LEFT JOIN banks b ON fe.source_bank_id = b.id
                LEFT JOIN player_characters pc ON fe.pg_id = pc.id
            """)
            expenses = cursor.fetchall() or []
            for expense in expenses:
                if str(expense.get('frequency', '')).lower() != 'giornaliera':
                    continue
                src_bank_id = expense.get('source_bank_id')
                if not src_bank_id:
                    self.append_time_log(f"  Spesa '{expense.get('description','?')}' senza banca: non applicata")
                    continue
                amount = float(expense.get('amount') or 0.0)
                try:
                    cursor.execute("START TRANSACTION")
                    cursor.execute(
                        "UPDATE banks SET current_balance = current_balance - %s WHERE id = %s AND current_balance >= %s",
                        (amount, src_bank_id, amount)
                    )
                    if cursor.rowcount == 0:
                        self.db.rollback()
                        self.append_time_log(f"  Saldo insufficiente per '{expense.get('description')}' (banca id {src_bank_id})")
                        continue
                    cursor.execute("""
                        INSERT INTO bank_transactions
                        (pg_id, user_id, bank_id, operation_type, amount, reason, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """, (
                        expense.get('pg_id'),
                        expense.get('user_id'),
                        src_bank_id,
                        'SPESA_FISSA',
                        amount,
                        f"Spesa fissa giornaliera: {expense.get('description', '')}"
                    ))
                    self.db.commit()
                    self.append_time_log(f"  Spesa giornaliera {amount:.2f} MO prelevata da banca id {src_bank_id}")
                except Exception as e:
                    try:
                        self.db.rollback()
                    except:
                        pass
                    self.append_time_log(f"  Errore applicazione spesa '{expense.get('description')}': {e}")

            # Applica 1/28 di mese sugli obiettivi
            self._apply_objective_progress(frazione_mensile=1/28.0, etichetta='giornaliero')

        except Exception as e:
            self.append_time_log(f"Errore in _apply_daily_events: {e}")
        finally:
            try:
                cursor.close()
            except:
                pass

    def _apply_weekly_events(self):
        """Applica eventi settimanali e 1/4 mese sugli obiettivi."""
        self.append_time_log("Applicazione eventi settimanali...")
        try:
            cursor = self.db.cursor()

            # Attività economiche settimanali
            cursor.execute("""
                SELECT ea.*, pc.user_id
                FROM economic_activities ea
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
                LEFT JOIN player_characters pc ON ea.pg_id = pc.id
            """)
            activities = cursor.fetchall() or []
            for activity in activities:
                if str(activity.get('frequency', '')).lower() != 'settimanale':
                    continue
                dest_bank_id = activity.get('destination_bank_id')
                if not dest_bank_id:
                    self.append_time_log(f"  Attività '{activity.get('description','?')}' senza banca: guadagno non applicato")
                    continue
                income = float(activity.get('income') or 0.0)
                try:
                    cursor.execute("START TRANSACTION")
                    cursor.execute("UPDATE banks SET current_balance = current_balance + %s WHERE id = %s", (income, dest_bank_id))
                    cursor.execute("""
                        INSERT INTO bank_transactions
                        (pg_id, user_id, bank_id, operation_type, amount, reason, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """, (
                        activity.get('pg_id'),
                        activity.get('user_id'),
                        dest_bank_id,
                        'ATTIVITA_ECONOMICA',
                        income,
                        f"Attività settimanale: {activity.get('description', '')}"
                    ))
                    self.db.commit()
                    self.append_time_log(f"  Guadagno settimanale {income:.2f} MO -> banca id {dest_bank_id}")
                except Exception as e:
                    try:
                        self.db.rollback()
                    except:
                        pass
                    self.append_time_log(f"  Errore update banca attività settimanale: {e}")

            # Spese fisse settimanali
            cursor.execute("""
                SELECT fe.*, pc.user_id
                FROM fixed_expenses fe
                LEFT JOIN banks b ON fe.source_bank_id = b.id
                LEFT JOIN player_characters pc ON fe.pg_id = pc.id
            """)
            expenses = cursor.fetchall() or []
            for expense in expenses:
                if str(expense.get('frequency', '')).lower() != 'settimanale':
                    continue
                src_bank_id = expense.get('source_bank_id')
                if not src_bank_id:
                    self.append_time_log(f"  Spesa '{expense.get('description','?')}' senza banca: non applicata")
                    continue
                amount = float(expense.get('amount') or 0.0)
                try:
                    cursor.execute("START TRANSACTION")
                    cursor.execute(
                        "UPDATE banks SET current_balance = current_balance - %s WHERE id = %s AND current_balance >= %s",
                        (amount, src_bank_id, amount)
                    )
                    if cursor.rowcount == 0:
                        self.db.rollback()
                        self.append_time_log(f"  Saldo insufficiente per spesa '{expense.get('description')}' (banca id {src_bank_id})")
                        continue
                    cursor.execute("""
                        INSERT INTO bank_transactions
                        (pg_id, user_id, bank_id, operation_type, amount, reason, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """, (
                        expense.get('pg_id'),
                        expense.get('user_id'),
                        src_bank_id,
                        'SPESA_FISSA',
                        amount,
                        f"Spesa fissa settimanale: {expense.get('description', '')}"
                    ))
                    self.db.commit()
                    self.append_time_log(f"  Spesa settimanale {amount:.2f} MO prelevata da banca id {src_bank_id}")
                except Exception as e:
                    try:
                        self.db.rollback()
                    except:
                        pass
                    self.append_time_log(f"  Errore applicazione spesa settimanale: {e}")

            # Gli obiettivi avanzano gia' giorno per giorno dentro advance_days().
            # Non applicare qui un ulteriore avanzamento settimanale, altrimenti
            # avanzare di una settimana raddoppia progresso e costi.

        except Exception as e:
            self.append_time_log(f"Errore in _apply_weekly_events: {e}")
        finally:
            try:
                cursor.close()
            except:
                pass

    def _apply_monthly_events(self):
        """Applica eventi mensili (spese/attività mensili e progress 1 mese)."""
        self.append_time_log("Applicazione eventi mensili...")
        try:
            cursor = self.db.cursor()

            # Spese mensili
            cursor.execute("""
                SELECT fe.*, pc.user_id
                FROM fixed_expenses fe
                LEFT JOIN banks b ON fe.source_bank_id = b.id
                LEFT JOIN player_characters pc ON fe.pg_id = pc.id
            """)
            fixed_expenses = cursor.fetchall() or []
            for expense in fixed_expenses:
                if str(expense.get('frequency', '')).lower() != 'mensile':
                    continue
                src_bank_id = expense.get('source_bank_id')
                if not src_bank_id:
                    self.append_time_log(f"  Spesa '{expense.get('description','?')}' senza banca: non applicata")
                    continue
                amount = float(expense.get('amount') or 0.0)
                try:
                    cursor.execute("START TRANSACTION")
                    cursor.execute(
                        "UPDATE banks SET current_balance = current_balance - %s WHERE id = %s AND current_balance >= %s",
                        (amount, src_bank_id, amount)
                    )
                    if cursor.rowcount == 0:
                        self.db.rollback()
                        self.append_time_log(f"  Saldo insufficiente per spesa mensile '{expense.get('description')}' (banca id {src_bank_id})")
                        continue
                    cursor.execute("""
                        INSERT INTO bank_transactions
                        (pg_id, user_id, bank_id, operation_type, amount, reason, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """, (
                        expense.get('pg_id'),
                        expense.get('user_id'),
                        src_bank_id,
                        'SPESA_FISSA',
                        amount,
                        f"Spesa fissa mensile: {expense.get('description', '')}"
                    ))
                    self.db.commit()
                    self.append_time_log(f"  Spesa mensile {amount:.2f} MO prelevata da banca id {src_bank_id}")
                except Exception as e:
                    try:
                        self.db.rollback()
                    except:
                        pass
                    self.append_time_log(f"  Errore applicazione spesa mensile: {e}")

            # Attività mensili
            cursor.execute("""
                SELECT ea.*, pc.user_id
                FROM economic_activities ea
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
                LEFT JOIN player_characters pc ON ea.pg_id = pc.id
            """)
            activities = cursor.fetchall() or []
            for activity in activities:
                if str(activity.get('frequency', '')).lower() != 'mensile':
                    continue
                dest_bank_id = activity.get('destination_bank_id')
                if not dest_bank_id:
                    self.append_time_log(f"  Attività '{activity.get('description','?')}' senza banca: guadagno non applicato")
                    continue
                income = float(activity.get('income') or 0.0)
                try:
                    cursor.execute("START TRANSACTION")
                    cursor.execute("UPDATE banks SET current_balance = current_balance + %s WHERE id = %s", (income, dest_bank_id))
                    cursor.execute("""
                        INSERT INTO bank_transactions
                        (pg_id, user_id, bank_id, operation_type, amount, reason, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """, (
                        activity.get('pg_id'),
                        activity.get('user_id'),
                        dest_bank_id,
                        'ATTIVITA_ECONOMICA',
                        income,
                        f"Attività mensile: {activity.get('description', '')}"
                    ))
                    self.db.commit()
                    self.append_time_log(f"  Guadagno mensile {income:.2f} MO -> banca id {dest_bank_id}")
                except Exception as e:
                    try:
                        self.db.rollback()
                    except:
                        pass
                    self.append_time_log(f"  Errore update banca per attività mensile: {e}")

            # Gli obiettivi avanzano gia' giorno per giorno dentro advance_days().
            # Non applicare qui un ulteriore avanzamento mensile, altrimenti
            # avanzare di un mese raddoppia progresso e costi.

        except Exception as e:
            self.append_time_log(f"Errore in _apply_monthly_events: {e}")
        finally:
            try:
                cursor.close()
            except:
                pass

    def _apply_objective_progress(self, frazione_mensile=1.0, etichetta='periodico'):
        """
        Applica progresso obiettivi basato sulla frazione di mese passata.
        Aggiorna progress_percentage e preleva il costo dalla banca collegata.
        """
        self.append_time_log(f"Applicazione avanzamento obiettivi ({etichetta}) — frazione_mensile={frazione_mensile}")
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT fo.*, f.pg_id, pc.user_id
                FROM follower_objectives fo
                LEFT JOIN followers f ON fo.follower_id = f.id
                LEFT JOIN player_characters pc ON f.pg_id = pc.id
                WHERE fo.status = %s
            """, (self.OBJECTIVE_STATUS['IN_CORSO'],))
            objectives = cursor.fetchall() or []

            for obj in objectives:
                obj_id = obj.get('id')
                name = obj.get('name', 'Sconosciuto')
                bank_id = obj.get('bank_id')
                pg_id = obj.get('pg_id')
                user_id = obj.get('user_id') or (self.current_user.get('id') if self.current_user else None)
                estimated_months = int(obj.get('estimated_months') or 0)
                total_cost = float(obj.get('total_cost') or 0.0)
                progress_pct = float(obj.get('progress_percentage') or 0.0)

                duration_months = estimated_months
                if duration_months <= 0 or estimated_months <= 0:
                    self.append_time_log(f"  Obiettivo '{name}' ha mesi non validi, ignorato.")
                    continue

                progress_per_month = (100.0 / duration_months) if duration_months > 0 else 0.0

                progress_to_apply = progress_per_month * float(frazione_mensile)
                new_progress = min(progress_pct + progress_to_apply, 100.0)
                actual_progress_delta = max(new_progress - progress_pct, 0.0)
                cost_to_apply = total_cost * (actual_progress_delta / 100.0)

                if not bank_id:
                    self.append_time_log(f"  Obiettivo '{name}' senza banca; costo non applicato.")
                    continue

                cursor.execute("SELECT current_balance FROM banks WHERE id = %s", (bank_id,))
                bank = cursor.fetchone()
                if not bank:
                    self.append_time_log(f"  Obiettivo '{name}' collegato a banca non trovata (id {bank_id}).")
                    continue

                current_balance = float(bank.get('current_balance') or 0.0)

                if cost_to_apply > 0 and current_balance < cost_to_apply:
                    self.append_time_log(f"  Saldo insufficiente per obiettivo '{name}' (necessario {cost_to_apply:.2f}, disponibile {current_balance:.2f})")
                    continue

                new_status = obj.get('status')
                if new_progress >= 100.0:
                    new_status = self.OBJECTIVE_STATUS['COMPLETATO']

                try:
                    cursor.execute("START TRANSACTION")

                    if cost_to_apply > 0:
                        new_balance = current_balance - cost_to_apply
                        cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, bank_id))
                        cursor.execute("""
                            INSERT INTO bank_transactions
                            (pg_id, user_id, bank_id, operation_type, amount, reason, timestamp)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        """, (
                            pg_id,
                            user_id,
                            bank_id,
                            'COSTO_OBIETTIVO',
                            cost_to_apply,
                            f"Avanzamento obiettivo '{name}' {progress_pct:.2f}% -> {new_progress:.2f}%"
                        ))

                    cursor.execute("""
                        UPDATE follower_objectives
                        SET progress_percentage = %s, status = %s
                        WHERE id = %s
                    """, (new_progress, new_status, obj_id))
                    self.db.commit()
                    if cost_to_apply > 0:
                        self.append_time_log(
                            f"  Prelevati {cost_to_apply:.2f} MO per obiettivo '{name}' "
                            f"({progress_pct:.2f}% -> {new_progress:.2f}%, banca id {bank_id})"
                        )
                    else:
                        self.append_time_log(f"  Obiettivo '{name}' senza costo da applicare in questo avanzamento.")
                    self.append_time_log(f"  Obiettivo '{name}': {progress_pct:.1f}% -> {new_progress:.1f}% (status: {self.OBJECTIVE_STATUS_REV.get(new_status,new_status)})")
                    # se completato, aggiorna GUI obiettivi
                    if new_status == self.OBJECTIVE_STATUS['COMPLETATO']:
                        try:
                            if hasattr(self, 'objectives_tree') and hasattr(self, 'load_objectives_list'):
                                self.load_objectives_list(self.objectives_tree)
                        except Exception as e:
                            self.append_time_log(f"  Impossibile ricaricare GUI obiettivi: {e}")
                except Exception as e:
                    try:
                        self.db.rollback()
                    except:
                        pass
                    self.append_time_log(f"  Errore aggiornamento obiettivo '{name}': {e}")

        except Exception as e:
            self.append_time_log(f"Errore in _apply_objective_progress: {e}")
        finally:
            try:
                cursor.close()
            except:
                pass

    def apply_unhandled_objective_events(self):
        """Applica automaticamente le scelte dei giocatori per gli imprevisti non ancora gestiti."""
        self.append_time_log("Applicazione scelte imprevisti non gestiti...")
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT id, objective_id, player_choice, response_options, handled
                FROM follower_objective_events
                WHERE handled = FALSE
            """)
            events = cursor.fetchall() or []

            if not events:
                self.append_time_log("  Nessun imprevisto non gestito.")
                try:
                    cursor.close()
                except:
                    pass
                return

            for event in events:
                eid = event.get('id')
                player_choice_raw = event.get('player_choice')
                response_options_raw = event.get('response_options')

                if not player_choice_raw or not response_options_raw:
                    self.append_time_log(f"  Evento id {eid} senza scelta/opzioni; saltato.")
                    continue

                # decode JSON sicuro
                try:
                    if isinstance(player_choice_raw, bytes):
                        player_choice_raw = player_choice_raw.decode('utf-8')
                    player_choice = json.loads(player_choice_raw) if isinstance(player_choice_raw, str) else player_choice_raw
                except Exception as e:
                    self.append_time_log(f"  Impossibile decodificare player_choice evento {eid}: {e}")
                    continue

                if not isinstance(player_choice, dict) or 'option' not in player_choice:
                    self.append_time_log(f"  player_choice evento {eid} malformato; saltato.")
                    continue

                objective_id = event.get('objective_id')
                cursor.execute("""
                    SELECT name, estimated_months, total_cost, progress_percentage, status
                    FROM follower_objectives
                    WHERE id = %s
                """, (objective_id,))
                objective = cursor.fetchone()
                if not objective:
                    self.append_time_log(f"  Obiettivo id {objective_id} non trovato per evento {eid}")
                    continue

                name = objective.get('name', 'Sconosciuto')
                est_months = int(objective.get('estimated_months') or 0)
                tot_cost = float(objective.get('total_cost') or 0.0)
                old_progress = float(objective.get('progress_percentage') or 0.0)

                if player_choice.get('fail'):
                    try:
                        cursor.execute("START TRANSACTION")
                        cursor.execute("UPDATE follower_objectives SET status = %s WHERE id = %s", (self.OBJECTIVE_STATUS['FALLITO'], objective_id))
                        cursor.execute("UPDATE follower_objective_events SET handled = TRUE WHERE id = %s", (eid,))
                        self.db.commit()
                        self.append_time_log(f"  Evento {eid}: obiettivo '{name}' segnato FALLITO (scelta giocatore).")
                    except Exception as e:
                        try:
                            self.db.rollback()
                        except:
                            pass
                        self.append_time_log(f"  Errore marking FAIL per obiettivo {objective_id}: {e}")
                else:
                    add_months = int(player_choice.get('extra_months', 0))
                    add_cost = float(player_choice.get('extra_cost', 0.0))
                    new_est = max(1, est_months + add_months)
                    new_cost = max(0.0, tot_cost + add_cost)
                    if est_months > 0 and new_est != est_months:
                        recalibrated_progress = min(max(old_progress * (est_months / new_est), 0.0), 100.0)
                    else:
                        recalibrated_progress = old_progress

                    new_status = objective.get('status')
                    if recalibrated_progress >= 100.0:
                        new_status = self.OBJECTIVE_STATUS['COMPLETATO']

                    try:
                        cursor.execute("START TRANSACTION")
                        cursor.execute("""
                            UPDATE follower_objectives
                            SET estimated_months = %s,
                                total_cost = %s,
                                progress_percentage = %s,
                                status = %s
                            WHERE id = %s
                        """, (new_est, new_cost, recalibrated_progress, new_status, objective_id))
                        cursor.execute("UPDATE follower_objective_events SET handled = TRUE, extra_cost = %s, extra_months = %s WHERE id = %s", (add_cost, add_months, eid))
                        self.db.commit()
                        self.append_time_log(
                            f"  Evento {eid}: obiettivo '{name}' aggiornato "
                            f"{est_months} -> {new_est} mesi, {tot_cost:.2f} -> {new_cost:.2f} MO, "
                            f"progresso {old_progress:.2f}% -> {recalibrated_progress:.2f}%"
                        )
                    except Exception as e:
                        try:
                            self.db.rollback()
                        except:
                            pass
                        self.append_time_log(f"  Errore aggiornamento obiettivo per evento {eid}: {e}")

            # ricarica lista imprevisti pendenti in GUI
            try:
                self.load_pending_events()
            except Exception as e:
                self.append_time_log(f"Errore aggiornamento imprevisti GUI: {e}")

        except Exception as e:
            self.append_time_log(f"Errore in apply_unhandled_objective_events: {e}")
        finally:
            try:
                cursor.close()
            except:
                pass

    def load_pending_events(self):
        """Carica imprevisti/obiettivi in sospeso nella Listbox GUI (best-effort)."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT 
                    e.id AS event_id,
                    e.objective_id,
                    e.description,
                    e.extra_months,
                    e.extra_cost,
                    e.response_options,
                    e.player_choice,
                    e.event_date,
                    o.name AS objective_name
                FROM follower_objective_events e
                LEFT JOIN follower_objectives o ON e.objective_id = o.id
                WHERE e.handled = FALSE
                ORDER BY e.event_date DESC
            """)
            rows = cursor.fetchall() or []
            cursor.close()
        except Exception as e:
            self.append_time_log(f"Errore load_pending_events: {e}")
            rows = []

        try:
            if hasattr(self, 'imprevisti_listbox') and self.imprevisti_listbox is not None:
                try:
                    widget_ok = self.imprevisti_listbox.winfo_exists()
                except Exception:
                    widget_ok = False
                if widget_ok:
                    self.imprevisti_listbox.delete(0, tk.END)
                    for r in rows:
                        label = f"{r.get('objective_name','?')} - {str(r.get('description',''))[:80]}"
                        self.imprevisti_listbox.insert(tk.END, label)
                else:
                    # widget distrutto: stampa solo sul log
                    for r in rows:
                        self.append_time_log(f"PENDENTE: {r.get('objective_name','?')} - {r.get('description','')}")
            else:
                # se non esiste la GUI, stampo il riepilogo su log
                for r in rows:
                    self.append_time_log(f"PENDENTE: {r.get('objective_name','?')} - {r.get('description','')}")
        except Exception as e:
            self.append_time_log(f"Errore aggiornamento imprevisti GUI: {e}")

    def show_current_game_date(self):
        """Mostra la data di gioco corrente nel formato Mystara (GUI)."""
        try:
            messagebox.showinfo("Data di Gioco", self.convert_date_to_ded_format(self.game_date))
        except Exception as e:
            self.append_time_log(f"Errore show_current_game_date: {e}")

    def set_date_manually_dialog(self):
        """Impostazione manuale usando il formato Mystara (GG MESE ANNO)"""
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showwarning("Avviso", "Solo un DM può impostare manualmente la data.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Imposta Data Mystara")
        dialog.geometry("400x250")

        # Mostra data corrente in formato Mystara
        current_mystara = self.convert_date_to_ded_format(self.game_date)
        ttk.Label(dialog, text=f"Data attuale: {current_mystara}", 
                  font=('Arial', 10, 'bold')).pack(pady=5)
        
        ttk.Label(dialog, text="Formato: GG MESE ANNO (es: 15 THAUMONT 1000)").pack(pady=8)
        
        # Frame per input
        input_frame = ttk.Frame(dialog)
        input_frame.pack(pady=10)
        
        # Giorno
        ttk.Label(input_frame, text="Giorno:").grid(row=0, column=0, padx=5, pady=5)
        day_entry = ttk.Spinbox(input_frame, from_=1, to=28, width=5)
        day_entry.grid(row=0, column=1, padx=5, pady=5)
        
        # Mese
        ttk.Label(input_frame, text="Mese:").grid(row=0, column=2, padx=5, pady=5)
        month_combo = ttk.Combobox(input_frame, values=self.MONTH_NAMES, width=12, state='readonly')
        month_combo.grid(row=0, column=3, padx=5, pady=5)
        
        # Anno
        ttk.Label(input_frame, text="Anno:").grid(row=0, column=4, padx=5, pady=5)
        year_entry = ttk.Entry(input_frame, width=8)
        year_entry.grid(row=0, column=5, padx=5, pady=5)
        
        # Precompila con la data corrente
        try:
            # Estrai giorno, mese e anno dalla data Mystara corrente
            parts = current_mystara.split()
            if len(parts) == 3:
                day_entry.delete(0, tk.END)
                day_entry.insert(0, parts[0])
                
                month_combo.set(parts[1])
                
                year_entry.delete(0, tk.END)
                year_entry.insert(0, parts[2])
        except:
            # Valori di default in caso di errore
            day_entry.insert(0, "1")
            month_combo.set("NUWMONT")
            year_entry.insert(0, "1")

        def save_date():
            try:
                day = int(day_entry.get().strip())
                month_name = month_combo.get().strip()
                year = int(year_entry.get().strip())
                
                if not (1 <= day <= 28):
                    messagebox.showerror("Errore", "Il giorno deve essere tra 1 e 28")
                    return
                
                if month_name not in self.MONTH_NAMES:
                    messagebox.showerror("Errore", "Mese non valido")
                    return
                
                if year < 1:
                    messagebox.showerror("Errore", "L'anno deve essere maggiore di 0")
                    return
                
                # CALCOLO CORRETTO DELL'ABSOLUTE_DAY
                # Anni completi: (year - 1) * 336 giorni
                # Mesi completi: month_index * 28 giorni  
                # Giorni nel mese corrente: (day - 1) perché i giorni partono da 0
                month_index = self.MONTH_NAMES.index(month_name)
                absolute_day = ((year - 1) * self.DAYS_PER_YEAR + 
                               (month_index * self.DAYS_PER_MONTH) + 
                               (day - 1))
                
                # Converti absolute_day in data gregoriana per il salvataggio
                new_date = self.absolute_day_to_date(absolute_day)

                current_abs = self.date_to_absolute_day(self.game_date)
                delta_days = absolute_day - current_abs
                new_mystara_date = f"{day:02d} {month_name} {year}"

                if delta_days > 0:
                    if not messagebox.askyesno(
                        "Conferma avanzamento",
                        "La nuova data è nel futuro.\n"
                        f"Avanzare di {delta_days} giorno/i applicando attività, spese, obiettivi, imprevisti e interessi?"
                    ):
                        return
                    dialog.destroy()
                    self.append_time_log(f"Cambio data manuale in avanti verso {new_mystara_date}: applico {delta_days} giorno/i.")
                    self.advance_days(delta_days)
                    return

                if delta_days < 0:
                    if not messagebox.askyesno(
                        "Conferma arretramento",
                        "La nuova data è nel passato.\n"
                        "Il sistema aggiornerà solo la data: attività, spese, obiettivi e interessi non verranno invertiti.\n"
                        "Vuoi procedere?"
                    ):
                        return

                # Data uguale o arretramento confermato: aggiorna solo stato data.
                self.game_date = new_date
                self._update_game_state_date(new_date)

                if hasattr(self, 'date_label'):
                    try:
                        self.date_label.config(text=self.convert_date_to_ded_format(new_date))
                    except:
                        pass

                self.append_time_log(f"Data impostata manualmente: {new_mystara_date}")
                messagebox.showinfo("Successo", f"Data impostata a:\n{new_mystara_date}\nGregoriana: {new_date}\nAbsolute_day: {absolute_day}")
                dialog.destroy()
                
                try:
                    self.show_time_menu()
                except:
                    pass
                    
            except ValueError:
                messagebox.showerror("Errore", "Valori non validi. Controlla giorno e anno.")
            except Exception as e:
                messagebox.showerror("Errore", f"Errore salvataggio data: {e}")
        ttk.Button(dialog, text="💾 Salva", command=save_date).pack(pady=12)

    def show_about(self):
        """Mostra informazioni sull'applicazione"""
        about_text = f"""
    🎲 D&D Tool - Gestione Campagna

    Versione: {__VERSION__}
    Autore: Massimo Trevisan

    Un tool completo per la gestione di campagne
    Dungeons & Dragons con calendario Mystara.

    Funzionalità:
    • Gestione Personaggi
    • Sistema Bancario con desposito Oggetti
    • Seguaci, Obiettivi, Imprevisti
    • Attività Economiche
    • Spese Fisse
    • Sistema Chat
    • Diario Campagna    

    Database: SQL MariaDB
    Interfaccia: Tkinter/Python
        """
        
        messagebox.showinfo("Informazioni", about_text)

    # FUNZIONE: Toggle fullscreen
    def toggle_fullscreen(self):
        """Attiva/disattiva schermo intero"""
        current_state = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not current_state)

    def init_connection_pool(self):
        with self._pool_lock:
            if not self._pool_initialized:
                try:
                    self.connection_pool = PooledDB(
                        creator=pymysql,
                        host=self.env_sec.get("DB_HOST"),
                        user=self.env_sec.get("DB_USER"),
                        password=self.env_sec.get("DB_PASSWORD"),
                        database=self.env_sec.get("DB_NAME"),
                        port=int(self.env_sec.get("DB_PORT", 3307)),
                        charset='utf8mb4',
                        autocommit=True,
                        cursorclass=pymysql.cursors.DictCursor,
                        mincached=2,      # Connessioni minime nel pool
                        maxcached=5,      # Connessioni massime nel pool  
                        maxconnections=10, # Connessioni totali massime
                        blocking=True,    # Aspetta se pool pieno
                        ping=2            # Check connessione all'uso
                    )
                    self._pool_initialized = True
                    
                except Exception as e:
                    print(f"❌ Errore inizializzazione pool PyMySQL: {e}")
                    # Fallback alla connessione normale
                    self.connect_database()

    def get_db_connection(self):
        if not self._pool_initialized:
            self.init_connection_pool()
        
        try:
            if self.connection_pool:
                return self.connection_pool.connection()
            else:
                # Fallback alla connessione esistente
                return self.db
        except Exception as e:
            print(f"❌ Errore ottenimento connessione pool: {e}")
            try:
                # prova a re-inizializzare il pool
                self._pool_initialized = False
                self.init_connection_pool()
                if self.connection_pool:
                    return self.connection_pool.connection()
            except Exception as e2:
                print(f"❌ Errore reinizializzazione pool: {e2}")
            return self.db

    def safe_cursor(self):
        """
        Restituisce (conn, cursor) da pool oppure una connessione di fallback.
        In caso di errore tenta una riconnessione re-inizializzando il pool.
        """
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            return conn, cursor
        except Exception as e:
            print(f"⚠️ safe_cursor: errore ottenimento connessione: {e} - provo a re-inizializzare il pool")

            try:
                self._pool_initialized = False
                self.init_connection_pool()
                conn = self.get_db_connection()
                cursor = conn.cursor()
                return conn, cursor
            except Exception as e2:
                print(f"❌ safe_cursor: reconnection failed: {e2}")

                # fallback estremo: prova self.db se esiste
                try:
                    cursor = self.db.cursor()
                    return self.db, cursor
                except Exception:
                    raise

    def close_connection(self, connection, cursor=None):
        try:
            if cursor:
                cursor.close()
            if connection and connection != self.db:
                connection.close()
        except Exception as e:
            print(f"❌ Errore chiusura connessione: {e}")

    def show_chat(self):
        """Apertura chat con pulizia corretta"""
        # Pulizia chat precedente
        if hasattr(self, '_current_chat_cleanup'):
            try:
                self._current_chat_cleanup()
            except:
                pass
        
        if hasattr(self, '_current_chat_frame') and self._current_chat_frame:
            try:
                if hasattr(self._current_chat_frame, '_polling_active'):
                    self._current_chat_frame._polling_active = False
            except:
                pass
        
        self.clear_content()

        title = ttk.Label(self.content_frame, text="💬 Sistema Chat", style='Title.TLabel')
        title.pack(pady=10)

        unread_counts = self._count_unread_by_category_fast()
        notebook = ttk.Notebook(self.content_frame)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

        self._chat_users_cache = self._get_chat_users_cache()

        # Tab Chat Comune
        comune_label = "💬 Chat Comune"
        if unread_counts.get('comune', 0) > 0:
            comune_label += f" ({unread_counts['comune']})"
        comune_frame = ttk.Frame(notebook)
        notebook.add(comune_frame, text=comune_label)
        
        # 🔥 MODIFICA: Rendi il frame accessibile e crea l'interfaccia
        self._chat_common_frame = comune_frame
        self._current_chat_frame = self.create_chat_interface_fast(comune_frame, chat_type='comune')

        # Tab Chat Segreta
        segreta_label = "🤫 Chat Segreta"
        if unread_counts.get('segreti', 0) > 0:
            segreta_label += f" ({unread_counts['segreti']})"
        segreta_frame = ttk.Frame(notebook)
        notebook.add(segreta_frame, text=segreta_label)
        self.create_secret_chat_interface_fast(segreta_frame)

        def stop_all_polling():
            try:
                if hasattr(comune_frame, '_polling_active'):
                    comune_frame._polling_active = False
                
                self._close_all_chat_windows()
                
                # 🔥 MODIFICA: NON cancellare tutto il dict, solo la chiave specifica
                if hasattr(self, '_last_chat_message_id'):
                    chat_key = f"comune_{self.current_user['id']}"
                    if chat_key in self._last_chat_message_id:
                        del self._last_chat_message_id[chat_key]
                        
            except Exception as e:
                print(f"Errore stop polling: {e}")

        def on_tab_changed(event):
            selected_tab = notebook.index(notebook.select())
            tab_name = notebook.tab(selected_tab, "text")

            if "(" in tab_name:
                clean_name = tab_name.split(" (")[0]
                notebook.tab(selected_tab, text=clean_name)

            self.update_chat_button_fast()

            # Refresh leggero quando si torna al tab Chat Comune: non azzerare l'ultimo ID,
            # altrimenti ogni cambio tab ricarica lo storico e peggiora il lag.
            if "Chat Comune" in tab_name:
                try:
                    # Trova il widget messages_text all'interno del frame
                    for widget in comune_frame.winfo_children():
                        if isinstance(widget, ttk.Frame):
                            for subwidget in widget.winfo_children():
                                if isinstance(subwidget, scrolledtext.ScrolledText):
                                    chat_key = f"comune_{self.current_user['id']}"
                                    self._load_common_messages_display(subwidget, chat_key)
                                    break
                except Exception as e:
                    print(f"Errore refresh chat comune: {e}")
            
            if "Chat Segreta" in tab_name:
                if hasattr(self, "secret_contacts_tree"):
                    self._load_secret_conversations_list(self.secret_contacts_tree)

        notebook.bind("<<NotebookTabChanged>>", on_tab_changed)
        
        def cleanup_chat():
            stop_all_polling()
            notebook.unbind("<<NotebookTabChanged>>")
            
            if hasattr(self, '_current_chat_frame'):
                self._current_chat_frame = None
            if hasattr(self, '_chat_common_frame'):
                self._chat_common_frame = None  # 🔥 Aggiungi questa pulizia
            if hasattr(self, '_chat_notebook'):
                self._chat_notebook = None
        
        self._current_chat_cleanup = cleanup_chat
        self._chat_notebook = notebook
        
        # La chat comune viene gia' inizializzata da create_chat_interface_fast().
        # Evitare un secondo caricamento iniziale ritardato riduce query duplicate e lag.
        
        return notebook

    def _initialize_chat_common(self, comune_frame):
        """Inizializza la chat comune dopo un breve ritardo"""
        try:
            # Cerca il widget messages_text
            for widget in comune_frame.winfo_children():
                if isinstance(widget, ttk.Frame):
                    for subwidget in widget.winfo_children():
                        if isinstance(subwidget, scrolledtext.ScrolledText):
                            # Usa la nuova funzione di caricamento
                            chat_key = f"comune_{self.current_user['id']}"
                            self._load_common_messages_display(subwidget, chat_key)
                            break
        except Exception as e:
            print(f"Errore inizializzazione chat comune: {e}")

    def _get_chat_users_cache(self):
        """Cache per i dati degli utenti - una sola query"""
        conn = None
        cursor = None
        try:
            conn, cursor = self.safe_cursor()
            cursor.execute("SELECT id, username, role FROM users")
            return {user['id']: user for user in cursor.fetchall()}
        finally:
            self.close_connection(conn, cursor)

    def _count_unread_by_category_fast(self):
        """Conta messaggi non letti - Versione OTTIMIZZATA"""
        if not self.current_user:
            return {"comune": 0, "privati": 0, "segreti": 0}
        
        conn, cursor = self.safe_cursor()
        user_id = self.current_user['id']
        
        try:
            # Conta solo messaggi ricevuti/non propri: evita badge fantasma su messaggi inviati dall'utente.
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN c.receiver_id IS NULL AND c.is_secret = 0 AND c.sender_id != %s THEN 1 ELSE 0 END) as comune,
                    SUM(CASE WHEN c.is_secret = 1 AND c.receiver_id = %s THEN 1 ELSE 0 END) as segreti
                FROM chat_messages c
                LEFT JOIN chat_reads r ON c.id = r.message_id AND r.user_id = %s
                WHERE r.id IS NULL
                  AND c.sender_id != %s
            """, (user_id, user_id, user_id, user_id))
            
            result = cursor.fetchone()
            comune = result['comune'] or 0
            segreti = result['segreti'] or 0
            
            return {
                "comune": comune,
                "privati": 0,
                "segreti": segreti
            }
            
        finally:
            self.close_connection(conn, cursor)

    def create_chat_interface_fast(self, parent, chat_type='comune'):
        """Interfaccia chat comune con funzionamento simile alla chat segreta"""
        if not hasattr(self, '_last_chat_message_id'):
            self._last_chat_message_id = {}
        
        chat_key = f"{chat_type}_{self.current_user['id']}"
        
        # Inizializza last_id a 0
        if chat_key not in self._last_chat_message_id:
            self._last_chat_message_id[chat_key] = 0
        
        # Area messaggi
        messages_frame = ttk.Frame(parent)
        messages_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        messages_text = scrolledtext.ScrolledText(messages_frame, wrap=tk.WORD, height=20)
        messages_text.pack(fill='both', expand=True)
        messages_text.config(state='disabled')
        
        # Configura tag per messaggi nuovi
        messages_text.tag_configure("new_message",
                                    background='#e8f5e8',
                                    foreground='#2c3e50',
                                    font=('Arial', 10, 'normal'))
        
        # Input area - 🔥 QUESTA ERA LA PARTE MANCANTE!
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill='x', padx=5, pady=5)
        
        message_entry = ttk.Entry(input_frame)
        message_entry.pack(side='left', fill='x', expand=True, padx=5)
        
        send_btn = ttk.Button(input_frame, text="📤 Invia", command=lambda: self._send_common_message(message_entry, messages_text))
        send_btn.pack(side='right', padx=5)
        
        message_entry.bind('<Return>', lambda e: self._send_common_message(message_entry, messages_text))
            
        def load_messages_periodic():
            """Polling per chat comune - Versione simile a quella segreta"""
            if not hasattr(parent, '_polling_active') or not parent._polling_active:
                return
            
            parent._polling_scheduled = False
            
            try:
                was_at_bottom = messages_text.yview()[1] >= 0.95
                
                # Carica i messaggi
                self._load_common_messages_display(messages_text, chat_key)
                
                if was_at_bottom:
                    messages_text.see(tk.END)
                    
            except Exception as e:
                print(f"Errore polling chat comune: {e}")
            
            # Ripianifica il polling
            if hasattr(parent, '_polling_active') and parent._polling_active and not parent._polling_scheduled:
                try:
                    parent._polling_scheduled = True
                    polling_interval = 1500
                    parent.after_id = parent.after(polling_interval, load_messages_periodic)
                except Exception as e:
                    print(f"Errore scheduling: {e}")
        
        parent.load_messages_periodic = load_messages_periodic
        
        # Inizializza polling
        parent._polling_active = True
        parent._polling_scheduled = False
        
        # Avvia il polling
        load_messages_periodic()
        
        def clean_up_polling():
            """Pulizia risorse"""
            try:
                if hasattr(parent, '_polling_active'):
                    parent._polling_active = False
                
                if hasattr(parent, 'after_id'):
                    try:
                        parent.after_cancel(parent.after_id)
                    except:
                        pass
                
                chat_key = f"{chat_type}_{self.current_user['id']}"
                if hasattr(self, '_last_chat_message_id') and chat_key in self._last_chat_message_id:
                    del self._last_chat_message_id[chat_key]
                    
                
            except Exception as e:
                print(f"Errore pulizia: {e}")
        
        def on_parent_destroy(event):
            if event.widget == parent:
                clean_up_polling()
        
        parent.bind("<Destroy>", on_parent_destroy)
        
        return parent
        
    def _load_common_messages_display(self, text_widget, chat_key):
        """Carica e mostra i messaggi della chat comune - Versione simile a chat segreta"""
        conn = None
        cursor = None
        try:
            user_id = self.current_user['id']
            
            conn, cursor = self.safe_cursor()
            
            # 🔥 QUERY OTTIMIZZATA: simile a quella della chat segreta
            last_seen_id = self._last_chat_message_id.get(chat_key, 0)
            initial_load = last_seen_id <= 0

            if initial_load:
                cursor.execute("""
                    SELECT
                        c.id,
                        c.message,
                        c.created_at,
                        c.sender_id,
                        CASE
                            WHEN r.id IS NULL AND c.sender_id != %s THEN 1
                            ELSE 0
                        END as is_new
                    FROM chat_messages c
                    LEFT JOIN chat_reads r ON c.id = r.message_id AND r.user_id = %s
                    WHERE c.receiver_id IS NULL
                      AND c.is_secret = 0
                    ORDER BY c.id DESC
                    LIMIT 100
                """, (user_id, user_id))
                msgs = list(reversed(cursor.fetchall()))
            else:
                cursor.execute("""
                    SELECT
                        c.id,
                        c.message,
                        c.created_at,
                        c.sender_id,
                        CASE
                            WHEN r.id IS NULL AND c.sender_id != %s THEN 1
                            ELSE 0
                        END as is_new
                    FROM chat_messages c
                    LEFT JOIN chat_reads r ON c.id = r.message_id AND r.user_id = %s
                    WHERE c.receiver_id IS NULL
                      AND c.is_secret = 0
                      AND c.id > %s
                    ORDER BY c.id ASC
                    LIMIT 100
                """, (user_id, user_id, last_seen_id))
                msgs = cursor.fetchall()

            if not msgs and not initial_load:
                return
            
            # 🔥 MARCA COME LETTI IN BATCH
            new_msg_ids = [m['id'] for m in msgs if m['is_new'] == 1]
            
            if new_msg_ids:
                # Query batch per marcare come letti
                placeholders = ','.join(['%s'] * len(new_msg_ids))
                cursor.execute(f"""
                    INSERT IGNORE INTO chat_reads (user_id, message_id)
                    SELECT %s, id FROM chat_messages WHERE id IN ({placeholders})
                """, [user_id] + new_msg_ids)
                conn.commit()
            
            # 🔥 AGGIORNA L'ULTIMO ID (il più grande)
            if msgs:
                self._last_chat_message_id[chat_key] = max(m['id'] for m in msgs)
            
            # 🔥 MOSTRA MESSAGGI (in ordine cronologico inverso per visualizzazione)
            text_widget.config(state='normal')
            if initial_load:
                text_widget.delete(1.0, tk.END)
            
            for m in msgs:
                created_at = m.get('created_at')
                if created_at:
                    date_str = created_at.strftime('%d/%m/%Y %H:%M:%S')
                else:
                    date_str = ''
                
                sender_name = self._chat_users_cache.get(m['sender_id'], {}).get('username', 'Unknown')
                
                if m['sender_id'] == user_id:
                    header = f"[{date_str}] Tu: "
                else:
                    header = f"[{date_str}] {sender_name}: "
                
                text_widget.insert(tk.END, header)
                text_widget.insert(tk.END, m['message'] + "\n")
                
                # 🔥 EVIDENZIA IN VERDE CHIARO SOLO I NUOVI MESSAGGI
                if m['is_new'] == 1:
                    start_idx = text_widget.index("end-2l linestart")
                    end_idx = text_widget.index("end-1l lineend")
                    text_widget.tag_add("new_message", start_idx, end_idx)
            
            text_widget.config(state='disabled')
            text_widget.see(tk.END)
            
            # 🔥 AGGIORNA IL CONTATORE
            self.update_chat_button_fast()
            
        except Exception as e:
            print(f"Errore caricamento chat comune: {e}")
            traceback.print_exc()
        finally:
            self.close_connection(conn, cursor)

    def _send_common_message(self, message_entry, messages_text):
        """Invia messaggio nella chat comune - Versione semplificata"""
        text = message_entry.get().strip()
        if not text:
            return
        
        conn = None
        cursor = None
        try:
            conn, cursor = self.safe_cursor()
            
            # Inserisci il messaggio
            cursor.execute("""
                INSERT INTO chat_messages (sender_id, receiver_id, is_secret, message, created_at)
                VALUES (%s, NULL, 0, %s, NOW())
            """, (self.current_user['id'], text))
            
            # Marca come letto immediatamente (mio messaggio)
            new_msg_id = cursor.lastrowid
            cursor.execute("""
                INSERT IGNORE INTO chat_reads (user_id, message_id) VALUES (%s, %s)
            """, (self.current_user['id'], new_msg_id))
            
            conn.commit()
            
            message_entry.delete(0, tk.END)
            
            # 🔥 FORZA IL REFRESH DEI MESSAGGI
            chat_key = f"comune_{self.current_user['id']}"
            self._load_common_messages_display(messages_text, chat_key)
            
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore invio messaggio: {e}")
        finally:
            self.close_connection(conn, cursor)

    def _mark_and_remove_highlight(self, message_ids, text_widget):
        """
        Marca i messaggi come letti nel DB e rimuove l'evidenziazione verde
        dopo 3-5 secondi dalla visualizzazione
        """
        conn = None
        cursor = None
        try:
            # 1. Marca come letti nel database
            if message_ids:
                conn, cursor = self.safe_cursor()
                
                # Crea batch di INSERT per performance
                values = []
                for msg_id in message_ids:
                    values.append((self.current_user['id'], msg_id))
                
                # Esegui INSERT in batch
                cursor.executemany("""
                    INSERT IGNORE INTO chat_reads (user_id, message_id)
                    VALUES (%s, %s)
                """, values)
                
                conn.commit()
                # Aggiorna contatore chat
                self.update_chat_button_fast()
                            
            # 2. Rimuovi evidenziazione verde dalla UI
            text_widget.tag_remove("new_message", "1.0", "end")
            
        except Exception as e:
            print(f"❌ Errore in _mark_and_remove_highlight: {e}")
            traceback.print_exc()
        finally:
            self.close_connection(conn, cursor)

    def mark_common_chat_as_read(self):
        """Marca tutti i messaggi della chat comune come letti"""
        conn, cursor = self.safe_cursor()
        try:
            cursor.execute("""
                SELECT c.id 
                FROM chat_messages c
                LEFT JOIN chat_reads r ON c.id = r.message_id AND r.user_id = %s
                WHERE r.id IS NULL
                  AND c.receiver_id IS NULL
                  AND c.is_secret = 0
                  AND c.sender_id != %s
            """, (self.current_user['id'], self.current_user['id']))
            
            unread_ids = [row['id'] for row in cursor.fetchall()]
            
            if unread_ids:
                placeholders = ','.join(['%s'] * len(unread_ids))
                cursor.execute(f"""
                    INSERT IGNORE INTO chat_reads (user_id, message_id) 
                    VALUES {','.join([f'(%s, %s)'] * len(unread_ids))}
                """, [val for msg_id in unread_ids for val in (self.current_user['id'], msg_id)])
                conn.commit()
                
        finally:
            cursor.close()
            self.close_connection(conn)

    def _open_selected_secret_conversation(self, tree):
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Avviso", "Seleziona un contatto.")
            return
        contact_id = int(sel[0])
        self._open_secret_chat_window(contact_id)

    def create_secret_chat_interface_fast(self, parent):
        """Interfaccia chat segreta con fix doppio click"""
        if self.current_user['role'] == 'DM':
            ttk.Label(parent, text="🤫 Chat Segrete", style='Subtitle.TLabel').pack(pady=8)
        else:
            ttk.Label(parent, text="🤫 Chat Segrete tra Giocatori e DM", style='Subtitle.TLabel').pack(pady=8)

        container = ttk.Frame(parent)
        container.pack(fill='both', expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(container, width=380)
        left_frame.pack(side='left', fill='y')
        left_frame.pack_propagate(False)

        cols = ('nome', 'last', 'unread')
        tree = ttk.Treeview(left_frame, columns=cols, show='headings', height=25)
        tree.heading('nome', text='Contatto')
        tree.heading('last', text='Ultimo messaggio')
        tree.heading('unread', text='Non letti')
        tree.column('nome', width=140, anchor='w')
        tree.column('last', width=180, anchor='w')
        tree.column('unread', width=60, anchor='center')
        tree.pack(side='left', fill='both', expand=True)

        sb = ttk.Scrollbar(left_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')

        right_frame = ttk.Frame(container)
        right_frame.pack(side='right', fill='both', expand=True, padx=10)

        info_lbl = ttk.Label(
            right_frame,
            text="Doppio click su un contatto per aprire la conversazione.",
            wraplength=300,
            justify='left'
        )
        info_lbl.pack(anchor='nw', pady=6)

        # Carica lista contatti
        self._load_secret_conversations_list(tree)

        # FIX: Doppio click con gestione errori migliorata
        def on_tree_double_click(event):
            try:
                item = tree.identify_row(event.y)
                if item:
                    tree.selection_set(item)
                    contact_id = int(item)
                    self._open_secret_chat_window(contact_id)
            except ValueError as ve:
                print(f"Errore conversione ID: {ve}")
                messagebox.showerror("Errore", "ID contatto non valido")
            except Exception as e:
                print(f"Errore apertura chat segreta: {e}")
                traceback.print_exc()
                messagebox.showerror("Errore", f"Impossibile aprire la chat: {e}")

        tree.bind("<Double-1>", on_tree_double_click)

        # Salva per aggiornamenti automatici
        self.secret_contacts_tree = tree

    def _load_secret_conversations_list(self, tree):
        """Versione corretta per contare SOLO messaggi ricevuti non letti"""
        conn = None
        cursor = None
        try:
            for iid in tree.get_children():
                tree.delete(iid)

            conn, cursor = self.safe_cursor()
            user_id = self.current_user['id']

            # Query per DM
            if self.current_user['role'] == 'DM':
                cursor.execute("""
                    SELECT 
                        u.id,
                        u.username,
                        (SELECT message FROM chat_messages 
                         WHERE is_secret = 1 
                         AND ((sender_id = %s AND receiver_id = u.id) OR (sender_id = u.id AND receiver_id = %s))
                         ORDER BY id DESC LIMIT 1) as last_message,
                        (SELECT COUNT(*) FROM chat_messages m
                         LEFT JOIN chat_reads r ON m.id = r.message_id AND r.user_id = %s
                         WHERE r.id IS NULL 
                         AND m.is_secret = 1 
                         AND m.sender_id = u.id
                         AND m.receiver_id = %s) as unread_count
                    FROM users u
                    WHERE u.role = 'GIOCATORE'
                    ORDER BY u.username
                """, (user_id, user_id, user_id, user_id))
            else:
                # Query per giocatori (DM + altri giocatori)
                cursor.execute("""
                    SELECT 
                        u.id,
                        u.username,
                        (SELECT message FROM chat_messages 
                         WHERE is_secret = 1 
                         AND ((sender_id = %s AND receiver_id = u.id) OR (sender_id = u.id AND receiver_id = %s))
                         ORDER BY id DESC LIMIT 1) as last_message,
                        (SELECT COUNT(*) FROM chat_messages m
                         LEFT JOIN chat_reads r ON m.id = r.message_id AND r.user_id = %s
                         WHERE r.id IS NULL 
                         AND m.is_secret = 1 
                         AND m.sender_id = u.id
                         AND m.receiver_id = %s) as unread_count
                    FROM users u
                    WHERE (u.role = 'DM' OR (u.role = 'GIOCATORE' AND u.id != %s))
                    ORDER BY u.role = 'DM' DESC, u.username
                """, (user_id, user_id, user_id, user_id, user_id))

            contacts = cursor.fetchall()
            
            for contact in contacts:
                last_text = contact['last_message'][:60] + "..." if contact['last_message'] and len(contact['last_message']) > 60 else contact['last_message'] or ""
                unread = contact['unread_count'] or 0
                tree.insert('', 'end', iid=str(contact['id']), 
                           values=(contact['username'], last_text, unread))
        except Exception as e:
            print(f"Errore caricamento conversazioni: {e}")
            traceback.print_exc()
        finally:
            self.close_connection(conn, cursor)

    def _open_secret_chat_window(self, contact_id):
        """
        Apre popup conversazione segreta con contact_id.
        Questo popup ha polling (after) per aggiornare i messaggi ogni 2s.
        """
        try:
            # Recupera info contatto
            conn, cursor = self.safe_cursor()
            cursor.execute("SELECT id, username, role FROM users WHERE id = %s", (contact_id,))
            contact = cursor.fetchone()
            self.close_connection(conn, cursor)

            if not contact:
                messagebox.showerror("Errore", "Contatto non trovato.")
                return

            # Crea finestra popup
            popup = tk.Toplevel(self.root)
            popup.title(f"Chat segreta — {contact['username']}")
            popup.geometry("700x500")
            popup._last_chat_message_id = 0

            # Frame messaggi
            messages_frame = ttk.Frame(popup)
            messages_frame.pack(fill='both', expand=True, padx=8, pady=8)

            messages_text = scrolledtext.ScrolledText(messages_frame, wrap=tk.WORD)
            messages_text.pack(fill='both', expand=True)
            messages_text.config(state='disabled')
            
            # 🔥 SPOSTATO QUI: Configura tag per messaggi nuovi
            messages_text.tag_configure("new_message", 
                                      background='#e8f5e8',  # Verde chiaro
                                      foreground='#2c3e50',
                                      font=('Arial', 10, 'normal'))

            # input area
            input_frame = ttk.Frame(popup)
            input_frame.pack(fill='x', padx=8, pady=6)

            msg_entry = ttk.Entry(input_frame)
            msg_entry.pack(side='left', fill='x', expand=True, padx=5)

            send_btn = ttk.Button(
                input_frame,
                text="📤 Invia",
                command=lambda: self._send_secret_message_popup(contact_id, msg_entry, messages_text)
            )
            send_btn.pack(side='right', padx=5)

            msg_entry.bind('<Return>', lambda e: self._send_secret_message_popup(contact_id, msg_entry, messages_text))

            # ------- FUNZIONE DI POLLING -------
            def load_messages_periodic():
                """Polling ottimizzato per chat segreta"""
                conn = None
                cursor = None
                try:
                    conn, cursor = self.safe_cursor()
                    user_id = self.current_user['id']
                    
                    # ---- 1) QUERY OTTIMIZZATA ----
                    last_seen_id = getattr(popup, '_last_chat_message_id', 0)
                    initial_load = last_seen_id <= 0

                    if initial_load:
                        cursor.execute("""
                            SELECT
                                c.id,
                                c.message,
                                c.created_at,
                                c.sender_id,
                                CASE
                                    WHEN r.id IS NULL AND c.sender_id != %s THEN 1
                                    ELSE 0
                                END as is_new
                            FROM chat_messages c
                            LEFT JOIN chat_reads r ON c.id = r.message_id AND r.user_id = %s
                            WHERE c.is_secret = 1
                              AND ((c.sender_id = %s AND c.receiver_id = %s)
                                   OR (c.sender_id = %s AND c.receiver_id = %s))
                            ORDER BY c.id DESC
                            LIMIT 200
                        """, (user_id, user_id, user_id, contact_id, contact_id, user_id))
                        msgs = list(reversed(cursor.fetchall()))
                    else:
                        cursor.execute("""
                            SELECT
                                c.id,
                                c.message,
                                c.created_at,
                                c.sender_id,
                                CASE
                                    WHEN r.id IS NULL AND c.sender_id != %s THEN 1
                                    ELSE 0
                                END as is_new
                            FROM chat_messages c
                            LEFT JOIN chat_reads r ON c.id = r.message_id AND r.user_id = %s
                            WHERE c.is_secret = 1
                              AND ((c.sender_id = %s AND c.receiver_id = %s)
                                   OR (c.sender_id = %s AND c.receiver_id = %s))
                              AND c.id > %s
                            ORDER BY c.id ASC
                            LIMIT 200
                        """, (user_id, user_id, user_id, contact_id, contact_id, user_id, last_seen_id))
                        msgs = cursor.fetchall()

                    if not msgs and not initial_load:
                        pass
                    
                    # ---- 2) MARCA COME LETTI IN BATCH ----
                    new_msg_ids = [m['id'] for m in msgs if m['is_new'] == 1]
                    
                    if new_msg_ids:
                        # Query batch per marcare come letti
                        placeholders = ','.join(['%s'] * len(new_msg_ids))
                        cursor.execute(f"""
                            INSERT IGNORE INTO chat_reads (user_id, message_id)
                            SELECT %s, id FROM chat_messages WHERE id IN ({placeholders})
                        """, [user_id] + new_msg_ids)
                        conn.commit()

                    if msgs:
                        popup._last_chat_message_id = max(m['id'] for m in msgs)
                    
                    # ---- 3) MOSTRA MESSAGGI CON DATA GREGORIANA ----
                    messages_text.config(state='normal')
                    if initial_load:
                        messages_text.delete(1.0, tk.END)
                    
                    for m in msgs:
                        # 🔥 USA DATA GREGORIANA (created_at)
                        created_at = m.get('created_at')
                        if created_at:
                            date_str = created_at.strftime('%d/%m/%Y %H:%M:%S')
                        else:
                            date_str = ''
                        
                        sender_name = self._chat_users_cache.get(m['sender_id'], {}).get('username', 'Unknown')
                        
                        if m['sender_id'] == user_id:
                            header = f"[{date_str}] Tu → {contact['username']}: "
                        else:
                            header = f"[{date_str}] {sender_name} → Tu: "
                        
                        messages_text.insert(tk.END, header)
                        messages_text.insert(tk.END, m['message'] + "\n")
                        
                        # 🔥 EVIDENZIA IN VERDE CHIARO SOLO I NUOVI MESSAGGI
                        if m['is_new'] == 1:
                            start_idx = messages_text.index("end-2l linestart")
                            end_idx = messages_text.index("end-1l lineend")
                            messages_text.tag_add("new_message", start_idx, end_idx)
                    
                    messages_text.config(state='disabled')
                    messages_text.see(tk.END)
                    
                except Exception as e:
                    print(f"Errore caricamento chat segreta: {e}")
                    traceback.print_exc()
                    
                    try:
                        # Se la connessione è morta, resetto il pool
                        self._pool_initialized = False
                        self.init_connection_pool()
                    except Exception:
                        pass
                finally:
                    self.close_connection(conn, cursor)
                
                # ---- 4) SCHEDULA PROSSIMA LETTURA CON INTERVALLO MAGGIORE ----
                try:
                    polling_interval = 2000  # 2 secondi per chat segreta (meno frequente)
                    popup._chat_after_id = popup.after(polling_interval, load_messages_periodic)
                except:
                    pass

            # ------- CHIUSURA POPUP -------
            def on_close():
                try:
                    if hasattr(popup, '_chat_after_id'):
                        popup.after_cancel(popup._chat_after_id)
                except:
                    pass
                popup.destroy()
                # Aggiorna lista conversazioni
                try:
                    if hasattr(self, 'secret_contacts_tree'):
                        self._load_secret_conversations_list(self.secret_contacts_tree)
                except:
                    pass

            popup.protocol("WM_DELETE_WINDOW", on_close)

            # Avvia polling immediatamente
            load_messages_periodic()

        except Exception as e:
            messagebox.showerror("Errore", f"Errore apertura conversazione: {e}")

    def load_secret_chat_messages_fast(self, text_widget, contact_id):
        """Caricamento ottimizzato per chat segreta - METODO DI CLASSE"""
        connection = None
        cursor = None
        
        try:
            connection = self.get_db_connection()
            cursor = connection.cursor()
            user_id = self.current_user['id']
            
            # Query ottimizzata con JOIN singolo
            cursor.execute("""
                SELECT 
                    c.id, 
                    c.message, 
                    c.created_at,
                    c.sender_id,
                    CASE 
                        WHEN r.id IS NULL AND c.sender_id != %s THEN 1 
                        ELSE 0 
                    END as is_new
                FROM chat_messages c
                LEFT JOIN chat_reads r ON c.id = r.message_id AND r.user_id = %s
                WHERE c.is_secret = 1
                  AND c.receiver_id = %s  # Solo messaggi dove IO sono il destinatario
                ORDER BY c.created_at ASC
                LIMIT 50
            """, (user_id, user_id, user_id))
            
            new_messages = cursor.fetchall()
            
            if not new_messages:
                return
            
            # Marca come letti in batch
            new_msg_ids = [msg['id'] for msg in new_messages if msg['is_new'] == 1]
            
            if new_msg_ids:
                placeholders = ','.join(['%s'] * len(new_msg_ids))
                cursor.execute(f"""
                    INSERT IGNORE INTO chat_reads (user_id, message_id)
                    VALUES {','.join([f'(%s, %s)'] * len(new_msg_ids))}
                """, [val for msg_id in new_msg_ids for val in (user_id, msg_id)])
                connection.commit()
            
            # Mostra messaggi
            text_widget.config(state='normal')
            scroll_pos = text_widget.yview()
            at_bottom = scroll_pos[1] >= 0.95
            
            for msg in new_messages:
                # Data gregoriana
                created_at = msg.get('created_at')
                if created_at:
                    date_str = created_at.strftime('%d/%m/%Y %H:%M:%S')
                else:
                    date_str = ''
                    
                sender_name = self._chat_users_cache.get(msg['sender_id'], {}).get('username', 'Unknown')
                message_line = f"[{date_str}] {sender_name}: {msg['message']}\n"
                text_widget.insert(tk.END, message_line)
                
                # Evidenzia in verde chiaro solo se nuovo
                if msg['is_new'] == 1:
                    start_idx = text_widget.index("end-2l linestart")
                    end_idx = text_widget.index("end-1l lineend")
                    text_widget.tag_add("new_message", start_idx, end_idx)
            
            text_widget.config(state='disabled')
            
            if at_bottom:
                text_widget.see(tk.END)
            
            self.update_chat_button_fast()
            
        except Exception as e:
            print(f"Errore caricamento chat segreta: {e}")
        finally:
            self.close_connection(connection, cursor)

    def _send_secret_message_popup(self, contact_id, msg_entry, messages_text):
        """Invia messaggio segreto verso contact_id (usato dal popup)."""
        text = msg_entry.get().strip()
        if not text:
            return
        conn = None
        cursor = None
        try:
            # per inviare verso il DM quando il contact_id è il DM, o per inviare giocatore→giocatore
            ded_date = self.convert_date_to_ded_format(self.game_date)
            conn, cursor = self.safe_cursor()
            cursor.execute("""
                INSERT INTO chat_messages (sender_id, receiver_id, is_secret, message, mystara_date)
                VALUES (%s, %s, 1, %s, %s)
            """, (self.current_user['id'], contact_id, text, ded_date))
            new_msg_id = cursor.lastrowid
            cursor.execute("""
                INSERT IGNORE INTO chat_reads (user_id, message_id) VALUES (%s, %s)
            """, (self.current_user['id'], new_msg_id))
            conn.commit()
            msg_entry.delete(0, tk.END)
            # forziamo refresh immediato della finestra popup (caricamento con funzione interna)
            # il polling la ricaricherà automaticamente entro 1s; qui ricarichiamo subito
            try:
                # simula il refresh: cerca il Toplevel aperto con titolo contenente username
                # ma più robusto è fare refresh della tree delle conversazioni e lasciare il polling aggiornare il testo
                if hasattr(self, 'secret_contacts_tree'):
                    self._load_secret_conversations_list(self.secret_contacts_tree)
            except:
                pass
        except Exception as e:
            messagebox.showerror("Errore", f"Errore invio messaggio segreto: {e}")
        finally:
            self.close_connection(conn, cursor)
            
    def update_chat_button_fast(self):
        if hasattr(self, 'chat_button'):
            counts = self._count_unread_by_category_fast()

            unread_total = counts["comune"] + counts["segreti"]  # privati = 0

            if unread_total > 0:
                self.chat_button.config(text=f"💬 Chat ({unread_total})")
            else:
                self.chat_button.config(text="💬 Chat")

    def export_to_excel(self):
        """Esporta i dati finanziari in Excel (solo DM)"""
        if not self.current_user or self.current_user['role'] != 'DM':
            messagebox.showwarning("Avviso", "Solo il DM può esportare in Excel")
            return
        
        try:
            
            cursor = self.db.cursor()
            
            # 🔹 CORREZIONE: Rimossa la colonna created_at che non esiste
            cursor.execute("""
                SELECT 
                    pc.name as 'Nome PG',
                    u.username as 'Giocatore',
                    b.name as 'Nome Banca', 
                    b.current_balance as 'Saldo (MO)',
                    b.annual_interest as 'Tasso Interesse (%)',
                    b.location as 'Luogo'
                    -- Rimossa: b.created_at as 'Data Creazione'
                FROM banks b
                LEFT JOIN player_characters pc ON b.pg_id = pc.id
                LEFT JOIN users u ON pc.user_id = u.id
                ORDER BY pc.name, b.name
            """)
            bank_data = cursor.fetchall()
            
            cursor.execute("""
                SELECT 
                    pc.name as 'Nome PG',
                    u.username as 'Giocatore',
                    ea.description as 'Attività',
                    ea.income as 'Reddito (MO)',
                    ea.frequency as 'Frequenza',
                    b.name as 'Banca Destinazione'
                FROM economic_activities ea
                LEFT JOIN player_characters pc ON ea.pg_id = pc.id
                LEFT JOIN users u ON pc.user_id = u.id
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
                ORDER BY pc.name, ea.description
            """)
            activity_data = cursor.fetchall()
            
            cursor.execute("""
                SELECT 
                    pc.name as 'Nome PG',
                    u.username as 'Giocatore',
                    fe.description as 'Spesa',
                    fe.amount as 'Importo (MO)',
                    fe.frequency as 'Frequenza',
                    b.name as 'Banca Sorgente'
                FROM fixed_expenses fe
                LEFT JOIN player_characters pc ON fe.pg_id = pc.id
                LEFT JOIN users u ON pc.user_id = u.id
                LEFT JOIN banks b ON fe.source_bank_id = b.id
                ORDER BY pc.name, fe.description
            """)
            expense_data = cursor.fetchall()
            
            if not bank_data and not activity_data and not expense_data:
                messagebox.showinfo("Info", "Nessun dato da esportare")
                return
            
            # 🔹 MODIFICA: Crea file Excel con più fogli
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"Dati_Finanziari_{timestamp}.xlsx"
            
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # Foglio BANCHE
                if bank_data:
                    df_banks = pd.DataFrame(bank_data)
                    df_banks['Saldo (MO)'] = df_banks['Saldo (MO)'].apply(lambda x: f"{float(x):.2f}")
                    df_banks['Tasso Interesse (%)'] = df_banks['Tasso Interesse (%)'].apply(lambda x: f"{float(x):.2f}%" if x else "0.00%")
                    df_banks.to_excel(writer, sheet_name='Banche', index=False)
                
                # Foglio ATTIVITÀ ECONOMICHE
                if activity_data:
                    df_activities = pd.DataFrame(activity_data)
                    df_activities['Reddito (MO)'] = df_activities['Reddito (MO)'].apply(lambda x: f"{float(x):.2f}")
                    df_activities.to_excel(writer, sheet_name='Attività Economiche', index=False)
                
                # Foglio SPESE FISSE
                if expense_data:
                    df_expenses = pd.DataFrame(expense_data)
                    df_expenses['Importo (MO)'] = df_expenses['Importo (MO)'].apply(lambda x: f"-{float(x):.2f}")
                    df_expenses.to_excel(writer, sheet_name='Spese Fisse', index=False)
                
                # 🔹 Formatta automaticamente le colonne
                workbook = writer.book
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    for column in worksheet.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(str(cell.value))
                            except:
                                pass
                        adjusted_width = min(max_length + 2, 50)
                        worksheet.column_dimensions[column_letter].width = adjusted_width
            
            messagebox.showinfo("Successo", f"Dati esportati in:\n{filename}")
            
        except ImportError:
            messagebox.showerror("Errore", "Librerie necessarie non installate.\nInstalla con: pip install pandas openpyxl")
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante l'esportazione: {e}")

    def refresh_mount_list(self, pg_id, tree=None):
        """Ricarica cavalcature con i campi logistici della Fase 04."""
        try:
            tree = tree or self.mount_tree
            tree.delete(*tree.get_children())
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_cavalcature WHERE pg_id = %s ORDER BY nome, id", (pg_id,))
            mounts = cursor.fetchall()
            cursor.close()
            for i, mount in enumerate(mounts):
                values = (
                    mount.get('tipo') or '',
                    mount.get('nome') or '',
                )
                if len(tree['columns']) > 2:
                    values = (
                        mount.get('tipo') or '',
                        mount.get('nome') or '',
                        mount.get('classe_armatura') or '',
                        f"{mount.get('pf_attuali') or 0}/{mount.get('pf_massimi') or 0}",
                        mount.get('movimento') or '',
                        mount.get('carico_attuale') or 0,
                        mount.get('capacita_carico') or '',
                        mount.get('stato_salute') or '',
                        mount.get('luogo') or '',
                    )
                tree.insert('', 'end', values=values, tags=(mount['id'], 'evenrow' if i % 2 == 0 else 'oddrow'))
        except Exception as e:
            print(f"Errore refresh cavalcature: {e}")

    def add_mount_dialog(self, pg_id, tree=None):
        self._mount_dialog(pg_id, tree=tree)

    def edit_mount_dialog(self, pg_id, tree=None):
        tree = tree or self.mount_tree
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona una cavalcatura da modificare.")
            return
        mount_id = tree.item(selection[0])['tags'][0]
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM pc_cavalcature WHERE id = %s AND pg_id = %s", (mount_id, pg_id))
        mount = cursor.fetchone()
        cursor.close()
        if mount:
            self._mount_dialog(pg_id, mount=mount, tree=tree)

    def _mount_dialog(self, pg_id, mount=None, tree=None):
        tree = tree or getattr(self, 'info_mount_tree', None)
        dialog = tk.Toplevel(self.root)
        dialog.title("Cavalcatura")
        dialog.geometry("540x500")
        dialog.transient(self.root)
        dialog.grab_set()
        field_specs = [
            ('tipo', 'Tipo'), ('nome', 'Nome'), ('classe_armatura', 'CA'),
            ('pf_attuali', 'PF attuali'), ('pf_massimi', 'PF massimi'),
            ('movimento', 'Movimento'), ('capacita_carico', 'Capacita carico'),
            ('carico_attuale', 'Carico attuale'), ('stato_salute', 'Stato salute'),
            ('luogo', 'Luogo'), ('costo_mantenimento', 'Costo mantenimento')
        ]
        widgets = {}
        for row, (field, label) in enumerate(field_specs):
            ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=4)
            widget = ttk.Entry(dialog, width=38)
            widget.grid(row=row, column=1, sticky='ew', padx=10, pady=4)
            widget.insert(0, '' if not mount or mount.get(field) is None else str(mount.get(field)))
            widgets[field] = widget
        ttk.Label(dialog, text="Note:").grid(row=len(field_specs), column=0, sticky='nw', padx=10, pady=4)
        notes = tk.Text(dialog, width=40, height=5)
        notes.grid(row=len(field_specs), column=1, padx=10, pady=4)
        notes.insert('1.0', mount.get('note') or '' if mount else '')

        def num(field, decimal=False):
            raw = widgets[field].get().strip()
            if not raw:
                return None
            return Decimal(raw.replace(',', '.')) if decimal else int(raw)

        def save():
            data = {
                'pg_id': pg_id,
                'tipo': widgets['tipo'].get().strip(),
                'nome': widgets['nome'].get().strip(),
                'classe_armatura': num('classe_armatura'),
                'pf_attuali': num('pf_attuali'),
                'pf_massimi': num('pf_massimi'),
                'movimento': num('movimento'),
                'capacita_carico': num('capacita_carico', True),
                'carico_attuale': num('carico_attuale', True) or Decimal('0'),
                'stato_salute': widgets['stato_salute'].get().strip(),
                'luogo': widgets['luogo'].get().strip(),
                'costo_mantenimento': num('costo_mantenimento', True),
                'note': notes.get('1.0', 'end-1c').strip(),
            }
            cursor = self.db.cursor()
            try:
                if mount:
                    data['id'] = mount['id']
                    cursor.execute("""
                        UPDATE pc_cavalcature
                        SET tipo=%(tipo)s, nome=%(nome)s, classe_armatura=%(classe_armatura)s,
                            pf_attuali=%(pf_attuali)s, pf_massimi=%(pf_massimi)s,
                            movimento=%(movimento)s, capacita_carico=%(capacita_carico)s,
                            carico_attuale=%(carico_attuale)s, stato_salute=%(stato_salute)s,
                            luogo=%(luogo)s, costo_mantenimento=%(costo_mantenimento)s,
                            note=%(note)s
                        WHERE id=%(id)s AND pg_id=%(pg_id)s
                    """, data)
                else:
                    cursor.execute("""
                        INSERT INTO pc_cavalcature
                            (pg_id, tipo, nome, classe_armatura, pf_attuali, pf_massimi,
                             movimento, capacita_carico, carico_attuale, stato_salute,
                             luogo, costo_mantenimento, note)
                        VALUES
                            (%(pg_id)s, %(tipo)s, %(nome)s, %(classe_armatura)s,
                             %(pf_attuali)s, %(pf_massimi)s, %(movimento)s,
                             %(capacita_carico)s, %(carico_attuale)s, %(stato_salute)s,
                             %(luogo)s, %(costo_mantenimento)s, %(note)s)
                    """, data)
                self.db.commit()
                cursor.close()
                dialog.destroy()
                if tree:
                    self.refresh_mount_list(pg_id, tree)
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore cavalcatura: {e}")

        ttk.Button(dialog, text="Salva", command=save).grid(row=len(field_specs) + 1, column=0, pady=10)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=len(field_specs) + 1, column=1, pady=10)

    def create_character_properties_tab(self, notebook, pg_id, character):
        """Tab Possedimenti con dati logistici Fase 04."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Possedimenti")
        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        main_frame = ttk.LabelFrame(tab, text="Terreni e proprieta", padding=10)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        columns = ('tipo', 'possedimento', 'localita', 'stato', 'valore', 'rendita', 'manut')
        self.property_tree = ttk.Treeview(main_frame, columns=columns, show='headings')
        labels = {
            'tipo': 'Tipo', 'possedimento': 'Descrizione', 'localita': 'Localita',
            'stato': 'Stato', 'valore': 'Valore', 'rendita': 'Rendita', 'manut': 'Manut.'
        }
        for col in columns:
            self.property_tree.heading(col, text=labels[col])
            self.property_tree.column(col, width=130 if col != 'possedimento' else 220)
        self.property_tree.pack(side='left', fill='both', expand=True)
        self.property_tree.bind("<Double-1>", lambda e: self.show_property_details_dialog(pg_id))
        prop_scroll = ttk.Scrollbar(main_frame, orient='vertical', command=self.property_tree.yview)
        prop_scroll.pack(side='right', fill='y')
        self.property_tree.config(yscrollcommand=prop_scroll.set)
        self.refresh_property_list(pg_id)
        if is_dm:
            btn_frame = ttk.Frame(tab)
            btn_frame.pack(fill='x', padx=10, pady=5)
            ttk.Button(btn_frame, text="Aggiungi", command=lambda: self.add_property_dialog(pg_id)).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="Modifica", command=lambda: self.edit_property_dialog(pg_id)).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="Elimina", command=lambda: self.delete_property(pg_id)).pack(side='left', padx=5)

    def refresh_property_list(self, pg_id):
        try:
            self.property_tree.delete(*self.property_tree.get_children())
            self.property_tree.tag_configure('oddrow', background='white')
            self.property_tree.tag_configure('evenrow', background='#f0f0f0')
            cursor = self.db.cursor()
            query = "SELECT * FROM pc_possedimenti WHERE pg_id = %s"
            params = [pg_id]
            if self.current_user and self.current_user.get('role') == 'GIOCATORE':
                query += " AND visible_to_player = 1"
            query += " ORDER BY tipo, possedimento"
            cursor.execute(query, params)
            for i, prop in enumerate(cursor.fetchall()):
                self.property_tree.insert('', 'end', values=(
                    prop.get('tipo') or '',
                    prop.get('possedimento') or '',
                    prop.get('localita') or '',
                    prop.get('stato') or '',
                    prop.get('valore') or 0,
                    prop.get('rendita') or '',
                    prop.get('costo_manutenzione') or '',
                ), tags=(prop['id'], 'evenrow' if i % 2 == 0 else 'oddrow'))
            cursor.close()
        except Exception as e:
            print(f"Errore refresh possedimenti: {e}")

    def add_property_dialog(self, pg_id):
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' aggiungere possedimenti.")
            return
        self._property_dialog(pg_id)

    def edit_property_dialog(self, pg_id):
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' modificare possedimenti.")
            return
        selection = self.property_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un possedimento.")
            return
        prop_id = self.property_tree.item(selection[0])['tags'][0]
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM pc_possedimenti WHERE id = %s AND pg_id = %s", (prop_id, pg_id))
        prop = cursor.fetchone()
        cursor.close()
        if prop:
            self._property_dialog(pg_id, prop)

    def _property_dialog(self, pg_id, prop=None):
        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        if not is_dm:
            messagebox.showerror("Permesso negato", "Solo il DM puo' gestire i possedimenti.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Possedimento")
        dialog.geometry("650x590")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)
        specs = [
            ('tipo', 'Tipo'), ('possedimento', 'Descrizione'), ('valore', 'Valore MO'),
            ('localita', 'Localita'), ('stato', 'Stato'), ('rendita', 'Rendita'),
            ('costo_manutenzione', 'Costo manutenzione')
        ]
        widgets = {}
        for row, (field, label) in enumerate(specs):
            ttk.Label(dialog, text=f"{label}:").grid(row=row, column=0, sticky='w', padx=10, pady=4)
            widget = ttk.Entry(dialog, width=42)
            widget.grid(row=row, column=1, sticky='ew', padx=10, pady=4)
            widget.insert(0, '' if not prop or prop.get(field) is None else str(prop.get(field)))
            widgets[field] = widget

        freq_row = len(specs)
        ttk.Label(dialog, text="Frequenza:").grid(row=freq_row, column=0, sticky='w', padx=10, pady=4)
        freq_combo = ttk.Combobox(dialog, values=['giornaliera', 'settimanale', 'mensile'], state='readonly', width=39)
        freq_combo.grid(row=freq_row, column=1, sticky='ew', padx=10, pady=4)
        freq_combo.set((prop.get('frequenza') if prop else '') or 'mensile')
        widgets['frequenza'] = freq_combo

        bank_row = freq_row + 1
        ttk.Label(dialog, text="Banca collegata:").grid(row=bank_row, column=0, sticky='w', padx=10, pady=4)
        bank_combo = ttk.Combobox(dialog, state='readonly', width=39)
        banks = self.get_property_banks(pg_id)
        bank_labels = [b['label'] for b in banks]
        bank_combo['values'] = bank_labels
        bank_combo.grid(row=bank_row, column=1, sticky='ew', padx=10, pady=4)
        bank_combo.set('')
        current_bank_id = prop.get('banca_collegata') if prop else None
        if current_bank_id:
            for index, bank in enumerate(banks):
                if bank['id'] == current_bank_id:
                    bank_combo.current(index)
                    break
        widgets['banca_collegata'] = bank_combo

        visible_var = tk.BooleanVar(value=bool(prop.get('visible_to_player', 1)) if prop else True)
        ttk.Checkbutton(dialog, text="Visibile al giocatore", variable=visible_var).grid(row=bank_row + 1, column=1, sticky='w', padx=10, pady=4)
        ttk.Label(dialog, text="Note:").grid(row=bank_row + 2, column=0, sticky='nw', padx=10, pady=4)
        notes = tk.Text(dialog, width=44, height=5)
        notes.grid(row=bank_row + 2, column=1, sticky='ew', padx=10, pady=4)
        notes.insert('1.0', prop.get('note') or '' if prop else '')
        ttk.Label(dialog, text="Note DM:").grid(row=bank_row + 3, column=0, sticky='nw', padx=10, pady=4)
        dm_notes = tk.Text(dialog, width=44, height=4)
        dm_notes.grid(row=bank_row + 3, column=1, sticky='ew', padx=10, pady=4)
        dm_notes.insert('1.0', prop.get('dm_notes') or '' if prop and is_dm else '')

        def dec(field):
            raw = widgets[field].get().strip()
            return Decimal(raw.replace(',', '.')) if raw else None

        def selected_bank_id():
            index = bank_combo.current()
            if index < 0 or index >= len(banks):
                return None
            return banks[index]['id']

        def positive(value):
            return value is not None and value > 0

        def save():
            rendita = dec('rendita')
            manutenzione = dec('costo_manutenzione')
            bank_id = selected_bank_id()
            frequency = widgets['frequenza'].get().strip() or None
            if (positive(rendita) or positive(manutenzione)) and (not bank_id or not frequency):
                messagebox.showerror(
                    "Dati mancanti",
                    "Per rendita o costo manutenzione maggiori di zero devi selezionare banca collegata e frequenza."
                )
                return
            data = {
                'pg_id': pg_id,
                'tipo': widgets['tipo'].get().strip(),
                'possedimento': widgets['possedimento'].get().strip(),
                'valore': dec('valore') or Decimal('0'),
                'localita': widgets['localita'].get().strip(),
                'stato': widgets['stato'].get().strip(),
                'rendita': rendita,
                'costo_manutenzione': manutenzione,
                'frequenza': frequency,
                'banca_collegata': bank_id,
                'visible_to_player': int(visible_var.get()),
                'dm_notes': dm_notes.get('1.0', 'end-1c').strip(),
                'note': notes.get('1.0', 'end-1c').strip(),
                'economic_activity_id': prop.get('economic_activity_id') if prop else None,
                'fixed_expense_id': prop.get('fixed_expense_id') if prop else None,
            }
            cursor = self.db.cursor()
            try:
                if prop:
                    data['id'] = prop['id']
                    cursor.execute("""
                        UPDATE pc_possedimenti
                        SET tipo=%(tipo)s, possedimento=%(possedimento)s, valore=%(valore)s,
                            localita=%(localita)s, stato=%(stato)s, rendita=%(rendita)s,
                            costo_manutenzione=%(costo_manutenzione)s, frequenza=%(frequenza)s,
                            banca_collegata=%(banca_collegata)s, visible_to_player=%(visible_to_player)s,
                            economic_activity_id=%(economic_activity_id)s,
                            fixed_expense_id=%(fixed_expense_id)s,
                            dm_notes=%(dm_notes)s, note=%(note)s
                        WHERE id=%(id)s AND pg_id=%(pg_id)s
                    """, data)
                    prop_id = prop['id']
                else:
                    cursor.execute("""
                        INSERT INTO pc_possedimenti
                            (pg_id, tipo, possedimento, valore, localita, stato, rendita,
                             costo_manutenzione, frequenza, banca_collegata, visible_to_player,
                             economic_activity_id, fixed_expense_id, dm_notes, note)
                        VALUES
                            (%(pg_id)s, %(tipo)s, %(possedimento)s, %(valore)s,
                             %(localita)s, %(stato)s, %(rendita)s,
                             %(costo_manutenzione)s, %(frequenza)s, %(banca_collegata)s,
                             %(visible_to_player)s, %(economic_activity_id)s,
                             %(fixed_expense_id)s, %(dm_notes)s, %(note)s)
                    """, data)
                    prop_id = cursor.lastrowid

                economy_ids = self.sync_property_economy(cursor, pg_id, prop_id, data)
                data.update(economy_ids)
                cursor.execute("""
                    UPDATE pc_possedimenti
                    SET economic_activity_id = %(economic_activity_id)s,
                        fixed_expense_id = %(fixed_expense_id)s
                    WHERE id = %(id)s AND pg_id = %(pg_id)s
                """, {
                    'id': prop_id,
                    'pg_id': pg_id,
                    'economic_activity_id': data.get('economic_activity_id'),
                    'fixed_expense_id': data.get('fixed_expense_id'),
                })
                self.db.commit()
                cursor.close()
                dialog.destroy()
                self.refresh_property_list(pg_id)
            except Exception as e:
                self.db.rollback()
                cursor.close()
                messagebox.showerror("Errore", f"Errore possedimento: {e}")

        ttk.Button(dialog, text="Salva", command=save).grid(row=bank_row + 4, column=0, pady=10)
        ttk.Button(dialog, text="Annulla", command=dialog.destroy).grid(row=bank_row + 4, column=1, sticky='w', pady=10)

    def get_property_banks(self, pg_id):
        """Restituisce le banche del PG con etichetta leggibile per le dropdown."""
        banks = []
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT id, name, location, current_balance
                FROM banks
                WHERE pg_id = %s
                ORDER BY name
            """, (pg_id,))
            for row in cursor.fetchall():
                balance = row.get('current_balance')
                try:
                    balance_text = f"{float(balance or 0):.2f} MO"
                except Exception:
                    balance_text = "0.00 MO"
                location = row.get('location') or 'Senza localita'
                banks.append({
                    'id': row['id'],
                    'name': row.get('name') or 'Banca senza nome',
                    'location': location,
                    'current_balance': balance,
                    'label': f"{row.get('name') or 'Banca senza nome'} - {location} - {balance_text}",
                })
            cursor.close()
        except Exception as e:
            print(f"Errore caricamento banche possedimento: {e}")
        return banks

    def get_property_bank_display(self, bank_id):
        if not bank_id:
            return ''
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT name, location, current_balance FROM banks WHERE id = %s", (bank_id,))
            bank = cursor.fetchone()
            cursor.close()
            if not bank:
                return "Banca non trovata"
            balance = float(bank.get('current_balance') or 0)
            return f"{bank.get('name') or 'Banca senza nome'} - {bank.get('location') or 'Senza localita'} - {balance:.2f} MO"
        except Exception:
            return "Banca non leggibile"

    def sync_property_economy(self, cursor, pg_id, prop_id, data):
        """Crea, aggiorna o rimuove attivita/spese automatiche collegate al possedimento."""
        description_name = data.get('possedimento') or data.get('tipo') or f"ID {prop_id}"
        frequency = data.get('frequenza')
        bank_id = data.get('banca_collegata')
        income = data.get('rendita')
        maintenance = data.get('costo_manutenzione')
        economic_activity_id = data.get('economic_activity_id')
        fixed_expense_id = data.get('fixed_expense_id')

        if income is not None and income > 0:
            description = f"Rendita possedimento: {description_name}"
            if economic_activity_id:
                cursor.execute("""
                    UPDATE economic_activities
                    SET pg_id = %s, description = %s, income = %s,
                        frequency = %s, destination_bank_id = %s
                    WHERE id = %s AND pg_id = %s
                """, (pg_id, description, income, frequency, bank_id, economic_activity_id, pg_id))
                if cursor.rowcount == 0:
                    cursor.execute(
                        "SELECT id FROM economic_activities WHERE id = %s AND pg_id = %s",
                        (economic_activity_id, pg_id)
                    )
                    if not cursor.fetchone():
                        economic_activity_id = None
            if not economic_activity_id:
                cursor.execute("""
                    INSERT INTO economic_activities
                        (pg_id, description, income, frequency, destination_bank_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (pg_id, description, income, frequency, bank_id))
                economic_activity_id = cursor.lastrowid
        elif economic_activity_id:
            cursor.execute("DELETE FROM economic_activities WHERE id = %s AND pg_id = %s", (economic_activity_id, pg_id))
            economic_activity_id = None

        if maintenance is not None and maintenance > 0:
            description = f"Manutenzione possedimento: {description_name}"
            if fixed_expense_id:
                cursor.execute("""
                    UPDATE fixed_expenses
                    SET pg_id = %s, description = %s, amount = %s,
                        frequency = %s, source_bank_id = %s
                    WHERE id = %s AND pg_id = %s
                """, (pg_id, description, maintenance, frequency, bank_id, fixed_expense_id, pg_id))
                if cursor.rowcount == 0:
                    cursor.execute(
                        "SELECT id FROM fixed_expenses WHERE id = %s AND pg_id = %s",
                        (fixed_expense_id, pg_id)
                    )
                    if not cursor.fetchone():
                        fixed_expense_id = None
            if not fixed_expense_id:
                cursor.execute("""
                    INSERT INTO fixed_expenses
                        (pg_id, description, amount, frequency, source_bank_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (pg_id, description, maintenance, frequency, bank_id))
                fixed_expense_id = cursor.lastrowid
        elif fixed_expense_id:
            cursor.execute("DELETE FROM fixed_expenses WHERE id = %s AND pg_id = %s", (fixed_expense_id, pg_id))
            fixed_expense_id = None

        return {
            'economic_activity_id': economic_activity_id,
            'fixed_expense_id': fixed_expense_id,
        }

    def show_property_details_dialog(self, pg_id):
        selection = self.property_tree.selection()
        if not selection:
            return
        prop_id = self.property_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            query = "SELECT * FROM pc_possedimenti WHERE id = %s AND pg_id = %s"
            params = [prop_id, pg_id]
            if self.current_user and self.current_user.get('role') == 'GIOCATORE':
                query += " AND visible_to_player = 1"
            cursor.execute(query, params)
            prop = cursor.fetchone()
            cursor.close()
            if not prop:
                return
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura possedimento: {e}")
            return

        is_dm = self.current_user and self.current_user.get('role') == 'DM'
        dialog = tk.Toplevel(self.root)
        dialog.title(prop.get('possedimento') or "Dettaglio possedimento")
        dialog.geometry("720x560")
        dialog.transient(self.root)
        dialog.grab_set()

        info = ttk.LabelFrame(dialog, text="Dati possedimento", padding=10)
        info.pack(fill='x', padx=10, pady=10)
        bank_text = self.get_property_bank_display(prop.get('banca_collegata'))
        rows = [
            ("Tipo", prop.get('tipo') or ''),
            ("Descrizione", prop.get('possedimento') or ''),
            ("Valore MO", f"{float(prop.get('valore') or 0):.2f}"),
            ("Localita", prop.get('localita') or ''),
            ("Stato", prop.get('stato') or ''),
            ("Rendita", f"{float(prop.get('rendita') or 0):.2f}"),
            ("Costo manutenzione", f"{float(prop.get('costo_manutenzione') or 0):.2f}"),
            ("Frequenza", prop.get('frequenza') or ''),
            ("Banca collegata", bank_text),
            ("Visibile al giocatore", "Si" if prop.get('visible_to_player') else "No"),
        ]
        for i, (label, value) in enumerate(rows):
            ttk.Label(info, text=f"{label}:").grid(row=i // 2, column=(i % 2) * 2, sticky='w', padx=5, pady=3)
            ttk.Label(info, text=str(value), wraplength=260).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky='w', padx=5, pady=3)

        details = ttk.LabelFrame(dialog, text="Note", padding=10)
        details.pack(fill='both', expand=True, padx=10, pady=5)
        text = tk.Text(details, wrap='word', height=14)
        text.pack(side='left', fill='both', expand=True)
        detail_scroll = ttk.Scrollbar(details, orient='vertical', command=text.yview)
        detail_scroll.pack(side='right', fill='y')
        text.config(yscrollcommand=detail_scroll.set)
        full_text = f"Note:\n{prop.get('note') or ''}"
        if is_dm:
            full_text += f"\n\nNote DM:\n{prop.get('dm_notes') or ''}"
        text.insert('1.0', full_text)
        text.configure(state='disabled')
        ttk.Button(dialog, text="Chiudi", command=dialog.destroy).pack(pady=10)

    def delete_property(self, pg_id):
        if not self.current_user or self.current_user.get('role') != 'DM':
            messagebox.showerror("Permesso negato", "Solo il DM puo' eliminare possedimenti.")
            return
        selection = self.property_tree.selection()
        if not selection:
            messagebox.showwarning("Attenzione", "Seleziona un possedimento.")
            return
        prop_id = self.property_tree.item(selection[0])['tags'][0]
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT * FROM pc_possedimenti WHERE id = %s AND pg_id = %s", (prop_id, pg_id))
            prop = cursor.fetchone()
            cursor.close()
            if not prop:
                messagebox.showwarning("Attenzione", "Possedimento non trovato.")
                return
        except Exception as e:
            messagebox.showerror("Errore", f"Errore lettura possedimento: {e}")
            return

        linked = []
        if prop.get('economic_activity_id'):
            linked.append("attivita economica collegata")
        if prop.get('fixed_expense_id'):
            linked.append("spesa fissa collegata")
        extra = ""
        if linked:
            extra = "\n\nVerranno eliminate anche: " + ", ".join(linked) + "."
        if not messagebox.askyesno("Conferma", f"Eliminare il possedimento selezionato?{extra}"):
            return

        cursor = self.db.cursor()
        try:
            if prop.get('economic_activity_id'):
                cursor.execute(
                    "DELETE FROM economic_activities WHERE id = %s AND pg_id = %s",
                    (prop.get('economic_activity_id'), pg_id)
                )
            if prop.get('fixed_expense_id'):
                cursor.execute(
                    "DELETE FROM fixed_expenses WHERE id = %s AND pg_id = %s",
                    (prop.get('fixed_expense_id'), pg_id)
                )
            cursor.execute("DELETE FROM pc_possedimenti WHERE id = %s AND pg_id = %s", (prop_id, pg_id))
            self.db.commit()
            cursor.close()
            self.refresh_property_list(pg_id)
        except Exception as e:
            self.db.rollback()
            cursor.close()
            messagebox.showerror("Errore", f"Errore eliminazione possedimento: {e}")

def main():
    """Funzione principale"""
    check_for_updates()
    app = DeDToolGUI()
    app.run()

if __name__ == "__main__":
    main()

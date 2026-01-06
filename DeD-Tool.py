import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import requests
import os
import sys
from datetime import date as date, datetime as datetime, timedelta as timedelta
from decimal import Decimal
import pymysql
from cryptography.fernet import Fernet
import json
from dateutil.relativedelta import relativedelta
import pandas as pd
from openai import OpenAI
import smtplib
from email.message import EmailMessage
import re
import threading
from dbutils.pooled_db import PooledDB

__VERSION__ = "1.0.3"

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
            from openai import OpenAI
            self.client = OpenAI(
                base_url="http://localhost:1234/v1",  # porta LM Studio
                api_key="lmstudio"
            )
            print("✅ Client LM Studio inizializzato correttamente.")
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

    def append_time_log(self, message):
        """Metodo per logging - sostituisce la funzione mancante"""
        print(f"📅 {message}")

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
        file_menu.add_command(label="Esporta Stato", command=lambda: self.export_status_to_pdf(None))
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

    def toggle_fullscreen(self):
        """Attiva/disattiva la modalità schermo intero"""
        current_state = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not current_state)

    def show_about(self):
        """Mostra informazioni sull'applicazione"""
        messagebox.showinfo("Informazioni", 
                           f"D&D Tool - Gestione Campagna\n"
                           f"Versione: {__VERSION__}\n"
                           f"Creato da Massimo Trevisan\n\n"
                           f"Un tool completo per gestire campagne di Dungeons & Dragons")

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
            
            # Notebook (tabs)
            style.configure('TNotebook',
                          font=('Arial', 10))
            
            style.configure('TNotebook.Tab',
                          font=('Arial', 10),
                          padding=[10, 5])
            
            print("✅ Stili interfaccia configurati")
            
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
            if not hasattr(self, "EPOCH_DATE") or not isinstance(self.EPOCH_DATE, date):
                epoch = date(1, 1, 1)
            else:
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
            if not hasattr(self, "EPOCH_DATE") or not isinstance(self.EPOCH_DATE, date):
                epoch = date(1, 1, 1)
            else:
                epoch = self.EPOCH_DATE

            abs_days = int(absolute_day)
            result_date = epoch + timedelta(days=abs_days)
            
            return result_date
            
        except Exception as e:
            self.append_time_log(f"absolute_day_to_date error: {e}")
            return self.EPOCH_DATE if hasattr(self, "EPOCH_DATE") else date(1, 1, 1)

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

    def check_nuovo_diario(self):
        """Controlla se esiste una nuova versione del diario su GitHub."""
        VERSION_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/diario_version.txt"
        try:
            versione_locale = self.current_user.get('diario_version', "0.0.0")

            response = requests.get(VERSION_URL, timeout=3)
            response.raise_for_status()
            ultima_versione_online = response.text.strip()

            return ultima_versione_online != versione_locale

        except Exception:
            return False
    
    def download_diary(self):
        """Scarica il diario della campagna"""
        try:
            # Ferma il lampeggio
            self.stop_diario_blink()
            
            VERSION_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/diario_version.txt"
            PDF_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/Diario_Campagna.pdf"
            
            versione_locale = self.current_user.get('diario_version', '0.0.0')
            
            response = requests.get(VERSION_URL, timeout=5)
            response.raise_for_status()
            ultima_versione = response.text.strip()
            
            if versione_locale == ultima_versione:
                messagebox.showinfo("Diario Aggiornato", 
                                  f"Hai già l'ultima versione del diario ({versione_locale})")
                return
            
            if not messagebox.askyesno("Nuovo Diario Disponibile", 
                                      f"Nuova versione disponibile: {ultima_versione}\n"
                                      f"Versione attuale: {versione_locale}\n\n"
                                      f"Scaricare il diario?"):
                return  # L'utente ha cliccato "No"
            
            # Scarica PDF
            r = requests.get(PDF_URL, stream=True)
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
            self.diario_has_new_version = False
            if hasattr(self, 'diario_button') and self.diario_button.winfo_exists():
                self.diario_button.configure(
                    text="📘 Diario",
                    bg='SystemButtonFace', 
                    fg='black', 
                    font=('Arial', 9)
                )
            
            print("Diario scaricato con successo!")
            messagebox.showinfo("Successo", f"Diario scaricato: {filename}")
            
        except Exception as e:
            print(f"Errore nel download del diario: {e}")
            messagebox.showerror("Errore", f"Errore download diario: {e}")

    def aggiorna_pulsante_diario(self):
        """Aggiorna il testo del pulsante diario dopo il download"""
        if hasattr(self, 'diario_button') and self.diario_button.winfo_exists():
            self.diario_button.configure(text="📘 Diario")
            self.diario_has_new_version = False

    def mostra_messaggio(self, messaggio, tipo="info"):
        """Mostra un messaggio all'utente"""
        from tkinter import messagebox
        if tipo == "info":
            messagebox.showinfo("Info", messaggio)
        elif tipo == "errore":
            messagebox.showerror("Errore", messaggio)
        elif tipo == "avviso":
            messagebox.showwarning("Avviso", messaggio)

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
        cursor.execute("SELECT id, name, current_balance FROM banks ORDER BY name ASC")
        banks = cursor.fetchall()

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
            if from_combo.get() == to_combo.get():
                messagebox.showerror("Errore", "Seleziona banche diverse")
                return
            try:
                amount = float(amount_entry.get().strip())
            except ValueError:
                messagebox.showerror("Errore", "Importo non valido")
                return

            from_bank = banks[from_combo.current()]
            to_bank = banks[to_combo.current()]

            # controllo saldo
            if float(from_bank.get('current_balance',0)) < amount:
                if not messagebox.askyesno("Conferma", "Saldo insufficiente. Vuoi procedere lo stesso?"):
                    return

            try:
                cursor.execute("UPDATE banks SET current_balance = current_balance - %s WHERE id=%s", (amount, from_bank['id']))
                cursor.execute("UPDATE banks SET current_balance = current_balance + %s WHERE id=%s", (amount, to_bank['id']))
                cursor.execute("INSERT INTO bank_transactions (bank_id, amount, type, description) VALUES (%s, %s, %s, %s)",
                               (from_bank['id'], -amount, 'TRASFERIMENTO', f"Trasferito a {to_bank['name']}"))
                cursor.execute("INSERT INTO bank_transactions (bank_id, amount, type, description) VALUES (%s, %s, %s, %s)",
                               (to_bank['id'], amount, 'TRASFERIMENTO', f"Ricevuto da {from_bank['name']}"))
                self.db.commit()
                messagebox.showinfo("Successo", "Trasferimento completato")
                dialog.destroy()
                self.show_banks_menu()
            except Exception as e:
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
            cursor.execute("SELECT id, name, current_balance, annual_interest FROM banks")
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
                new_balance = balance + interest
                try:
                    cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, bank_id))
                    self.db.commit()
                    self.append_time_log(f" - 💰 '{name}': {balance:.2f} → {new_balance:.2f} (interessi {interest:.2f})")
                except Exception as e:
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
            pg_name = pg_combo.get()
            if not pg_name:
                return

            cursor = self.db.cursor()
            cursor.execute("SELECT id FROM player_characters WHERE name=%s", (pg_name,))
            pg = cursor.fetchone()
            if not pg:
                return

            cursor.execute("SELECT id, name FROM banks WHERE pg_id = %s", (pg['id'],))
            banks = cursor.fetchall()

            if banks:
                bank_combo['values'] = [f"{b['id']} - {b['name']}" for b in banks]
                bank_combo.current(0)
            else:
                bank_combo['values'] = []
                bank_combo.set("")

        pg_combo.bind("<<ComboboxSelected>>", update_banks_for_pg)
        update_banks_for_pg()  # inizializza

        def save_new_follower():
            name = name_entry.get().strip()
            f_class = class_entry.get().strip()
            level = int(level_spinbox.get())
            cost = float(cost_entry.get())
            notes = notes_text.get("1.0", "end").strip()
            race = desc_entry.get().strip()
            pg_name = pg_combo.get().strip()
            bank_value = bank_combo.get().strip()

            if not name or not pg_name:
                messagebox.showerror("Errore", "Nome e PG obbligatori")
                return

            cursor = self.db.cursor()
            cursor.execute("SELECT id FROM player_characters WHERE name=%s", (pg_name,))
            pg = cursor.fetchone()
            pg_id = pg['id']

            bank_id = None
            if bank_value:
                bank_id = int(bank_value.split(" - ")[0])

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
            SELECT f.id, f.name, pc.name AS pg_name
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
        cursor.execute("SELECT id, name FROM banks ORDER BY name")
        banks = cursor.fetchall()
        bank_combo = ttk.Combobox(dialog, width=33, state='readonly')
        bank_combo['values'] = [b['name'] for b in banks]
        bank_combo.pack(pady=5)

        def save_objective():
            try:
                name = name_entry.get().strip()
                months = int(months_spin.get())
                cost = float(cost_entry.get())
                notes = notes_text.get("1.0", tk.END).strip()
                if follower_combo.current() < 0 or bank_combo.current() < 0:
                    messagebox.showwarning("Dati mancanti", "Seleziona un seguace e una banca.")
                    return

                follower_id = followers[follower_combo.current()]['id']
                bank_id = banks[bank_combo.current()]['id']

                cursor.execute("""
                    INSERT INTO follower_objectives
                    (follower_id, name, estimated_months, total_cost, notes, bank_id, status, progress_percentage)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (follower_id, name, months, cost, notes, bank_id, self.OBJECTIVE_STATUS['NON_INIZIATO'], 0.0))
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
            SELECT f.id, f.name, pc.name AS pg_name
            FROM followers f
            JOIN player_characters pc ON f.pg_id = pc.id
        """)
        followers = cursor.fetchall()
        follower_combo = ttk.Combobox(dialog, width=38, state='readonly')
        follower_combo['values'] = [f"{f['name']} (PG: {f['pg_name']})" for f in followers]
        for i, f in enumerate(followers):
            if f['name'] == objective['follower_name']:
                follower_combo.current(i)
                break
        follower_combo.pack(pady=5)

        # Seleziona banca
        ttk.Label(dialog, text="Banca:").pack(pady=5)
        cursor.execute("SELECT id, name FROM banks ORDER BY name")
        banks = cursor.fetchall()
        bank_combo = ttk.Combobox(dialog, width=38, state='readonly')
        bank_combo['values'] = [b['name'] for b in banks]
        for i, b in enumerate(banks):
            if b['name'] == objective.get('bank_name', ''):
                bank_combo.current(i)
                break
        bank_combo.pack(pady=5)

        def save_changes():
            try:
                name = name_entry.get().strip()
                months = int(months_spin.get())
                cost = float(cost_entry.get())
                notes = notes_text.get("1.0", tk.END).strip()
                status_name = status_combo.get()
                status_value = self.OBJECTIVE_STATUS[status_name]
                progress = float(progress_spin.get())

                follower_id = followers[follower_combo.current()]['id'] if follower_combo.current() >= 0 else objective['follower_id']
                bank_id = banks[bank_combo.current()]['id'] if bank_combo.current() >= 0 else objective['bank_id']

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
        import json

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
        import re

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
                SET status = %s, start_date = %s, progress_percentage = 0.0
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

        # Recupero descrizione dalla prima colonna (compatibile con la tua edit_fixed_expense)
        try:
            desc = tree.item(selected)["values"][0]
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
                WHERE fe.description = %s
                LIMIT 1
            """, (desc,))
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
            if banks:
                bank_combo.current(0)

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

                cursor.execute("SELECT id FROM banks WHERE name = %s AND pg_id = %s", 
                               (bank_combo.get(), pg_id))
                bank = cursor.fetchone()
                bank_id = bank['id'] if bank else None

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
        """Modifica una spesa fissa esistente (ricerca per description come nella versione originale).
        Aggiunge la possibilità di cambiare PG e Banca di origine."""
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Avviso", "Seleziona una spesa da modificare.")
            return

        # Manteniamo la logica precedente: la prima colonna visibile è la description
        desc = tree.item(sel[0])['values'][0]

        cursor = self.db.cursor()
        try:
            # Recuperiamo il record usando la description (come nella tua versione funzionante)
            cursor.execute("SELECT * FROM fixed_expenses WHERE description = %s LIMIT 1", (desc,))
            exp = cursor.fetchone()
            if not exp:
                messagebox.showerror("Errore", f"Spesa non trovata nel database (descrizione: {desc})")
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

        desc = tree.item(selection[0])['values'][0]
        if not messagebox.askyesno("Conferma", f"Eliminare la spesa '{desc}'?"):
            return

        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM fixed_expenses WHERE description = %s", (desc,))
            self.db.commit()
            messagebox.showinfo("Successo", "Spesa rimossa.")
            self.show_expenses_menu()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore eliminazione: {e}")

    def show_users_menu(self):
        """Mostra il menu gestione utenti"""
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
            
            tables = ['users', 'player_characters', 'banks', 'bank_transactions', 
                     'followers', 'economic_activities', 'fixed_expenses', 
                     'game_state', 'follower_objectives', 'follower_objective_events',
                     'chat_messages', 'chat_reads']
            
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
        
        print_btn = ttk.Button(header_frame, text="🖨️ Esporta PDF", 
                              command=lambda: self.export_status_to_pdf(scrollable_frame))
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
            cursor.execute("""
                SELECT pc.id, pc.name, pc.user_id, u.username
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

            # Filtra PG se l'utente è un giocatore
            if self.current_user and self.current_user['role'] == 'GIOCATORE':
                pgs_to_display = [pg for pg in all_pgs if pg['user_id'] == self.current_user['id']]
                if not pgs_to_display:
                    ttk.Label(scrollable_frame, text="Nessun PG associato al tuo account per visualizzare lo stato.").pack(pady=10)
                    canvas.pack(side="left", fill="both", expand=True)
                    scrollbar.pack(side="right", fill="y")
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
                        else:
                            ttk.Label(pg_frame, text="     Nessun obiettivo.").pack(anchor='w')
                else:
                    ttk.Label(pg_frame, text="   Nessun seguace.").pack(anchor='w')

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

    def export_status_to_pdf(self, frame_widget):
        """Esporta lo stato della campagna in PDF"""
        from tkinter import filedialog
        import datetime
        
        try:
            # Chiedi dove salvare il file
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("File di testo", "*.txt"), ("Tutti i file", "*.*")],
                initialfile=f"stato_campagna_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                f.write(f"Data esportazione: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n")
                
                # PGs e utente associato
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
                
                # Filtra PG se l'utente è un giocatore
                if self.current_user and self.current_user['role'] == 'GIOCATORE':
                    pgs_to_display = [pg for pg in all_pgs if pg['user_id'] == self.current_user['id']]
                    if not pgs_to_display:
                        f.write("Nessun PG associato al tuo account per visualizzare lo stato.\n")
                        cursor.close()
                        messagebox.showinfo("Successo", f"File esportato con successo in:\n{filename}")
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
                import os
                os.startfile(filename)
        
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante l'esportazione: {e}")
            import traceback
            traceback.print_exc()

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
                if hasattr(self, 'tree_imprevisti'):
                    self.load_events_list(self.tree_imprevisti)
                else:
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

            # Calcola mese iniziale
            old_abs_day = self.date_to_absolute_day(self.game_date)
            old_month = (old_abs_day // self.DAYS_PER_MONTH) % 12

            # Avanza tutti i giorni in una volta
            self.advance_days(total_days)

            # Calcola mese finale e controlla transizioni
            new_abs_day = self.date_to_absolute_day(self.game_date)
            new_month = (new_abs_day // self.DAYS_PER_MONTH) % 12

            # Se c'è stata una transizione di mese, applica eventi mensili
            if new_month != old_month:
                self.append_time_log("→ Transizione mese Mystara rilevata: applico eventi mensili")
                try:
                    self._apply_monthly_events()
                except Exception as e:
                    self.append_time_log(f"Errore eventi mensili: {e}")

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
                SELECT ea.*, b.current_balance
                FROM economic_activities ea
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
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
                current_balance = float(activity.get('current_balance') or 0.0)
                new_balance = current_balance + income
                try:
                    cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, dest_bank_id))
                    self.db.commit()
                    self.append_time_log(f"  Guadagno giornaliero {income:.2f} MO -> banca id {dest_bank_id}")
                except Exception as e:
                    self.append_time_log(f"  Errore aggiornamento banca per attività {activity.get('description')}: {e}")

            # Spese fisse giornaliere
            cursor.execute("""
                SELECT fe.*, b.current_balance
                FROM fixed_expenses fe
                LEFT JOIN banks b ON fe.source_bank_id = b.id
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
                current_balance = float(expense.get('current_balance') or 0.0)
                if current_balance >= amount:
                    new_balance = current_balance - amount
                    try:
                        cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, src_bank_id))
                        self.db.commit()
                        self.append_time_log(f"  Spesa giornaliera {amount:.2f} MO prelevata da banca id {src_bank_id}")
                    except Exception as e:
                        self.append_time_log(f"  Errore applicazione spesa '{expense.get('description')}': {e}")
                else:
                    self.append_time_log(f"  Saldo insufficiente per '{expense.get('description')}' (banca id {src_bank_id})")

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
                SELECT ea.*, b.current_balance
                FROM economic_activities ea
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
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
                current_balance = float(activity.get('current_balance') or 0.0)
                new_balance = current_balance + income
                try:
                    cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, dest_bank_id))
                    self.db.commit()
                    self.append_time_log(f"  Guadagno settimanale {income:.2f} MO -> banca id {dest_bank_id}")
                except Exception as e:
                    self.append_time_log(f"  Errore update banca attività settimanale: {e}")

            # Spese fisse settimanali
            cursor.execute("""
                SELECT fe.*, b.current_balance
                FROM fixed_expenses fe
                LEFT JOIN banks b ON fe.source_bank_id = b.id
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
                current_balance = float(expense.get('current_balance') or 0.0)
                if current_balance >= amount:
                    new_balance = current_balance - amount
                    try:
                        cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, src_bank_id))
                        self.db.commit()
                        self.append_time_log(f"  Spesa settimanale {amount:.2f} MO prelevata da banca id {src_bank_id}")
                    except Exception as e:
                        self.append_time_log(f"  Errore applicazione spesa settimanale: {e}")
                else:
                    self.append_time_log(f"  Saldo insufficiente per spesa '{expense.get('description')}' (banca id {src_bank_id})")

            # Applica 1/4 mese sugli obiettivi
            self._apply_objective_progress(frazione_mensile=1/4.0, etichetta='settimanale')

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
                SELECT fe.*, b.current_balance
                FROM fixed_expenses fe
                LEFT JOIN banks b ON fe.source_bank_id = b.id
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
                current_balance = float(expense.get('current_balance') or 0.0)
                if current_balance >= amount:
                    new_balance = current_balance - amount
                    try:
                        cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, src_bank_id))
                        self.db.commit()
                        self.append_time_log(f"  Spesa mensile {amount:.2f} MO prelevata da banca id {src_bank_id}")
                    except Exception as e:
                        self.append_time_log(f"  Errore applicazione spesa mensile: {e}")
                else:
                    self.append_time_log(f"  Saldo insufficiente per spesa mensile '{expense.get('description')}' (banca id {src_bank_id})")

            # Attività mensili
            cursor.execute("""
                SELECT ea.*, b.current_balance
                FROM economic_activities ea
                LEFT JOIN banks b ON ea.destination_bank_id = b.id
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
                current_balance = float(activity.get('current_balance') or 0.0)
                new_balance = current_balance + income
                try:
                    cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, dest_bank_id))
                    self.db.commit()
                    self.append_time_log(f"  Guadagno mensile {income:.2f} MO -> banca id {dest_bank_id}")
                except Exception as e:
                    self.append_time_log(f"  Errore update banca per attività mensile: {e}")

            # Applica 1.0 (intero) frazione per gli obiettivi
            self._apply_objective_progress(frazione_mensile=1.0, etichetta='mensile')

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
                SELECT fo.*, b.current_balance
                FROM follower_objectives fo
                LEFT JOIN banks b ON fo.bank_id = b.id
                WHERE fo.status = %s
            """, (self.OBJECTIVE_STATUS['IN_CORSO'],))
            objectives = cursor.fetchall() or []

            for obj in objectives:
                obj_id = obj.get('id')
                name = obj.get('name', 'Sconosciuto')
                bank_id = obj.get('bank_id')
                estimated_months = int(obj.get('estimated_months') or 0)
                total_cost = float(obj.get('total_cost') or 0.0)
                progress_pct = float(obj.get('progress_percentage') or 0.0)

                base_months = int(obj.get('base_estimated_months') or estimated_months or 0)
                if base_months <= 0 or estimated_months <= 0:
                    self.append_time_log(f"  Obiettivo '{name}' ha mesi non validi, ignorato.")
                    continue

                current_balance = float(obj.get('current_balance') or 0.0)

                cost_per_month = (total_cost / estimated_months) if estimated_months > 0 else 0.0
                progress_per_month = (100.0 / base_months) if base_months > 0 else 0.0

                cost_to_apply = cost_per_month * float(frazione_mensile)
                progress_to_apply = progress_per_month * float(frazione_mensile)

                if not bank_id:
                    self.append_time_log(f"  Obiettivo '{name}' senza banca; costo non applicato.")
                    continue

                if cost_to_apply > 0 and current_balance >= cost_to_apply:
                    try:
                        new_balance = current_balance - cost_to_apply
                        cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, bank_id))
                        self.db.commit()
                        self.append_time_log(f"  Prelevati {cost_to_apply:.2f} MO per obiettivo '{name}' (banca id {bank_id})")
                    except Exception as e:
                        self.append_time_log(f"  Errore prelievo per obiettivo '{name}': {e}")
                        continue
                else:
                    self.append_time_log(f"  Saldo insufficiente per obiettivo '{name}' (necessario {cost_to_apply:.2f}, disponibile {current_balance:.2f})")
                    continue

                new_progress = min(progress_pct + progress_to_apply, 100.0)
                new_status = obj.get('status')
                if new_progress >= 100.0:
                    new_status = self.OBJECTIVE_STATUS['COMPLETATO']

                try:
                    cursor.execute("""
                        UPDATE follower_objectives
                        SET progress_percentage = %s, status = %s
                        WHERE id = %s
                    """, (new_progress, new_status, obj_id))
                    self.db.commit()
                    self.append_time_log(f"  Obiettivo '{name}': {progress_pct:.1f}% -> {new_progress:.1f}% (status: {self.OBJECTIVE_STATUS_REV.get(new_status,new_status)})")
                    # se completato, aggiorna GUI obiettivi
                    if new_status == self.OBJECTIVE_STATUS['COMPLETATO']:
                        try:
                            if hasattr(self, 'objectives_tree') and hasattr(self, 'load_objectives_list'):
                                self.load_objectives_list(self.objectives_tree)
                        except Exception as e:
                            self.append_time_log(f"  Impossibile ricaricare GUI obiettivi: {e}")
                except Exception as e:
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
                cursor.execute("SELECT name, estimated_months, total_cost FROM follower_objectives WHERE id = %s", (objective_id,))
                objective = cursor.fetchone()
                if not objective:
                    self.append_time_log(f"  Obiettivo id {objective_id} non trovato per evento {eid}")
                    continue

                name = objective.get('name', 'Sconosciuto')
                est_months = int(objective.get('estimated_months') or 0)
                tot_cost = float(objective.get('total_cost') or 0.0)

                if player_choice.get('fail'):
                    try:
                        cursor.execute("UPDATE follower_objectives SET status = %s WHERE id = %s", (self.OBJECTIVE_STATUS['FALLITO'], objective_id))
                        self.db.commit()
                        self.append_time_log(f"  Evento {eid}: obiettivo '{name}' segnato FALLITO (scelta giocatore).")
                    except Exception as e:
                        self.append_time_log(f"  Errore marking FAIL per obiettivo {objective_id}: {e}")
                else:
                    add_months = int(player_choice.get('extra_months', 0))
                    add_cost = float(player_choice.get('extra_cost', 0.0))
                    new_est = est_months + add_months
                    new_cost = tot_cost + add_cost
                    try:
                        cursor.execute("UPDATE follower_objectives SET estimated_months=%s, total_cost=%s WHERE id=%s", (new_est, new_cost, objective_id))
                        cursor.execute("UPDATE follower_objective_events SET handled = TRUE, extra_cost = %s, extra_months = %s WHERE id = %s", (add_cost, add_months, eid))
                        self.db.commit()
                        self.append_time_log(f"  Evento {eid}: obiettivo '{name}' aggiornato +{add_months} mesi, +{add_cost:.2f} MO")
                    except Exception as e:
                        self.append_time_log(f"  Errore aggiornamento obiettivo per evento {eid}: {e}")

            # ricarica lista imprevisti pendenti in GUI
            try:
                if hasattr(self, "tree_imprevisti") and self.tree_imprevisti is not None:
                    if self.tree_imprevisti.winfo_exists():
                        self.load_events_list(self.tree_imprevisti)
                    else:
                        self.load_pending_events()
                else:
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
            if hasattr(self, 'imprevisti_listbox'):
                self.imprevisti_listbox.delete(0, tk.END)
                for r in rows:
                    label = f"{r.get('objective_name','?')} - {str(r.get('description',''))[:80]}"
                    self.imprevisti_listbox.insert(tk.END, label)
            else:
                # se non esiste la GUI, stampo il riepilogo su log
                for r in rows:
                    self.append_time_log(f"PENDENTE: {r.get('obj_name')} - {r.get('description')}")
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
                
                # AGGIORNAMENTO CRITICO: Salva la data nel database
                self.game_date = new_date
                self._update_game_state_date(new_date)
                
                # Aggiorna GUI
                if hasattr(self, 'date_label'):
                    try:
                        self.date_label.config(text=self.convert_date_to_ded_format(new_date))
                    except:
                        pass
                
                new_mystara_date = f"{day:02d} {month_name} {year}"
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
                    print("✅ Connection pool PyMySQL inizializzato")
                    
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
                        
                print("✓ Polling fermati")
            except Exception as e:
                print(f"Errore stop polling: {e}")

        def on_tab_changed(event):
            selected_tab = notebook.index(notebook.select())
            tab_name = notebook.tab(selected_tab, "text")

            if "(" in tab_name:
                clean_name = tab_name.split(" (")[0]
                notebook.tab(selected_tab, text=clean_name)

            self.update_chat_button_fast()

            # 🔥 MODIFICA: Refresh forzato quando si torna al tab Chat Comune
            if "Chat Comune" in tab_name:
                try:
                    # Trova il widget messages_text all'interno del frame
                    for widget in comune_frame.winfo_children():
                        if isinstance(widget, ttk.Frame):
                            for subwidget in widget.winfo_children():
                                if isinstance(subwidget, scrolledtext.ScrolledText):
                                    # 🔥 FORZA RICARICAMENTO INIZIALE
                                    chat_key = f"comune_{self.current_user['id']}"
                                    self._last_chat_message_id[chat_key] = 0
                                    
                                    # 🔥 MODIFICA: Usa la nuova funzione
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
        
        # 🔥 AGGIUNGI: Inizializza immediatamente la chat comune
        # Questo garantisce che i messaggi siano visibili subito
        self.root.after(100, lambda: self._initialize_chat_common(comune_frame))
        
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
                            self._last_chat_message_id[chat_key] = 0  # Reset per caricare tutto
                            self._load_common_messages_display(subwidget, chat_key)
                            break
        except Exception as e:
            print(f"Errore inizializzazione chat comune: {e}")

    def _get_chat_users_cache(self):
        """Cache per i dati degli utenti - una sola query"""
        conn, cursor = self.safe_cursor()
        cursor.execute("SELECT id, username, role FROM users")
        users = {user['id']: user for user in cursor.fetchall()}
        cursor.close()
        return users

    def _count_unread_by_category_fast(self):
        """Conta messaggi non letti - Versione OTTIMIZZATA"""
        if not self.current_user:
            return {"comune": 0, "privati": 0, "segreti": 0}
        
        conn, cursor = self.safe_cursor()
        user_id = self.current_user['id']
        
        try:
            # UNICA QUERY per tutti i conteggi
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN c.receiver_id IS NULL AND c.is_secret = 0 THEN 1 ELSE 0 END) as comune,
                    SUM(CASE WHEN c.is_secret = 1 AND c.receiver_id = %s THEN 1 ELSE 0 END) as segreti
                FROM chat_messages c
                LEFT JOIN chat_reads r ON c.id = r.message_id AND r.user_id = %s
                WHERE r.id IS NULL
            """, (user_id, user_id))
            
            result = cursor.fetchone()
            comune = result['comune'] or 0
            segreti = result['segreti'] or 0
            
            return {
                "comune": comune,
                "privati": 0,
                "segreti": segreti
            }
            
        finally:
            cursor.close()

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
                    
                print("✓ Polling chat fermato")
                
            except Exception as e:
                print(f"Errore pulizia: {e}")
        
        def on_parent_destroy(event):
            if event.widget == parent:
                clean_up_polling()
        
        parent.bind("<Destroy>", on_parent_destroy)
        
        return parent
        
    def _load_common_messages_display(self, text_widget, chat_key):
        """Carica e mostra i messaggi della chat comune - Versione simile a chat segreta"""
        try:
            user_id = self.current_user['id']
            
            conn, cursor = self.safe_cursor()
            
            # 🔥 QUERY OTTIMIZZATA: simile a quella della chat segreta
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
                ORDER BY c.created_at DESC
                LIMIT 100
            """, (user_id, user_id))
            
            msgs = cursor.fetchall()
            
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
            text_widget.delete(1.0, tk.END)  # 🔥 Cancella e ricarica tutto (come fa la chat segreta)
            
            for m in reversed(msgs):  # Ordine cronologico corretto
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
            
            self.close_connection(conn, cursor)
            
        except Exception as e:
            print(f"Errore caricamento chat comune: {e}")
            import traceback
            traceback.print_exc()

    def _send_common_message(self, message_entry, messages_text):
        """Invia messaggio nella chat comune - Versione semplificata"""
        text = message_entry.get().strip()
        if not text:
            return
        
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
            cursor.close()
            
            message_entry.delete(0, tk.END)
            
            # 🔥 FORZA IL REFRESH DEI MESSAGGI
            chat_key = f"comune_{self.current_user['id']}"
            self._load_common_messages_display(messages_text, chat_key)
            
            print(f"✅ Messaggio comune inviato (ID: {new_msg_id})")
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore invio messaggio: {e}")

    def _mark_and_remove_highlight(self, message_ids, text_widget):
        """
        Marca i messaggi come letti nel DB e rimuove l'evidenziazione verde
        dopo 3-5 secondi dalla visualizzazione
        """
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
                cursor.close()
                
                # Aggiorna contatore chat
                self.update_chat_button_fast()
                            
            # 2. Rimuovi evidenziazione verde dalla UI
            text_widget.tag_remove("new_message", "1.0", "end")
            
        except Exception as e:
            print(f"❌ Errore in _mark_and_remove_highlight: {e}")
            import traceback
            traceback.print_exc()
        
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
                import traceback
                traceback.print_exc()
                messagebox.showerror("Errore", f"Impossibile aprire la chat: {e}")

        tree.bind("<Double-1>", on_tree_double_click)

        # Salva per aggiornamenti automatici
        self.secret_contacts_tree = tree

    def _load_secret_conversations_list(self, tree):
        """Versione corretta per contare SOLO messaggi ricevuti non letti"""
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
                         ORDER BY created_at DESC LIMIT 1) as last_message,
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
                         ORDER BY created_at DESC LIMIT 1) as last_message,
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
            
            cursor.close()
        except Exception as e:
            print(f"Errore caricamento conversazioni: {e}")
            import traceback
            traceback.print_exc()

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
                try:
                    conn, cursor = self.safe_cursor()
                    user_id = self.current_user['id']
                    
                    # ---- 1) QUERY OTTIMIZZATA ----
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
                        ORDER BY c.created_at DESC
                        LIMIT 200
                    """, (user_id, user_id, user_id, contact_id, contact_id, user_id))
                    
                    msgs = cursor.fetchall()
                    
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
                    
                    # ---- 3) MOSTRA MESSAGGI CON DATA GREGORIANA ----
                    messages_text.config(state='normal')
                    messages_text.delete(1.0, tk.END)
                    
                    for m in reversed(msgs):  # Ordine cronologico
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
                    
                    self.close_connection(conn, cursor)
                    
                except Exception as e:
                    print(f"Errore caricamento chat segreta: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    try:
                        # Se la connessione è morta, resetto il pool
                        self._pool_initialized = False
                        self.init_connection_pool()
                    except Exception:
                        pass
                
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
        try:
            # per inviare verso il DM quando il contact_id è il DM, o per inviare giocatore→giocatore
            ded_date = self.convert_date_to_ded_format(self.game_date)
            conn, cursor = self.safe_cursor()
            cursor.execute("""
                INSERT INTO chat_messages (sender_id, receiver_id, is_secret, message, mystara_date)
                VALUES (%s, %s, 1, %s, %s)
            """, (self.current_user['id'], contact_id, text, ded_date))
            self.db.commit()
            cursor.close()
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
            import pandas as pd
            from datetime import datetime
            
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

def main():
    """Funzione principale"""
    check_for_updates()
    app = DeDToolGUI()
    app.run()

if __name__ == "__main__":
    main()
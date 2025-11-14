import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import os
import sys
from datetime import datetime, timedelta, date
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

__VERSION__ = "1.0.2"

# URL per aggiornamenti
VERSION_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/version.txt"
SCRIPT_URL = "https://raw.githubusercontent.com/MaxTrevi/DeD-Tool/main/DeD-Tool.py"

class DeDToolGUI:
    """Classe principale per l'interfaccia grafica"""
    
    MONTH_NAMES = [
        "NUWMONT", "VATERMONT", "THAUMONT", "FLAURMONT",
        "YARTHMONT", "KLARMONT", "FELMONT", "FYRMONT",
        "AMBYRMONT", "SVIFTMONT", "EIRMONT", "KALDMONT"
    ]
    
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
        self.root.geometry("1200x800")
        
        # Variabili
        self.current_user = None
        self.db = None
        self.game_date = None
        self.env_sec = {}
        self.tree_followers = None
        self.client = None  # <- aggiungi qui

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
        
    def setup_style(self):
        """Configura lo stile dell'interfaccia"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colori personalizzati
        style.configure('Title.TLabel', font=('Arial', 16, 'bold'))
        style.configure('Subtitle.TLabel', font=('Arial', 12, 'bold'))
        style.configure('Info.TLabel', font=('Arial', 10))
        
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
    
    def load_game_date(self):
        """Carica la data di gioco dal database"""
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT game_date FROM game_state WHERE id = 1")
            result = cursor.fetchone()
            
            if result and result["game_date"]:
                return result["game_date"]
            else:
                initial_date = datetime(1, 1, 1).date()
                cursor.execute(
                    "INSERT INTO game_state (id, game_date) VALUES (%s, %s)",
                    (1, initial_date)
                )
                self.db.commit()
                return initial_date
        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento data: {e}")
            return datetime(1, 1, 1).date()
    
    def convert_date_to_ded_format(self, date_obj):
        """
        Converte una data standard in formato Mystara (es: '01 NUWMONT 1').
        La lista dei mesi deve essere definita come self.MONTH_NAMES = [...]
        """
        try:
            day = date_obj.day
            month = self.MONTH_NAMES[date_obj.month - 1]  # Indici 0-11
            year = date_obj.year
            return f"{day:02d} {month} {year}"
        except Exception as e:
            print(f"Errore conversione data: {e}")
            return str(date_obj)  # fallback in caso di errore

    def save_game_date(self):
        """
        Salva la data di gioco corrente su MariaDB.
        Se la riga con id=1 non esiste, la crea.
        """
        try:
            cursor = self.db.cursor()
            update_query = "UPDATE game_state SET game_date = %s WHERE id = 1"
            cursor.execute(update_query, (self.game_date,))
            self.db.commit()

            if cursor.rowcount == 0:
                # Nessuna riga aggiornata → inseriamo la riga
                insert_query = "INSERT INTO game_state (id, game_date) VALUES (%s, %s)"
                cursor.execute(insert_query, (1, self.game_date))
                self.db.commit()

            cursor.close()
            print("✅ Data di gioco salvata correttamente.")

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
        title.grid(row=0, column=0, columnspan=2, pady=20)
        
        subtitle = ttk.Label(login_frame, text="by Massimo Trevisan", style='Info.TLabel')
        subtitle.grid(row=1, column=0, columnspan=2, pady=5)
        
        # Campo username
        ttk.Label(login_frame, text="Username:").grid(row=2, column=0, sticky='e', padx=5, pady=5)
        username_entry = ttk.Entry(login_frame, width=30)
        username_entry.grid(row=2, column=1, padx=5, pady=5)
        
        # Campo password
        ttk.Label(login_frame, text="Password:").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        password_entry = ttk.Entry(login_frame, width=30, show='*')
        password_entry.grid(row=3, column=1, padx=5, pady=5)
        
        # Pulsante login
        def attempt_login():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            
            if self.login(username, password):
                self.show_main_menu()
            else:
                messagebox.showerror("Errore Login", "Username o password non validi")
        
        login_btn = ttk.Button(login_frame, text="🔓 Login", command=attempt_login)
        login_btn.grid(row=4, column=0, columnspan=2, pady=20)
        
        # Bind Enter key
        password_entry.bind('<Return>', lambda e: attempt_login())
        
        # Focus su username
        username_entry.focus()
    
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
        """Mostra il menu principale"""
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
        
        # Header sidebar
        user_frame = ttk.Frame(sidebar)
        user_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(user_frame, text=f"👤 {self.current_user['username']}", 
                 style='Subtitle.TLabel').pack()
        ttk.Label(user_frame, text=f"Ruolo: {self.current_user['role']}", 
                 style='Info.TLabel').pack()
        
        # Data di gioco
        date_frame = ttk.Frame(sidebar)
        date_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(date_frame, text="📅 Data di Gioco:", style='Info.TLabel').pack()
        self.date_label = ttk.Label(date_frame, 
                                    text=self.convert_date_to_ded_format(self.game_date),
                                    font=('Arial', 10, 'bold'))
        self.date_label.pack()
        
        ttk.Separator(sidebar, orient='horizontal').pack(fill='x', pady=10)
        
        # Menu buttons
        menu_items = [
            ("🧙 Personaggi", self.show_characters_menu),
            ("🏦 Banche", self.show_banks_menu),
            ("🛡️ Seguaci", self.show_followers_menu),
            ("⚒️ Attività Economiche", self.show_economic_menu),
            ("💰 Spese Fisse", self.show_expenses_menu),
        ]
        
        if self.current_user['role'] == 'DM':
            menu_items.extend([
                ("⏳ Gestione Tempo", self.show_time_menu),
                ("👥 Utenti", self.show_users_menu),
                ("💾 Backup", self.show_backup_menu),
            ])
        
        menu_items.extend([
            ("📊 Stato Campagna", self.show_status),
            ("💬 Chat", self.show_chat),
            ("📘 Diario", self.download_diary),
        ])
        
        for text, command in menu_items:
            btn = ttk.Button(sidebar, text=text, command=command, width=25)
            btn.pack(padx=10, pady=5)
        
        ttk.Separator(sidebar, orient='horizontal').pack(fill='x', pady=10)
        
        # Pulsante logout
        logout_btn = ttk.Button(sidebar, text="🚪 Logout", 
                               command=self.show_login_screen,
                               style='Accent.TButton')
        logout_btn.pack(padx=10, pady=10)
        
        # Contenuto principale
        self.content_frame = ttk.Frame(main_container)
        self.content_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        
        # Mostra schermata iniziale
        self.show_welcome_content()
    
    def show_welcome_content(self):
        """Mostra il contenuto di benvenuto"""
        self.clear_content()
        
        welcome = ttk.Label(self.content_frame, 
                           text="🎲 Benvenuto nel D&D Tool", 
                           style='Title.TLabel')
        welcome.pack(pady=20)
        
        info = ttk.Label(self.content_frame,
                        text=f"Utente: {self.current_user['username']}\n"
                             f"Ruolo: {self.current_user['role']}\n\n"
                             f"Data di Gioco: {self.convert_date_to_ded_format(self.game_date)}",
                        style='Info.TLabel')
        info.pack(pady=20)
        
        # Statistiche rapide
        stats_frame = ttk.LabelFrame(self.content_frame, text="📊 Statistiche Rapide", padding=10)
        stats_frame.pack(pady=20, padx=20, fill='both')
        
        try:
            cursor = self.db.cursor()
            
            # Conta PG
            cursor.execute("SELECT COUNT(*) as count FROM player_characters")
            pg_count = cursor.fetchone()['count']
            
            # Conta banche
            cursor.execute("SELECT COUNT(*) as count FROM banks")
            banks_count = cursor.fetchone()['count']
            
            # Conta seguaci
            cursor.execute("SELECT COUNT(*) as count FROM followers")
            followers_count = cursor.fetchone()['count']
            
            # Mostra statistiche
            ttk.Label(stats_frame, text=f"Personaggi: {pg_count}").grid(row=0, column=0, padx=20, pady=5)
            ttk.Label(stats_frame, text=f"Banche: {banks_count}").grid(row=0, column=1, padx=20, pady=5)
            ttk.Label(stats_frame, text=f"Seguaci: {followers_count}").grid(row=0, column=2, padx=20, pady=5)
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento statistiche: {e}")
    
    def clear_content(self):
        """Pulisce il frame del contenuto"""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

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

        title = ttk.Label(self.content_frame, text="🏦 Gestione Banche", style='Title.TLabel')
        title.pack(pady=10)

        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(pady=10)

        if self.current_user['role'] == 'DM':
            ttk.Button(btn_frame, text="➕ Aggiungi Banca", command=self.add_bank_dialog).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Modifica", command=self.edit_bank_dialog).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Rimuovi", command=self.remove_bank_action).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="💰 Deposita", command=self.deposit_dialog).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="💸 Preleva", command=self.withdraw_dialog).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="💱 Trasferisci Fondi", command=self.transfer_funds_dialog).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="📜 Storico Operazioni", command=self.show_bank_history_dialog).pack(side='left', padx=5)
        # 🔄 Pulsante "Aggiorna" rimosso come richiesto.

        self.show_banks_list()
    
    def show_banks_list(self):
        """Mostra la lista delle banche (ID nascosto come iid); include location e PG associato; supporta ordinamento colonne"""
        
        list_frame = ttk.Frame(self.content_frame)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Colonne aggiornate, senza 'Proprietario'
        columns = ('Nome', 'Luogo', 'PG associato', 'Saldo', 'Interesse %')
        self.tree_banks = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        for col in columns:
            # Attiva ordinamento cliccando sull'intestazione
            self.tree_banks.heading(col, text=col, command=lambda c=col: self.treeview_sort_column(self.tree_banks, c, False))
            self.tree_banks.column(col, width=140, anchor='center')

        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree_banks.yview)
        self.tree_banks.configure(yscrollcommand=scrollbar.set)
        self.tree_banks.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        try:
            cursor = self.db.cursor()
            if self.current_user['role'] == 'DM':
                cursor.execute("""
                    SELECT b.id, b.name, b.location, pc.name AS pg_name, b.current_balance, b.annual_interest
                    FROM banks b
                    LEFT JOIN player_characters pc ON b.pg_id = pc.id
                    ORDER BY b.name ASC
                """)
            else:
                cursor.execute("""
                    SELECT b.id, b.name, b.location, pc.name AS pg_name, b.current_balance, b.annual_interest
                    FROM banks b
                    LEFT JOIN player_characters pc ON b.pg_id = pc.id
                    WHERE b.user_id = %s
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
        dialog.geometry("420x380")

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
        dialog.geometry("450x550")
        
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
        
        # Razza (description)
        ttk.Label(dialog, text="Razza (es. Umano, Elfo):").pack(pady=5)
        desc_entry = ttk.Entry(dialog, width=35)
        desc_entry.pack(pady=5)
        
        # Seleziona PG
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

        def save_new_follower():
            name = name_entry.get().strip()
            f_class = class_entry.get().strip()
            level = int(level_spinbox.get())
            cost = float(cost_entry.get())
            notes = notes_text.get("1.0", "end").strip()
            race = desc_entry.get().strip()
            pg_name = pg_combo.get().strip()

            if not name or not pg_name:
                messagebox.showerror("Errore", "Nome e PG obbligatori")
                return

            try:
                cursor = self.db.cursor()
                cursor.execute("SELECT id FROM player_characters WHERE name=%s", (pg_name,))
                pg = cursor.fetchone()
                pg_id = pg['id'] if pg else None

                # Recupera eventuale banca per il costo (opzionale)
                bank_destination_cost = None
                cursor.execute("SELECT * FROM banks WHERE pg_id = %s", (pg_id,))
                pg_banks = cursor.fetchall()
                if pg_banks:
                    bank_destination_cost = pg_banks[0]['id']  # default prima banca, puoi creare dialog se vuoi

                cursor.execute("""
                    INSERT INTO followers (
                        pg_id, name, class, level, annual_cost, notes, bank_destination_cost, description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (pg_id, name, f_class, level, cost, notes, bank_destination_cost, race))

                self.db.commit()
                messagebox.showinfo("Successo", f"Seguace '{name}' aggiunto correttamente!")
                dialog.destroy()
                if self.tree_followers:
                    self.load_followers_list(self.tree_followers)

            except Exception as e:
                messagebox.showerror("Errore", f"Errore durante l'inserimento: {e}")

        ttk.Button(dialog, text="💾 Salva", command=save_new_follower).pack(pady=15)

    def edit_follower_dialog(self, tree):
        """Modifica un seguace usando l'ID invisibile"""
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
        dialog.geometry("450x550")

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

        def save_changes():
            name = name_entry.get().strip()
            f_class = class_entry.get().strip()
            level = int(level_spinbox.get())
            cost = float(cost_entry.get())
            desc = desc_entry.get().strip()
            notes = notes_text.get("1.0", "end").strip()

            if not name:
                messagebox.showerror("Errore", "Il nome è obbligatorio")
                return

            try:
                cursor = self.db.cursor()
                cursor.execute("""
                    UPDATE followers
                    SET name=%s, class=%s, level=%s, annual_cost=%s,
                        description=%s, notes=%s
                    WHERE id=%s
                """, (name, f_class, level, cost, desc, notes, follower['id']))

                self.db.commit()
                messagebox.showinfo("Successo", "Seguace aggiornato correttamente!")
                dialog.destroy()
                if self.tree_followers:
                    self.load_followers_list(self.tree_followers)

            except Exception as e:
                messagebox.showerror("Errore", f"Errore durante l'aggiornamento: {e}")

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
        """Crea il tab per la gestione dei seguaci"""
        
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(pady=10)

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)

        columns = ('Nome Seguace', 'Classe', 'Livello', 'Costo Ann. (MO)', 
                   'Banca di Costo', 'Note', 'Razza', 'PG Proprietario', 'Giocatore')

        tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        self.tree_followers = tree  # attributo principale
        for col in columns:
            tree.heading(col, text=col, command=lambda c=col: self.treeview_sort_column(tree, c, False))
            tree.column(col, width=140, anchor='center')

        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

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

        columns = ('ID', 'Data', 'Descrizione', 'Obiettivo', 'Scelta Giocatore')
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

    def show_event_details_popup(self, tree):
        """Mostra una finestra popup con i dettagli completi dell'imprevisto selezionato."""
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
                    choice_formatted = f"{choice_text}. Costo Extra {extra_cost} MO, Mesi Extra {extra_months}"
                else:
                    # Se è già solo testo
                    choice_formatted = str(choice_data)
            except json.JSONDecodeError:
                # Se non è JSON valido, lo mostriamo com’è
                choice_formatted = choice_raw

            # --- Finestra popup ---
            win = tk.Toplevel(self.root)
            win.title("Dettagli Imprevisto")
            win.geometry("650x450")

            ttk.Label(win, text=f"Obiettivo: {ev.get('objective_name', 'N/A')}", font=('Arial', 11, 'bold')).pack(pady=5)
            ttk.Label(win, text=f"Data Evento: {ev.get('event_date', '')}").pack(pady=5)

            # 🔸 Descrizione
            ttk.Label(win, text="Descrizione:", font=('Arial', 10, 'bold')).pack(anchor='w', padx=10)
            txt_desc = tk.Text(win, wrap='word', height=8)
            txt_desc.insert('1.0', desc_text)
            txt_desc.config(state='disabled')
            txt_desc.pack(fill='both', expand=True, padx=10, pady=5)

            # 🔸 Scelta del Giocatore (pulita e formattata)
            ttk.Label(win, text="Scelta del Giocatore:", font=('Arial', 10, 'bold')).pack(anchor='w', padx=10)
            txt_choice = tk.Text(win, wrap='word', height=5)
            txt_choice.insert('1.0', choice_formatted)
            txt_choice.config(state='disabled')
            txt_choice.pack(fill='both', expand=True, padx=10, pady=5)

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

                # --- Pulisci descrizione ---
                desc_full = ev.get('description', '') or ''
                desc_clean = re.sub(r'["{}]', '', desc_full).strip()
                desc_short = (desc_clean[:80] + '...') if len(desc_clean) > 80 else desc_clean

                # --- Pulisci scelta ---
                choice_full = ev.get('player_choice', '') or '—'
                choice_clean = re.sub(r'["{}]|option:|option', '', choice_full, flags=re.IGNORECASE).strip()
                choice_short = (choice_clean[:60] + '...') if len(choice_clean) > 60 else choice_clean

                # --- Inserimento dati (ID come IID invisibile) ---
                vals = (
                    ev.get('event_date', ''),
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
            cursor.execute("""
                SELECT event_date, description, player_choice
                FROM follower_objective_events
                WHERE objective_id = %s
                ORDER BY event_date DESC
            """, (obj_id,))

            events = cursor.fetchall()
            for ev in events:
                # Controllo sicuro per valori NULL
                event_date = ev.get('event_date', '')
                description = ev.get('description', '')
                player_choice = ev.get('player_choice', '')

                tree_events.insert('', 'end', values=(event_date, description, player_choice))

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
        
        # Salva riferimento
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
        
        # Lista spese (niente pulsante “aggiorna” — refresh automatico)
        list_frame = ttk.Frame(self.content_frame)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        columns = ('Descrizione', 'Ammontare', 'Frequenza', 'PG', 'Banca Origine')
        tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        for col in columns:
            tree.heading(col, text=col, command=lambda c=col: self.treeview_sort_column(tree, c, False))
            tree.column(col, width=160 if col != 'Descrizione' else 250)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
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
                tree.insert('', 'end', values=(
                    exp['description'],
                    f"{float(exp['amount']):.2f} MO",
                    exp['frequency'],
                    exp.get('pg_name', 'N/A'),
                    exp.get('bank_name', 'N/A')
                ))
                
        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento spese fisse: {e}")

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
        bank_combo.banks = []  # placeholder per la lista di banche (id,name)

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
        """Mostra lo stato della campagna"""
        self.clear_content()
        
        title = ttk.Label(self.content_frame, text="📊 Stato Campagna", style='Title.TLabel')
        title.pack(pady=10)
        
        # Frame con scrollbar per lo stato
        canvas = tk.Canvas(self.content_frame)
        scrollbar = ttk.Scrollbar(self.content_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        try:
            cursor = self.db.cursor()
            
            # Data di gioco
            date_frame = ttk.LabelFrame(scrollable_frame, text="📅 Data di Gioco", padding=10)
            date_frame.pack(fill='x', padx=10, pady=5)
            ttk.Label(date_frame, text=self.convert_date_to_ded_format(self.game_date),
                     font=('Arial', 12, 'bold')).pack()
            
            # Personaggi
            cursor.execute("SELECT COUNT(*) as count FROM player_characters")
            pg_count = cursor.fetchone()['count']
            
            pg_frame = ttk.LabelFrame(scrollable_frame, text="🧙 Personaggi", padding=10)
            pg_frame.pack(fill='x', padx=10, pady=5)
            ttk.Label(pg_frame, text=f"Totale: {pg_count}").pack()
            
            # Banche
            cursor.execute("""
                SELECT COUNT(*) as count, SUM(current_balance) as total 
                FROM banks
            """)
            banks_data = cursor.fetchone()
            
            banks_frame = ttk.LabelFrame(scrollable_frame, text="🏦 Banche", padding=10)
            banks_frame.pack(fill='x', padx=10, pady=5)
            ttk.Label(banks_frame, 
                     text=f"Totale Banche: {banks_data['count']}\n"
                          f"Fondi Totali: {float(banks_data['total'] or 0):.2f} MO").pack()
            
            # Seguaci
            cursor.execute("SELECT COUNT(*) as count FROM followers")
            followers_count = cursor.fetchone()['count']
            
            followers_frame = ttk.LabelFrame(scrollable_frame, text="🛡️ Seguaci", padding=10)
            followers_frame.pack(fill='x', padx=10, pady=5)
            ttk.Label(followers_frame, text=f"Totale: {followers_count}").pack()
            
            # Obiettivi
            cursor.execute("""
                SELECT status, COUNT(*) as count 
                FROM follower_objectives 
                GROUP BY status
            """)
            objectives = cursor.fetchall()
            
            obj_frame = ttk.LabelFrame(scrollable_frame, text="🎯 Obiettivi", padding=10)
            obj_frame.pack(fill='x', padx=10, pady=5)
            
            for obj in objectives:
                status_name = self.OBJECTIVE_STATUS_REV.get(obj['status'], 'Sconosciuto')
                ttk.Label(obj_frame, text=f"{status_name}: {obj['count']}").pack()
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento stato: {e}")
        
        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y")
    
    def show_chat(self):
        """Mostra il sistema chat"""
        self.clear_content()
        
        title = ttk.Label(self.content_frame, text="💬 Sistema Chat", style='Title.TLabel')
        title.pack(pady=10)
        
        # Notebook per diverse chat
        notebook = ttk.Notebook(self.content_frame)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Tab Chat Comune
        comune_frame = ttk.Frame(notebook)
        notebook.add(comune_frame, text="💬 Chat Comune")
        self.create_chat_interface(comune_frame, chat_type='comune')
        
        # Tab Chat Privata
        privata_frame = ttk.Frame(notebook)
        notebook.add(privata_frame, text="📩 Chat Privata")
        self.create_private_chat_interface(privata_frame)
        
        # Tab Chat Segreta (solo giocatori)
        if self.current_user['role'] == 'GIOCATORE':
            segreta_frame = ttk.Frame(notebook)
            notebook.add(segreta_frame, text="🤫 Chat Segreta")
            self.create_secret_chat_interface(segreta_frame)
    
    def create_chat_interface(self, parent, chat_type='comune'):
        """Crea l'interfaccia per una chat"""
        # Area messaggi
        messages_frame = ttk.Frame(parent)
        messages_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        messages_text = scrolledtext.ScrolledText(messages_frame, wrap=tk.WORD, height=20)
        messages_text.pack(fill='both', expand=True)
        messages_text.config(state='disabled')
        
        # Carica messaggi
        self.load_chat_messages(messages_text, chat_type)
        
        # Input area
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill='x', padx=5, pady=5)
        
        message_entry = ttk.Entry(input_frame)
        message_entry.pack(side='left', fill='x', expand=True, padx=5)
        
        def send_message():
            message = message_entry.get().strip()
            if not message:
                return
            
            try:
                ded_date = self.convert_date_to_ded_format(self.game_date)
                
                cursor = self.db.cursor()
                cursor.execute("""
                    INSERT INTO chat_messages (sender_id, receiver_id, is_secret, message, mystara_date)
                    VALUES (%s, NULL, 0, %s, %s)
                """, (self.current_user['id'], message, ded_date))
                self.db.commit()
                
                message_entry.delete(0, tk.END)
                self.load_chat_messages(messages_text, chat_type)
                
            except Exception as e:
                messagebox.showerror("Errore", f"Errore invio messaggio: {e}")
        
        send_btn = ttk.Button(input_frame, text="📤 Invia", command=send_message)
        send_btn.pack(side='right', padx=5)
        
        message_entry.bind('<Return>', lambda e: send_message())
        
        # Pulsante refresh
        refresh_btn = ttk.Button(parent, text="🔄 Aggiorna", 
                                command=lambda: self.load_chat_messages(messages_text, chat_type))
        refresh_btn.pack(pady=5)
    
    def load_chat_messages(self, text_widget, chat_type='comune'):
        """Carica i messaggi nella chat"""
        try:
            cursor = self.db.cursor()
            
            cursor.execute("""
                SELECT c.*, u.username AS sender_name
                FROM chat_messages c
                JOIN users u ON c.sender_id = u.id
                WHERE c.receiver_id IS NULL
                ORDER BY c.created_at DESC
                LIMIT 50
            """)
            messages = cursor.fetchall()
            
            text_widget.config(state='normal')
            text_widget.delete(1.0, tk.END)
            
            for msg in reversed(messages):
                date_str = msg.get('mystara_date', '')
                sender = msg['sender_name']
                text_widget.insert(tk.END, f"[{date_str}] {sender}: {msg['message']}\n")
            
            text_widget.config(state='disabled')
            text_widget.see(tk.END)
            
            # Marca come letti
            for msg in messages:
                cursor.execute("""
                    INSERT IGNORE INTO chat_reads (user_id, message_id) VALUES (%s, %s)
                """, (self.current_user['id'], msg['id']))
            self.db.commit()
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore caricamento messaggi: {e}")
    
    def create_private_chat_interface(self, parent):
        """Crea interfaccia chat privata"""
        ttk.Label(parent, text="📩 Chat Privata DM ↔ Giocatore", 
                 style='Subtitle.TLabel').pack(pady=10)
        
        # Seleziona destinatario
        select_frame = ttk.Frame(parent)
        select_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(select_frame, text="Destinatario:").pack(side='left', padx=5)
        
        cursor = self.db.cursor()
        if self.current_user['role'] == 'DM':
            cursor.execute("SELECT id, username FROM users WHERE role = 'GIOCATORE'")
        else:
            cursor.execute("SELECT id, username FROM users WHERE role = 'DM'")
        
        users = cursor.fetchall()
        
        if not users:
            ttk.Label(parent, text="Nessun destinatario disponibile").pack(pady=20)
            return
        
        user_combo = ttk.Combobox(select_frame, width=25, state='readonly')
        user_combo['values'] = [u['username'] for u in users]
        user_combo.pack(side='left', padx=5)
        
        # Area messaggi
        messages_frame = ttk.Frame(parent)
        messages_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        messages_text = scrolledtext.ScrolledText(messages_frame, wrap=tk.WORD, height=15)
        messages_text.pack(fill='both', expand=True)
        messages_text.config(state='disabled')
    
    def create_secret_chat_interface(self, parent):
        """Crea interfaccia chat segreta tra giocatori"""
        if self.current_user['role'] == 'DM':
            # DM vede tutte le chat segrete (solo lettura)
            ttk.Label(parent, text="🤫 Chat Segrete tra Giocatori (Solo Lettura)", 
                     style='Subtitle.TLabel').pack(pady=10)
            
            # Area messaggi
            messages_frame = ttk.Frame(parent)
            messages_frame.pack(fill='both', expand=True, padx=10, pady=10)
            
            messages_text = scrolledtext.ScrolledText(messages_frame, wrap=tk.WORD, height=20)
            messages_text.pack(fill='both', expand=True)
            messages_text.config(state='disabled')
            
            def load_all_secret_messages():
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        SELECT c.*, s.username AS sender_name, r.username AS receiver_name
                        FROM chat_messages c
                        JOIN users s ON c.sender_id = s.id
                        LEFT JOIN users r ON c.receiver_id = r.id
                        WHERE c.is_secret = 1
                        ORDER BY c.created_at DESC
                        LIMIT 100
                    """)
                    
                    messages = cursor.fetchall()
                    
                    messages_text.config(state='normal')
                    messages_text.delete(1.0, tk.END)
                    
                    for msg in reversed(messages):
                        date_str = msg.get('mystara_date', '')
                        sender = msg['sender_name']
                        receiver = msg.get('receiver_name', 'N/A')
                        messages_text.insert(tk.END, f"[{date_str}] {sender} → {receiver}: {msg['message']}\n")
                    
                    messages_text.config(state='disabled')
                    messages_text.see(tk.END)
                    
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore caricamento: {e}")
            
            ttk.Button(parent, text="🔄 Aggiorna", 
                      command=load_all_secret_messages).pack(pady=5)
            
            load_all_secret_messages()
            
        else:
            # Giocatori possono inviare chat segrete
            ttk.Label(parent, text="🤫 Chat Segreta tra Giocatori", 
                     style='Subtitle.TLabel').pack(pady=10)
            
            # Seleziona destinatario
            select_frame = ttk.Frame(parent)
            select_frame.pack(fill='x', padx=10, pady=5)
            
            ttk.Label(select_frame, text="Giocatore:").pack(side='left', padx=5)
            
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT id, username FROM users 
                WHERE role = 'GIOCATORE' AND id != %s
            """, (self.current_user['id'],))
            players = cursor.fetchall()
            
            if not players:
                ttk.Label(parent, text="Nessun altro giocatore disponibile").pack(pady=20)
                return
            
            player_combo = ttk.Combobox(select_frame, width=25, state='readonly')
            player_combo['values'] = [p['username'] for p in players]
            player_combo.pack(side='left', padx=5)
            
            # Area messaggi
            messages_frame = ttk.Frame(parent)
            messages_frame.pack(fill='both', expand=True, padx=10, pady=10)
            
            messages_text = scrolledtext.ScrolledText(messages_frame, wrap=tk.WORD, height=15)
            messages_text.pack(fill='both', expand=True)
            messages_text.config(state='disabled')
            
            def load_secret_messages():
                if player_combo.current() < 0:
                    return
                
                receiver_id = players[player_combo.current()]['id']
                
                try:
                    cursor = self.db.cursor()
                    cursor.execute("""
                        SELECT c.*, s.username AS sender_name, r.username AS receiver_name
                        FROM chat_messages c
                        JOIN users s ON c.sender_id = s.id
                        LEFT JOIN users r ON c.receiver_id = r.id
                        WHERE c.is_secret = 1
                          AND ((c.sender_id = %s AND c.receiver_id = %s)
                            OR (c.sender_id = %s AND c.receiver_id = %s))
                        ORDER BY c.created_at DESC
                        LIMIT 50
                    """, (self.current_user['id'], receiver_id, receiver_id, self.current_user['id']))
                    
                    messages = cursor.fetchall()
                    
                    messages_text.config(state='normal')
                    messages_text.delete(1.0, tk.END)
                    
                    for msg in reversed(messages):
                        date_str = msg.get('mystara_date', '')
                        
                        if msg['sender_id'] == self.current_user['id']:
                            messages_text.insert(tk.END, 
                                f"[{date_str}] Tu → {msg['receiver_name']}: {msg['message']}\n")
                        else:
                            messages_text.insert(tk.END, 
                                f"[{date_str}] {msg['sender_name']} → Tu: {msg['message']}\n")
                    
                    messages_text.config(state='disabled')
                    messages_text.see(tk.END)
                    
                    # Marca come letti
                    for msg in messages:
                        cursor.execute("""
                            INSERT IGNORE INTO chat_reads (user_id, message_id) VALUES (%s, %s)
                        """, (self.current_user['id'], msg['id']))
                    self.db.commit()
                    
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore caricamento: {e}")
            
            ttk.Button(select_frame, text="📨 Carica Chat", 
                      command=load_secret_messages).pack(side='left', padx=5)
            
            # Input area
            input_frame = ttk.Frame(parent)
            input_frame.pack(fill='x', padx=10, pady=5)
            
            message_entry = ttk.Entry(input_frame)
            message_entry.pack(side='left', fill='x', expand=True, padx=5)
            
            def send_secret_message():
                if player_combo.current() < 0:
                    messagebox.showwarning("Avviso", "Seleziona un giocatore")
                    return
                
                message = message_entry.get().strip()
                if not message:
                    return
                
                receiver_id = players[player_combo.current()]['id']
                
                try:
                    ded_date = self.convert_date_to_ded_format(self.game_date)
                    
                    cursor = self.db.cursor()
                    cursor.execute("""
                        INSERT INTO chat_messages (sender_id, receiver_id, is_secret, message, mystara_date)
                        VALUES (%s, %s, 1, %s, %s)
                    """, (self.current_user['id'], receiver_id, message, ded_date))
                    self.db.commit()
                    
                    message_entry.delete(0, tk.END)
                    load_secret_messages()
                    
                except Exception as e:
                    messagebox.showerror("Errore", f"Errore invio: {e}")
            
            send_btn = ttk.Button(input_frame, text="📤 Invia Segreto", command=send_secret_message)
            send_btn.pack(side='right', padx=5)
            
            message_entry.bind('<Return>', lambda e: send_secret_message())

    def _count_unread_messages(self):
        """Conta i messaggi non letti per l'utente loggato"""
        if not self.current_user:
            return 0
        cursor = self.db.cursor()
        try:
            if self.current_user['role'] == 'DM':
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM chat_messages m
                    LEFT JOIN chat_reads r ON m.id = r.message_id AND r.user_id = %s
                    WHERE r.id IS NULL
                """, (self.current_user['id'],))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM chat_messages m
                    LEFT JOIN chat_reads r ON m.id = r.message_id AND r.user_id = %s
                    WHERE r.id IS NULL
                      AND (
                          m.receiver_id IS NULL
                          OR m.receiver_id = %s
                          OR m.sender_id = %s
                          OR (m.is_secret = 1 AND (m.receiver_id = %s OR m.sender_id = %s))
                      )
                """, (self.current_user['id'], self.current_user['id'], self.current_user['id'], 
                     self.current_user['id'], self.current_user['id']))
            result = cursor.fetchone()
            return result['count'] if result else 0
        except:
            return 0
        finally:
            cursor.close()


        """Crea interfaccia chat privata"""
        ttk.Label(parent, text="📩 Chat Privata DM ↔ Giocatore", 
                 style='Subtitle.TLabel').pack(pady=10)
        
        # Seleziona destinatario
        select_frame = ttk.Frame(parent)
        select_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(select_frame, text="Destinatario:").pack(side='left', padx=5)
        
        cursor = self.db.cursor()
        if self.current_user['role'] == 'DM':
            cursor.execute("SELECT id, username FROM users WHERE role = 'GIOCATORE'")
        else:
            cursor.execute("SELECT id, username FROM users WHERE role = 'DM'")
        
        users = cursor.fetchall()
        
        if not users:
            ttk.Label(parent, text="Nessun destinatario disponibile").pack(pady=20)
            return
        
        user_combo = ttk.Combobox(select_frame, width=25, state='readonly')
        user_combo['values'] = [u['username'] for u in users]
        user_combo.pack(side='left', padx=5)
        
        # Area messaggi
        messages_frame = ttk.Frame(parent)
        messages_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        messages_text = scrolledtext.ScrolledText(messages_frame, wrap=tk.WORD, height=15)
        messages_text.pack(fill='both', expand=True)
        messages_text.config(state='disabled')
    
    def download_diary(self):
        """Scarica il diario della campagna"""
        try:
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
            
            if messagebox.askyesno("Nuovo Diario Disponibile", 
                                  f"Nuova versione disponibile: {ultima_versione}\n"
                                  f"Versione attuale: {versione_locale}\n\n"
                                  f"Scaricare il diario?"):
                
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
                
                messagebox.showinfo("Successo", f"Diario scaricato: {filename}")
                
        except Exception as e:
            messagebox.showerror("Errore", f"Errore download diario: {e}")

    # FUNZIONE: Export Excel
    def export_to_excel(self):
        """Esporta i fondi PG in Excel"""
        if not self.current_user or self.current_user['role'] != 'DM':
            messagebox.showwarning("Avviso", "Solo il DM può esportare in Excel")
            return
        
        try:
            cursor = self.db.cursor()
            
            cursor.execute("""
                SELECT pc.id, pc.name, u.username
                FROM player_characters pc
                LEFT JOIN users u ON pc.user_id = u.id
            """)
            pg_data = cursor.fetchall()
            
            cursor.execute("SELECT * FROM banks")
            bank_data = cursor.fetchall()
            
            cursor.execute("SELECT * FROM economic_activities")
            activity_data = cursor.fetchall()
            
            cursor.execute("SELECT * FROM fixed_expenses")
            expense_data = cursor.fetchall()
            
            export_list = []
            
            for pg in pg_data:
                pg_id = pg['id']
                pg_name = pg['name']
                pg_user = pg['username'] if pg['username'] else 'N/A'
                
                pg_banks = [b for b in bank_data if b['pg_id'] == pg_id]
                for bank in pg_banks:
                    export_list.append({
                        "Nome PG": pg_name,
                        "Utente": pg_user,
                        "Tipo": "Banca",
                        "Nome": bank['name'],
                        "Descrizione": bank.get('location', ''),
                        "Importo": float(bank['current_balance']),
                        "Frequenza": "N/A"
                    })
                
                pg_activities = [a for a in activity_data if a['pg_id'] == pg_id]
                for act in pg_activities:
                    export_list.append({
                        "Nome PG": pg_name,
                        "Utente": pg_user,
                        "Tipo": "Attività Economica",
                        "Nome": act['description'],
                        "Descrizione": act['description'],
                        "Importo": float(act['income']),
                        "Frequenza": act['frequency']
                    })
                
                pg_expenses = [e for e in expense_data if e['pg_id'] == pg_id]
                for exp in pg_expenses:
                    export_list.append({
                        "Nome PG": pg_name,
                        "Utente": pg_user,
                        "Tipo": "Spesa Fissa",
                        "Nome": exp['description'],
                        "Descrizione": exp['description'],
                        "Importo": -float(exp['amount']),
                        "Frequenza": exp['frequency']
                    })
            
            if not export_list:
                messagebox.showinfo("Info", "Nessun dato da esportare")
                return
            
            df = pd.DataFrame(export_list)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"FondiPG_{timestamp}.xlsx"
            
            df.to_excel(filename, index=False)
            messagebox.showinfo("Successo", f"Dati esportati in: {filename}")
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore export: {e}")

    def append_time_log(self, message):
        """Aggiunge una riga al riquadro log (GUI) e la stampa su stdout."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}\n"
        try:
            # Text widget GUI
            if hasattr(self, "time_log_text") and isinstance(self.time_log_text, tk.Text):
                self.time_log_text.configure(state='normal')
                self.time_log_text.insert(tk.END, line)
                self.time_log_text.see(tk.END)
                self.time_log_text.configure(state='disabled')
            # sempre stampa su console per debug
            print(line.strip())
        except Exception as e:
            print("append_time_log error:", e)

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

    def advance_days(self, days=1):
        """Avanza il tempo di N giorni; applica eventi giornalieri per ogni giorno."""
        try:
            for i in range(days):
                # incrementa di un giorno
                if isinstance(self.game_date, datetime):
                    self.game_date = (self.game_date + timedelta(days=1)).date()
                elif isinstance(self.game_date, date):
                    self.game_date = self.game_date + timedelta(days=1)
                else:
                    # fallback parsing
                    self.game_date = datetime.strptime(str(self.game_date), "%Y-%m-%d").date() + timedelta(days=1)

                # salva nel DB
                try:
                    cursor = self.db.cursor()
                    cursor.execute("UPDATE game_state SET game_date = %s WHERE id = 1", (self.game_date.strftime('%Y-%m-%d'),))
                    self.db.commit()
                    cursor.close()
                except Exception as db_e:
                    self.append_time_log(f"Errore salvataggio data su DB: {db_e}")

                self.append_time_log(f"Data avanzata a {self.convert_date_to_ded_format(self.game_date)} (giorno {i+1}/{days})")

                # Applica eventi giornalieri
                self._apply_daily_events()

                # dopo eventi giornalieri, applica imprevisti non gestiti (se qualcuno ha già inviato scelta)
                self.apply_unhandled_objective_events()

            # Aggiorna grafica (data nel menu principale, ecc.)
            if hasattr(self, 'date_label'):
                try:
                    self.date_label.config(text=self.convert_date_to_ded_format(self.game_date))
                except:
                    pass

            # Ricarica tab obiettivi se presente
            try:
                if hasattr(self, 'objectives_tree') and hasattr(self, 'load_objectives_list'):
                    self.load_objectives_list(self.objectives_tree)
            except Exception as e:
                self.append_time_log(f"Impossibile aggiornare lista obiettivi GUI: {e}")

            # aggiorna lista imprevisti
            self.load_pending_events()

            messagebox.showinfo("Successo", f"Avanzati {days} giorni. Data: {self.convert_date_to_ded_format(self.game_date)}")

        except Exception as e:
            messagebox.showerror("Errore", f"Errore avanzamento giorni: {e}")
            self.append_time_log(f"Errore avanzamento giorni: {e}")

    def advance_weeks(self, weeks=1):
        """Avanza settimane: esegue advance_days(1) sette volte per ogni settimana (garantisce conteggi giornalieri corretti), poi esegue eventi settimanali."""
        try:
            for w in range(weeks):
                self.append_time_log(f"Inizio settimana {w+1}/{weeks} — avanzamento giorno-per-giorno")
                # esegui 7 volte (giorno-per-giorno) — ogni giorno applica _apply_daily_events
                for d in range(7):
                    self.advance_days(1)  # già applica daily e unhandled
                # una volta completati i 7 giorni, applica weekly events
                self._apply_weekly_events()
                self.apply_unhandled_objective_events()

            # aggiorna DB data (già aggiornata in advance_days)
            try:
                if hasattr(self, 'date_label'):
                    self.date_label.config(text=self.convert_date_to_ded_format(self.game_date))
            except:
                pass

            messagebox.showinfo("Successo", f"Avanzate {weeks} settimane. Data: {self.convert_date_to_ded_format(self.game_date)}")

        except Exception as e:
            messagebox.showerror("Errore", f"Errore avanzamento settimane: {e}")
            self.append_time_log(f"Errore advance_weeks: {e}")

    def advance_months(self, months=1):
        """
        Avanza mesi: avanzamento giorno-per-giorno fino a raggiungere la nuova data mese-per-mese.
        Quando si varca il confine di mese si applicano gli eventi mensili.
        """
        try:
            # calcola data target
            if isinstance(self.game_date, datetime):
                start_dt = self.game_date.date()
            else:
                start_dt = self.game_date

            target_dt = start_dt + relativedelta(months=months)

            self.append_time_log(f"Avanzamento mesi: da {self.convert_date_to_ded_format(start_dt)} a {self.convert_date_to_ded_format(target_dt)}")

            # percorri giorno per giorno
            current = start_dt
            while current < target_dt:
                # avanza di un giorno (usiamo advance_days(1) per uniformità e per trigger giornalieri)
                self.advance_days(1)
                # se siamo al primo giorno del mese successivo -> applica eventi mensili
                new_current = self.game_date
                if (new_current.day == 1) or (new_current.month != current.month):
                    # Applica eventi mensili alla transizione di mese
                    self._apply_monthly_events()
                    self.apply_unhandled_objective_events()
                current = new_current

            # definisce la data finale come target_dt (già impostata)
            try:
                if hasattr(self, 'date_label'):
                    self.date_label.config(text=self.convert_date_to_ded_format(self.game_date))
            except:
                pass

            messagebox.showinfo("Successo", f"Avanzati {months} mesi. Data: {self.convert_date_to_ded_format(self.game_date)}")

        except Exception as e:
            messagebox.showerror("Errore", f"Errore avanzamento mesi: {e}")
            self.append_time_log(f"Errore advance_months: {e}")

    # --- Eventi: implementazioni che replicano la logica del codice DOS ma con log GUI ---
    def _apply_daily_events(self):
        """Applica eventi giornalieri (attività economiche giornaliere, spese giornaliere, progress obiettivi 1/30 mese)."""
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

            # Applica 1/30 di mese sugli obiettivi
            self._apply_objective_progress(frazione_mensile=1/30.0, etichetta='giornaliero')

        except Exception as e:
            self.append_time_log(f"Errore in _apply_daily_events: {e}")
        finally:
            try:
                cursor.close()
            except:
                pass

    def _apply_weekly_events(self):
        """Applica eventi settimanali (attività settimanali, spese settimanali, progress obiettivi 1/4 mese)."""
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
        """Applica eventi mensili (spese mensili, attività mensili, progress obiettivi 1 mese)."""
        self.append_time_log("Applicazione eventi mensili...")
        try:
            cursor = self.db.cursor()

            # Spese fisse mensili
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
                amount = float(expense.get('amount') or 0.0)
                if not src_bank_id:
                    self.append_time_log(f"  Spesa '{expense.get('description','?')}' senza banca: non applicata")
                    continue
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

            # Attività economiche mensili
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

            # Per gli obiettivi: applichiamo la progressione mensile (frazione 1.0)
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
        Aggiorna progress_percent e preleva il costo dalla banca collegata.
        frazione_mensile: frazione del mese da applicare (es. 1/30 giornaliero, 1/4 settimanale, 1.0 mensile)
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

                # base_estimated_months o fallback a estimated_months
                base_months = int(obj.get('base_estimated_months') or estimated_months or 0)
                if base_months <= 0 or estimated_months <= 0:
                    self.append_time_log(f"  Obiettivo '{name}' ha mesi non validi, ignorato.")
                    continue

                current_balance = float(obj.get('current_balance') or 0.0)

                # costi e progressione calcolati
                cost_per_month = total_cost / estimated_months if estimated_months > 0 else 0.0
                progress_per_month = 100.0 / base_months if base_months > 0 else 0.0

                # applica la frazione
                cost_to_apply = cost_per_month * float(frazione_mensile)
                progress_to_apply = progress_per_month * float(frazione_mensile)

                if not bank_id:
                    self.append_time_log(f"  Obiettivo '{name}' senza banca; costo non applicato.")
                    continue

                if current_balance >= cost_to_apply and cost_to_apply > 0:
                    new_balance = current_balance - cost_to_apply
                    try:
                        cursor.execute("UPDATE banks SET current_balance = %s WHERE id = %s", (new_balance, bank_id))
                        self.db.commit()
                        self.append_time_log(f"  Prelevati {cost_to_apply:.2f} MO per obiettivo '{name}' (banca id {bank_id})")
                    except Exception as e:
                        self.append_time_log(f"  Errore prelievo per obiettivo '{name}': {e}")
                        continue
                else:
                    # se non c'è abbastanza saldo, non applicare il progresso
                    self.append_time_log(f"  Saldo insufficiente per obiettivo '{name}' (necessario {cost_to_apply:.2f}, disponibile {current_balance:.2f})")
                    continue

                # Aggiorna progresso
                new_progress = min(progress_pct + progress_to_apply, 100.0)
                update_status = obj.get('status')
                if new_progress >= 100.0:
                    update_status = self.OBJECTIVE_STATUS['COMPLETATO']

                try:
                    cursor.execute("""
                        UPDATE follower_objectives
                        SET progress_percentage = %s, status = %s
                        WHERE id = %s
                    """, (new_progress, update_status, obj_id))
                    self.db.commit()
                    self.append_time_log(f"  Obiettivo '{name}' avanzato: {progress_pct:.1f}% -> {new_progress:.1f}% (status: {self.OBJECTIVE_STATUS_REV.get(update_status, update_status)})")
                    # se completato, aggiorna la GUI obiettivi
                    if update_status == self.OBJECTIVE_STATUS['COMPLETATO']:
                        # best-effort: ricarica la lista obiettivi se esiste
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
        """Applica automaticamente le scelte dei giocatori per gli imprevisti (handled/process)."""
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
                return

            for event in events:
                eid = event.get('id')
                player_choice_raw = event.get('player_choice')
                response_options_raw = event.get('response_options')

                if not player_choice_raw or not response_options_raw:
                    self.append_time_log(f"  Evento id {eid} senza scelta o opzioni; saltato.")
                    continue

                # decode JSON safely
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
                # recupera obiettivo
                cursor.execute("SELECT name, estimated_months, total_cost FROM follower_objectives WHERE id = %s", (objective_id,))
                objective = cursor.fetchone()
                if not objective:
                    self.append_time_log(f"  Obiettivo id {objective_id} non trovato per evento {eid}")
                    continue

                name = objective.get('name', 'Sconosciuto')
                est_months = int(objective.get('estimated_months') or 0)
                tot_cost = float(objective.get('total_cost') or 0.0)

                # se scelta indica fallimento
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

            # ricarica lista imprevisti pendenti
            self.load_pending_events()

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
        """Dialog per impostare manualmente la data (GUI) e aggiornare DB + GUI."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Imposta Data")
        dialog.geometry("320x180")

        ttk.Label(dialog, text="Formato: YYYY-MM-DD").pack(pady=8)
        date_entry = ttk.Entry(dialog, width=20)
        try:
            date_entry.insert(0, self.game_date.strftime('%Y-%m-%d'))
        except:
            date_entry.insert(0, str(self.game_date))

        date_entry.pack(pady=6)

        def save_date():
            new_date_str = date_entry.get().strip()
            try:
                new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
            except ValueError:
                messagebox.showerror("Errore", "Formato data non valido (usa YYYY-MM-DD)")
                return

            try:
                cursor = self.db.cursor()
                cursor.execute("UPDATE game_state SET game_date = %s WHERE id = 1", (new_date_str,))
                self.db.commit()
                cursor.close()
            except Exception as e:
                messagebox.showerror("Errore", f"Errore salvataggio data: {e}")
                return

            self.game_date = new_date
            if hasattr(self, 'date_label'):
                try:
                    self.date_label.config(text=self.convert_date_to_ded_format(self.game_date))
                except:
                    pass

            self.append_time_log(f"Data impostata manualmente a {self.convert_date_to_ded_format(self.game_date)}")
            dialog.destroy()
            # aggiorna GUI tempo
            try:
                self.show_time_menu()
            except:
                pass

        ttk.Button(dialog, text="💾 Salva", command=save_date).pack(pady=12)

    # FUNZIONE: Controllo aggiornamenti
    def check_for_updates(self):
        """Controlla aggiornamenti dello script"""
        try:
            response = requests.get(VERSION_URL, timeout=5)
            response.raise_for_status()
            latest_version = response.text.strip()
            
            if latest_version > __VERSION__:
                if messagebox.askyesno("Aggiornamento Disponibile",
                                      f"Nuova versione disponibile: {latest_version}\n"
                                      f"Versione attuale: {__VERSION__}\n\n"
                                      f"Scaricare l'aggiornamento?"):
                    
                    response = requests.get(SCRIPT_URL, timeout=5)
                    response.raise_for_status()
                    
                    script_path = os.path.abspath(__file__)
                    with open(script_path, 'wb') as f:
                        f.write(response.content)
                    
                    messagebox.showinfo("Successo", 
                                      "Aggiornamento completato!\n"
                                      "Riavvia l'applicazione.")
                    self.root.quit()
            else:
                messagebox.showinfo("Nessun Aggiornamento",
                                  f"Stai usando l'ultima versione: {__VERSION__}")
        except Exception as e:
            messagebox.showerror("Errore", f"Errore controllo aggiornamenti: {e}")

    # FUNZIONE: About
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
    • Sistema Bancario
    • Seguaci e Obiettivi
    • Attività Economiche
    • Spese Fisse
    • Sistema Chat
    • Backup Database
    • Export Excel

    Database: MariaDB
    Interfaccia: Tkinter/Python
        """
        
        messagebox.showinfo("Informazioni", about_text)

    # FUNZIONE: Toggle fullscreen
    def toggle_fullscreen(self):
        """Attiva/disattiva schermo intero"""
        current_state = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not current_state)

    # FUNZIONE: Chiusura app
    def on_closing(self):
        """Gestisce la chiusura dell'applicazione"""
        if messagebox.askyesno("Conferma Uscita", "Sei sicuro di voler uscire?"):
            try:
                if self.db:
                    self.db.close()
            except:
                pass
            self.root.destroy()

    # FUNZIONE: Setup menu bar
    def setup_menu_bar(self):
        """Crea la barra dei menu"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        
        if self.current_user and self.current_user['role'] == 'DM':
            file_menu.add_command(label="📊 Esporta Excel", command=self.export_to_excel)
            file_menu.add_separator()
        
        file_menu.add_command(label="🔄 Controlla Aggiornamenti", command=self.check_for_updates)
        file_menu.add_separator()
        file_menu.add_command(label="🚪 Logout", command=self.show_login_screen)
        file_menu.add_command(label="❌ Esci", command=self.on_closing)
        
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Visualizza", menu=view_menu)
        view_menu.add_command(label="🖥️ Schermo Intero", command=self.toggle_fullscreen)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Aiuto", menu=help_menu)
        help_menu.add_command(label="ℹ️ Informazioni", command=self.show_about)
        help_menu.add_command(label="📘 Scarica Diario", command=self.download_diary)

    # FUNZIONE: Setup shortcut tastiera
    def setup_keyboard_shortcuts(self):
        """Configura scorciatoie da tastiera"""
        self.root.bind('<F11>', lambda e: self.toggle_fullscreen())
        self.root.bind('<Control-q>', lambda e: self.on_closing())
        self.root.bind('<Escape>', lambda e: self.root.attributes('-fullscreen', False))

    
    def run(self):
        """Avvia l'applicazione"""
        self.root.mainloop()

def main():
    """Funzione principale"""
    app = DeDToolGUI()
    app.run()

if __name__ == "__main__":
    main()
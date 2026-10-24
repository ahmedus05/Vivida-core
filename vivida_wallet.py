import os
import json
import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
import requests
import hashlib
import threading
import time
from Crypto.PublicKey import RSA
from Crypto.Signature import pss
from Crypto.Hash import SHA256
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# ПОДКЛЮЧЕНИЕ К СЕРВЕРУ: укажите публичный IP-адрес купленного VDS
NODE_URL = "http://127.0.0.1:5000" 
VAULT_FILE = "vivida_vault.json"

def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000, 32)

def encrypt_vault(password: str, private_key_pem: bytes, public_key_pem: bytes) -> dict:
    salt = os.urandom(16)
    iv = os.urandom(16)
    key = derive_key(password, salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted_priv = cipher.encrypt(pad(private_key_pem, AES.block_size))
    return {
        "salt": salt.hex(),
        "iv": iv.hex(),
        "public_key": public_key_pem.hex(),
        "encrypted_private_key": encrypted_priv.hex()
    }

def decrypt_vault(password: str, vault: dict) -> bytes:
    salt = bytes.fromhex(vault["salt"])
    iv = bytes.fromhex(vault["iv"])
    encrypted_priv = bytes.fromhex(vault["encrypted_private_key"])
    key = derive_key(password, salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(encrypted_priv), AES.block_size)

class VividaSecureWallet:
    def __init__(self, root):
        self.root = root
        self.root.title("🛡️ VIVIDA SECURE VAULT")
        self.root.geometry("700x580")
        self.root.configure(bg="#0c0714")
        
        self.my_priv_key_pem = b""
        self.my_pub_key_pem = ""
        self.my_address = ""

        self.auth_frame = tk.Frame(self.root, bg="#130b1e")
        self.auth_frame.pack(fill='both', expand=True)
        self.build_auth_screen()

    def build_auth_screen(self):
        tk.Label(self.auth_frame, text="⚙️ АВТОРИЗАЦИЯ VIVIDA", font=("Courier", 16, "bold"), fg="#00e5ff", bg="#130b1e").pack(pady=40)
        is_new = not os.path.exists(VAULT_FILE)
        txt = "Придумайте пароль для нового кошелька:" if is_new else "Введите пароль для расшифровки ключей:"
        tk.Label(self.auth_frame, text=txt, font=("Arial", 11), fg="white", bg="#130b1e").pack(pady=10)

        self.pass_entry = tk.Entry(self.auth_frame, bg="#21153b", fg="white", font=("Arial", 14), show="*", width=25, insertbackground="white")
        self.pass_entry.pack(pady=10)
        self.pass_entry.focus()

        btn_text = "СОЗДАТЬ КОШЕЛЕК" if is_new else "ВОЙТИ В КОШЕЛЕК"
        tk.Button(self.auth_frame, text=btn_text, font=("Arial", 11, "bold"), bg="#5e35b1", fg="white", width=20, command=self.handle_auth).pack(pady=20)

    def handle_auth(self):
        password = self.pass_entry.get()
        if not password: return

        if not os.path.exists(VAULT_FILE):
            rsa_key = RSA.generate(2048)
            priv_pem = rsa_key.export_key()
            pub_pem = rsa_key.publickey().export_key()
            with open(VAULT_FILE, 'w') as f:
                json.dump(encrypt_vault(password, priv_pem, pub_pem), f)
            self.my_priv_key_pem, self.my_pub_key_pem = priv_pem, pub_pem.decode()
        else:
            try:
                with open(VAULT_FILE, 'r') as f:
                    vault = json.load(f)
                self.my_priv_key_pem = decrypt_vault(password, vault)
                self.my_pub_key_pem = bytes.fromhex(vault["public_key"]).decode()
            except Exception:
                messagebox.showerror("Ошибка", "Неверный пароль!")
                return

        self.my_address = hashlib.sha256(self.my_pub_key_pem.encode()).hexdigest()[:34]
        self.auth_frame.destroy()
        self.build_main_wallet_interface()

    def build_main_wallet_interface(self):
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook', background='#0c0714', borderwidth=0)
        style.configure('TNotebook.Tab', background='#1e122b', foreground='#b39ddb', font=('Courier', 10, 'bold'), padding=8)
        style.map('TNotebook.Tab', background=[('selected', '#5e35b1')], foreground=[('selected', 'white')])

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)

        self.tab_main = tk.Frame(self.notebook, bg="#130b1e")
        self.tab_market = tk.Frame(self.notebook, bg="#130b1e")
        self.notebook.add(self.tab_main, text=" 🔒 Кошелек и Майнинг ")
        self.notebook.add(self.tab_market, text=" 📈 Глобальный Рынок ")

        tk.Label(self.tab_main, text="БАЛАНС КРИПТОВАЛЮТЫ VIVIDA", font=("Courier", 13, "bold"), fg="#b39ddb", bg="#130b1e").pack(pady=10)
        self.lbl_balance = tk.Label(self.tab_main, text="0.00 VIV", font=("Courier", 36, "bold"), fg="#00e676", bg="#130b1e")
        self.lbl_balance.pack()

        tk.Label(self.tab_main, text=f"Ваш адрес:\n{self.my_address}", font=("Courier", 10), fg="#81c784", bg="#130b1e").pack(pady=5)
        self.lbl_diff = tk.Label(self.tab_main, text="Сложность сети: Вычисление...", font=("Arial", 10, "italic"), fg="#ffb74d", bg="#130b1e")
        self.lbl_diff.pack()

        self.btn_mine = tk.Button(self.tab_main, text="⛏️ ЗАПУСТИТЬ СЛОЖНЫЙ МАЙНИНГ (Proof-of-Work)", font=("Courier", 11, "bold"), 
                                  bg="#e91e63", fg="white", command=self.start_mine_thread, height=2)
        self.btn_mine.pack(fill='x', padx=40, pady=15)

        frame_order = tk.LabelFrame(self.tab_market, text=" Выставить монеты на продажу ", bg="#130b1e", fg="#00e5ff", padx=10, pady=5)
        frame_order.pack(fill='x', padx=20, pady=5)
        tk.Label(frame_order, text="Объём VIV:", fg="white", bg="#130b1e").grid(row=0, column=0)
        self.ent_sell_amt = tk.Entry(frame_order, bg="#21153b", fg="white", width=12)
        self.ent_sell_amt.grid(row=0, column=1, padx=5)
        tk.Label(frame_order, text="Цена ($):", fg="white", bg="#130b1e").grid(row=0, column=2)
        self.ent_sell_price = tk.Entry(frame_order, bg="#21153b", fg="white", width=12)
        self.ent_sell_price.grid(row=0, column=3, padx=5)
        tk.Button(frame_order, text="Выставить ордер", bg="#00e5ff", fg="#130b1e", command=self.create_sell_order).grid(row=0, column=4, padx=10)

        self.order_box = tk.Listbox(self.tab_market, bg="#0c0714", fg="#00e676", font=("Courier", 10), height=12)
        self.order_box.pack(fill='both', expand=True, padx=20, pady=5)
        self.order_box.bind('<Double-1>', self.buy_order_action)

        self.start_update_thread()

    def start_update_thread(self):
        def loop():
            while True:
                try:
                    res = requests.get(f"{NODE_URL}/balance?address={self.my_pub_key_pem}", timeout=2).json()
                    m_data = requests.get(f"{NODE_URL}/market/orders", timeout=2).json()
                    self.lbl_balance.config(text=f"{res['balance']:.2f} VIV")
                    self.lbl_diff.config(text=f"Текущая сложность сети: {m_data['difficulty']} нулей (Защита от инфляции)")
                    
                    self.order_box.delete(0, tk.END)
                    for o in m_data['orders']:
                        self.order_box.insert(tk.END, f"Ордер ID: {o['id']} | Продавец: {o['seller'][:12]}... | Сумма: {o['amount']} VIV | Цена: ${o['price']}")
                except: pass
                time.sleep(3)
        threading.Thread(target=loop, daemon=True).start()

    def start_mine_thread(self):
        self.btn_mine.config(text="⚙️ АКТИВНЫЙ МАЙНИНГ В ФОНЕ...", state="disabled", bg="#424242")
        threading.Thread(target=self.mine_proof_of_work, daemon=True).start()

    def mine_proof_of_work(self):
        try:
            latest = requests.get(f"{NODE_URL}/chain/latest", timeout=3).json()
            m_data = requests.get(f"{NODE_URL}/market/orders", timeout=3).json()
            diff = m_data['difficulty']
            target = "0" * diff
            latest_hash, new_idx, timestamp, nonce = latest['hash'], latest['index'] + 1, time.time(), 0
            
            block_template = {"index": new_idx, "transactions": [{"sender": "Network_Reward", "recipient": self.my_pub_key_pem, "amount": 50.0}], "previous_hash": latest_hash, "timestamp": timestamp}
            while True:
                block_template["nonce"] = nonce
                block_str = json.dumps(block_template, sort_keys=True).encode()
                block_hash = hashlib.sha256(block_str).hexdigest()
                if block_hash[:diff] == target: break
                nonce += 1

            payload = {"miner_address": self.my_pub_key_pem, "nonce": nonce, "hash": block_hash, "timestamp": timestamp, "transactions": []}
            server_res = requests.post(f"{NODE_URL}/mine", json=payload, timeout=3).json()
            if server_res.get("status") == "accepted":
                messagebox.showinfo("Майнинг", "🎉 Блок успешно принят сетью!")
            else:
                messagebox.showerror("Отказ", server_res.get('message'))
        except Exception as e:
            messagebox.showerror("Ошибка сети", str(e))
        self.btn_mine.config(text="⛏️ ЗАПУСТИТЬ СЛОЖНЫЙ МАЙНИНГ (Proof-of-Work)", state="normal", bg="#e91e63")

    def create_sell_order(self):
        try:
            order_data = {"seller": self.my_pub_key_pem, "amount": float(self.ent_sell_amt.get()), "price": float(self.ent_sell_price.get())}
            key = RSA.import_key(self.my_priv_key_pem)
            h = SHA256.new(json.dumps(order_data, sort_keys=True).encode())
            order_data["signature"] = pss.new(key).sign(h).hex()
            requests.post(f"{NODE_URL}/market/sell", json=order_data, timeout=3)
        except Exception as e: messagebox.showerror("Ошибка", str(e))

    def buy_order_action(self, event):
        selection = self.order_box.curselection()
        if not selection: return
        order_id = int(self.order_box.get(selection).split("ID: ")[1].split(" |")[0])
        if messagebox.askyesno("Биржа", f"Купить Ордер #{order_id}?"):
            try:
                buy_data = {"buyer": self.my_pub_key_pem, "order_id": order_id}
                key = RSA.import_key(self.my_priv_key_pem)
                h = SHA256.new(json.dumps(buy_data, sort_keys=True).encode())
                buy_data["signature"] = pss.new(key).sign(h).hex()
                res = requests.post(f"{NODE_URL}/market/buy", json=buy_data, timeout=3).json()
                messagebox.showinfo("Биржа", res.get('message', res.get('error')))
            except Exception as e: messagebox.showerror("Ошибка", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = VividaSecureWallet(root)
    root.mainloop()

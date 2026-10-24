import hashlib
import json
import time
import sqlite3
from flask import Flask, jsonify, request
from Crypto.PublicKey import RSA
from Crypto.Signature import pss
from Crypto.Hash import SHA256

app = Flask(__name__)
DB_FILE = "vivida.db"

INITIAL_REWARD = 50.0
HALVING_INTERVAL = 210000  
TARGET_BLOCK_TIME = 30.0   

def auto_init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS blocks 
                          (idx INTEGER PRIMARY KEY, prev_hash TEXT, block_hash TEXT, timestamp REAL, nonce INTEGER, tx_json TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, seller TEXT, amount REAL, price REAL)''')
        conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM blocks")
        if cursor.fetchone() == 0:
            genesis_hash = hashlib.sha256(b"vivida_genesis").hexdigest()
            cursor.execute("INSERT INTO blocks VALUES (0, '0', ?, ?, 0, '[]')", (genesis_hash, time.time()))
            conn.commit()

auto_init_db()

class BlockchainBackend:
    @staticmethod
    def get_latest_block():
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT idx, block_hash, timestamp, tx_json FROM blocks ORDER BY idx DESC LIMIT 1")
            row = cursor.fetchone()
            if row is None:
                genesis_hash = hashlib.sha256(b"vivida_genesis").hexdigest()
                return (0, genesis_hash, time.time(), "[]")
            return row

    @staticmethod
    def calculate_current_reward(block_index, time_diff):
        halvings = block_index // HALVING_INTERVAL
        reward = INITIAL_REWARD / (2 ** halvings)
        if time_diff < TARGET_BLOCK_TIME:
            factor = max(0.1, time_diff / TARGET_BLOCK_TIME)
            reward = reward * factor
        return round(reward, 4)

    @staticmethod
    def get_difficulty():
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM blocks")
            count = cursor.fetchone()
            if count > 100: return 6
            return 5 

    @staticmethod
    def get_balance(address):
        balance = 0.0
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tx_json FROM blocks")
            blocks = cursor.fetchall()
            for row in blocks:
                txs = json.loads(row)
                for tx in txs:
                    if tx.get('sender') == address: balance -= float(tx['amount'])
                    if tx.get('recipient') == address: balance += float(tx['amount'])
        return balance

    @staticmethod
    def verify_tx_signature(sender_pem, data_dict, sig_hex):
        try:
            key = RSA.import_key(bytes.fromhex(sender_pem))
            msg = json.dumps(data_dict, sort_keys=True).encode()
            h = SHA256.new(msg)
            pss.new(key).verify(h, bytes.fromhex(sig_hex))
            return True
        except Exception:
            return False

@app.route('/balance', methods=['GET'])
def get_balance():
    addr = request.args.get('address')
    if not addr: return jsonify({"error": "Missing address"}), 400
    return jsonify({"balance": BlockchainBackend.get_balance(addr)})

@app.route('/mine', methods=['POST'])
def mine_block():
    values = request.get_json()
    miner_addr = values.get('miner_address')
    nonce = int(values.get('nonce', 0))
    block_hash = values.get('hash')
    timestamp = float(values.get('timestamp', time.time()))
    txs_list = values.get('transactions', [])

    if not miner_addr or not block_hash: return jsonify({"error": "Invalid data"}), 400

    latest_block = BlockchainBackend.get_latest_block()
    latest_idx, latest_hash, latest_timestamp, _ = latest_block
    new_idx = latest_idx + 1

    time_diff = max(1.0, timestamp - latest_timestamp)
    dynamic_reward = BlockchainBackend.calculate_current_reward(new_idx, time_diff)

    difficulty = BlockchainBackend.get_difficulty()
    if block_hash[:difficulty] != "0" * difficulty:
        return jsonify({"status": "rejected", "message": "Слабый Proof of Work!"}), 400

    reward_tx = {"sender": "Network_Reward", "recipient": miner_addr, "amount": dynamic_reward}
    full_txs = txs_list + [reward_tx]

    block_template = {"index": new_idx, "transactions": full_txs, "previous_hash": latest_hash, "timestamp": timestamp, "nonce": nonce}
    calc_str = json.dumps(block_template, sort_keys=True).encode()
    if hashlib.sha256(calc_str).hexdigest() != block_hash:
        return jsonify({"status": "rejected", "message": "Фальсификация структуры блока!"}), 400

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO blocks (idx, prev_hash, block_hash, timestamp, nonce, tx_json) VALUES (?, ?, ?, ?, ?, ?)",
                       (new_idx, latest_hash, block_hash, timestamp, nonce, json.dumps(full_txs)))
        conn.commit()

    return jsonify({"status": "accepted", "message": f"Блок #{new_idx} добавлен. Награда: {dynamic_reward} VIV!"})

@app.route('/market/sell', methods=['POST'])
def place_order():
    values = request.get_json()
    seller = values.get('seller')
    amount = float(values.get('amount', 0))
    price = float(values.get('price', 0))
    sig = values.get('signature')

    if BlockchainBackend.get_balance(seller) < amount:
        return jsonify({"error": "Недостаточно VIV"}), 400

    order_data = {"seller": seller, "amount": amount, "price": price}
    if not BlockchainBackend.verify_tx_signature(seller, order_data, sig):
        return jsonify({"error": "Подпись не валидна"}), 400

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (seller, amount, price) VALUES (?, ?, ?)", (seller, amount, price))
        conn.commit()
    return jsonify({"message": "Ордер выставлен!"})

@app.route('/market/orders', methods=['GET'])
def get_orders():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, seller, amount, price FROM orders")
        rows = cursor.fetchall()
        orders = [{"id": r[0], "seller": r[1], "amount": r[2], "price": r[3]} for r in rows]
    return jsonify({"orders": orders, "difficulty": BlockchainBackend.get_difficulty()})

@app.route('/chain/latest', methods=['GET'])
def get_latest():
    latest = BlockchainBackend.get_latest_block()
    return jsonify({"index": latest[0], "hash": latest[1]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

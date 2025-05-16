from flask import Flask, jsonify, request
from threading import Thread
import json
import os

app = Flask(__name__)

DATA_FILE = 'data.json'

# ============ UTILS DE BASE ============

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "alerts": {},
        "tracked_cryptos": {},
        "user_verified": []
    }

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

# ============ ROUTES ============

@app.route('/')
def home():
    return "✅ API TrackBot en ligne."

@app.route('/api/user/<int:user_id>', methods=['GET'])
def get_user_data(user_id):
    data = load_data()
    uid = str(user_id)
    return jsonify({
        "alerts": data.get("alerts", {}).get(uid, {}),
        "tracked_cryptos": data.get("tracked_cryptos", {}).get(uid, []),
        "verified": uid in data.get("user_verified", [])
    })

@app.route('/api/user/<int:user_id>/alerts', methods=['POST'])
def update_user_alerts(user_id):
    body = request.json
    data = load_data()
    uid = str(user_id)
    data["alerts"][uid] = body
    save_data(data)
    return jsonify({"success": True, "message": "Alertes mises à jour."})

@app.route('/api/user/<int:user_id>/cryptos', methods=['POST'])
def update_user_cryptos(user_id):
    body = request.json  # attend une liste ["btc", "eth"]
    if not isinstance(body, list):
        return jsonify({"success": False, "error": "Format attendu: liste de cryptos"}), 400

    data = load_data()
    uid = str(user_id)
    data["tracked_cryptos"][uid] = body
    save_data(data)
    return jsonify({"success": True, "message": "Cryptos mises à jour."})

@app.route('/api/user/<int:user_id>/verify', methods=['POST'])
def verify_user(user_id):
    data = load_data()
    uid = str(user_id)
    if uid not in data["user_verified"]:
        data["user_verified"].append(uid)
    save_data(data)
    return jsonify({"success": True, "message": "Utilisateur vérifié."})

# ============ THREAD KEEP ALIVE ============

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

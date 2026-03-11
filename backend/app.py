"""
app.py — Flask + Socket.IO backend entry point.
"""
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from network_manager import NetworkManager
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from network_manager import NetworkManager

app = Flask(__name__)
app.config["SECRET_KEY"] = "blockchain-secret-2026"
CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
)

manager = NetworkManager()

def _emit(event, payload):
    socketio.emit(event, payload, namespace="/")

manager.emit_cb = _emit

@socketio.on("connect")
def on_connect():
    print(f"[WS] Client connected: {request.sid}")
    state = manager.get_network_state()
    emit("graph_update",  {"nodes": state["nodes"], "edges": state["edges"]})
    emit("stats_update",  {
        "block_count":       state["block_count"],
        "tx_rate":           state["tx_rate"],
        "attack_active":     state["attack_active"],
        "compromised_nodes": state["compromised_nodes"],
    })
    emit("phase_change", {"phase": manager._phase})

@socketio.on("disconnect")
def on_disconnect():
    print(f"[WS] Disconnected: {request.sid}")

@socketio.on("request_state")
def on_request_state():
    state = manager.get_network_state()
    emit("graph_update",  {"nodes": state["nodes"], "edges": state["edges"]})
    emit("stats_update",  {
        "block_count":       state["block_count"],
        "tx_rate":           state["tx_rate"],
        "attack_active":     state["attack_active"],
        "compromised_nodes": state["compromised_nodes"],
    })
    emit("phase_change", {"phase": manager._phase})

@app.route("/api/attack", methods=["POST"])
def api_attack():
    data        = request.get_json(force=True)
    attack_type = data.get("type", "byzantine")
    target_id   = data.get("target", "")
    if not target_id:
        import random
        healthy = [nid for nid, n in manager.nodes.items() if n.status == "healthy"]
        if not healthy:
            return jsonify({"error": "No healthy nodes"}), 400
        target_id = random.choice(healthy)
    return jsonify(manager.trigger_attack(attack_type, target_id))

@app.route("/api/heal",   methods=["POST"])
def api_heal():
    return jsonify(manager.trigger_heal())

@app.route("/api/reset",  methods=["POST"])
def api_reset():
    return jsonify(manager.reset_network())

@app.route("/api/pause", methods=["POST"])
def pause_network():
    return jsonify(manager.pause_network())

@app.route("/api/resume", methods=["POST"])
def resume_network():
    return jsonify(manager.resume_network())

@app.route("/api/state",  methods=["GET"])
def api_state():
    return jsonify(manager.get_network_state())

@app.route("/api/metrics", methods=["GET"])
def api_metrics():
    return jsonify(manager.get_metrics())

@app.route("/api/chain/<node_id>", methods=["GET"])
def api_chain(node_id):
    return jsonify(manager.get_chain(node_id))

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    print("Backend starting on http://localhost:5000")
    socketio.run(app, host="127.0.0.1", port=5000,
                 debug=False, allow_unsafe_werkzeug=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "blockchain-secret-2026"

CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
)

# ── Network manager — emits via socketio ──────────────────────────────────────
manager = NetworkManager()

def _emit(event: str, payload: dict):
    socketio.emit(event, payload, namespace="/")

manager.emit_cb = _emit

# ── Socket events ─────────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    print(f"[WS] Client connected: {request.sid}")
    state = manager.get_network_state()
    emit("graph_update",  {"nodes": state["nodes"], "edges": state["edges"]})
    emit("stats_update",  {
        "block_count":       state["block_count"],
        "tx_rate":           state["tx_rate"],
        "attack_active":     state["attack_active"],
        "compromised_nodes": state["compromised_nodes"],
    })
    emit("phase_change", {"phase": manager._phase})

@socketio.on("disconnect")
def on_disconnect():
    print(f"[WS] Client disconnected: {request.sid}")

@socketio.on("request_state")
def on_request_state():
    state = manager.get_network_state()
    emit("graph_update",  {"nodes": state["nodes"], "edges": state["edges"]})
    emit("stats_update",  {
        "block_count":       state["block_count"],
        "tx_rate":           state["tx_rate"],
        "attack_active":     state["attack_active"],
        "compromised_nodes": state["compromised_nodes"],
    })
    emit("phase_change", {"phase": manager._phase})

# ── REST API ──────────────────────────────────────────────────────────────────
@app.route("/api/attack", methods=["POST"])
def api_attack():
    data        = request.get_json(force=True)
    attack_type = data.get("type", "sybil")
    target_id   = data.get("target", "")
    if not target_id:
        healthy = [nid for nid, n in manager.nodes.items() if n.status == "healthy"]
        if not healthy:
            return jsonify({"error": "No healthy nodes"}), 400
        import random
        target_id = random.choice(healthy)
    result = manager.trigger_attack(attack_type, target_id)
    return jsonify(result)

@app.route("/api/heal", methods=["POST"])
def api_heal():
    return jsonify(manager.trigger_heal())

@app.route("/api/reset", methods=["POST"])
def api_reset():
    return jsonify(manager.reset_network())

@app.route("/api/state", methods=["GET"])
def api_state():
    return jsonify(manager.get_network_state())

@app.route("/api/chain/<node_id>", methods=["GET"])
def api_chain(node_id):
    return jsonify(manager.get_chain(node_id))

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Starting blockchain backend on port 5000...")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
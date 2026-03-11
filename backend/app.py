"""
app.py — Flask + Socket.IO backend entry point.
Compatible with new network_manager.py (v3).
"""

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from network_manager import NetworkManager
import random

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

# ── Emit function passed into NetworkManager ──────────────────────────────────
# This is the ONLY change needed: pass _emit as emit_fn at construction time.
def _emit(event: str, payload: dict):
    socketio.emit(event, payload, namespace="/")

manager = NetworkManager(emit_fn=_emit)
manager.start()

# ── Socket events ─────────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    print(f"[WS] Client connected: {request.sid}")
    state = manager.get_state()
    emit("graph_update", {"nodes": state["nodes"], "edges": state["edges"]})
    emit("stats_update", state["stats"])
    emit("phase_change", {"phase": state["phase"]})

@socketio.on("disconnect")
def on_disconnect():
    print(f"[WS] Disconnected: {request.sid}")

@socketio.on("request_state")
def on_request_state():
    state = manager.get_state()
    emit("graph_update", {"nodes": state["nodes"], "edges": state["edges"]})
    emit("stats_update", state["stats"])
    emit("phase_change", {"phase": state["phase"]})

# ── REST API ──────────────────────────────────────────────────────────────────
@app.route("/api/attack", methods=["POST"])
def api_attack():
    data        = request.get_json(force=True)
    attack_type = data.get("type", "byzantine")
    target_id   = data.get("target", "")

    if not target_id:
        healthy = [nid for nid, n in manager.nodes.items() if n.status == "healthy"]
        if not healthy:
            return jsonify({"error": "No healthy nodes"}), 400
        target_id = random.choice(healthy)

    result = manager.launch_attack(attack_type, target_id)
    return jsonify(result)

@app.route("/api/heal", methods=["POST"])
def api_heal():
    return jsonify(manager.heal())

@app.route("/api/reset", methods=["POST"])
def api_reset():
    return jsonify(manager.reset())

@app.route("/api/pause", methods=["POST"])
def api_pause():
    manager.pause()
    return jsonify({"status": "paused"})

@app.route("/api/resume", methods=["POST"])
def api_resume():
    manager.resume()
    return jsonify({"status": "resumed"})

@app.route("/api/state", methods=["GET"])
def api_state():
    return jsonify(manager.get_state())

@app.route("/api/metrics", methods=["GET"])
def api_metrics():
    return jsonify(manager.get_metrics())

@app.route("/api/chain/<node_id>", methods=["GET"])
def api_chain(node_id):
    return jsonify(manager.get_chain(node_id))

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Backend starting on http://localhost:5000")
    socketio.run(
        app,
        host="127.0.0.1",
        port=5000,
        debug=False,
        allow_unsafe_werkzeug=True,
    )
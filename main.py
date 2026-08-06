"""
Servidor local do painel.

Serve o front (dist/) e expõe a varredura de vendas x afiliados. A varredura é
lenta de propósito — tem pausa entre produtos para não acordar o anti-bot — então
ela roda numa thread e o front acompanha por polling, em vez de segurar a
requisição HTTP aberta por minutos.

    python3 main.py     →  http://localhost:10000
"""

import asyncio
import os
import threading
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import affiliate_scan

app = Flask(__name__, static_folder="dist")
CORS(app)

# Jobs em memória. O painel é de uso local e single-user: reiniciar o servidor
# limpa tudo, e é o esperado.
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()

MAX_LINKS = 300


def run_job(job_id: str, entries: list[str], min_sales: int, max_affiliates: int, delay: float):
    def on_result(stats):
        with JOBS_LOCK:
            JOBS[job_id]["results"].append(asdict(stats))
            JOBS[job_id]["done"] += 1

    try:
        asyncio.run(
            affiliate_scan.run(
                entries,
                cookies_path="cookies.json",
                min_sales=min_sales,
                max_affiliates=max_affiliates,
                delay=delay,
                on_result=on_result,
            )
        )
        status, error = "finished", None
    except Exception as e:  # falha global: rede caiu, cookies ilegíveis, etc.
        status, error = "failed", str(e)

    with JOBS_LOCK:
        JOBS[job_id]["status"] = status
        JOBS[job_id]["error"] = error
        JOBS[job_id]["finished_at"] = datetime.now().isoformat(timespec="seconds")


@app.route("/api/status")
def status():
    """Diz ao painel o que já está configurado, para ele avisar antes de varrer."""
    cookies_ok = False
    cookie_names: list[str] = []
    if Path("cookies.json").exists():
        cookies = affiliate_scan.load_cookies("cookies.json")
        cookie_names = sorted(cookies)
        cookies_ok = "SPC_U" in cookies or "SPC_EC" in cookies

    return jsonify(
        {
            "cookies_present": Path("cookies.json").exists(),
            "cookies_ok": cookies_ok,
            "cookie_names": cookie_names,
            "endpoint_configured": Path(affiliate_scan.ENDPOINTS_FILE).exists(),
        }
    )


@app.route("/api/scan", methods=["POST"])
def scan():
    """Inicia uma varredura. Aceita um link ou uma lista — o fluxo é o mesmo."""
    data = request.get_json(silent=True) or {}
    raw = data.get("links", "")

    if isinstance(raw, str):
        entries = [line.strip() for line in raw.splitlines() if line.strip()]
    else:
        entries = [str(x).strip() for x in raw if str(x).strip()]

    entries = [e for e in entries if not e.startswith("#")]

    if not entries:
        return jsonify({"error": "Nenhum link informado"}), 400
    if len(entries) > MAX_LINKS:
        return jsonify({"error": f"Máximo de {MAX_LINKS} links por varredura"}), 400

    try:
        min_sales = int(data.get("min_sales", 100))
        max_affiliates = int(data.get("max_affiliates", 50))
        delay = float(data.get("delay", 2.0))
    except (TypeError, ValueError):
        return jsonify({"error": "Parâmetros numéricos inválidos"}), 400

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "total": len(entries),
            "done": 0,
            "results": [],
            "error": None,
            "min_sales": min_sales,
            "max_affiliates": max_affiliates,
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }

    threading.Thread(
        target=run_job,
        args=(job_id, entries, min_sales, max_affiliates, delay),
        daemon=True,
    ).start()

    # Estimativa grosseira: ~1,5s de rede por produto, mais a pausa anti-bot.
    return jsonify(
        {
            "job_id": job_id,
            "total": len(entries),
            "eta_seconds": round(len(entries) * (delay + 1.5)),
        }
    )


@app.route("/api/scan/<job_id>")
def scan_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "Job não encontrado"}), 404
        return jsonify({"job_id": job_id, **job})


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path: str):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    if not os.path.exists(os.path.join(app.static_folder, "index.html")):
        return (
            "Front não compilado. Rode <code>npm install &amp;&amp; npm run build</code>, "
            "ou use <code>npm run dev</code> para desenvolvimento.",
            503,
        )
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"\n  Painel em http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port)

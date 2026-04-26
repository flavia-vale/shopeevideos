import os
from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
import asyncio
import importlib

# Importa o scraper dinamicamente para evitar problemas de loop de evento
scraper = importlib.import_module("scraper")

app = Flask(__name__, static_folder='dist')
CORS(app)

# Rota para servir o frontend React
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

# API para disparar o scraper
@app.route('/api/scan', methods=['POST'])
def scan_product():
    data = request.json
    product_url = data.get('url')
    
    if not product_url:
        return jsonify({"error": "URL não fornecida"}), 400

    # Extrai ID do produto da URL
    import re
    match = re.search(r'i\.(\d+)\.(\d+)', product_url)
    if not match:
        return jsonify({"error": "URL inválida"}), 400
    
    product_id = f"{match.group(1)}/{match.group(2)}"
    
    # Executa o scraper (simplificado para o exemplo)
    try:
        # Nota: Em produção, você usaria uma fila de tarefas (Celery/Redis)
        # Aqui rodamos de forma assíncrona simples para demonstração
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Configurações básicas
        results = loop.run_until_complete(scraper.run(
            ids=[product_id],
            cookies="cookies.json",
            concurrency=1,
            rps=1.0,
            threshold=5,
            headless=True
        ))
        
        if results and len(results) > 0:
            res = results[0]
            return jsonify({
                "id": res.product_id,
                "videos": res.video_count,
                "status": res.status,
                "detail": res.selector_used or res.error
            })
        
        return jsonify({"error": "Nenhum resultado retornado"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
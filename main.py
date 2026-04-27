import os
from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
import asyncio
import importlib
import subprocess

# Importa o scraper dinamicamente para evitar problemas de loop de evento
scraper = importlib.import_module("scraper")

app = Flask(__name__, static_folder='dist')
CORS(app)

@app.route('/api/extract_mitm', methods=['GET'])
def extract_mitm():
    try:
        import re
        def extract_strings(filename, output_filename):
            with open(filename, 'rb') as f:
                data = f.read()
            strings = re.findall(b'[a-zA-Z0-9./?=&_-]{5,}', data)
            with open(output_filename, 'w') as out:
                for s in strings:
                    try:
                        out.write(s.decode('utf-8') + '\n')
                    except:
                        pass
        
        extract_strings('.dyad/media/1f6dd4416d5ad9966f1399c2a2722d0e.mitm', 'strings1.txt')
        extract_strings('.dyad/media/f306333995e49235958be36ecaae81d8.mitm', 'strings2.txt')
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
            cookies_path="cookies.json",
            threshold=5
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
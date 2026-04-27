"""
Shopee Video Counter - v2.0 (API Based)
Conta vídeos usando a API interna do aplicativo Shopee mapeada via proxy.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import httpx

# ── Logging ──────────────────────────────────────────────────────────────────

def setup_logging(debug: bool = False) -> logging.Logger:
    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler("scraper.log", encoding="utf-8"),
        ],
    )
    return logging.getLogger("shopee")

log = logging.getLogger("shopee")

# ── Configurações ────────────────────────────────────────────────────────────

API_URL = "https://sv.shopee.com.br/api/v2/timeline/unify/common"

# User-Agent do aplicativo iOS capturado no proxy
APP_USER_AGENT = "iOS app iPhone Shopee appver=37235 language=pt-BR app_type=1 platform=native_ios os_ver=26.3.1 Cronet/102.0.5005.61"

@dataclass
class ProductResult:
    product_id: str
    video_count: int | None
    status: str = "ok"
    error: str | None = None
    elapsed_s: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

def load_cookies(path: str) -> dict:
    if not os.path.exists(path):
        log.warning("Arquivo de cookies %s não encontrado.", path)
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "cookies" in data:
            data = data["cookies"]
        return {c["name"]: c["value"] for c in data}
    except Exception as e:
        log.error("Erro ao carregar cookies: %s", e)
        return {}

async def get_video_count_api(shop_id: int, item_id: int, cookies: dict) -> int:
    """Chama a API de timeline para contar os vídeos do produto."""
    
    headers = {
        "User-Agent": APP_USER_AGENT,
        "Content-Type": "application/json",
        "X-CSRFToken": cookies.get("csrftoken", ""),
        "Referer": f"https://shopee.com.br/product/{shop_id}/{item_id}",
        "Origin": "https://shopee.com.br"
    }

    # Payload capturado no proxy
    payload = {
        "limit": 20, # Aumentamos o limite para pegar mais vídeos de uma vez
        "page_context": json.dumps({
            "item_id": item_id,
            "shop_id": shop_id,
            "offset": 0,
            "filter_video": None,
            "template_tab_id": "5", # Aba de criadores
            "order_type": 1
        }),
        "device_id": "204E33D7540D48258995F115C7930559",
        "request_type": 0,
        "ext_info": [],
        "rcmd_source": 22,
        "lang": "pt-BR",
        "rec_request_info": "{\"dayPages\":1,\"sessionPages\":1,\"interactDataFromVideo\":[]}",
        "page_no": 1,
        "need_product_v2": True,
        "product_v2_scene": "affiliate_video_common_timeline",
        "ug_param": "{\"is_merge_reward\":1}"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(API_URL, json=payload, headers=headers, cookies=cookies)
        
        if response.status_code != 200:
            log.error("Erro na API: HTTP %d", response.status_code)
            return 0
            
        data = response.json()
        
        # A API retorna uma lista de 'feed_list' ou similar
        # Precisamos verificar a estrutura exata do retorno
        feed_list = data.get("data", {}).get("feed_list", [])
        
        # Se houver paginação, o total_count pode estar presente
        total_count = data.get("data", {}).get("total_count", len(feed_list))
        
        log.debug("API retornou %d vídeos para o produto %d/%d", total_count, shop_id, item_id)
        return total_count

async def process_product(pid: str, cookies: dict, threshold: int) -> ProductResult:
    t0 = time.monotonic()
    try:
        if "/" in pid:
            shop_id, item_id = map(int, pid.split("/", 1))
        else:
            # Tenta extrair de URL se for o caso
            match = re.search(r'i\.(\d+)\.(\d+)', pid)
            if match:
                shop_id, item_id = int(match.group(1)), int(match.group(2))
            else:
                return ProductResult(pid, None, "error", "ID inválido", elapsed_s=round(time.monotonic()-t0, 2))

        count = await get_video_count_api(shop_id, item_id, cookies)
        
        status = "blue_ocean" if count < threshold else "competed"
        return ProductResult(pid, count, status, elapsed_s=round(time.monotonic()-t0, 2))
        
    except Exception as e:
        log.error("Erro ao processar %s: %s", pid, e)
        return ProductResult(pid, None, "error", str(e), elapsed_s=round(time.monotonic()-t0, 2))

async def run(ids: list[str], cookies_path: str, threshold: int) -> list[ProductResult]:
    cookies = load_cookies(cookies_path)
    results = []
    
    for pid in ids:
        res = await process_product(pid, cookies, threshold)
        results.append(res)
        # Pequeno delay para evitar rate limit
        await asyncio.sleep(0.5)
        
    return results

def main():
    p = argparse.ArgumentParser(description="Shopee Video Counter (API)")
    p.add_argument("--products", required=True, help="IDs dos produtos (shop_id/item_id)")
    p.add_argument("--cookies", default="cookies.json", help="Caminho para cookies.json")
    p.add_argument("--threshold", type=int, default=5, help="Limite para Oceano Azul")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()
    
    setup_logging(args.debug)
    ids = [x.strip() for x in args.products.split(",")]
    
    log.info("Iniciando contagem via API para %d produtos...", len(ids))
    results = asyncio.run(run(ids, args.cookies, args.threshold))
    
    print(f"\n{'ID':<25} {'Videos':<10} {'Status'}")
    print("-" * 50)
    for r in results:
        v_str = str(r.video_count) if r.video_count is not None else "N/A"
        print(f"{r.product_id:<25} {v_str:<10} {r.status}")

if __name__ == "__main__":
    main()

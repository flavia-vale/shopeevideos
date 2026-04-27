"""
Shopee Video Counter - v2.2 (Super Stealth)
Tenta capturar tokens dinamicamente e conta vídeos via API.
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
# User-Agent de um iPhone real para despistar
APP_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Shopee/3.0.1"

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
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, http2=True) as client:
        # PASSO 1: Visitar a página do produto para "esquentar" a sessão e pegar o csrftoken
        product_url = f"https://shopee.com.br/product/{shop_id}/{item_id}"
        log.info(f"Visitando produto para capturar tokens: {shop_id}/{item_id}")
        
        initial_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        
        resp = await client.get(product_url, headers=initial_headers, cookies=cookies)
        
        # Atualiza os cookies com o que o servidor mandou de volta (incluindo o csrftoken)
        current_cookies = dict(client.cookies)
        current_cookies.update(cookies)
        
        csrftoken = current_cookies.get("csrftoken", "")
        if not csrftoken:
            log.warning("csrftoken não encontrado nos cookies. Tentando prosseguir mesmo assim...")

        # PASSO 2: Fazer a chamada da API de vídeos
        headers = {
            "User-Agent": APP_USER_AGENT,
            "Content-Type": "application/json",
            "X-CSRFToken": csrftoken,
            "Referer": product_url,
            "x-requested-from": "rn",
            "x-api-sdk-version": "3.0.1",
            "Origin": "https://shopee.com.br"
        }

        payload = {
            "limit": 20,
            "page_context": json.dumps({
                "item_id": item_id,
                "shop_id": shop_id,
                "offset": 0,
                "template_tab_id": "5",
                "order_type": 1
            }),
            "request_type": 0,
            "lang": "pt-BR",
            "page_no": 1,
            "need_product_v2": True,
            "product_v2_scene": "affiliate_video_common_timeline"
        }

        response = await client.post(API_URL, json=payload, headers=headers, cookies=current_cookies)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("data", {}).get("total_count", 0)
        elif response.status_code == 418:
            log.error("Bloqueio 418: Anti-bot detectado. Tente renovar os cookies no navegador.")
            return -1
        else:
            log.error("Erro API: %d - %s", response.status_code, response.text)
            return 0

async def process_product(pid: str, cookies: dict, threshold: int) -> ProductResult:
    t0 = time.monotonic()
    try:
        if "/" in pid:
            shop_id, item_id = map(int, pid.split("/", 1))
        else:
            match = re.search(r'i\.(\d+)\.(\d+)', pid)
            if match:
                shop_id, item_id = int(match.group(1)), int(match.group(2))
            else:
                return ProductResult(pid, None, "error", "ID inválido")

        count = await get_video_count_api(shop_id, item_id, cookies)
        
        if count == -1:
            return ProductResult(pid, None, "expired", "Bloqueio 418 - Anti-bot")
            
        status = "blue_ocean" if count < threshold else "competed"
        return ProductResult(pid, count, status, elapsed_s=round(time.monotonic()-t0, 2))
        
    except Exception as e:
        log.exception("Erro ao processar produto")
        return ProductResult(pid, None, "error", str(e))

async def run(ids: list[str], cookies_path: str, threshold: int) -> list[ProductResult]:
    cookies = load_cookies(cookies_path)
    results = []
    for pid in ids:
        res = await process_product(pid, cookies, threshold)
        results.append(res)
        # Delay maior entre produtos para evitar detecção
        await asyncio.sleep(2.0)
    return results

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--products", required=True)
    p.add_argument("--cookies", default="cookies.json")
    p.add_argument("--threshold", type=int, default=5)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()
    
    setup_logging(args.debug)
    ids = [x.strip() for x in args.products.split(",")]
    results = asyncio.run(run(ids, args.cookies, args.threshold))
    
    print(f"\n{'ID':<25} {'Videos':<10} {'Status'}")
    print("-" * 50)
    for r in results:
        v_str = str(r.video_count) if r.video_count is not None else "N/A"
        print(f"{r.product_id:<25} {v_str:<10} {r.status}")

if __name__ == "__main__":
    main()
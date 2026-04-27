"""
Diagnose API — v3.2
Tenta capturar o csrftoken e testa APIs alternativas (App vs Web).
"""

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
import httpx

API_URL_APP = "https://sv.shopee.com.br/api/v2/timeline/unify/common"
API_URL_WEB = "https://shopee.com.br/api/v4/item/get" # API de detalhes do produto
APP_USER_AGENT = "iOS app iPhone Shopee appver=37235 language=pt-BR app_type=1 platform=native_ios os_ver=26.3.1 Cronet/102.0.5005.61"

def load_cookies(path: str) -> dict:
    if not os.path.exists(path): return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "cookies" in data: data = data["cookies"]
        return {c["name"]: c["value"] for c in data}
    except: return {}

async def diagnose_api(product_id: str, cookies_path: str):
    if "/" in product_id:
        shop_id, item_id = map(int, product_id.split("/", 1))
    else:
        print("Erro: Use o formato shop_id/item_id")
        return

    cookies = load_cookies(cookies_path)
    
    # Tenta pegar o csrftoken se ele existir
    csrftoken = cookies.get("csrftoken", "")
    
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        # PASSO 1: Tentar obter um csrftoken novo se estiver faltando
        if not csrftoken:
            print("[!] csrftoken ausente. Tentando obter um visitando a home...")
            resp = await client.get("https://shopee.com.br", cookies=cookies)
            csrftoken = resp.cookies.get("csrftoken", "")
            if csrftoken:
                print(f"[+] Token obtido com sucesso: {csrftoken[:10]}...")
                cookies["csrftoken"] = csrftoken
            else:
                print("[!] Não foi possível obter o csrftoken automaticamente.")

        # PASSO 2: Testar API do App (a que conta vídeos)
        print(f"\n[1] Testando API do APP (Contagem de Vídeos)...")
        headers_app = {
            "User-Agent": APP_USER_AGENT,
            "Content-Type": "application/json",
            "X-CSRFToken": csrftoken,
            "Referer": f"https://shopee.com.br/product/{shop_id}/{item_id}",
            "x-requested-from": "rn",
        }
        payload = {
            "limit": 5,
            "page_context": json.dumps({"item_id": item_id, "shop_id": shop_id, "template_tab_id": "5"}),
            "request_type": 0,
            "need_product_v2": True,
            "product_v2_scene": "affiliate_video_common_timeline"
        }

        try:
            res = await client.post(API_URL_APP, json=payload, headers=headers_app, cookies=cookies)
            print(f"Status App API: {res.status_code}")
            if res.status_code == 200:
                total = res.json().get("data", {}).get("total_count", 0)
                print(f"✅ SUCESSO! Vídeos encontrados: {total}")
            elif res.status_code == 418:
                print("❌ Bloqueio 418 (Anti-bot).")
        except Exception as e:
            print(f"Erro na API do App: {e}")

        # PASSO 3: Testar API de Web (apenas para ver se a sessão está viva)
        print(f"\n[2] Testando API de WEB (Sessão Geral)...")
        try:
            res_web = await client.get(f"{API_URL_WEB}?itemid={item_id}&shopid={shop_id}", cookies=cookies)
            print(f"Status Web API: {res_web.status_code}")
            if res_web.status_code == 200:
                print("✅ Sua sessão (cookies) está ATIVA e funcionando para a Web.")
            else:
                print("❌ Seus cookies podem estar expirados ou inválidos.")
        except Exception as e:
            print(f"Erro na API de Web: {e}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--product", required=True)
    p.add_argument("--cookies", default="cookies.json")
    args = p.parse_args()
    asyncio.run(diagnose_api(args.product, args.cookies))

if __name__ == "__main__":
    main()
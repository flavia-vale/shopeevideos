"""
Diagnose API — v3.0
Valida a chamada de API interna da Shopee.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import httpx

API_URL = "https://sv.shopee.com.br/api/v2/timeline/unify/common"
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
    
    headers = {
        "User-Agent": APP_USER_AGENT,
        "Content-Type": "application/json",
        "X-CSRFToken": cookies.get("csrftoken", ""),
        "Referer": f"https://shopee.com.br/product/{shop_id}/{item_id}",
    }

    payload = {
        "limit": 10,
        "page_context": json.dumps({
            "item_id": item_id,
            "shop_id": shop_id,
            "offset": 0,
            "template_tab_id": "5",
            "order_type": 1
        }),
        "device_id": "204E33D7540D48258995F115C7930559",
        "request_type": 0,
        "lang": "pt-BR",
        "page_no": 1,
        "need_product_v2": True,
        "product_v2_scene": "affiliate_video_common_timeline"
    }

    print(f"\n[1] Testando API para o produto {shop_id}/{item_id}...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(API_URL, json=payload, headers=headers, cookies=cookies)
            print(f"[2] Status da Resposta: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("[3] Resposta JSON recebida com sucesso.")
                
                # Analisa a estrutura
                res_data = data.get("data", {})
                feed_list = res_data.get("feed_list", [])
                total_count = res_data.get("total_count", len(feed_list))
                
                print(f"\n--- RESULTADO ---")
                print(f"Total de vídeos (total_count): {total_count}")
                print(f"Vídeos na primeira página: {len(feed_list)}")
                
                if len(feed_list) > 0:
                    print("\nExemplo de vídeo encontrado:")
                    video = feed_list[0]
                    print(f"  - ID: {video.get('id')}")
                    print(f"  - Título: {video.get('title')}")
                else:
                    print("\nNenhum vídeo encontrado na lista.")
                    if total_count == 0:
                        print("Isso confirma que o produto não tem vídeos de criadores.")
            else:
                print(f"Erro: {response.text}")
                
        except Exception as e:
            print(f"Erro na requisição: {e}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--product", required=True)
    p.add_argument("--cookies", default="cookies.json")
    args = p.parse_args()
    asyncio.run(diagnose_api(args.product, args.cookies))

if __name__ == "__main__":
    main()

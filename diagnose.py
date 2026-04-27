"""
Diagnose API — v3.1
Valida a chamada de API interna da Shopee com tratamento de erro 418.
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
    if not os.path.exists(path): 
        print(f"Erro: Arquivo {path} não encontrado.")
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "cookies" in data: data = data["cookies"]
        cookie_dict = {c["name"]: c["value"] for c in data}
        print(f"Cookies carregados: {list(cookie_dict.keys())}")
        return cookie_dict
    except Exception as e:
        print(f"Erro ao ler cookies: {e}")
        return {}

async def diagnose_api(product_id: str, cookies_path: str):
    if "/" in product_id:
        shop_id, item_id = map(int, product_id.split("/", 1))
    else:
        print("Erro: Use o formato shop_id/item_id")
        return

    cookies = load_cookies(cookies_path)
    csrftoken = cookies.get("csrftoken", "")
    
    if not csrftoken:
        print("AVISO: 'csrftoken' não encontrado nos cookies. Isso pode causar erro 418.")

    headers = {
        "User-Agent": APP_USER_AGENT,
        "Content-Type": "application/json",
        "X-CSRFToken": csrftoken,
        "Referer": f"https://shopee.com.br/product/{shop_id}/{item_id}",
        "x-requested-from": "rn",
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
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.post(API_URL, json=payload, headers=headers, cookies=cookies)
            print(f"[2] Status da Resposta: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                res_data = data.get("data", {})
                total_count = res_data.get("total_count", 0)
                print(f"\n--- SUCESSO! ---")
                print(f"Total de vídeos: {total_count}")
            elif response.status_code == 418:
                print("\n--- BLOQUEIO DETECTADO (418) ---")
                print("A Shopee bloqueou a requisição.")
                print("Tente o seguinte:")
                print("1. Abra o site da Shopee no seu navegador e faça um scroll na página de qualquer produto.")
                print("2. Exporte os cookies novamente para o arquivo cookies.json.")
                print("3. Verifique se o cookie 'csrftoken' está presente.")
            else:
                print(f"Erro inesperado: {response.text}")
                
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
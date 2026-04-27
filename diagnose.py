"""
Diagnose — v2.0
Agora com captura de tela para depuração visual.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright


SHOPEE_BASE = "https://shopee.com.br"

def _normalize_cookie(c: dict) -> dict:
    VALID_SAME_SITE = {"Strict", "Lax", "None"}
    same_site = c.get("sameSite")
    if same_site not in VALID_SAME_SITE:
        same_site = "None"
    normalized: dict = {
        "name":     c["name"],
        "value":    c["value"],
        "domain":   c.get("domain", ""),
        "path":     c.get("path", "/"),
        "secure":   bool(c.get("secure", False)),
        "httpOnly": bool(c.get("httpOnly", False)),
        "sameSite": same_site,
    }
    expires = c.get("expires") or c.get("expirationDate")
    if expires is not None:
        normalized["expires"] = int(expires)
    return normalized

async def diagnose(product_id: str, cookies_path: str, headless: bool) -> None:
    url = f"{SHOPEE_BASE}/product/{product_id}"
    timestamp = datetime.now().strftime("%H%M%S")
    screenshot_path = f"debug_shopee_{timestamp}.png"

    async with async_playwright() as pw:
        print(f"\n[1] Iniciando navegador (Headless: {headless})...")
        browser = await pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
        
        # Testando com User Agent de Desktop para ver se a aba aparece melhor
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="pt-BR"
        )

        if os.path.exists(cookies_path):
            print(f"[2] Carregando cookies de {cookies_path}...")
            try:
                raw = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "cookies" in raw: raw = raw["cookies"]
                await context.add_cookies([_normalize_cookie(c) for c in raw])
                print("    Cookies injetados com sucesso.")
            except Exception as e:
                print(f"    Erro ao carregar cookies: {e}")
        else:
            print(f"[!] AVISO: Arquivo {cookies_path} não encontrado. Rodando sem login.")

        page = await context.new_page()
        print(f"[3] Navegando para: {url}")
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            # Espera um pouco mais para o conteúdo dinâmico
            await page.wait_for_timeout(8000)
        except Exception as e:
            print(f"    Erro na navegação: {e}")

        print(f"    Título: {await page.title()}")
        
        # Tira o print da tela
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"\n[4] SCREENSHOT SALVA: {screenshot_path}")
        print("    Abra esse arquivo na sua pasta para ver o que o robô está vendo.")

        # Analisa textos de botões e abas
        print("\n[5] Analisando botões e textos na página:")
        elements = await page.query_selector_all("button, span, div[role='tab']")
        found_creators = False
        for el in elements:
            try:
                txt = (await el.inner_text()).strip()
                if txt and len(txt) < 50:
                    if "criador" in txt.lower() or "video" in txt.lower() or "aprender" in txt.lower():
                        print(f"    -> ENCONTRADO: '{txt}'")
                        found_creators = True
            except: pass
        
        if not found_creators:
            print("    Nenhuma aba de vídeos/criadores detectada no texto da página.")

        if not headless:
            print("\nNavegador aberto. Verifique a tela e feche quando terminar.")
            while browser.is_connected():
                await asyncio.sleep(1)
        else:
            await browser.close()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--product", required=True)
    p.add_argument("--cookies", default="cookies.json")
    p.add_argument("--no-headless", action="store_true")
    args = p.parse_args()
    asyncio.run(diagnose(args.product, args.cookies, not args.no_headless))

if __name__ == "__main__":
    main()
"""
Diagnose — v2.3
Busca exaustiva por abas e rolagem de página.
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
    
    async with async_playwright() as pw:
        print(f"\n[1] Iniciando navegador...")
        browser = await pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 1000},
            locale="pt-BR"
        )

        if os.path.exists(cookies_path):
            try:
                raw = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "cookies" in raw: raw = raw["cookies"]
                await context.add_cookies([_normalize_cookie(c) for c in raw])
                print("[2] Cookies injetados.")
            except: pass

        page = await context.new_page()
        print(f"[3] Navegando para: {url}")
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(5000)

        # Tenta limpar a tela clicando no fundo
        await page.mouse.click(10, 10)
        
        print("[4] Rolando a página para carregar seções ocultas...")
        for i in range(3):
            await page.evaluate("window.scrollBy(0, 600)")
            await page.wait_for_timeout(1500)

        # Tira print da parte do meio da página
        screenshot_path = f"debug_scroll_{timestamp}.png"
        await page.screenshot(path=screenshot_path)
        print(f"[5] SCREENSHOT DA SEÇÃO MÉDIA: {screenshot_path}")

        print("\n[6] Analisando elementos de texto (Abas em potencial):")
        # Procura por textos que contenham palavras-chave
        keywords = ["criador", "video", "aprender", "inspira", "ver"]
        
        elements = await page.query_selector_all("button, span, div[role='tab']")
        found_count = 0
        for el in elements:
            try:
                text = (await el.inner_text()).strip()
                if text and len(text) < 50: # Ignora textos muito longos
                    is_match = any(k in text.lower() for k in keywords)
                    if is_match:
                        print(f"    -> ENCONTRADO: '{text}'")
                        found_count += 1
            except: pass
        
        if found_count == 0:
            print("    Nenhuma aba óbvia encontrada. Listando os primeiros 10 botões da página para debug:")
            for el in elements[:10]:
                try: print(f"       - {await el.inner_text()}")
                except: pass

        if not headless:
            print("\nVerifique o navegador e feche para terminar.")
            while browser.is_connected(): await asyncio.sleep(1)
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
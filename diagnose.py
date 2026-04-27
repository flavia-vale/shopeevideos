"""
Diagnose — v2.1
Agora com fechamento automático de modal de idioma.
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
        print(f"\n[1] Iniciando navegador...")
        browser = await pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
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
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Tenta fechar o modal de idioma
        print("[4] Verificando modais de bloqueio...")
        lang_button = page.get_by_role("button", name="Português (BR)").or_(page.get_by_text("Português (BR)")).first
        if await lang_button.is_visible(timeout=3000):
            print("    -> Modal de idioma detectado! Clicando para fechar...")
            await lang_button.click()
            await page.wait_for_timeout(2000)
        else:
            print("    -> Nenhum modal de idioma visível.")

        # Tira novo print após tentar fechar o modal
        await page.screenshot(path=screenshot_path)
        print(f"[5] SCREENSHOT ATUALIZADA: {screenshot_path}")

        # Procura a aba
        print("\n[6] Procurando abas de vídeos:")
        tabs = await page.query_selector_all("button, span, div[role='tab']")
        for t in tabs:
            txt = (await t.inner_text()).strip()
            if txt and any(x in txt.lower() for x in ["criador", "video", "aprender"]):
                print(f"    -> ENCONTRADA: '{txt}'")

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
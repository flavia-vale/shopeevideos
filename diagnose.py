"""
Diagnose — valida seletores CSS e Shadow DOM em uma página de produto real.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

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

PROBE_SELECTORS = [
    "[data-sqe='video-item']",
    "[data-testid='video-item']",
    "._3X5KM",
    ".creator-video-item",
    "div[class*='VideoCard']",
    "div[class*='video-card']",
    "div[class*='video'] div[class*='item']",
    "[role='tab']",
    "div[class*='tab'] span",
    "li[class*='tab'] span",
    "button",
    "a"
]

async def diagnose(product_id: str, cookies_path: str, headless: bool) -> None:
    url = f"{SHOPEE_BASE}/product/{product_id}" if "/" in product_id else f"{SHOPEE_BASE}/product/{product_id}"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="pt-BR"
        )

        if os.path.exists(cookies_path):
            raw = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "cookies" in raw: raw = raw["cookies"]
            await context.add_cookies([_normalize_cookie(c) for c in raw])

        page = await context.new_page()
        print(f"\n[1] Abrindo {url}...")
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60_000)
        except Exception as e:
            print(f"    Erro ao carregar: {e}")

        print(f"    URL final: {page.url}")
        print(f"    Título: {await page.title()}")

        # Verifica se há sinais de bloqueio
        content = await page.content()
        if "verify" in content.lower() or "robot" in content.lower() or "captcha" in content.lower():
            print("\n[!] ALERTA: Detectada tela de verificação/captcha!")
            if headless:
                print("    DICA: Rode com --no-headless para resolver o captcha manualmente.")
            else:
                print("    Aguardando você resolver o captcha no navegador...")
                await page.wait_for_timeout(15000)

        print("\n[2] Analisando elementos (aguardando 5s para renderização)...")
        await page.wait_for_timeout(5000)
        
        print(f"    {'Seletor':<45} {'Encontrados':>11}")
        print("    " + "-" * 58)
        for sel in PROBE_SELECTORS:
            try:
                els = await page.query_selector_all(sel)
                found = len(els)
                mark = " <-- ATIVO" if found > 0 else ""
                print(f"    {sel:<45} {found:>11}{mark}")
            except: pass

        print("\n[3] Textos das abas:")
        tabs = await page.query_selector_all("[role='tab'], .shopee-tabs__tab, button")
        for t in tabs:
            txt = (await t.inner_text()).strip()
            if txt:
                mark = " <-- CRIADORES" if "criador" in txt.lower() or "video" in txt.lower() else ""
                print(f"    '{txt}'{mark}")

        print("\nDiagnóstico concluído.")
        if not headless:
            print("Feche a janela do navegador para encerrar.")
            while True:
                if browser.is_connected(): await asyncio.sleep(1)
                else: break
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
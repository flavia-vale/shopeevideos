"""
Diagnose — valida seletores CSS e Shadow DOM em uma página de produto real.

Uso:
    python diagnose.py --product shop_id/item_id --cookies cookies.json
    python diagnose.py --product 1234567890 --cookies cookies.json --no-headless
"""

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


SHOPEE_BASE = "https://shopee.com.br"
CHROMIUM_EXEC = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


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
]

SHADOW_PROBE_JS = """
() => {
    const results = [];
    document.querySelectorAll('*').forEach(el => {
        if (!el.shadowRoot) return;
        const host = el.tagName + (el.id ? '#' + el.id : '') +
                     (el.className && typeof el.className === 'string'
                         ? '.' + el.className.trim().split(/\s+/).join('.')
                         : '');
        const children = el.shadowRoot.querySelectorAll('*').length;
        results.push({ host, children });
    });
    return results;
}
"""

TAB_TEXT_JS = """
() => {
    const tabs = document.querySelectorAll("[role='tab'], div[class*='tab'] span, li[class*='tab'] span");
    return Array.from(tabs).map(t => t.innerText.trim()).filter(Boolean);
}
"""


async def diagnose(product_id: str, cookies_path: str, headless: bool) -> None:
    url = (
        f"{SHOPEE_BASE}/product/{product_id}"
        if "/" in product_id
        else f"{SHOPEE_BASE}/product/{product_id}"
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            executable_path=CHROMIUM_EXEC,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            viewport={"width": 390, "height": 844},
            locale="pt-BR",
            ignore_https_errors=True,
        )

        raw = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "cookies" in raw:
            raw = raw["cookies"]
        cookies = [_normalize_cookie(c) for c in raw]
        await context.add_cookies(cookies)
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [] });
            window.chrome = { runtime: { id: 'fakeId' } };
        """)

        page = await context.new_page()
        print(f"\n[1] Abrindo {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        final_url = page.url
        print(f"    URL final: {final_url}")
        if any(x in final_url for x in ["/login", "sign_up", "dologin"]):
            print("    AVISO: redirecionado para login — cookies expirados!")
            await browser.close()
            return

        print("\n[2] Seletores CSS no DOM principal:")
        print(f"    {'Seletor':<45} {'Encontrados':>11}")
        print("    " + "-" * 58)
        for sel in PROBE_SELECTORS:
            try:
                els = await page.query_selector_all(sel)
                found = len(els)
            except Exception:
                found = -1
            mark = " <-- ATIVO" if found > 0 else ""
            print(f"    {sel:<45} {found:>11}{mark}")

        print("\n[3] Shadow DOM hosts:")
        hosts = await page.evaluate(SHADOW_PROBE_JS)
        if not hosts:
            print("    Nenhum Shadow Root encontrado.")
        else:
            for h in hosts[:20]:
                print(f"    {h['host'][:60]:<60}  {h['children']} filho(s)")
            if len(hosts) > 20:
                print(f"    ... e mais {len(hosts) - 20} hosts")

        print("\n[4] Textos das abas encontradas:")
        tab_texts = await page.evaluate(TAB_TEXT_JS)
        if not tab_texts:
            print("    Nenhuma aba encontrada com os seletores atuais.")
        else:
            for t in tab_texts:
                mark = " <-- CRIADORES" if "criador" in t.lower() or "creator" in t.lower() else ""
                print(f"    '{t}'{mark}")

        print("\n[5] Scroll rápido para forçar lazy loading...")
        await page.evaluate("""
            () => new Promise(resolve => {
                let n = 0;
                const iv = setInterval(() => {
                    window.scrollBy(0, 800);
                    if (++n >= 10) { clearInterval(iv); resolve(); }
                }, 300);
            })
        """)

        print("\n[6] Re-contagem após scroll:")
        for sel in PROBE_SELECTORS[:7]:
            try:
                els = await page.query_selector_all(sel)
                found = len(els)
            except Exception:
                found = -1
            if found > 0:
                print(f"    {sel}: {found}")

        print("\nDiagnóstico concluído.")
        await browser.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Valida seletores em página de produto Shopee")
    p.add_argument("--product", required=True, help="ID ou shop_id/item_id do produto")
    p.add_argument("--cookies", required=True, help="Caminho para cookies.json")
    p.add_argument("--no-headless", action="store_true", help="Abrir browser visível")
    args = p.parse_args()

    asyncio.run(diagnose(args.product, args.cookies, headless=not args.no_headless))


if __name__ == "__main__":
    main()

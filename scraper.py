"""
Shopee Video Counter - v1.2
Agora com suporte para fechar modais de idioma e melhor detecção.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    TimeoutError as PWTimeout,
)

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
    logging.getLogger("playwright").setLevel(logging.WARNING)
    return logging.getLogger("shopee")

log = logging.getLogger("shopee")

# ── Configurações ────────────────────────────────────────────────────────────

SHOPEE_BASE = "https://shopee.com.br"

CREATORS_TAB_TEXTS = [
    "aprender com criadores", 
    "learn from creators", 
    "vídeos", 
    "videos", 
    "criadores",
    "ver vídeos",
    "vídeos do produto",
    "inspiração"
]

VIDEO_ITEM_SELECTORS = [
    "[data-sqe='video-item']",
    "[data-testid='video-item']",
    "._3X5KM",
    ".creator-video-item",
    "div[class*='VideoCard']",
    "div[class*='video-card']",
    "div[class*='video'] div[class*='item']",
]

NAV_TAB_SELECTOR = (
    "[role='tab'], "
    "div[class*='tab'] span, "
    "li[class*='tab'] span, "
    "div[class*='Tab'] span, "
    ".shopee-tabs__tab, "
    "._2u_8_X"
)

LOGIN_INDICATORS = ["/login", "sign_up", "dologin", "accounts.shopee"]

MOBILE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

@dataclass
class ProductResult:
    product_id: str
    video_count: int | None
    status: str = "ok"
    error: str | None = None
    selector_used: str | None = None
    elapsed_s: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

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

async def handle_modals(page: Page):
    """Fecha modais que bloqueiam a tela, como seleção de idioma."""
    try:
        # Procura pelo botão de idioma "Português (BR)"
        lang_button = page.get_by_role("button", name="Português (BR)").or_(page.get_by_text("Português (BR)")).first
        if await lang_button.is_visible(timeout=3000):
            log.info("Modal de idioma detectado. Clicando em 'Português (BR)'...")
            await lang_button.click()
            await asyncio.sleep(1)
    except Exception:
        pass

async def inject_cookies(context: BrowserContext, path: str) -> None:
    if not os.path.exists(path): return
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "cookies" in data: data = data["cookies"]
        await context.add_cookies([_normalize_cookie(c) for c in data])
    except Exception as e:
        log.error("Erro ao carregar cookies: %s", e)

async def navigate(page: Page, product_id: str) -> str | None:
    url = f"{SHOPEE_BASE}/product/{product_id}"
    try:
        log.info("Navegando para %s", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await asyncio.sleep(3)
        
        # Tenta fechar modais antes de prosseguir
        await handle_modals(page)
        
        if any(ind in page.url for ind in LOGIN_INDICATORS):
            return "sessão expirada"
        return None
    except PWTimeout:
        return "timeout ao navegar"

async def find_and_click_tab(page: Page) -> bool:
    try:
        # Espera as abas aparecerem
        await page.wait_for_selector(NAV_TAB_SELECTOR, timeout=10_000)
        tabs = await page.query_selector_all(NAV_TAB_SELECTOR)
        
        for tab in tabs:
            text = (await tab.inner_text()).strip().lower()
            if any(t in text for t in CREATORS_TAB_TEXTS):
                log.info("Aba encontrada: '%s'. Clicando...", text)
                await tab.scroll_into_view_if_needed()
                await tab.click()
                await asyncio.sleep(2)
                return True
    except Exception:
        pass
    return False

_SCROLL_JS = """
(selectorList, stableMs, maxMs) => new Promise((resolve) => {
    let lastCount = 0, timer = null;
    const sel = selectorList.join(', ');
    const startTime = Date.now();

    const tick = () => {
        window.scrollBy(0, 800);
        const n = document.querySelectorAll(sel).length;
        if (n !== lastCount && n > 0) {
            lastCount = n;
            if (timer) { clearTimeout(timer); timer = null; }
        } else if (!timer) {
            timer = setTimeout(() => { 
                clearInterval(iv); 
                resolve(lastCount); 
            }, stableMs);
        }
        if (Date.now() - startTime > maxMs) {
            clearInterval(iv);
            resolve(lastCount);
        }
    };
    const iv = setInterval(tick, 600);
})
"""

async def process_product(page: Page, pid: str, threshold: int) -> ProductResult:
    t0 = time.monotonic()
    err = await navigate(page, pid)
    if err: return ProductResult(pid, None, "error", err, elapsed_s=round(time.monotonic()-t0, 2))

    if not await find_and_click_tab(page):
        # Tenta um scroll rápido caso a aba esteja escondida
        await page.evaluate("window.scrollBy(0, 500)")
        await asyncio.sleep(1)
        if not await find_and_click_tab(page):
            return ProductResult(pid, None, "no_tab", "aba não encontrada", elapsed_s=round(time.monotonic()-t0, 2))

    await page.evaluate(_SCROLL_JS, VIDEO_ITEM_SELECTORS, 3000, 20000)
    
    count, selector = None, None
    for sel in VIDEO_ITEM_SELECTORS:
        els = await page.query_selector_all(sel)
        if els:
            count, selector = len(els), sel
            break

    if count is None:
        return ProductResult(pid, None, "error", "nenhum vídeo detectado", elapsed_s=round(time.monotonic()-t0, 2))
    
    status = "blue_ocean" if count < threshold else "competed"
    return ProductResult(pid, count, status, selector_used=selector, elapsed_s=round(time.monotonic()-t0, 2))

async def run(ids: list[str], cookies: str, concurrency: int, rps: float, threshold: int, headless: bool) -> list[ProductResult]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(user_agent=MOBILE_UA, viewport={"width": 1280, "height": 800})
        await inject_cookies(context, cookies)
        
        results = []
        for pid in ids:
            page = await context.new_page()
            try:
                res = await process_product(page, pid, threshold)
                results.append(res)
                if len(ids) > 1: await asyncio.sleep(1.0 / rps)
            finally:
                await page.close()
        await browser.close()
        return results

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--products", required=True)
    p.add_argument("--cookies", default="cookies.json")
    p.add_argument("--threshold", type=int, default=5)
    p.add_argument("--no-headless", action="store_false", dest="headless")
    p.add_argument("--debug", action="store_true")
    p.set_defaults(headless=True)
    args = p.parse_args()
    
    setup_logging(args.debug)
    ids = [x.strip() for x in args.products.split(",")]
    results = asyncio.run(run(ids, args.cookies, 1, 1, args.threshold, args.headless))
    
    for r in results:
        print(f"{r.product_id:<25} {r.video_count if r.video_count is not None else 'N/A':<10} {r.status}")

if __name__ == "__main__":
    main()
"""
Shopee Video Counter - v1.1
Conta vídeos na aba "Aprender com criadores" para identificar Oceanos Azuis.
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
CHROMIUM_EXEC = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" if os.path.exists("/opt/pw-browsers") else None

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
    "._2u_8_X" # Seletor genérico de abas mobile
)

LOGIN_INDICATORS = ["/login", "sign_up", "dologin", "accounts.shopee"]

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Mobile Safari/537.36"
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

def load_cookies_from_file(path: str) -> list[dict]:
    if not os.path.exists(path):
        log.warning("Arquivo de cookies %s não encontrado.", path)
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "cookies" in data:
            data = data["cookies"]
        return [_normalize_cookie(c) for c in data]
    except Exception as e:
        log.error("Erro ao carregar cookies: %s", e)
        return []

async def inject_cookies(context: BrowserContext, path: str) -> None:
    cookies = load_cookies_from_file(path)
    if cookies:
        await context.add_cookies(cookies)

def is_session_expired(url: str) -> bool:
    return any(indicator in url for indicator in LOGIN_INDICATORS)

def build_url(product_id: str) -> str:
    if "/" in product_id:
        shop_id, item_id = product_id.split("/", 1)
        return f"{SHOPEE_BASE}/product/{shop_id}/{item_id}"
    return f"{SHOPEE_BASE}/product/{product_id}"

async def navigate(page: Page, product_id: str) -> str | None:
    url = build_url(product_id)
    try:
        log.info("Navegando para %s", url)
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(3) # Espera um pouco mais para carregar abas
        if is_session_expired(page.url):
            return "sessão expirada"
        if response and response.status >= 400:
            return f"HTTP {response.status}"
        return None
    except PWTimeout:
        return "timeout ao navegar"

async def find_and_click_tab(page: Page) -> bool:
    try:
        # Tenta esperar pelas abas aparecerem
        await page.wait_for_selector(NAV_TAB_SELECTOR, timeout=10_000)
        tabs = await page.query_selector_all(NAV_TAB_SELECTOR)
        
        found_texts = []
        for tab in tabs:
            text = (await tab.inner_text()).strip().lower()
            if text:
                found_texts.append(text)
                if any(t in text for t in CREATORS_TAB_TEXTS):
                    log.info("Aba encontrada: '%s'. Clicando...", text)
                    await tab.scroll_into_view_if_needed()
                    await tab.click()
                    await asyncio.sleep(2)
                    return True
        
        log.warning("Abas encontradas na página: %s", found_texts)
    except Exception as e:
        log.debug("Erro ao procurar abas: %s", e)
    return False

_SCROLL_JS = """
(selectorList, stableMs, maxMs) => new Promise((resolve) => {
    let lastCount = 0, timer = null;
    const sel = selectorList.join(', ');
    const startTime = Date.now();

    const tick = () => {
        window.scrollBy(0, 1000);
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
    const iv = setInterval(tick, 800);
})
"""

async def scroll_and_wait(page: Page, stable_ms: int = 3000, max_ms: int = 30_000) -> int:
    count = await page.evaluate(_SCROLL_JS, VIDEO_ITEM_SELECTORS, stable_ms, max_ms)
    return count

async def count_videos(page: Page) -> tuple[int | None, str | None]:
    for sel in VIDEO_ITEM_SELECTORS:
        try:
            elements = await page.query_selector_all(sel)
            if elements and len(elements) > 0:
                return len(elements), sel
        except Exception:
            continue
    return None, None

async def process_product(page: Page, pid: str, threshold: int) -> ProductResult:
    t0 = time.monotonic()
    err = await navigate(page, pid)
    if err: 
        return ProductResult(pid, None, "expired" if "expirada" in err else "error", err, elapsed_s=round(time.monotonic()-t0, 2))

    if not await find_and_click_tab(page):
        return ProductResult(pid, None, "no_tab", "aba não encontrada", elapsed_s=round(time.monotonic()-t0, 2))

    await scroll_and_wait(page)
    count, selector = await count_videos(page)

    if count is None:
        count, selector = await count_videos(page)
        if count is None:
            return ProductResult(pid, None, "error", "nenhum vídeo detectado na aba", elapsed_s=round(time.monotonic()-t0, 2))
    
    status = "blue_ocean" if count < threshold else "competed"
    return ProductResult(pid, count, status, selector_used=selector, elapsed_s=round(time.monotonic()-t0, 2))

async def run(ids: list[str], cookies: str, concurrency: int, rps: float, threshold: int, headless: bool) -> list[ProductResult]:
    async with async_playwright() as pw:
        launch_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        browser = await pw.chromium.launch(headless=headless, executable_path=CHROMIUM_EXEC, args=launch_args)
        context = await browser.new_context(user_agent=MOBILE_UA, viewport={"width": 390, "height": 844}, ignore_https_errors=True, locale="pt-BR")
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
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
    p = argparse.ArgumentParser(description="Shopee Video Counter")
    p.add_argument("--products", required=True, help="IDs dos produtos separados por vírgula")
    p.add_argument("--cookies", required=True, help="Caminho para o arquivo cookies.json")
    p.add_argument("--threshold", type=int, default=5, help="Limite para Oceano Azul")
    p.add_argument("--no-headless", action="store_false", dest="headless", help="Desativa o modo headless")
    p.add_argument("--debug", action="store_true", help="Ativa logs detalhados")
    p.set_defaults(headless=True)
    
    args = p.parse_args()
    
    setup_logging(args.debug)
    ids = [x.strip() for x in args.products.split(",")]
    
    log.info("Iniciando contagem para %d produtos...", len(ids))
    results = asyncio.run(run(ids, args.cookies, 1, 1, args.threshold, args.headless))
    
    print(f"\n{'ID':<25} {'Videos':<10} {'Status'}")
    print("-" * 50)
    for r in results:
        v_str = str(r.video_count) if r.video_count is not None else "N/A"
        print(f"{r.product_id:<25} {v_str:<10} {r.status}")

if __name__ == "__main__":
    main()
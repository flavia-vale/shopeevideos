"""
Shopee Video Counter
Conta vídeos na aba "Aprender com criadores" para identificar Oceanos Azuis.
"""

import argparse
import asyncio
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PWTimeout,
)

# ── Logging ──────────────────────────────────────────────────────────────────

def setup_logging(debug: bool = False) -> logging.Logger:
    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
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
CHROMIUM_EXEC = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
CREATORS_TAB_TEXTS = ["aprender com criadores", "learn from creators", "vídeos"]

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
    "div[class*='Tab'] span"
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
    screenshot: str | None = None
    elapsed_s: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

async def with_retry(coro_fn, retries: int = 2, base_delay: float = 2.0, label: str = ""):
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await coro_fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                delay = base_delay * (2 ** attempt)
                log.warning("%s falhou (%d/%d): %s — retry em %.0fs", label, attempt + 1, retries + 1, exc, delay)
                await asyncio.sleep(delay)
    raise last_exc

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
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    return [_normalize_cookie(c) for c in data]

async def inject_cookies(context: BrowserContext, path: str) -> None:
    cookies = load_cookies_from_file(path)
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
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        if is_session_expired(page.url):
            return "sessão expirada"
        if response and response.status >= 400:
            return f"HTTP {response.status}"
        return None
    except PWTimeout:
        return "timeout ao navegar"

async def find_and_click_tab(page: Page) -> bool:
    try:
        await page.wait_for_selector(NAV_TAB_SELECTOR, timeout=10_000)
        tabs = await page.query_selector_all(NAV_TAB_SELECTOR)
        for tab in tabs:
            text = (await tab.inner_text()).strip().lower()
            if any(t in text for t in CREATORS_TAB_TEXTS):
                await tab.scroll_into_view_if_needed()
                await tab.click()
                await page.wait_for_load_state("networkidle", timeout=10_000)
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
        window.scrollBy(0, 1000);
        const n = document.querySelectorAll(sel).length;
        
        if (n !== lastCount) {
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

    const iv = setInterval(tick, 500);
})
"""

async def scroll_and_wait(page: Page, stable_ms: int = 3000, max_ms: int = 60_000) -> int:
    # Aumentado o tempo para 60s e estabilidade para 3s para garantir que 80+ vídeos carreguem
    count = await page.evaluate(_SCROLL_JS, VIDEO_ITEM_SELECTORS, stable_ms, max_ms)
    log.debug("Scroll finalizado. Total encontrado: %d", count)
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

async def process_product(page: Page, pid: str, threshold: int, screenshot: bool) -> ProductResult:
    t0 = time.monotonic()
    err = await navigate(page, pid)
    if err: return ProductResult(pid, None, "expired" if "expirada" in err else "error", err, elapsed_s=round(time.monotonic()-t0, 2))

    if not await find_and_click_tab(page):
        return ProductResult(pid, None, "no_tab", "aba não encontrada", elapsed_s=round(time.monotonic()-t0, 2))

    await scroll_and_wait(page)
    count, selector = await count_videos(page)

    if count is None:
        return ProductResult(pid, None, "error", "nenhum vídeo detectado", elapsed_s=round(time.monotonic()-t0, 2))
    
    status = "blue_ocean" if count < threshold else "competed"
    return ProductResult(pid, count, status, selector_used=selector, elapsed_s=round(time.monotonic()-t0, 2))

async def run(ids: list[str], cookies: str, concurrency: int, rps: float, threshold: int, headless: bool) -> list[ProductResult]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, executable_path=CHROMIUM_EXEC, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(user_agent=MOBILE_UA, viewport={"width": 390, "height": 844}, ignore_https_errors=True)
        await inject_cookies(context, cookies)
        
        results = []
        for pid in ids:
            page = await context.new_page()
            try:
                res = await process_product(page, pid, threshold, False)
                results.append(res)
            finally:
                await page.close()
        await browser.close()
        return results

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--products", required=True)
    p.add_argument("--cookies", required=True)
    p.add_argument("--threshold", type=int, default=5)
    args = p.parse_args()
    
    setup_logging()
    ids = [x.strip() for x in args.products.split(",")]
    results = asyncio.run(run(ids, args.cookies, 1, 1, args.threshold, True))
    
    print(f"\n{'ID':<25} {'Videos':<10} {'Status'}")
    print("-" * 50)
    for r in results:
        print(f"{r.product_id:<25} {r.video_count if r.video_count else 'N/A':<10} {r.status}")

if __name__ == "__main__":
    main()
"""
Shopee Video Counter
Conta vídeos na aba "Aprender com criadores" para identificar Oceanos Azuis.

Uso:
    python scraper.py --products 1234567890,9876543210 --cookies cookies.json
    python scraper.py --products-file ids.txt --cookies cookies.json --output csv
    python scraper.py --products-file ids.txt --cookies cookies.json --threshold 3
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
    # silencia logs verbosos do playwright
    logging.getLogger("playwright").setLevel(logging.WARNING)
    return logging.getLogger("shopee")


log = logging.getLogger("shopee")


# ── Configurações ────────────────────────────────────────────────────────────

SHOPEE_BASE = "https://shopee.com.br"

# Chromium pré-instalado no ambiente (evita download bloqueado pelo CDN)
CHROMIUM_EXEC = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

CREATORS_TAB_TEXTS = ["aprender com criadores", "learn from creators"]

# Seletores em ordem de confiança — atualize aqui se a Shopee mudar o DOM
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


# ── Resultado ────────────────────────────────────────────────────────────────

@dataclass
class ProductResult:
    product_id: str
    video_count: int | None
    status: str = "ok"          # ok | blue_ocean | competed | error | no_tab | expired
    error: str | None = None
    selector_used: str | None = None
    screenshot: str | None = None
    elapsed_s: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ── Retry ────────────────────────────────────────────────────────────────────

async def with_retry(coro_fn, retries: int = 2, base_delay: float = 2.0, label: str = ""):
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await coro_fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                delay = base_delay * (2 ** attempt)
                log.warning("%s falhou (tentativa %d/%d): %s — retry em %.0fs",
                            label, attempt + 1, retries + 1, exc, delay)
                await asyncio.sleep(delay)
    raise last_exc


# ── Cookies ──────────────────────────────────────────────────────────────────

def _normalize_cookie(c: dict) -> dict:
    """
    Converte cookies do formato Chrome/EditThisCookie para o formato Playwright.
    - expirationDate → expires (int)
    - sameSite null  → "None"
    - remove campos desconhecidos pelo Playwright
    """
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
    log.debug("Injetados %d cookies de %s", len(cookies), path)


def is_session_expired(url: str) -> bool:
    return any(indicator in url for indicator in LOGIN_INDICATORS)


# ── Navegação ─────────────────────────────────────────────────────────────────

def build_url(product_id: str) -> str:
    # aceita "shop_id/item_id" ou somente "item_id"
    if "/" in product_id:
        shop_id, item_id = product_id.split("/", 1)
        return f"{SHOPEE_BASE}/product/{shop_id}/{item_id}"
    return f"{SHOPEE_BASE}/product/{product_id}"


async def navigate(page: Page, product_id: str) -> str | None:
    """Navega e retorna None se ok, ou mensagem de erro."""
    url = build_url(product_id)
    log.debug("Abrindo %s", url)
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        final_url = page.url
        if is_session_expired(final_url):
            return "sessão expirada — renove cookies.json"
        if response and response.status >= 400:
            return f"HTTP {response.status}"
        return None
    except PWTimeout:
        return "timeout ao navegar"


# ── Aba de Criadores ─────────────────────────────────────────────────────────

async def find_and_click_tab(page: Page) -> bool:
    try:
        # aguarda qualquer aba aparecer
        await page.wait_for_selector(NAV_TAB_SELECTOR, timeout=8_000)
        tabs = await page.query_selector_all(NAV_TAB_SELECTOR)
        for tab in tabs:
            text = (await tab.inner_text()).strip().lower()
            if any(t in text for t in CREATORS_TAB_TEXTS):
                await tab.scroll_into_view_if_needed()
                await tab.click()
                # espera conteúdo estabilizar após clique
                await page.wait_for_load_state("networkidle", timeout=10_000)
                log.debug("Aba 'Aprender com criadores' clicada")
                return True
    except Exception as exc:
        log.debug("find_and_click_tab falhou: %s", exc)
    return False


# ── Scroll / Lazy Loading ────────────────────────────────────────────────────

_SCROLL_JS = """
(selectorList, stableMs, maxMs) => new Promise((resolve) => {
    let lastCount = 0, timer = null;
    const sel = selectorList.join(', ');

    const tick = () => {
        window.scrollBy(0, 700);
        const n = document.querySelectorAll(sel).length;
        if (n !== lastCount) {
            lastCount = n;
            clearTimeout(timer);
            timer = null;
        } else if (!timer) {
            timer = setTimeout(() => { clearInterval(iv); resolve(lastCount); }, stableMs);
        }
    };

    const iv = setInterval(tick, 350);
    setTimeout(() => { clearInterval(iv); resolve(lastCount); }, maxMs);
})
"""

async def scroll_and_wait(page: Page, stable_ms: int = 2000, max_ms: int = 30_000) -> int:
    count = await page.evaluate(_SCROLL_JS, VIDEO_ITEM_SELECTORS, stable_ms, max_ms)
    log.debug("scroll_and_wait terminou com %d elementos visíveis", count)
    return count


# ── Contagem de Vídeos ───────────────────────────────────────────────────────

async def count_videos(page: Page) -> tuple[int | None, str | None]:
    """Retorna (contagem, seletor_usado)."""
    for sel in VIDEO_ITEM_SELECTORS:
        try:
            elements = await page.query_selector_all(sel)
            if elements:
                log.debug("Seletor '%s' encontrou %d vídeos", sel, len(elements))
                return len(elements), sel
        except Exception:
            continue

    # fallback: Shadow DOM (1 nível)
    shadow_count: int = await page.evaluate("""
        () => {
            let total = 0;
            const terms = ['video-item', 'VideoCard', 'video-card', 'creator-video'];
            document.querySelectorAll('*').forEach(el => {
                if (!el.shadowRoot) return;
                terms.forEach(t => {
                    total += el.shadowRoot.querySelectorAll(`[class*='${t}'], [data-sqe='${t}']`).length;
                });
            });
            return total;
        }
    """)
    if shadow_count > 0:
        log.debug("Shadow DOM fallback encontrou %d vídeos", shadow_count)
        return shadow_count, "shadow-dom"

    return None, None


# ── Screenshot de Erro ───────────────────────────────────────────────────────

async def take_error_screenshot(page: Page, product_id: str) -> str:
    path = f"error_{product_id}_{int(time.time())}.png"
    try:
        await page.screenshot(path=path, full_page=False)
        log.debug("Screenshot salvo: %s", path)
    except Exception:
        pass
    return path


# ── Pipeline por Produto ──────────────────────────────────────────────────────

async def process_product(
    page: Page,
    product_id: str,
    blue_ocean_threshold: int,
    screenshot_on_error: bool,
) -> ProductResult:
    t0 = time.monotonic()

    err = await navigate(page, product_id)
    if err:
        result = ProductResult(product_id, None, "error" if "expirada" not in err else "expired", err)
        if screenshot_on_error:
            result.screenshot = await take_error_screenshot(page, product_id)
        result.elapsed_s = round(time.monotonic() - t0, 2)
        return result

    found = await find_and_click_tab(page)
    if not found:
        result = ProductResult(product_id, None, "no_tab", "aba 'Aprender com criadores' não encontrada")
        if screenshot_on_error:
            result.screenshot = await take_error_screenshot(page, product_id)
        result.elapsed_s = round(time.monotonic() - t0, 2)
        return result

    await scroll_and_wait(page)
    count, selector = await count_videos(page)

    if count is None:
        result = ProductResult(product_id, None, "error", "nenhum seletor retornou elementos")
        if screenshot_on_error:
            result.screenshot = await take_error_screenshot(page, product_id)
    else:
        status = "blue_ocean" if count < blue_ocean_threshold else "competed"
        result = ProductResult(product_id, count, status, selector_used=selector)

    result.elapsed_s = round(time.monotonic() - t0, 2)
    log.info("%-25s videos=%-5s status=%s (%.1fs)", product_id, result.video_count, result.status, result.elapsed_s)
    return result


# ── Rate Limiter ──────────────────────────────────────────────────────────────

class RateLimiter:
    def __init__(self, rps: float):
        self._interval = 1.0 / rps
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


# ── Orquestrador ─────────────────────────────────────────────────────────────

async def run(
    product_ids: list[str],
    cookies_path: str,
    concurrency: int = 3,
    rps: float = 1.0,
    blue_ocean_threshold: int = 5,
    screenshot_on_error: bool = False,
    headless: bool = True,
) -> list[ProductResult]:

    rate = RateLimiter(rps)
    semaphore = asyncio.Semaphore(concurrency)
    results: list[ProductResult | None] = [None] * len(product_ids)

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=headless,
            executable_path=CHROMIUM_EXEC,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context: BrowserContext = await browser.new_context(
            user_agent=MOBILE_UA,
            viewport={"width": 390, "height": 844},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            ignore_https_errors=True,
        )
        # injeta JavaScript para mascarar Playwright
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [] });
            window.chrome = { runtime: { id: 'fakeId' } };
        """)
        await inject_cookies(context, cookies_path)

        async def bounded(idx: int, pid: str) -> None:
            await rate.acquire()
            async with semaphore:
                page = await context.new_page()
                try:
                    result = await with_retry(
                        lambda: process_product(page, pid, blue_ocean_threshold, screenshot_on_error),
                        retries=2,
                        label=pid,
                    )
                    results[idx] = result
                except Exception as exc:
                    log.error("%s falhou após retries: %s", pid, exc)
                    results[idx] = ProductResult(pid, None, "error", str(exc))
                finally:
                    await page.close()

        await asyncio.gather(*[bounded(i, pid) for i, pid in enumerate(product_ids)])
        await browser.close()

    return [r for r in results if r is not None]


# ── Saída ─────────────────────────────────────────────────────────────────────

BLUE_OCEAN_EMOJI = ""
COMPETED_EMOJI   = ""

STATUS_LABELS = {
    "blue_ocean": "Oceano Azul",
    "competed":   "Competido",
    "no_tab":     "Sem aba criadores",
    "expired":    "Sessao expirada",
    "error":      "Erro",
}

def print_table(results: list[ProductResult], threshold: int) -> None:
    print(f"\n{'ID do Produto':<28} {'Videos':>7}  {'Status':<20}  Detalhe")
    print("-" * 75)
    for r in results:
        count = str(r.video_count) if r.video_count is not None else "N/A"
        label = STATUS_LABELS.get(r.status, r.status)
        detail = r.error or r.selector_used or ""
        print(f"{r.product_id:<28} {count:>7}  {label:<20}  {detail}")
    print()
    blue = [r for r in results if r.status == "blue_ocean"]
    print(f"Oceanos Azuis (< {threshold} videos): {len(blue)}/{len(results)}")


def write_csv(results: list[ProductResult], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(r) for r in results)
    log.info("CSV salvo em %s", path)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Shopee Video Counter — identifica Oceanos Azuis por contagem de vídeos de criadores"
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--products", metavar="IDS", help="IDs separados por vírgula")
    src.add_argument("--products-file", metavar="FILE", help="Arquivo com um ID por linha")

    p.add_argument("--cookies", required=True, metavar="FILE", help="Caminho para cookies.json")
    p.add_argument("--output", choices=["table", "json", "csv"], default="table")
    p.add_argument("--output-file", metavar="FILE", help="Salvar saída neste arquivo (csv/json)")
    p.add_argument("--concurrency", type=int, default=3, help="Abas paralelas (padrão: 3)")
    p.add_argument("--rps", type=float, default=1.0, help="Requisições por segundo (padrão: 1.0)")
    p.add_argument("--threshold", type=int, default=5, help="Videos < N = Oceano Azul (padrão: 5)")
    p.add_argument("--screenshot-on-error", action="store_true", help="Salvar PNG em caso de falha")
    p.add_argument("--no-headless", action="store_true", help="Abrir browser visível (debug)")
    p.add_argument("--debug", action="store_true", help="Logging verboso")
    return p.parse_args()


def load_ids(args: argparse.Namespace) -> list[str]:
    if args.products:
        return [x.strip() for x in args.products.split(",") if x.strip()]
    return [ln.strip() for ln in Path(args.products_file).read_text().splitlines() if ln.strip()]


def main() -> None:
    args = parse_args()
    setup_logging(args.debug)

    ids = load_ids(args)
    if not ids:
        log.error("Nenhum product ID fornecido.")
        sys.exit(1)

    log.info("Iniciando: %d produto(s) | concurrency=%d | rps=%.1f | threshold=%d",
             len(ids), args.concurrency, args.rps, args.threshold)

    results = asyncio.run(run(
        product_ids=ids,
        cookies_path=args.cookies,
        concurrency=args.concurrency,
        rps=args.rps,
        blue_ocean_threshold=args.threshold,
        screenshot_on_error=args.screenshot_on_error,
        headless=not args.no_headless,
    ))

    out_file = args.output_file

    if args.output == "table":
        print_table(results, args.threshold)
    elif args.output == "json":
        payload = json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2)
        if out_file:
            Path(out_file).write_text(payload, encoding="utf-8")
            log.info("JSON salvo em %s", out_file)
        else:
            print(payload)
    elif args.output == "csv":
        dest = out_file or f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        write_csv(results, dest)
        print_table(results, args.threshold)


if __name__ == "__main__":
    main()

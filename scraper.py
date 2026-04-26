"""
Shopee Video Counter — conta vídeos na aba "Aprender com criadores"
para identificar produtos em "Oceano Azul" (poucos criadores = baixa competição).

Uso:
    python scraper.py --products 1234567890,9876543210 --cookies cookies.json
    python scraper.py --products-file product_ids.txt --cookies cookies.json
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Page, TimeoutError as PWTimeout


# ── Configurações ────────────────────────────────────────────────────────────

SHOPEE_BASE = "https://shopee.com.br"
CREATORS_TAB_TEXTS = ["aprender com criadores", "learn from creators"]

# Seletores candidatos — Shopee muda com frequência, listar em ordem de confiança
VIDEO_ITEM_SELECTORS = [
    "[data-sqe='video-item']",
    "._3X5KM",           # classe comum em versões recentes
    ".creator-video-item",
    "div[class*='video'] div[class*='item']",
]

NAV_TAB_SELECTOR = "div[class*='tab'] span, li[class*='tab'] span, [role='tab'] span"


# ── Resultado ────────────────────────────────────────────────────────────────

@dataclass
class ProductResult:
    product_id: str
    video_count: int | None   # None = erro / não encontrado
    error: str | None = None


# ── Núcleo do scraper ────────────────────────────────────────────────────────

async def load_cookies(context: BrowserContext, path: str) -> None:
    cookies = json.loads(Path(path).read_text())
    await context.add_cookies(cookies)


async def navigate_to_product(page: Page, product_id: str) -> bool:
    """Navega para a página de compartilhamento do produto."""
    url = f"{SHOPEE_BASE}/product/{product_id}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        return True
    except PWTimeout:
        return False


async def click_creators_tab(page: Page) -> bool:
    """Localiza e clica na aba 'Aprender com criadores'."""
    try:
        tabs = await page.query_selector_all(NAV_TAB_SELECTOR)
        for tab in tabs:
            text = (await tab.inner_text()).strip().lower()
            if any(t in text for t in CREATORS_TAB_TEXTS):
                await tab.click()
                await page.wait_for_load_state("networkidle", timeout=10_000)
                return True
    except Exception:
        pass
    return False


async def scroll_until_stable(page: Page, container_selector: str, stable_ms: int = 2000) -> None:
    """
    Rola o container de vídeos até não aparecerem novos itens por `stable_ms`.
    Lida com lazy loading sem depender de paginação explícita.
    """
    await page.evaluate(f"""
        (containerSel, stableMs) => new Promise((resolve) => {{
            const container = document.querySelector(containerSel) || document.body;
            let lastCount = 0;
            let timer;

            const check = () => {{
                container.scrollBy(0, 600);
                const items = document.querySelectorAll(
                    "{VIDEO_ITEM_SELECTORS[0]}, {VIDEO_ITEM_SELECTORS[1]}, {VIDEO_ITEM_SELECTORS[2]}"
                );
                if (items.length === lastCount) {{
                    if (!timer) timer = setTimeout(resolve, stableMs);
                }} else {{
                    lastCount = items.length;
                    clearTimeout(timer);
                    timer = null;
                }}
            }};

            const interval = setInterval(check, 400);
            setTimeout(() => {{ clearInterval(interval); resolve(); }}, 30_000);
        }})
    """, container_selector)


def detect_video_selector(handles) -> str | None:
    """Retorna o primeiro seletor que encontrar elementos."""
    return next((s for s in VIDEO_ITEM_SELECTORS if handles.get(s, 0) > 0), None)


async def count_videos(page: Page) -> int | None:
    """
    Tenta contar vídeos usando a lista de seletores candidatos.
    Valida se os elementos estão no DOM real ou atrás de Shadow DOM.
    """
    counts: dict[str, int] = {}
    for sel in VIDEO_ITEM_SELECTORS:
        try:
            elements = await page.query_selector_all(sel)
            counts[sel] = len(elements)
        except Exception:
            counts[sel] = 0

    best = max(counts.values(), default=0)
    if best > 0:
        return best

    # Fallback: inspecionar Shadow DOM (1 nível de profundidade)
    shadow_count = await page.evaluate("""
        () => {
            let total = 0;
            document.querySelectorAll('*').forEach(el => {
                if (el.shadowRoot) {
                    total += el.shadowRoot.querySelectorAll(
                        "[data-sqe='video-item'], [class*='video'][class*='item']"
                    ).length;
                }
            });
            return total;
        }
    """)
    return shadow_count if shadow_count > 0 else None


# ── Orquestrador ─────────────────────────────────────────────────────────────

async def process_product(page: Page, product_id: str) -> ProductResult:
    ok = await navigate_to_product(page, product_id)
    if not ok:
        return ProductResult(product_id, None, "timeout ao navegar")

    found_tab = await click_creators_tab(page)
    if not found_tab:
        return ProductResult(product_id, None, "aba 'Aprender com criadores' não encontrada")

    await scroll_until_stable(page, "body")

    count = await count_videos(page)
    return ProductResult(product_id, count)


async def run(product_ids: list[str], cookies_path: str, concurrency: int = 3) -> list[ProductResult]:
    results: list[ProductResult] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            viewport={"width": 390, "height": 844},  # simula mobile (app Shopee)
            locale="pt-BR",
        )
        await load_cookies(context, cookies_path)

        semaphore = asyncio.Semaphore(concurrency)

        async def bounded(pid: str) -> ProductResult:
            async with semaphore:
                page = await context.new_page()
                try:
                    return await process_product(page, pid)
                finally:
                    await page.close()

        results = await asyncio.gather(*[bounded(pid) for pid in product_ids])
        await browser.close()

    return list(results)


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Conta vídeos de criadores por produto Shopee")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--products", help="IDs separados por vírgula: 111,222,333")
    group.add_argument("--products-file", help="Arquivo .txt com um ID por linha")
    parser.add_argument("--cookies", required=True, help="Caminho para cookies.json")
    parser.add_argument("--concurrency", type=int, default=3, help="Abas paralelas (padrão: 3)")
    parser.add_argument("--output", choices=["json", "table"], default="table")
    return parser.parse_args()


def load_product_ids(args: argparse.Namespace) -> list[str]:
    if args.products:
        return [p.strip() for p in args.products.split(",") if p.strip()]
    return [line.strip() for line in Path(args.products_file).read_text().splitlines() if line.strip()]


def print_table(results: list[ProductResult]) -> None:
    print(f"\n{'Product ID':<20} {'Videos':>8}  {'Status'}")
    print("-" * 50)
    for r in results:
        count = str(r.video_count) if r.video_count is not None else "N/A"
        status = r.error or ("oceano azul" if (r.video_count or 0) < 5 else "competido")
        print(f"{r.product_id:<20} {count:>8}  {status}")


def main() -> None:
    args = parse_args()
    product_ids = load_product_ids(args)

    if not product_ids:
        print("Nenhum product ID fornecido.", file=sys.stderr)
        sys.exit(1)

    print(f"Processando {len(product_ids)} produto(s) com concurrency={args.concurrency}...")
    results = asyncio.run(run(product_ids, args.cookies, args.concurrency))

    if args.output == "json":
        print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
    else:
        print_table(results)


if __name__ == "__main__":
    main()

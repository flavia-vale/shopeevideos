"""
Contagem de vídeos por produto — a parte que estava bloqueada.

## Por que as tentativas anteriores davam 418 / 403

O endpoint existe e funciona:

    POST https://sv.shopee.com.br/api/v2/timeline/unify/common

Chamado de fora do navegador, ele responde:

    403 {"is_login": false, "error": 90309999, ...}

`is_login: false` mesmo mandando os cookies certos. O motivo é que copiar
cookies para dentro do httpx reproduz *um* dos sinais que a Shopee checa e
nenhum dos outros: fingerprint de TLS, ordem de headers, e principalmente os
headers que o SDK anti-bot da própria página injeta em tempo de execução via
JavaScript. Não dá para forjar isso de fora — é uma corrida que não se ganha.

## A saída: não replicar a requisição, e sim emiti-la de dentro da página

Em vez de reconstruir a chamada, abrimos um Chrome real já logado e disparamos
o `fetch` **de dentro do contexto da página**, com `page.evaluate`. Aí o
navegador anexa tudo sozinho — cookies, tokens do SDK, fingerprint — porque do
ponto de vista da Shopee a requisição é indistinguível da que a própria
interface faz. É a mesma requisição, feita pelo mesmo navegador.

O perfil fica em disco (`--profile`), então o login é feito uma vez, à mão, e
vale para as execuções seguintes.

## Uso

    python -m shopeeops.video_count login
    python -m shopeeops.video_count count --products 862915940/18399230627
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

log = logging.getLogger("shopeeops.video_count")

SV_ORIGIN = "https://sv.shopee.com.br"
TIMELINE_API = f"{SV_ORIGIN}/api/v2/timeline/unify/common"
# página pública e leve, só para colocar o contexto na origem certa
WARMUP_URL = f"{SV_ORIGIN}/"
LOGIN_URL = "https://shopee.com.br/buyer/login?next=https%3A%2F%2Fsv.shopee.com.br%2F"

DEFAULT_PROFILE = Path.home() / ".shopeeops" / "chrome-profile"
PAGE_SIZE = 30
MAX_PAGES = 20

_PRODUCT_RE = re.compile(r"(?:i\.|product/|product-i\.)?(\d{6,})[/.](\d{6,})")


class NotLoggedIn(RuntimeError):
    """O perfil não tem sessão válida — rode o subcomando `login`."""


@dataclass
class VideoCount:
    product_key: str
    videos: int | None
    status: str                # ok | no_videos | blocked | not_logged_in | error
    creators: int = 0
    total_views: int = 0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_product(raw: str) -> tuple[int, int]:
    """Aceita '123/456', URL de produto, ou 'i.123.456'."""
    m = _PRODUCT_RE.search(raw.strip())
    if not m:
        raise ValueError(f"não consegui extrair shop_id/item_id de {raw!r}")
    return int(m.group(1)), int(m.group(2))


# O fetch roda dentro da página: mesma origem, mesmos cookies, mesmo
# fingerprint. `credentials: include` garante o envio da sessão.
_FETCH_JS = """
async ([url, payload]) => {
  const resp = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify(payload),
  });
  let body = null;
  try { body = await resp.json(); } catch (e) { body = { _parseError: String(e) }; }
  return { status: resp.status, body };
}
"""


def _build_payload(shop_id: int, item_id: int, offset: int, limit: int) -> dict[str, Any]:
    return {
        "limit": limit,
        "page_context": json.dumps(
            {
                "item_id": item_id,
                "shop_id": shop_id,
                "offset": offset,
                "template_tab_id": "5",   # aba "Aprenda com criadores"
                "order_type": 1,
            }
        ),
        "request_type": 0,
        "lang": "pt-BR",
        "page_no": offset // max(limit, 1) + 1,
        "need_product_v2": True,
        "product_v2_scene": "affiliate_video_common_timeline",
    }


def _extract_items(body: Any) -> list[dict[str, Any]]:
    """A resposta já mudou de formato algumas vezes; procuramos a lista onde ela estiver."""
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    if not isinstance(data, dict):
        return []
    for key in ("list", "items", "sections", "feeds", "data"):
        val = data.get(key)
        if isinstance(val, list) and val:
            return val
    return []


def _extract_total(body: Any) -> int | None:
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    for key in ("total_count", "total", "count", "video_count"):
        v = data.get(key)
        if isinstance(v, int) and v >= 0:
            return v
    return None


def _summarize(items: list[dict[str, Any]]) -> tuple[int, int]:
    """(criadores distintos, soma de views) do lote de vídeos."""
    creators, views = set(), 0
    for it in items:
        meta = it.get("meta") if isinstance(it, dict) else None
        if not isinstance(meta, dict):
            continue
        if meta.get("userId"):
            creators.add(meta["userId"])
        views += int((meta.get("countInfo") or {}).get("views") or 0)
    return len(creators), views


class VideoCounter:
    """Conta vídeos por produto usando um Chrome persistente já logado."""

    def __init__(self, profile_dir: Path = DEFAULT_PROFILE, headless: bool = True) -> None:
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self._pw = None
        self._ctx = None
        self._page = None

    async def __aenter__(self) -> "VideoCounter":
        from playwright.async_api import async_playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()

        launch_kwargs: dict[str, Any] = {
            "user_data_dir": str(self.profile_dir),
            "headless": self.headless,
            "locale": "pt-BR",
            "timezone_id": "America/Sao_Paulo",
            "viewport": {"width": 1366, "height": 900},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        # permite apontar para um Chrome do sistema, útil quando o download do
        # Chromium do Playwright está bloqueado
        if os.getenv("SHOPEEOPS_CHROME"):
            launch_kwargs["executable_path"] = os.environ["SHOPEEOPS_CHROME"]

        self._ctx = await self._pw.chromium.launch_persistent_context(**launch_kwargs)
        self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        await self._page.goto(WARMUP_URL, wait_until="domcontentloaded", timeout=60_000)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._ctx:
            await self._ctx.close()
        if self._pw:
            await self._pw.stop()

    async def _call_api(self, payload: dict[str, Any]) -> tuple[int, Any]:
        result = await self._page.evaluate(_FETCH_JS, [TIMELINE_API, payload])
        return int(result["status"]), result["body"]

    async def count(self, product: str) -> VideoCount:
        try:
            shop_id, item_id = parse_product(product)
        except ValueError as exc:
            return VideoCount(product, None, "error", detail=str(exc))

        key = f"{shop_id}/{item_id}"
        seen: list[dict[str, Any]] = []
        offset = 0
        reported_total: int | None = None

        for _ in range(MAX_PAGES):
            status, body = await self._call_api(_build_payload(shop_id, item_id, offset, PAGE_SIZE))

            if status in (401, 403) or (isinstance(body, dict) and body.get("is_login") is False):
                return VideoCount(
                    key, None, "not_logged_in",
                    detail="sessão ausente ou expirada — rode `python -m shopeeops.video_count login`",
                )
            if status == 418 or status == 429:
                return VideoCount(
                    key, None, "blocked",
                    detail=f"HTTP {status} — reduza a taxa (--delay) ou troque de IP",
                )
            if status != 200:
                return VideoCount(key, None, "error", detail=f"HTTP {status}")

            if reported_total is None:
                reported_total = _extract_total(body)

            items = _extract_items(body)
            seen.extend(items)
            if len(items) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        # o total que a própria API informa é mais confiável que a paginação,
        # mas nem toda versão da resposta traz esse campo
        total = reported_total if reported_total is not None else len(seen)
        creators, views = _summarize(seen)
        return VideoCount(
            key,
            total,
            "ok" if total else "no_videos",
            creators=creators,
            total_views=views,
            detail="total informado pela API" if reported_total is not None else "contagem por paginação",
        )

    async def count_many(self, products: list[str], delay: float = 2.0) -> list[VideoCount]:
        results = []
        for i, product in enumerate(products):
            res = await self.count(product)
            results.append(res)
            log.info("%s -> %s (%s)", res.product_key, res.videos, res.status)
            if res.status == "not_logged_in":
                break
            if i + 1 < len(products):
                await asyncio.sleep(delay)
        return results


async def do_login(profile_dir: Path) -> None:
    """Abre o navegador visível para o login manual, uma vez só."""
    from playwright.async_api import async_playwright

    profile_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        kwargs: dict[str, Any] = {
            "user_data_dir": str(profile_dir),
            "headless": False,
            "locale": "pt-BR",
            "timezone_id": "America/Sao_Paulo",
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if os.getenv("SHOPEEOPS_CHROME"):
            kwargs["executable_path"] = os.environ["SHOPEEOPS_CHROME"]
        ctx = await pw.chromium.launch_persistent_context(**kwargs)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        print("\n" + "=" * 70)
        print("Faça login na Shopee nesta janela (QR code pelo app é o mais rápido).")
        print("Depois abra um vídeo qualquer em sv.shopee.com.br para confirmar.")
        print("Quando terminar, volte aqui e aperte ENTER.")
        print("=" * 70 + "\n")
        await asyncio.get_event_loop().run_in_executor(None, input)

        await ctx.close()
    print(f"Sessão salva em {profile_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contagem de vídeos por produto na Shopee")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="perfil do Chrome")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="abre o navegador para login manual (uma vez)")

    c = sub.add_parser("count", help="conta vídeos dos produtos informados")
    c.add_argument("--products", help="IDs separados por vírgula (shop_id/item_id ou URL)")
    c.add_argument("--products-file", type=Path, help="arquivo com um ID por linha")
    c.add_argument("--delay", type=float, default=2.0, help="segundos entre produtos")
    c.add_argument("--no-headless", action="store_true", help="mostra o navegador")
    c.add_argument("--json", dest="as_json", action="store_true", help="saída em JSON")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.cmd == "login":
        asyncio.run(do_login(args.profile))
        return 0

    products: list[str] = []
    if args.products:
        products += [p.strip() for p in args.products.split(",") if p.strip()]
    if args.products_file:
        products += [
            ln.strip()
            for ln in args.products_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    if not products:
        parser.error("informe --products ou --products-file")

    async def run() -> list[VideoCount]:
        async with VideoCounter(args.profile, headless=not args.no_headless) as counter:
            return await counter.count_many(products, delay=args.delay)

    results = asyncio.run(run())

    if args.as_json:
        print(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
    else:
        print(f"\n{'PRODUTO':<28}{'VÍDEOS':>8}{'CRIADORES':>11}  STATUS")
        print("-" * 72)
        for r in results:
            videos = "-" if r.videos is None else str(r.videos)
            print(f"{r.product_key:<28}{videos:>8}{r.creators:>11}  {r.status}")
            if r.status in ("not_logged_in", "blocked", "error"):
                print(f"{'':<28}{r.detail}")

    return 0 if any(r.status in ("ok", "no_videos") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

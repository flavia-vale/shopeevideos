"""
Sonda de descoberta — para de adivinhar endpoint e passa a medir.

## O que já sabemos

  sv.shopee.com.br/api/v2/timeline/unify/common
      403 error 90309999  MESMO com is_login: true

`is_login: true` e ainda assim 403 significa que o problema **não é
autenticação**. Esse endpoint veio da captura de tráfego do app (os arquivos
.mitm das primeiras sessões), e a sessão web não está autorizada a chamá-lo —
é rota de app, não de navegador. Nenhum header extra conserta isso.

  sv.shopee.com.br/api/v2/timeline/common
      200 sem cookie nenhum, mas devolve sempre os mesmos 6 vídeos e
      `page_context` vazio: resposta degradada para quem não tem sessão.

## O que esta sonda mede

1. O `timeline/common` pagina de verdade quando chamado de dentro da sua
   sessão logada? Se sim, dá para colher um corpus grande de vídeos e montar
   o índice invertido produto -> nº de vídeos.

2. Existe alguma tela web — desktop ou mobile emulado — que mostre os vídeos
   de um produto? Ela grava TODO o tráfego de rede enquanto navega e sinaliza
   qualquer resposta que contenha lista de vídeos com produto atrelado.

O resultado sai num JSON. Se nenhuma superfície web expuser isso, a resposta
é definitiva: a aba de criadores é exclusiva do app, e o caminho passa a ser
o corpus estatístico em vez da contagem exata.

## Uso

    python -m shopeeops.discover --cdp
    python -m shopeeops.discover --cdp --product 862915940/18399230627
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from shopeeops.video_count import (
    DEFAULT_CDP,
    DEFAULT_PROFILE,
    SV_ORIGIN,
    VideoCounter,
    parse_product,
)

log = logging.getLogger("shopeeops.discover")

FEED_API = f"{SV_ORIGIN}/api/v2/timeline/common"

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

_FETCH_JS = """
async ([url, payload]) => {
  const r = await fetch(url, {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  let body = null;
  try { body = await r.json(); } catch (e) { body = {_err: String(e)}; }
  return {status: r.status, body};
}
"""


def _anchor(post: dict[str, Any]) -> tuple[str, str]:
    """(chave do produto, nome) de um post, aceitando os dois formatos de resposta."""
    content = post.get("content") or {}
    prods = content.get("products") or {}
    ap = prods.get("anchor_product") or prods.get("anchorProduct") or {}
    if not ap:
        p2 = content.get("product_v2") or content.get("productV2") or {}
        ap = {
            "shop_id": p2.get("shopId") or p2.get("shop_id"),
            "item_id": p2.get("itemId") or p2.get("item_id"),
            "name": p2.get("itemName") or p2.get("item_name"),
        }
    shop, item = ap.get("shop_id"), ap.get("item_id")
    if not shop or not item:
        return "", ""
    return f"{shop}/{item}", ap.get("name") or ""


async def probe_feed(counter: VideoCounter, rounds: int) -> dict[str, Any]:
    """Tenta colher o feed dentro da sessão logada, seguindo o cursor."""
    page = counter._page
    videos: dict[str, dict[str, Any]] = {}
    ctx = ""
    stalls = 0

    for i in range(rounds):
        payload: dict[str, Any] = {"limit": 30}
        if ctx:
            payload["page_context"] = ctx
        res = await page.evaluate(_FETCH_JS, [FEED_API, payload])
        if res["status"] != 200:
            log.warning("feed parou em HTTP %s", res["status"])
            break

        data = (res["body"] or {}).get("data") or {}
        lst = data.get("list") or []
        antes = len(videos)
        for it in lst:
            post = it.get("post") or it
            meta = post.get("meta") or {}
            pid = meta.get("post_id") or meta.get("postId")
            if not pid:
                continue
            key, nome = _anchor(post)
            counts = meta.get("count_info") or meta.get("countInfo") or {}
            videos[pid] = {
                "post_id": pid,
                "produto": key,
                "nome": nome,
                "views": counts.get("views", 0),
                "criador": meta.get("user_name") or meta.get("userName", ""),
            }

        pagina = data.get("page") or {}
        ctx = pagina.get("page_context") or pagina.get("pageContext") or ""
        novos = len(videos) - antes
        log.info(
            "rodada %d: +%d itens (%d novos) | total %d | has_more=%s | cursor=%s",
            i + 1, len(lst), novos, len(videos),
            pagina.get("has_more"), "sim" if ctx else "não",
        )

        # sem cursor e sem novidade = feed travado, igual ao anônimo
        stalls = stalls + 1 if novos == 0 else 0
        if stalls >= 3:
            log.warning("feed repetindo os mesmos itens — parando")
            break
        await asyncio.sleep(0.6)

    produtos: dict[str, int] = {}
    for v in videos.values():
        if v["produto"]:
            produtos[v["produto"]] = produtos.get(v["produto"], 0) + 1

    return {
        "videos_unicos": len(videos),
        "produtos_distintos": len(produtos),
        "paginou": len(videos) > 10,
        "amostra": list(videos.values())[:20],
        "produtos_repetidos": sorted(
            ({"produto": k, "videos": n} for k, n in produtos.items() if n > 1),
            key=lambda d: -d["videos"],
        )[:20],
    }


async def sniff_product(counter: VideoCounter, product: str, mobile: bool) -> dict[str, Any]:
    """Navega a página do produto gravando a rede, atrás de listas de vídeo."""
    shop_id, item_id = parse_product(product)
    ctx = counter._ctx
    page = await ctx.new_page()
    capturado: list[dict[str, Any]] = []

    if mobile:
        cdp = await ctx.new_cdp_session(page)
        await cdp.send("Emulation.setUserAgentOverride", {"userAgent": MOBILE_UA})
        await cdp.send("Emulation.setDeviceMetricsOverride", {
            "width": 390, "height": 844, "deviceScaleFactor": 3, "mobile": True,
        })

    async def on_response(resp) -> None:
        url = resp.url
        if not any(k in url for k in ("/api/", "graphql")):
            return
        try:
            body = await resp.text()
        except Exception:
            return
        # o que interessa: resposta que fala de vídeo E de item
        marcas = sum(k in body for k in ('"post_id"', '"postId"', '"video"', '"videoId"'))
        if marcas and ('"item_id"' in body or '"itemId"' in body):
            capturado.append({
                "url": url[:300],
                "metodo": resp.request.method,
                "status": resp.status,
                "post_data": (resp.request.post_data or "")[:500],
                "trecho": body[:1200],
            })

    page.on("response", on_response)

    alvo = f"https://shopee.com.br/product/{shop_id}/{item_id}"
    log.info("navegando (%s): %s", "mobile" if mobile else "desktop", alvo)
    try:
        await page.goto(alvo, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(6000)
        for _ in range(6):
            await page.mouse.wheel(0, 1600)
            await page.wait_for_timeout(1800)
    except Exception as exc:
        log.warning("falha ao navegar: %s", exc)

    titulo = await page.title()
    # procura a aba de criadores pelo texto, sem depender de seletor
    textos = await page.evaluate(
        """() => Array.from(document.querySelectorAll('div,span,button,a'))
             .map(e => (e.textContent || '').trim())
             .filter(t => t.length < 60 && /criador|creator|v[ií]deo/i.test(t))
             .slice(0, 40)"""
    )
    await page.close()

    return {
        "modo": "mobile" if mobile else "desktop",
        "titulo": titulo,
        "textos_suspeitos": sorted(set(textos))[:25],
        "respostas_com_video": capturado[:10],
        "total_capturado": len(capturado),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    relatorio: dict[str, Any] = {}
    async with VideoCounter(args.profile, headless=False, cdp=args.cdp) as counter:
        log.info("=== 1/3  feed autenticado ===")
        relatorio["feed"] = await probe_feed(counter, args.rounds)

        log.info("=== 2/3  página do produto (desktop) ===")
        relatorio["desktop"] = await sniff_product(counter, args.product, mobile=False)

        log.info("=== 3/3  página do produto (mobile emulado) ===")
        relatorio["mobile"] = await sniff_product(counter, args.product, mobile=True)
    return relatorio


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Sonda de descoberta de endpoints da Shopee")
    p.add_argument("--cdp", nargs="?", const=DEFAULT_CDP, default=None, metavar="URL",
                   help=f"Chrome já aberto em modo depuração (padrão {DEFAULT_CDP})")
    p.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    p.add_argument("--product", default="862915940/18399230627", help="produto de teste")
    p.add_argument("--rounds", type=int, default=15, help="rodadas de paginação do feed")
    p.add_argument("--out", type=Path, default=Path("descoberta.json"))
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    try:
        relatorio = asyncio.run(run(args))
    except Exception as exc:
        log.error("%s", exc)
        return 1

    args.out.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")

    feed = relatorio["feed"]
    print("\n" + "=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(f"\nFeed autenticado: {feed['videos_unicos']} vídeos únicos, "
          f"{feed['produtos_distintos']} produtos")
    print(f"  Paginou de verdade? {'SIM' if feed['paginou'] else 'NÃO (travou igual ao anônimo)'}")
    for modo in ("desktop", "mobile"):
        r = relatorio[modo]
        print(f"\nPágina do produto ({modo}): {r['total_capturado']} resposta(s) com vídeo+item")
        if r["textos_suspeitos"]:
            print(f"  textos na tela: {', '.join(r['textos_suspeitos'][:6])}")
        for c in r["respostas_com_video"][:3]:
            print(f"  -> {c['metodo']} {c['status']} {c['url'][:110]}")
    print(f"\nRelatório completo em {args.out} — me mande esse arquivo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

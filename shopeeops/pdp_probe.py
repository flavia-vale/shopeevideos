"""
Sonda da API de detalhe do produto (PDP), dentro da sua sessão.

A sonda anterior mostrou que, na página do produto no desktop, a única
resposta que menciona vídeo e item juntos é:

    GET https://shopee.com.br/api/v4/pdp/get_pc?item_id=...&shop_id=...

Ela devolve 403 para quem chama de fora e 200 dentro do navegador logado.
Este módulo a chama de dentro da sessão e vasculha o JSON inteiro atrás de
qualquer coisa ligada a vídeo — sem supor onde o campo está, porque a
estrutura da PDP é grande e muda com frequência.

Serve para responder uma pergunta objetiva: a PDP conhece os vídeos de
afiliado desse produto, ou só os vídeos do próprio anúncio?

    python -m shopeeops.pdp_probe --cdp --product 862915940/18399230627
    python -m shopeeops.pdp_probe --cdp --url "https://shopee.com.br/api/..."
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterator

from shopeeops.video_count import DEFAULT_CDP, DEFAULT_PROFILE, VideoCounter, parse_product

log = logging.getLogger("shopeeops.pdp")

PDP_URL = (
    "https://shopee.com.br/api/v4/pdp/get_pc"
    "?item_id={item_id}&shop_id={shop_id}&tz_offset_in_minutes=-180&detail_level=0"
)

# GET de dentro da página: herda cookies, fingerprint e tokens do SDK
_GET_JS = """
async (url) => {
  const r = await fetch(url, {credentials: 'include',
    headers: {'X-Requested-With': 'XMLHttpRequest'}});
  let body = null;
  try { body = await r.json(); } catch (e) { body = {_err: String(e)}; }
  return {status: r.status, body};
}
"""

# nomes que denunciam contagem, não só mídia solta
_COUNT_HINTS = ("count", "total", "num", "qty", "quantity")
_VIDEO_HINTS = ("video", "sv_", "creator", "criador", "ugc", "timeline", "post")


def walk(obj: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            yield p, v
            yield from walk(v, p)
    elif isinstance(obj, list):
        yield f"{path}[]", f"<lista de {len(obj)}>"
        for i, v in enumerate(obj[:3]):
            yield from walk(v, f"{path}[{i}]")


def video_fields(body: Any) -> list[tuple[str, str]]:
    """Todo caminho cujo nome sugere vídeo, com um resumo do valor."""
    achados = []
    for path, val in walk(body):
        nome = path.rsplit(".", 1)[-1].lower()
        if any(h in nome for h in _VIDEO_HINTS):
            resumo = json.dumps(val, ensure_ascii=False)[:220] if not isinstance(val, str) else val[:220]
            achados.append((path, resumo))
    return achados


def count_candidates(body: Any) -> list[tuple[str, int]]:
    """Números que parecem contagem de vídeo.

    Olha o caminho inteiro, não só a folha: em `creator_video.total_count` a
    pista de vídeo está no pai e a de contagem no filho, e é justamente esse
    formato que interessa.
    """
    out = []
    for path, val in walk(body):
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            continue
        baixo = path.lower()
        nome = baixo.rsplit(".", 1)[-1]
        if any(h in baixo for h in _VIDEO_HINTS) and any(h in nome for h in _COUNT_HINTS):
            out.append((path, val))
    return out


def sv_list_len(body: Any) -> int | None:
    """Tamanho de shopee_video_info_list — o candidato mais direto a contagem.

    Vazia num produto que comprovadamente tem vídeo de afiliado significa que
    a web não popula o campo. Preenchida significa que achamos o contador.
    """
    for path, val in walk(body):
        if path.endswith("shopee_video_info_list") and isinstance(val, list):
            return len(val)
    return None


async def probe_many(args: argparse.Namespace) -> int:
    """Compara vários produtos de uma vez — é assim que se separa
    'campo vazio porque não tem vídeo' de 'campo que a web nunca preenche'."""
    produtos = [p.strip() for p in args.products.split(",") if p.strip()]
    linhas = []

    async with VideoCounter(args.profile, headless=False, cdp=args.cdp) as counter:
        page = counter._page
        for prod in produtos:
            shop_id, item_id = parse_product(prod)
            await page.goto(
                f"https://shopee.com.br/product/{shop_id}/{item_id}",
                wait_until="domcontentloaded", timeout=60_000,
            )
            await page.wait_for_timeout(2500)
            res = await page.evaluate(
                _GET_JS, PDP_URL.format(shop_id=shop_id, item_id=item_id)
            )
            body = res["body"]
            n = sv_list_len(body) if res["status"] == 200 else None
            linhas.append((f"{shop_id}/{item_id}", res["status"], n, count_candidates(body)))
            log.info("%s/%s -> HTTP %s, shopee_video_info_list=%s",
                     shop_id, item_id, res["status"], n)
            await asyncio.sleep(1.5)

    print(f"\n{'PRODUTO':<26}{'HTTP':>6}{'sv_video_info_list':>21}  OUTRAS CONTAGENS")
    print("-" * 82)
    for key, status, n, cands in linhas:
        extra = ", ".join(f"{p.rsplit('.',1)[-1]}={v}" for p, v in cands[:3]) or "—"
        print(f"{key:<26}{status:>6}{('vazia' if n == 0 else n if n is not None else '—'):>21}  {extra}")

    populadas = [n for _, _, n, _ in linhas if n]
    print()
    if populadas:
        print("ACHAMOS: a lista vem preenchida — dá para contar por aqui.")
    else:
        print("A lista veio vazia em TODOS, inclusive nos que comprovadamente têm")
        print("vídeo de afiliado. Conclusão: a web não popula esse campo.")
    return 0


async def run(args: argparse.Namespace) -> int:
    if args.products:
        return await probe_many(args)

    if args.url:
        url = args.url
    else:
        shop_id, item_id = parse_product(args.product)
        url = PDP_URL.format(shop_id=shop_id, item_id=item_id)

    # a chamada tem que sair da origem shopee.com.br (a VideoCounter aquece na
    # sv.shopee.com.br, que é outra origem e levaria a CORS)
    origem = (
        "https://shopee.com.br/"
        if args.url
        else f"https://shopee.com.br/product/{parse_product(args.product)[0]}"
             f"/{parse_product(args.product)[1]}"
    )

    async with VideoCounter(args.profile, headless=False, cdp=args.cdp) as counter:
        await counter._page.goto(origem, wait_until="domcontentloaded", timeout=60_000)
        await counter._page.wait_for_timeout(3000)
        log.info("chamando %s", url[:120])
        res = await counter._page.evaluate(_GET_JS, url)

    status, body = res["status"], res["body"]
    print(f"\nHTTP {status}")
    if status != 200:
        print(json.dumps(body, ensure_ascii=False)[:600])
        print("\n403 aqui significa que a chamada saiu de uma origem/sessão que a "
              "Shopee não aceita. Confirme que o Chrome do --cdp está logado.")
        return 1

    achados = video_fields(body)
    args.out.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(achados)} campo(s) com cara de vídeo:\n")
    for path, val in achados[:60]:
        print(f"  {path}\n      {val}")

    contagens = count_candidates(body)
    if contagens:
        print("\n>>> Candidatos a CONTAGEM de vídeos:")
        for path, val in contagens:
            print(f"  {path} = {val}")
    else:
        print("\nNenhum campo numérico com cara de contagem de vídeos.")

    print(f"\nJSON completo em {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Sonda da PDP dentro da sessão logada")
    p.add_argument("--cdp", nargs="?", const=DEFAULT_CDP, default=None, metavar="URL")
    p.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    p.add_argument("--product", default="862915940/18399230627")
    p.add_argument("--products", help="vários produtos separados por vírgula, para comparar")
    p.add_argument("--url", help="chama esta URL em vez da PDP padrão")
    p.add_argument("--out", type=Path, default=Path("pdp.json"))
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

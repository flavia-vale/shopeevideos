#!/usr/bin/env python3
"""
Encontra produtos bons para gravar vídeo na Shopee.

Fluxo:

  1. busca candidatos na Open API oficial de afiliados (comissão + vendas)
  2. filtra os que valem o custo de checar (comissão e demanda mínimas)
  3. conta os vídeos já publicados de cada um, num Chrome logado
  4. ranqueia: ganho x demanda / disputa

O passo 3 é o caro (precisa de navegador e é lento), por isso ele só roda
depois do filtro do passo 2 — não adianta contar vídeo de produto que já
foi descartado por comissão baixa.

Exemplos:

    # varredura geral do catálogo de maior comissão
    python oportunidades.py --limit 60

    # nicho específico
    python oportunidades.py --keyword "organizador de cozinha" --limit 40

    # sem navegador: só comissão e demanda, bem mais rápido
    python oportunidades.py --keyword fone --sem-contagem

    # salva para abrir no Excel
    python oportunidades.py --limit 100 --csv oportunidades.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv é conveniência, não requisito
    pass

from shopeeops import scoring
from shopeeops.affiliate_api import AffiliateClient, AffiliateAPIError

log = logging.getLogger("oportunidades")

CSV_COLUMNS = [
    "score", "verdict", "product_key", "name", "price", "commission_pct",
    "commission_brl", "sales", "rating", "videos", "creators", "shop_name",
    "offer_link", "reasons",
]


def collect_offers(args: argparse.Namespace) -> list:
    with AffiliateClient() as client:
        offers = list(
            client.product_offers(
                keyword=args.keyword,
                list_type=args.list_type,
                limit=min(args.limit, 50),
                max_pages=max(1, -(-args.limit // 50)),
            )
        )[: args.limit]

    log.info("catálogo: %d ofertas recebidas", len(offers))

    kept = [
        o
        for o in offers
        if o.commission_pct >= args.min_comissao and o.sales >= args.min_vendas
    ]
    log.info(
        "filtro (comissão >= %.1f%%, vendas >= %d): %d candidatos",
        args.min_comissao, args.min_vendas, len(kept),
    )
    return kept


def load_counts_csv(path: Path) -> dict:
    """Lê o CSV gerado por console/contar_videos.js.

    Esse é o caminho para quem não pode instalar nada: o navegador conta e
    baixa o CSV, e aqui a gente só junta com a comissão.
    """
    counts: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            key = (row.get("chave") or row.get("product_key") or "").strip()
            if not key:
                continue
            raw = (row.get("videos") or "").strip()
            counts[key] = {
                "videos": int(raw) if raw.isdigit() else None,
                "creators": int((row.get("criadores") or "0").strip() or 0),
            }
    log.info("contagens carregadas de %s: %d produtos", path, len(counts))
    return counts


def count_videos(offers: list, args: argparse.Namespace) -> dict:
    from shopeeops.video_count import VideoCounter

    targets = [o.product_key for o in offers][: args.max_contagens]
    log.info("contando vídeos de %d produtos (isso demora)…", len(targets))

    async def run():
        async with VideoCounter(
            args.profile, headless=not args.no_headless, cdp=args.cdp
        ) as counter:
            return await counter.count_many(targets, delay=args.delay)

    try:
        results = asyncio.run(run())
    except Exception as exc:
        log.error("navegador: %s", exc)
        return {}

    if results and all(r.status == "not_logged_in" for r in results):
        log.error(
            "sessão do navegador ausente ou expirada. "
            "Rode: python -m shopeeops.video_count login"
        )
    return {r.product_key: r for r in results}


def write_csv(path: Path, ops: list) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for op in ops:
            writer.writerow(op.to_dict())


def print_table(ops: list, top: int) -> None:
    print(f"\n{'#':>3}  {'SCORE':>6}  {'COMIS':>6}  {'R$/VD':>7}  {'VEND':>7}  {'VÍD':>5}  PRODUTO")
    print("-" * 100)
    for i, op in enumerate(ops[:top], 1):
        videos = "?" if op.videos is None else str(op.videos)
        name = op.name[:44] + ("…" if len(op.name) > 44 else "")
        print(
            f"{i:>3}  {op.score:>6.1f}  {op.commission_pct:>5.1f}%  "
            f"{op.commission_brl:>7.2f}  {op.sales:>7}  {videos:>5}  {name}"
        )
    print("\nDetalhe dos melhores:")
    for op in ops[: min(top, 10)]:
        print(f"\n  [{op.score:.1f}] {op.name[:70]}")
        print(f"      {op.verdict} — {' | '.join(op.reasons)}")
        print(f"      {op.product_key}  {op.offer_link}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Ranking de oportunidades para Shopee Video",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--keyword", help="nicho a pesquisar; sem isso, varre o catálogo geral")
    p.add_argument("--limit", type=int, default=50, help="quantas ofertas buscar (padrão 50)")
    p.add_argument("--list-type", type=int, default=1,
                   help="0=recomendados 1=maior comissão 2=melhor performance (padrão 1)")
    p.add_argument("--min-comissao", type=float, default=8.0,
                   help="descarta comissão abaixo disso, em %% (padrão 8)")
    p.add_argument("--min-vendas", type=int, default=20,
                   help="descarta produto com menos vendas que isso (padrão 20)")
    p.add_argument("--max-contagens", type=int, default=40,
                   help="teto de produtos para contar vídeo (padrão 40)")
    p.add_argument("--sem-contagem", action="store_true",
                   help="pula o navegador; ranqueia só por comissão e demanda")
    p.add_argument("--contagens", type=Path,
                   help="CSV vindo de console/contar_videos.js, em vez de abrir navegador")
    p.add_argument("--lista-produtos", type=Path,
                   help="salva os candidatos num .txt pronto para colar no script do console")
    p.add_argument("--delay", type=float, default=2.0, help="segundos entre contagens")
    p.add_argument("--no-headless", action="store_true", help="mostra o navegador")
    p.add_argument("--cdp", nargs="?", const="http://127.0.0.1:9222", default=None,
                   metavar="URL",
                   help="conecta a um Chrome já aberto em modo depuração, "
                        "em vez de abrir um novo (resolve captcha no login)")
    p.add_argument("--profile", type=Path, default=None, help="perfil do Chrome")
    p.add_argument("--top", type=int, default=25, help="linhas na tabela (padrão 25)")
    p.add_argument("--csv", type=Path, help="salva o ranking completo em CSV")
    p.add_argument("--json", dest="as_json", type=Path, help="salva o ranking completo em JSON")
    p.add_argument("--debug", action="store_true")

    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.profile is None:
        from shopeeops.video_count import DEFAULT_PROFILE

        args.profile = DEFAULT_PROFILE

    try:
        offers = collect_offers(args)
    except AffiliateAPIError as exc:
        log.error("Open API de afiliados: %s", exc)
        return 2

    if not offers:
        log.warning("nenhum candidato passou no filtro — afrouxe --min-comissao / --min-vendas")
        return 1

    if args.lista_produtos:
        args.lista_produtos.write_text(
            "\n".join(o.product_key for o in offers) + "\n", encoding="utf-8"
        )
        log.info("lista de candidatos salva em %s", args.lista_produtos)

    if args.contagens:
        counts = load_counts_csv(args.contagens)
    elif args.sem_contagem:
        counts = {}
    else:
        counts = count_videos(offers, args)

    ops = scoring.build(offers, counts)

    print_table(ops, args.top)

    if args.csv:
        write_csv(args.csv, ops)
        log.info("CSV salvo em %s", args.csv)
    if args.as_json:
        args.as_json.write_text(
            json.dumps([o.to_dict() for o in ops], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("JSON salvo em %s", args.as_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())

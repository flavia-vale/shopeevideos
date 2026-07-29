"""
Leitor público do Shopee Video — sem login, sem cookie, sem anti-bot.

Descoberta que destrava o projeto: as páginas de vídeo de sv.shopee.com.br são
renderizadas no servidor (Next.js, getServerSideProps) e marcadas com
`robots: index, follow`. O HTML já vem com o blob `__NEXT_DATA__` inteiro.

    https://sv.shopee.com.br/web/@{usuario}/video/{postId}

Um GET simples devolve 200 com, entre outras coisas:

    content.productV2.itemId / .shopId / .itemName     produto anunciado
    content.productV2.sellStat.sold / .historicalSold  demanda
    meta.countInfo.views / .likes / .comments          performance do vídeo
    meta.userName / .userId / .ctime                   quem postou e quando
    content.hashtags                                   hashtags usadas

Ou seja: dá para ligar vídeo -> produto e medir performance de concorrentes
sem tocar em nenhuma API bloqueada. É a base do corpus de concorrência.

Limite honesto: não existe rota pública para *listar* vídeos de um produto nem
o perfil de um criador (ambas dão 404). Este módulo resolve vídeos que você já
tem a URL — a contagem por produto fica com `video_count.py`.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Iterable

import httpx

log = logging.getLogger("shopeeops.sv_public")

BASE = "https://sv.shopee.com.br"
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_NEXT_DATA_RE = re.compile(r'(\{"props":\{"pageProps".*?\})</script>', re.S)
# aceita /web/@user/video/<id>, /share-video/<id> e links s.shopee encurtados
_POST_URL_RE = re.compile(r"sv\.shopee\.com\.br/(?:web/@([^/]+)/video|share-video)/([^/?#\s\"']+)")
_PRODUCT_RE = re.compile(r"product-i\.(\d+)\.(\d+)|product/(\d+)/(\d+)")

PRICE_SCALE = 100_000  # a Shopee manda preço em micro-unidades


@dataclass
class VideoPost:
    """Um post do Shopee Video, extraído da página pública."""

    post_id: str
    url: str
    user_name: str = ""
    user_id: int = 0
    created_at: int = 0          # epoch em segundos
    views: int = 0
    likes: int = 0
    comments: int = 0
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    item_id: int = 0
    shop_id: int = 0
    product_name: str = ""
    price: float = 0.0
    sold_recent: int = 0
    sold_total: int = 0
    rating: float = 0.0
    offer_link: str = ""

    @property
    def product_key(self) -> str:
        return f"{self.shop_id}/{self.item_id}" if self.item_id else ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["product_key"] = self.product_key
        return d


def parse_post_url(url: str) -> str | None:
    """Extrai o postId de qualquer formato de link de vídeo da Shopee."""
    m = _POST_URL_RE.search(url)
    if m:
        return m.group(2)
    return None


def _dig(obj: Any, *path: str, default: Any = None) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key)
        if obj is None:
            return default
    return obj


def parse_next_data(html: str, url: str = "") -> VideoPost | None:
    """Converte o HTML de uma página de vídeo em VideoPost."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        log.debug("__NEXT_DATA__ não encontrado em %s", url)
        return None
    try:
        blob = json.loads(m.group(1))
    except json.JSONDecodeError:
        log.debug("__NEXT_DATA__ ilegível em %s", url)
        return None

    items = _dig(blob, "props", "pageProps", "timelineVideo", "list", default=[]) or []
    if not items:
        return None
    node = items[0]

    meta = node.get("meta") or {}
    content = node.get("content") or {}
    # productV2 é o formato atual; anchorProduct é o legado — ambos aparecem
    prod = content.get("productV2") or {}
    anchor = _dig(content, "products", "anchorProduct", default={}) or {}

    ctime_ms = meta.get("ctime") or meta.get("ptime") or 0

    post = VideoPost(
        post_id=meta.get("postId") or parse_post_url(url) or "",
        url=url,
        user_name=meta.get("userName") or "",
        user_id=int(meta.get("userId") or 0),
        created_at=int(ctime_ms // 1000) if ctime_ms else 0,
        views=int(_dig(meta, "countInfo", "views", default=0) or 0),
        likes=int(_dig(meta, "countInfo", "likes", default=0) or 0),
        comments=int(_dig(meta, "countInfo", "comments", default=0) or 0),
        caption=content.get("caption") or "",
        duration_s=round((_dig(content, "video", "duration", default=0) or 0) / 1000, 1),
        item_id=int(prod.get("itemId") or anchor.get("itemId") or 0),
        shop_id=int(prod.get("shopId") or anchor.get("shopId") or 0),
        product_name=prod.get("itemName") or anchor.get("name") or "",
        rating=float(_dig(prod, "reviewRating", "ratingStar", default=0.0) or 0.0),
        sold_recent=int(_dig(prod, "sellStat", "sold", default=0) or 0),
        sold_total=int(_dig(prod, "sellStat", "historicalSold", default=0) or 0),
        offer_link=_dig(prod, "affiliateTracking", "offerLink", default="")
        or anchor.get("offerLink", ""),
    )

    raw_price = prod.get("itemPrice", {}).get("price") or anchor.get("price") or 0
    post.price = round(raw_price / PRICE_SCALE, 2) if raw_price else 0.0

    caption = post.caption
    for tag in content.get("hashtags") or []:
        start, length = tag.get("start", 0), tag.get("length", 0)
        text = caption[start : start + length].lstrip("#")
        if text:
            post.hashtags.append(text)

    # fallback: alguns posts antigos só trazem o produto no ld+json
    if not post.item_id:
        pm = _PRODUCT_RE.search(html)
        if pm:
            a, b, c, d = pm.groups()
            post.shop_id, post.item_id = int(a or c or 0), int(b or d or 0)

    return post


class PublicVideoReader:
    """Busca e interpreta páginas públicas do Shopee Video."""

    def __init__(self, timeout: float = 25.0, min_interval: float = 1.0) -> None:
        self._min_interval = min_interval
        self._last = 0.0
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": DESKTOP_UA,
                "Accept-Language": "pt-BR,pt;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

    def _throttle(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def fetch(self, url_or_post_id: str) -> VideoPost | None:
        """Lê um vídeo a partir da URL completa ou só do postId.

        Sempre normalizamos para a rota /web/@.../video/<postId>: ela é a única
        que traz o produto no SSR (a /share-video só devolve mídia e legenda).
        O apelido no caminho é decorativo — a Shopee resolve pelo postId — então
        qualquer placeholder serve quando não sabemos quem postou.
        """
        post_id = parse_post_url(url_or_post_id) or url_or_post_id.strip()
        user = "x"
        m = _POST_URL_RE.search(url_or_post_id)
        if m and m.group(1):
            user = m.group(1)
        url = f"{BASE}/web/@{user}/video/{post_id}"

        self._throttle()
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            log.warning("falha de rede em %s: %s", url, exc)
            return None

        if resp.status_code != 200:
            log.warning("HTTP %d em %s", resp.status_code, url)
            return None
        return parse_next_data(resp.text, str(resp.url))

    def fetch_many(self, urls: Iterable[str]) -> list[VideoPost]:
        out = []
        for u in urls:
            post = self.fetch(u.strip())
            if post:
                out.append(post)
        return out

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PublicVideoReader":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def aggregate_by_product(posts: Iterable[VideoPost]) -> dict[str, dict[str, Any]]:
    """Agrupa um corpus de vídeos por produto — o índice invertido de concorrência.

    Para cada produto: quantos vídeos você já viu, quanta audiência eles somam,
    e se o último é recente. Views medianas altas com poucos vídeos é o padrão
    mais interessante: o produto engaja e ainda tem pouca gente postando.
    """
    from statistics import median

    index: dict[str, dict[str, Any]] = {}
    for p in posts:
        key = p.product_key
        if not key:
            continue
        entry = index.setdefault(
            key,
            {
                "product_key": key,
                "shop_id": p.shop_id,
                "item_id": p.item_id,
                "product_name": p.product_name,
                "videos_seen": 0,
                "creators": set(),
                "views": [],
                "total_views": 0,
                "last_video_at": 0,
                "sold_total": p.sold_total,
            },
        )
        entry["videos_seen"] += 1
        entry["creators"].add(p.user_name)
        entry["views"].append(p.views)
        entry["total_views"] += p.views
        entry["last_video_at"] = max(entry["last_video_at"], p.created_at)
        entry["sold_total"] = max(entry["sold_total"], p.sold_total)

    for entry in index.values():
        views = entry.pop("views")
        entry["creators"] = len(entry["creators"])
        entry["median_views"] = int(median(views)) if views else 0
    return index


def _main(argv: list[str] | None = None) -> int:
    """CLI: lê vídeos públicos e monta o índice produto -> concorrência.

        python -m shopeeops.sv_public URL [URL ...]
        python -m shopeeops.sv_public --file lista_de_videos.txt --json corpus.json
    """
    import argparse

    p = argparse.ArgumentParser(description="Leitor público do Shopee Video (sem login)")
    p.add_argument("urls", nargs="*", help="URLs ou postIds de vídeos")
    p.add_argument("--file", type=str, help="arquivo com uma URL por linha")
    p.add_argument("--json", dest="out", type=str, help="salva os vídeos lidos em JSON")
    p.add_argument("--delay", type=float, default=1.0, help="segundos entre requisições")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    urls = list(args.urls)
    if args.file:
        from pathlib import Path

        urls += [
            ln.strip()
            for ln in Path(args.file).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    if not urls:
        p.error("informe ao menos uma URL ou --file")

    with PublicVideoReader(min_interval=args.delay) as reader:
        posts = reader.fetch_many(urls)

    print(f"\n{len(posts)}/{len(urls)} vídeos lidos\n")
    for post in posts:
        print(f"  @{post.user_name}  {post.views} views, {post.likes} likes")
        print(f"    {post.product_name[:64]}")
        print(f"    {post.product_key}  R$ {post.price:.2f}  {post.sold_total} vendidos\n")

    index = aggregate_by_product(posts)
    if index:
        print("Concorrência por produto (dentro deste corpus):\n")
        print(f"  {'VÍDEOS':>6} {'CRIAD':>6} {'VIEWS MED':>10}  PRODUTO")
        for entry in sorted(index.values(), key=lambda e: -e["videos_seen"]):
            print(
                f"  {entry['videos_seen']:>6} {entry['creators']:>6} "
                f"{entry['median_views']:>10}  {entry['product_name'][:50]}"
            )

    if args.out:
        from pathlib import Path

        Path(args.out).write_text(
            json.dumps([p.to_dict() for p in posts], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nsalvo em {args.out}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main())

"""
Cliente da Open API oficial de Afiliados da Shopee (GraphQL).

Esta é a fonte de comissão e demanda. Diferente das APIs internas
(sv.shopee.com.br/api/...), esta é oficial, assinada com HMAC e não passa
por anti-bot — não existe 418 aqui.

Credenciais: painel de afiliados > Open API. Coloque em .env:

    SHOPEE_APP_ID=...
    SHOPEE_APP_SECRET=...

Autenticação:
    Authorization: SHA256 Credential={AppId}, Timestamp={ts}, Signature={sig}
    sig = sha256(AppId + Timestamp + Payload + Secret)

O Payload assinado tem que ser byte a byte o mesmo corpo enviado — por isso
serializamos o JSON uma única vez e mandamos como `content=`, nunca `json=`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Iterator

import httpx

log = logging.getLogger("shopeeops.affiliate")

ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"

# listType: 0=recomendados 1=maior comissão 2=melhor performance 3=mais vendidos
LIST_TYPE_HIGHEST_COMMISSION = 1

_PRODUCT_FIELDS = """
  itemId
  shopId
  productName
  productLink
  offerLink
  imageUrl
  price
  priceMin
  priceMax
  priceDiscountRate
  sales
  ratingStar
  commissionRate
  sellerCommissionRate
  shopeeCommissionRate
  commission
  shopName
  shopType
  productCatIds
  periodStartTime
  periodEndTime
"""

PRODUCT_OFFER_QUERY = """
query ProductOfferV2($keyword: String, $shopId: Int64, $itemId: Int64,
                     $listType: Int, $sortType: Int, $page: Int, $limit: Int) {
  productOfferV2(keyword: $keyword, shopId: $shopId, itemId: $itemId,
                 listType: $listType, sortType: $sortType, page: $page, limit: $limit) {
    nodes { %s }
    pageInfo { page limit hasNextPage scrollId }
  }
}
""" % _PRODUCT_FIELDS

SHORT_LINK_MUTATION = """
mutation GenerateShortLink($input: ShortLinkInput!) {
  generateShortLink(input: $input) { shortLink }
}
"""


class AffiliateAPIError(RuntimeError):
    pass


@dataclass
class ProductOffer:
    """Uma oferta de produto do catálogo de afiliados."""

    item_id: int
    shop_id: int
    name: str
    product_link: str
    offer_link: str
    image_url: str
    price: float
    discount_rate: float
    sales: int
    rating: float
    commission_rate: float          # fração: 0.38 == 38%
    seller_commission_rate: float
    shopee_commission_rate: float
    commission_value: float         # R$ por venda, quando a API informa
    shop_name: str
    shop_type: list[int]
    cat_ids: list[int]

    @property
    def product_key(self) -> str:
        return f"{self.shop_id}/{self.item_id}"

    @property
    def commission_pct(self) -> float:
        return round(self.commission_rate * 100, 2)

    @property
    def commission_brl(self) -> float:
        """Comissão estimada em reais por venda."""
        if self.commission_value:
            return round(self.commission_value, 2)
        return round(self.price * self.commission_rate, 2)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["product_key"] = self.product_key
        d["commission_pct"] = self.commission_pct
        d["commission_brl"] = self.commission_brl
        return d

    @classmethod
    def from_node(cls, n: dict[str, Any]) -> "ProductOffer":
        def num(key: str, default: float = 0.0) -> float:
            v = n.get(key)
            if v in (None, ""):
                return default
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        return cls(
            item_id=int(n.get("itemId") or 0),
            shop_id=int(n.get("shopId") or 0),
            name=n.get("productName") or "",
            product_link=n.get("productLink") or "",
            offer_link=n.get("offerLink") or "",
            image_url=n.get("imageUrl") or "",
            price=num("price"),
            discount_rate=num("priceDiscountRate"),
            sales=int(num("sales")),
            rating=num("ratingStar"),
            commission_rate=num("commissionRate"),
            seller_commission_rate=num("sellerCommissionRate"),
            shopee_commission_rate=num("shopeeCommissionRate"),
            commission_value=num("commission"),
            shop_name=n.get("shopName") or "",
            shop_type=list(n.get("shopType") or []),
            cat_ids=list(n.get("productCatIds") or []),
        )


class AffiliateClient:
    """Cliente síncrono da Open API de afiliados."""

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        timeout: float = 30.0,
        min_interval: float = 0.35,
    ) -> None:
        self.app_id = app_id or os.getenv("SHOPEE_APP_ID", "")
        self.app_secret = app_secret or os.getenv("SHOPEE_APP_SECRET", "")
        if not self.app_id or not self.app_secret:
            raise AffiliateAPIError(
                "SHOPEE_APP_ID / SHOPEE_APP_SECRET ausentes. "
                "Gere em https://affiliate.shopee.com.br > Open API e salve no .env"
            )
        self._min_interval = min_interval
        self._last_call = 0.0
        self._client = httpx.Client(timeout=timeout, headers={"User-Agent": "shopeeops/3.0"})

    # ── infra ────────────────────────────────────────────────────────────

    def _sign(self, payload: str) -> tuple[str, int]:
        ts = int(time.time())
        raw = f"{self.app_id}{ts}{payload}{self.app_secret}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest(), ts

    def _throttle(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body = {"query": query, "variables": variables or {}}
        # separators sem espaço: o payload assinado precisa bater com o enviado
        payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        signature, ts = self._sign(payload)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={self.app_id}, Timestamp={ts}, Signature={signature}",
        }

        self._throttle()
        resp = self._client.post(ENDPOINT, content=payload.encode("utf-8"), headers=headers)

        if resp.status_code != 200:
            raise AffiliateAPIError(f"HTTP {resp.status_code}: {resp.text[:400]}")

        data = resp.json()
        if data.get("errors"):
            msg = "; ".join(str(e.get("message", e)) for e in data["errors"])
            if "signature" in msg.lower():
                msg += (
                    "  [dica: relógio do sistema fora de hora, ou App Secret errado — "
                    "a assinatura usa timestamp em segundos com janela de ~5 min]"
                )
            raise AffiliateAPIError(msg)
        return data.get("data") or {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AffiliateClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── queries ──────────────────────────────────────────────────────────

    def product_offers(
        self,
        keyword: str | None = None,
        shop_id: int | None = None,
        item_id: int | None = None,
        list_type: int = LIST_TYPE_HIGHEST_COMMISSION,
        sort_type: int | None = None,
        limit: int = 50,
        max_pages: int = 10,
    ) -> Iterator[ProductOffer]:
        """Itera ofertas, paginando até `max_pages` ou o fim da lista.

        Sem `keyword`, devolve o catálogo por `list_type` — é assim que se
        varre "tudo que tem comissão alta" sem depender de busca por texto.
        """
        page = 1
        while page <= max_pages:
            variables: dict[str, Any] = {"page": page, "limit": limit, "listType": list_type}
            if keyword:
                variables["keyword"] = keyword
            if shop_id:
                variables["shopId"] = shop_id
            if item_id:
                variables["itemId"] = item_id
            if sort_type is not None:
                variables["sortType"] = sort_type

            block = self.execute(PRODUCT_OFFER_QUERY, variables).get("productOfferV2") or {}
            nodes = block.get("nodes") or []
            if not nodes:
                return

            for node in nodes:
                yield ProductOffer.from_node(node)

            log.debug("productOfferV2 página %d: %d itens", page, len(nodes))
            if not (block.get("pageInfo") or {}).get("hasNextPage"):
                return
            page += 1

    def offer_for_item(self, shop_id: int, item_id: int) -> ProductOffer | None:
        """Comissão de um produto específico, ou None se não estiver no catálogo."""
        for offer in self.product_offers(shop_id=shop_id, item_id=item_id, limit=1, max_pages=1):
            return offer
        return None

    def short_link(self, origin_url: str, sub_ids: list[str] | None = None) -> str:
        """Gera o link de afiliado rastreável para uma URL da Shopee."""
        payload = {"originUrl": origin_url, "subIds": (sub_ids or [])[:5]}
        data = self.execute(SHORT_LINK_MUTATION, {"input": payload})
        return ((data.get("generateShortLink") or {}).get("shortLink")) or ""

"""
Ranking de oportunidade.

A pergunta prática é "qual produto eu gravo agora?", e ela tem três fatores que
puxam em direções diferentes:

  ganho       quanto entra no bolso por venda      (comissão em R$)
  demanda     quanta gente compra isso             (vendas)
  disputa     quantos afiliados já postaram        (nº de vídeos)

Nenhum sozinho decide. Comissão alta em produto que ninguém compra não paga
nada; produto que vende muito e já tem 200 vídeos é briga perdida. O score
multiplica ganho por demanda e divide pela disputa.

Usamos log na demanda de propósito: a diferença entre 10 e 100 vendas importa
muito mais que entre 5.000 e 5.090. E somamos 1 no denominador para que "zero
vídeos" seja o melhor caso possível, não uma divisão por zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from typing import Any, Iterable

# pesos do score final; expostos para calibrar sem mexer na fórmula
COMMISSION_WEIGHT = 1.0
DEMAND_WEIGHT = 1.0
COMPETITION_EXPONENT = 1.0   # >1 pune saturação com mais força

BLUE_OCEAN_MAX_VIDEOS = 5
GOOD_COMMISSION_PCT = 10.0


@dataclass
class Opportunity:
    product_key: str
    name: str
    price: float = 0.0
    commission_pct: float = 0.0
    commission_brl: float = 0.0
    sales: int = 0
    rating: float = 0.0
    videos: int | None = None
    creators: int = 0
    offer_link: str = ""
    shop_name: str = ""

    raw_score: float = 0.0
    score: float = 0.0           # 0-100, normalizado dentro do lote
    verdict: str = ""
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reasons"] = " | ".join(self.reasons)
        return d


def _raw_score(commission_brl: float, sales: int, videos: int | None) -> float:
    ganho = max(commission_brl, 0.0) ** COMMISSION_WEIGHT
    demanda = math.log1p(max(sales, 0)) ** DEMAND_WEIGHT
    # vídeos desconhecidos: assume a fronteira do "oceano azul" para não
    # premiar um produto só por faltar dado sobre ele
    disputa = (1 + (BLUE_OCEAN_MAX_VIDEOS if videos is None else max(videos, 0))) ** COMPETITION_EXPONENT
    return ganho * demanda / disputa


def _classify(op: Opportunity) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if op.commission_pct >= GOOD_COMMISSION_PCT:
        reasons.append(f"comissão de {op.commission_pct:.0f}%")
    if op.commission_brl >= 10:
        reasons.append(f"R$ {op.commission_brl:.2f} por venda")
    if op.sales >= 100:
        reasons.append(f"{op.sales} vendas")
    if op.rating >= 4.7:
        reasons.append(f"nota {op.rating:.1f}")

    if op.videos is None:
        return "sem dado de vídeos", reasons + ["contagem de vídeos não coletada"]

    if op.videos == 0:
        reasons.append("nenhum vídeo publicado")
        verdict = "oceano azul"
    elif op.videos <= BLUE_OCEAN_MAX_VIDEOS:
        reasons.append(f"só {op.videos} vídeos")
        verdict = "oceano azul"
    elif op.videos <= 20:
        reasons.append(f"{op.videos} vídeos")
        verdict = "disputado"
    else:
        reasons.append(f"{op.videos} vídeos — saturado")
        verdict = "saturado"

    if verdict == "oceano azul" and op.sales < 10:
        verdict = "oceano azul (sem demanda comprovada)"
        reasons.append("pouca venda — pode ser produto ruim, não oportunidade")

    return verdict, reasons


def build(
    offers: Iterable[Any],
    video_counts: dict[str, Any] | None = None,
) -> list[Opportunity]:
    """Combina ofertas (ProductOffer) com contagens de vídeo e ranqueia.

    `video_counts` mapeia 'shop_id/item_id' -> VideoCount (ou dict equivalente).
    Produtos sem contagem entram no ranking marcados como tal.
    """
    counts = video_counts or {}
    result: list[Opportunity] = []

    for offer in offers:
        key = offer.product_key
        vc = counts.get(key)
        videos = getattr(vc, "videos", None) if vc is not None else None
        creators = getattr(vc, "creators", 0) if vc is not None else 0
        if isinstance(vc, dict):
            videos, creators = vc.get("videos"), vc.get("creators", 0)

        op = Opportunity(
            product_key=key,
            name=offer.name,
            price=offer.price,
            commission_pct=offer.commission_pct,
            commission_brl=offer.commission_brl,
            sales=offer.sales,
            rating=offer.rating,
            videos=videos,
            creators=creators,
            offer_link=offer.offer_link,
            shop_name=offer.shop_name,
        )
        op.raw_score = _raw_score(op.commission_brl, op.sales, op.videos)
        op.verdict, op.reasons = _classify(op)
        result.append(op)

    top = max((o.raw_score for o in result), default=0.0)
    for op in result:
        op.score = round(100 * op.raw_score / top, 1) if top else 0.0

    result.sort(key=lambda o: o.raw_score, reverse=True)
    return result

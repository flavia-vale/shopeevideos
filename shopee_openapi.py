"""
Cliente da Shopee Affiliate Open API.

Serve para montar a lista de candidatos: a API oficial devolve catálogo, vendas
e comissão em escala e sem anti-bot, mas não expõe quantos afiliados estão
promovendo. O fluxo é em dois tempos:

    shopee_openapi.py  →  lista.txt  →  affiliate_scan.py

Assim a chamada cara (com cookie e risco de 418) roda só nos produtos que já
passaram no filtro de vendas.

Credenciais ficam no .env, nunca no código:

    SHOPEE_APP_ID=18322390884
    SHOPEE_SECRET=sua_chave_secreta

Uso:
    python3 shopee_openapi.py --keyword "tenis feminino" --min-sales 300
    python3 shopee_openapi.py --keyword "organizador" --pages 5 --output lista.txt
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # o .env é conveniência; variável de ambiente também serve
    pass

API_URL = "https://open-api.affiliate.shopee.com.br/graphql"

# Campos documentados do productOfferV2. Se a Shopee renomear algum, o erro do
# GraphQL vem legível na saída — é só ajustar aqui.
PRODUCT_FIELDS = """
    itemId
    shopId
    productName
    sales
    priceMin
    priceMax
    commissionRate
    ratingStar
    shopName
    offerLink
"""

SORT_BY_SALES = 2  # 1=relevância, 2=vendas, 3=preço asc, 4=preço desc, 5=comissão


class OpenApiError(Exception):
    """A API respondeu, mas com erro de negócio ou de autenticação."""


def credentials() -> tuple[str, str]:
    app_id = os.getenv("SHOPEE_APP_ID", "").strip()
    secret = os.getenv("SHOPEE_SECRET", "").strip()

    if not app_id or not secret:
        raise OpenApiError(
            "Faltam credenciais. Crie um .env na raiz do projeto com:\n"
            "    SHOPEE_APP_ID=seu_app_id\n"
            "    SHOPEE_SECRET=sua_chave_secreta\n"
            "(o .env já está no .gitignore — a chave não vai para o repositório)"
        )
    return app_id, secret


def sign(app_id: str, secret: str, payload: str, timestamp: int) -> str:
    """
    Assinatura da Open API: SHA256 de app_id + timestamp + corpo + secret.

    O corpo entra byte a byte como foi enviado, por isso a requisição manda a
    string exata que foi assinada em vez de deixar o httpx serializar de novo.
    """
    return hashlib.sha256(f"{app_id}{timestamp}{payload}{secret}".encode()).hexdigest()


def query(graphql: str, timeout: float = 30.0) -> dict:
    app_id, secret = credentials()
    payload = json.dumps({"query": graphql})
    timestamp = int(time.time())

    response = httpx.post(
        API_URL,
        content=payload,
        timeout=timeout,
        headers={
            "Content-Type": "application/json",
            "Authorization": (
                f"SHA256 Credential={app_id}, Timestamp={timestamp}, "
                f"Signature={sign(app_id, secret, payload, timestamp)}"
            ),
        },
    )
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        messages = "; ".join(e.get("message", str(e)) for e in data["errors"])
        if "Invalid Signature" in messages:
            messages += "\n(confira o SHOPEE_SECRET no .env — o App ID foi aceito)"
        elif "Request Expired" in messages:
            messages += "\n(o relógio da máquina está fora de hora — a API rejeita timestamps antigos)"
        raise OpenApiError(messages)

    return data.get("data", {})


def fetch_products(
    keyword: str | None, pages: int, limit: int, sort_type: int = SORT_BY_SALES
) -> list[dict]:
    """Pagina o productOfferV2 e devolve os nós encontrados."""
    products: list[dict] = []

    for page in range(1, pages + 1):
        args = [f"page: {page}", f"limit: {limit}", f"sortType: {sort_type}"]
        if keyword:
            args.append(f'keyword: "{keyword}"')

        graphql = f"""
        {{
          productOfferV2({", ".join(args)}) {{
            nodes {{{PRODUCT_FIELDS}}}
            pageInfo {{ page limit hasNextPage }}
          }}
        }}
        """

        offer = query(graphql).get("productOfferV2") or {}
        nodes = offer.get("nodes") or []
        products.extend(nodes)

        print(f"  página {page}: {len(nodes)} produtos", file=sys.stderr)

        if not (offer.get("pageInfo") or {}).get("hasNextPage"):
            break
        time.sleep(0.5)  # a API tem limite de taxa; meio segundo já resolve

    return products


def to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Busca candidatos na Affiliate Open API")
    p.add_argument("--keyword", help="termo de busca; sem ele vêm as ofertas em destaque")
    p.add_argument("--pages", type=int, default=2, help="páginas a percorrer")
    p.add_argument("--limit", type=int, default=50, help="produtos por página (máx. 100)")
    p.add_argument("--min-sales", type=int, default=0, help="descarta quem vendeu menos que isso")
    p.add_argument("--output", help="arquivo com um shop_id/item_id por linha, para o affiliate_scan")
    args = p.parse_args()

    try:
        print("Consultando a Open API...", file=sys.stderr)
        products = fetch_products(args.keyword, args.pages, args.limit)
    except OpenApiError as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    except httpx.HTTPError as e:
        print(f"\nFalha de rede: {e}", file=sys.stderr)
        return 1

    filtered = [p for p in products if to_int(p.get("sales")) >= args.min_sales]
    filtered.sort(key=lambda p: to_int(p.get("sales")), reverse=True)

    if not filtered:
        print("\nNenhum produto passou no filtro.", file=sys.stderr)
        return 0

    print(f"\n{'Produto':<45} {'Vendas':>8} {'Comissão':>9}")
    print("-" * 66)
    for prod in filtered[:40]:
        name = (prod.get("productName") or "")[:44]
        rate = prod.get("commissionRate")
        rate_str = f"{float(rate) * 100:.1f}%" if rate else "—"
        print(f"{name:<45} {to_int(prod.get('sales')):>8} {rate_str:>9}")

    if len(filtered) > 40:
        print(f"... (+{len(filtered) - 40} produtos)")

    print(f"\n{len(filtered)} de {len(products)} produtos passaram no filtro.", file=sys.stderr)

    if args.output:
        lines = [
            f"{p['shopId']}/{p['itemId']}"
            for p in filtered
            if p.get("shopId") and p.get("itemId")
        ]
        Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nLista gravada em {args.output}. Próximo passo:")
        print(f"  python3 affiliate_scan.py --products-file {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

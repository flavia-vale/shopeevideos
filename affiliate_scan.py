"""
Shopee Blue Ocean — varredura por vendas x afiliados.

Em vez de contar vídeos na aba de criadores, compara duas métricas que a própria
Shopee exibe na página de afiliado do produto:

    vendas altas  +  poucos afiliados promovendo  =  oceano azul

A razão vendas/afiliado é o placar: quanto maior, mais demanda sobra por
divulgador. 557 vendas com 1,2mil afiliados dá 0,46 — disputadíssimo. As mesmas
557 vendas com 30 afiliados dariam 18,6.

Uso:
    python3 affiliate_scan.py --products https://s.shopee.com.br/4LILktFNEi
    python3 affiliate_scan.py --products-file lista.txt --output csv
    python3 affiliate_scan.py --products 303419140/57563387424 --debug
"""

import argparse
import asyncio
import csv
import io
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

from shopee_ids import ResolveError, resolve

log = logging.getLogger("blueocean")

ENDPOINTS_FILE = "endpoints.json"

# Endpoint conhecido da aba de criadores. Ele devolve o card do produto junto com
# os vídeos, então é a primeira aposta para achar as contagens sem configuração.
FALLBACK_ENDPOINT = {
    "method": "POST",
    "url": "https://sv.shopee.com.br/api/v2/timeline/unify/common",
    "payload": {
        "limit": 1,
        "page_context": {
            "item_id": "{item_id}",
            "shop_id": "{shop_id}",
            "offset": 0,
            "template_tab_id": "5",
            "order_type": 1,
        },
        "request_type": 0,
        "lang": "pt-BR",
        "page_no": 1,
        "need_product_v2": True,
        "product_v2_scene": "affiliate_video_common_timeline",
    },
    "payload_json_fields": ["page_context"],
}

APP_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 Shopee/3.0.1"
)

# Nomes de campo procurados quando não há caminho JSON configurado.
AFFILIATE_KEY_RE = re.compile(r"affiliate.*(count|num)|(count|num).*affiliate|promoter", re.I)
SALES_KEY_RE = re.compile(r"^(historical_)?sold$|sold_count|sales_count|order_count", re.I)


@dataclass
class ProductStats:
    entry: str
    shop_id: int | None = None
    item_id: int | None = None
    sales: int | None = None
    affiliates: int | None = None
    ratio: float | None = None
    status: str = "ok"
    error: str | None = None
    elapsed_s: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ── Configuração ─────────────────────────────────────────────────────────────


def load_cookies(path: str) -> dict:
    if not Path(path).exists():
        log.warning("Arquivo de cookies %s não encontrado — seguindo sem sessão.", path)
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "cookies" in data:
            data = data["cookies"]
        return {c["name"]: c["value"] for c in data}
    except Exception as e:
        log.error("Erro ao carregar cookies: %s", e)
        return {}


def load_endpoint(path: str = ENDPOINTS_FILE) -> dict:
    """
    Lê o endpoint de estatísticas do endpoints.json, se existir.

    Enquanto o campo de afiliados não for capturado (find_affiliate_field.py),
    caímos no endpoint da aba de criadores e procuramos os campos por nome.
    """
    if not Path(path).exists():
        log.info("Sem %s — usando o endpoint da aba de criadores e busca por nome.", path)
        return FALLBACK_ENDPOINT
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        endpoint = config.get("affiliate_stats")
        if not endpoint:
            log.warning("%s sem a chave 'affiliate_stats' — usando o fallback.", path)
            return FALLBACK_ENDPOINT
        log.info("Endpoint carregado de %s: %s", path, endpoint.get("url"))
        return endpoint
    except Exception as e:
        log.error("Erro ao ler %s: %s — usando o fallback.", path, e)
        return FALLBACK_ENDPOINT


# ── Extração ─────────────────────────────────────────────────────────────────


def substitute(value, shop_id: int, item_id: int):
    """Troca {shop_id}/{item_id} recursivamente em strings do payload/URL."""
    if isinstance(value, str):
        out = value.replace("{shop_id}", str(shop_id)).replace("{item_id}", str(item_id))
        # Se a string virou só dígitos vinda de um placeholder, devolve int.
        return int(out) if value in ("{shop_id}", "{item_id}") else out
    if isinstance(value, dict):
        return {k: substitute(v, shop_id, item_id) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, shop_id, item_id) for v in value]
    return value


def dig(data, path: str):
    """Segue um caminho tipo 'data.product.affiliate_count' (suporta [0])."""
    node = data
    for part in path.split("."):
        m = re.fullmatch(r"([^\[\]]*)((?:\[\d+\])*)", part)
        if not m:
            return None
        key, indices = m.group(1), m.group(2)
        if key:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
        for idx in re.findall(r"\[(\d+)\]", indices):
            if not isinstance(node, list) or int(idx) >= len(node):
                return None
            node = node[int(idx)]
    return node


def search_by_key(data, pattern: re.Pattern) -> int | None:
    """Varre o JSON inteiro procurando a primeira chave numérica que casa."""
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if (
                    pattern.search(key)
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                ):
                    log.debug("Campo casado por nome: %s = %s", key, value)
                    return int(value)
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(v for v in node if isinstance(v, (dict, list)))
    return None


def extract_metric(data, path: str | None, pattern: re.Pattern) -> int | None:
    """Usa o caminho configurado quando existir; senão procura pelo nome do campo."""
    if path:
        value = dig(data, path)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
        log.debug("Caminho %r não devolveu número — caindo na busca por nome.", path)
    return search_by_key(data, pattern)


# ── Rede ─────────────────────────────────────────────────────────────────────


async def fetch_stats(
    client: httpx.AsyncClient, endpoint: dict, shop_id: int, item_id: int, cookies: dict
) -> dict:
    """Chama o endpoint de estatísticas e devolve o JSON da resposta."""
    product_url = f"https://shopee.com.br/product/{shop_id}/{item_id}"

    # Visita a página antes: é o que faz a Shopee emitir o csrftoken da sessão.
    await client.get(
        product_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9",
        },
        cookies=cookies,
    )

    session_cookies = {**dict(client.cookies), **cookies}
    headers = {
        "User-Agent": APP_USER_AGENT,
        "Content-Type": "application/json",
        "X-CSRFToken": session_cookies.get("csrftoken", ""),
        "Referer": product_url,
        "x-requested-from": "rn",
        "x-api-sdk-version": "3.0.1",
        "Origin": "https://shopee.com.br",
        **substitute(endpoint.get("headers", {}), shop_id, item_id),
    }

    payload = substitute(endpoint.get("payload", {}), shop_id, item_id)
    # Alguns campos vão como JSON serializado dentro do JSON (ex.: page_context).
    for name in endpoint.get("payload_json_fields", []):
        if name in payload:
            payload[name] = json.dumps(payload[name])

    url = substitute(endpoint["url"], shop_id, item_id)
    method = endpoint.get("method", "POST").upper()

    if method == "GET":
        response = await client.get(url, params=payload, headers=headers, cookies=session_cookies)
    else:
        response = await client.post(url, json=payload, headers=headers, cookies=session_cookies)

    log.debug("%s %s -> %d", method, url, response.status_code)

    if response.status_code == 418:
        raise PermissionError("bloqueio 418 (anti-bot) — renove os cookies ou troque de IP")
    if response.status_code in (401, 403):
        raise PermissionError(f"sessão inválida ({response.status_code}) — renove os cookies")
    response.raise_for_status()
    return response.json()


async def process(
    entry: str, client: httpx.AsyncClient, endpoint: dict, cookies: dict
) -> ProductStats:
    t0 = time.monotonic()
    result = ProductStats(entry=entry)

    try:
        result.shop_id, result.item_id = resolve(entry)
    except (ResolveError, httpx.HTTPError) as e:
        result.status, result.error = "error", f"link não resolvido: {e}"
        return result

    try:
        data = await fetch_stats(client, endpoint, result.shop_id, result.item_id, cookies)
    except PermissionError as e:
        result.status, result.error = "expired", str(e)
        return result
    except Exception as e:
        result.status, result.error = "error", str(e)
        return result
    finally:
        result.elapsed_s = round(time.monotonic() - t0, 2)

    result.sales = extract_metric(data, endpoint.get("sales_path"), SALES_KEY_RE)
    result.affiliates = extract_metric(data, endpoint.get("affiliate_count_path"), AFFILIATE_KEY_RE)
    result.elapsed_s = round(time.monotonic() - t0, 2)

    if result.affiliates is None:
        result.status = "no_data"
        result.error = (
            "campo de afiliados ausente na resposta — capture o tráfego do app e rode "
            "find_affiliate_field.py para descobrir o endpoint certo"
        )
        return result

    # Afiliados pode ser 0 num produto recém-lançado: trate como 1 para não dividir por zero.
    result.ratio = round((result.sales or 0) / max(result.affiliates, 1), 2)
    return result


def classify(stats: ProductStats, min_sales: int, max_affiliates: int) -> str:
    """Rotula o produto depois que as duas métricas existem."""
    if stats.status != "ok" or stats.sales is None:
        return stats.status
    if stats.sales >= min_sales and stats.affiliates <= max_affiliates:
        return "blue_ocean"
    if stats.sales < min_sales:
        return "low_demand"
    return "competed"


def http2_available() -> bool:
    """HTTP/2 imita melhor o app, mas depende do pacote h2 — sem ele, seguimos em 1.1."""
    try:
        import h2  # noqa: F401
    except ImportError:
        log.warning("Pacote 'h2' ausente: usando HTTP/1.1 (mais fácil de detectar). "
                    "Instale com: pip install 'httpx[http2]'")
        return False
    return True


async def run(
    entries: list[str],
    cookies_path: str,
    min_sales: int,
    max_affiliates: int,
    delay: float,
    on_result=None,
) -> list[ProductStats]:
    """
    Varre a lista em série. `on_result` recebe cada ProductStats assim que fica
    pronto — é o que alimenta a barra de progresso da interface web.
    """
    cookies = load_cookies(cookies_path)
    endpoint = load_endpoint()
    results: list[ProductStats] = []

    if not cookies:
        log.warning(
            "Sem cookies de sessão: a Shopee vai recusar todas as chamadas. "
            "Exporte a sessão do navegador para %s.",
            cookies_path,
        )

    # Sessão inválida derruba tudo igual, então não faz sentido gastar minutos
    # varrendo uma lista longa para colecionar o mesmo 403.
    consecutive_auth_failures = 0

    async with httpx.AsyncClient(
        timeout=30.0, follow_redirects=True, http2=http2_available()
    ) as client:
        for i, entry in enumerate(entries):
            log.info("[%d/%d] %s", i + 1, len(entries), entry)
            stats = await process(entry, client, endpoint, cookies)
            stats.status = classify(stats, min_sales, max_affiliates)
            results.append(stats)
            if on_result:
                on_result(stats)

            consecutive_auth_failures = (
                consecutive_auth_failures + 1 if stats.status == "expired" else 0
            )
            restantes = len(entries) - i - 1
            if consecutive_auth_failures >= 3 and restantes:
                log.error(
                    "Três falhas de sessão seguidas — parando e deixando %d produtos de fora. "
                    "Renove os cookies e rode de novo.",
                    restantes,
                )
                break

            if i < len(entries) - 1:
                await asyncio.sleep(delay)

    return results


# ── Saída ────────────────────────────────────────────────────────────────────

STATUS_LABEL = {
    "blue_ocean": "Oceano Azul",
    "competed": "Competido",
    "low_demand": "Pouca venda",
    "no_data": "Sem dado de afiliados",
    "expired": "Cookies expirados",
    "error": "Erro",
}


def render_table(results: list[ProductStats]) -> str:
    out = io.StringIO()
    header = f"{'Produto':<26} {'Vendas':>8} {'Afiliados':>10} {'V/Afil':>8}  Status"
    out.write(f"\n{header}\n")
    out.write("-" * len(header) + "\n")

    for r in results:
        pid = f"{r.shop_id}/{r.item_id}" if r.shop_id else r.entry[:26]
        sales = str(r.sales) if r.sales is not None else "—"
        affiliates = str(r.affiliates) if r.affiliates is not None else "—"
        ratio = f"{r.ratio:.2f}" if r.ratio is not None else "—"
        out.write(f"{pid:<26} {sales:>8} {affiliates:>10} {ratio:>8}  {STATUS_LABEL.get(r.status, r.status)}\n")

    errors = [r for r in results if r.error]
    if errors:
        out.write("\nDetalhes:\n")
        for r in errors:
            pid = f"{r.shop_id}/{r.item_id}" if r.shop_id else r.entry
            out.write(f"  {pid}: {r.error}\n")

    return out.getvalue()


def render_csv(results: list[ProductStats]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(asdict(results[0]).keys()))
    writer.writeheader()
    for r in results:
        writer.writerow(asdict(r))
    return out.getvalue()


def setup_logging(debug: bool) -> None:
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler("affiliate_scan.log", encoding="utf-8"),
        ],
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Acha produtos com muitas vendas e poucos afiliados")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--products", help="links ou IDs separados por vírgula")
    src.add_argument("--products-file", help="arquivo com um link/ID por linha")
    p.add_argument("--cookies", default="cookies.json")
    p.add_argument("--min-sales", type=int, default=100, help="vendas mínimas para valer a pena")
    p.add_argument("--max-affiliates", type=int, default=50, help="teto de afiliados promovendo")
    p.add_argument("--delay", type=float, default=2.0, help="pausa entre produtos (anti-bot)")
    p.add_argument("--output", choices=["table", "csv", "json"], default="table")
    p.add_argument("--output-file", help="grava a saída em arquivo em vez do stdout")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    setup_logging(args.debug)

    if args.products_file:
        lines = Path(args.products_file).read_text(encoding="utf-8").splitlines()
        entries = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    else:
        entries = [x.strip() for x in args.products.split(",") if x.strip()]

    if not entries:
        print("Nenhum produto informado.", file=sys.stderr)
        return 1

    results = asyncio.run(
        run(entries, args.cookies, args.min_sales, args.max_affiliates, args.delay)
    )

    if args.output == "csv":
        text = render_csv(results)
    elif args.output == "json":
        text = json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2)
    else:
        text = render_table(results)

    if args.output_file:
        Path(args.output_file).write_text(text, encoding="utf-8")
        print(f"Saída gravada em {args.output_file}")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())

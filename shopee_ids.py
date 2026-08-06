"""
Utilitários de identificação de produtos Shopee.

- Resolve links curtos (s.shopee.com.br/XXXX) para shop_id/item_id
- Extrai IDs de URLs completas (i.SHOP.ITEM, /product/, /opaanlp/)
- Converte números abreviados em pt-BR ("1,2mil+", "3,4 mi") para inteiros
"""

import re
import unicodedata

import httpx

# UA de iPhone: o link curto só monta o deeplink quando acha que é mobile.
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)

SHORT_LINK_RE = re.compile(r"https?://s\.shopee\.com\.br/\w+", re.I)

# Padrões de ID em URLs completas, na ordem de tentativa.
ID_PATTERNS = [
    re.compile(r"\bi\.(\d+)\.(\d+)"),                        # .../produto-i.123.456
    re.compile(r"/(?:product|opaanlp)/(\d+)/(\d+)"),         # /product/123/456
    re.compile(r"shop_?id[=:](\d+).*?item_?id[=:](\d+)"),    # query string
    re.compile(r"^(\d+)/(\d+)$"),                            # formato interno "123/456"
]


class ResolveError(Exception):
    """Não foi possível chegar a um par shop_id/item_id."""


def extract_ids(text: str) -> tuple[int, int] | None:
    """Procura um par (shop_id, item_id) em qualquer texto. None se não achar."""
    for pattern in ID_PATTERNS:
        m = pattern.search(text.strip())
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def resolve_short_link(url: str, timeout: float = 30.0) -> tuple[int, int]:
    """
    Resolve um link curto de afiliado para (shop_id, item_id).

    O s.shopee.com.br não redireciona via HTTP: ele devolve uma página que monta
    o deeplink do app em JavaScript. Os IDs estão dentro do `httpUrl` desse
    payload, então basta ler o HTML — não precisa de cookies nem de browser.
    """
    resp = httpx.get(
        url,
        headers={"User-Agent": MOBILE_UA, "Accept-Language": "pt-BR,pt;q=0.9"},
        timeout=timeout,
        follow_redirects=True,
    )
    resp.raise_for_status()

    # O HTML traz as barras escapadas (https:\/\/shopee.com.br\/opaanlp\/...).
    html = resp.text.replace("\\/", "/")

    ids = extract_ids(html)
    if ids is None:
        raise ResolveError(f"IDs não encontrados no HTML de {url}")
    return ids


def resolve(entry: str, timeout: float = 30.0) -> tuple[int, int]:
    """
    Aceita link curto, URL completa ou "shop_id/item_id" e devolve (shop_id, item_id).
    """
    entry = entry.strip()
    if not entry:
        raise ResolveError("entrada vazia")

    if SHORT_LINK_RE.match(entry):
        return resolve_short_link(entry, timeout=timeout)

    ids = extract_ids(entry)
    if ids is None:
        raise ResolveError(f"formato não reconhecido: {entry!r}")
    return ids


# ── Números abreviados ───────────────────────────────────────────────────────

_NUM_RE = re.compile(r"([\d.,]+)\s*(mil|mi|k|m)?", re.I)

_MULTIPLIERS = {"mil": 1_000, "k": 1_000, "mi": 1_000_000, "m": 1_000_000}


def parse_br_number(text: str) -> int | None:
    """
    Converte números como a Shopee exibe para inteiro.

        "557"      -> 557
        "1,2mil+"  -> 1200
        "3,4 mi"   -> 3400000
        "12.5k"    -> 12500

    Devolve None se não houver número no texto. O "+" é ignorado: o valor
    exibido é um piso, então toda contagem abreviada é uma subestimativa.
    """
    if not text:
        return None

    normalized = unicodedata.normalize("NFKC", text).strip().lower()
    m = _NUM_RE.search(normalized)
    if not m:
        return None

    raw, suffix = m.group(1), m.group(2)

    if suffix:
        # Com sufixo o separador é decimal: "1,2mil" e "12.5k" valem 1200 e 12500.
        value = float(raw.replace(",", ".").replace(" ", ""))
        return int(value * _MULTIPLIERS[suffix])

    # Sem sufixo os separadores são de milhar: "1.234" e "1,234" valem 1234.
    digits = re.sub(r"[.,]", "", raw)
    return int(digits) if digits.isdigit() else None

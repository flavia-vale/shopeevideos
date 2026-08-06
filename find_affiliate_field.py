"""
Localizador do campo "Afiliados promoveram".

Esse número só aparece na página de afiliado dentro do app — não existe em
nenhuma API pública que dê para adivinhar. Em vez de chutar endpoints, capture
o tráfego do app (mitmproxy/Charles/HAR), abra a tela do produto e rode este
script informando o número que apareceu na tela. Ele varre o dump, acha em qual
resposta aquele valor está e imprime o caminho JSON exato — que é o que falta
para configurar o `endpoints.json`.

Uso:
    # vi "1,2mil+ Afiliados promoveram" na tela
    python3 find_affiliate_field.py --dump captura.mitm --valor "1,2mil+"

    # sem saber o número, só listando campos com nome suspeito
    python3 find_affiliate_field.py --dump captura.har
"""

import argparse
import json
import re
import sys
import zlib
from pathlib import Path

from shopee_ids import parse_br_number

# Palavras que costumam nomear o campo procurado nas APIs da Shopee.
SUSPECT_KEY_RE = re.compile(
    r"affiliate|afiliad|promot|promov|kol|creator|publisher|share_count|shared_by",
    re.I,
)

# Palavras que nomeiam o número de vendas, útil para configurar o mesmo endpoint.
SALES_KEY_RE = re.compile(r"sold|sale|vendid|order_count", re.I)


def decompress_chunks(data: bytes) -> list[bytes]:
    """Corpos de resposta vêm gzipados dentro do dump; devolve os que abrirem."""
    out = [data]
    for chunk in data.split(b"\x1f\x8b\x08")[1:]:
        try:
            out.append(zlib.decompress(b"\x1f\x8b\x08" + chunk, 16 + zlib.MAX_WBITS))
        except Exception:
            continue
    return out


def find_json_blobs(blob: bytes) -> list[dict]:
    """Extrai objetos JSON de um blob binário, varrendo a partir de cada '{'."""
    text = blob.decode("utf-8", errors="ignore")
    decoder = json.JSONDecoder()
    found: list[dict] = []
    pos = 0

    while True:
        start = text.find('{"', pos)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except ValueError:
            pos = start + 1
            continue
        if isinstance(obj, dict) and len(obj) > 1:
            found.append(obj)
            pos = start + end
        else:
            pos = start + 1

    return found


def walk(node, path: str = ""):
    """Percorre um JSON aninhado devolvendo (caminho, chave, valor) de cada folha."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else key
            if isinstance(value, (dict, list)):
                yield from walk(value, child)
            else:
                yield child, key, value
    elif isinstance(node, list):
        for idx, value in enumerate(node[:20]):  # amostra: listas longas se repetem
            child = f"{path}[{idx}]"
            if isinstance(value, (dict, list)):
                yield from walk(value, child)
            else:
                yield child, str(idx), value


def matches_target(value, target: int) -> bool:
    """
    Casa um valor com o número visto na tela.

    Contagens exibidas como "1,2mil+" são arredondadas para baixo, então o valor
    real está entre 1200 e 1299. Para números exatos exigimos igualdade.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    if target >= 1000:
        step = 100 if target < 10_000 else 1_000
        return target <= value < target + step
    return int(value) == target


def scan(dump_path: Path, target: int | None) -> None:
    raw = dump_path.read_bytes()
    blobs = decompress_chunks(raw)

    objects: list[dict] = []
    for blob in blobs:
        objects.extend(find_json_blobs(blob))

    print(f"Dump: {dump_path}  ({len(raw)} bytes, {len(objects)} objetos JSON)\n")
    if not objects:
        print("Nenhum JSON legível. O dump pode estar criptografado ou ser só metadados.")
        return

    exact_hits: list[tuple[str, str, object]] = []
    key_hits: list[tuple[str, str, object]] = []
    sales_hits: list[tuple[str, str, object]] = []

    for obj in objects:
        for path, key, value in walk(obj):
            if target is not None and matches_target(value, target):
                exact_hits.append((path, key, value))
            if SUSPECT_KEY_RE.search(key):
                key_hits.append((path, key, value))
            if SALES_KEY_RE.search(key):
                sales_hits.append((path, key, value))

    def report(title: str, hits: list[tuple[str, str, object]], limit: int = 40) -> None:
        print(f"── {title} ({len(hits)}) " + "─" * max(0, 50 - len(title)))
        if not hits:
            print("   (nada)\n")
            return
        seen: set[tuple[str, object]] = set()
        shown = 0
        for path, _key, value in hits:
            if (path, value) in seen:
                continue
            seen.add((path, value))
            print(f"   {path} = {value!r}")
            shown += 1
            if shown >= limit:
                print(f"   ... (+{len(hits) - shown} outros)")
                break
        print()

    if target is not None:
        report(f"Campos com o valor procurado ({target})", exact_hits)
    report("Campos com nome de afiliado/promoção", key_hits)
    report("Campos de vendas (para o mesmo endpoint)", sales_hits)

    if target is not None and exact_hits:
        path, _key, value = exact_hits[0]
        print("Provável campo dos afiliados:")
        print(f'   "affiliate_count_path": "{path}"  (valor {value})')
        print("\nCopie esse caminho para o endpoints.json junto com a URL da requisição")
        print("que devolveu esse corpo (procure no seu proxy pela mesma resposta).")


def main() -> int:
    p = argparse.ArgumentParser(description="Acha o campo de afiliados num dump de tráfego")
    p.add_argument("--dump", required=True, help="arquivo .mitm, .har ou qualquer dump binário")
    p.add_argument("--valor", help='número visto na tela, ex: "1,2mil+" ou "557"')
    args = p.parse_args()

    dump_path = Path(args.dump)
    if not dump_path.exists():
        print(f"Arquivo não encontrado: {dump_path}", file=sys.stderr)
        return 1

    target = None
    if args.valor:
        target = parse_br_number(args.valor)
        if target is None:
            print(f"Não consegui interpretar o valor {args.valor!r}", file=sys.stderr)
            return 1

    scan(dump_path, target)
    return 0


if __name__ == "__main__":
    sys.exit(main())

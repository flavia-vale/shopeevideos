"""
Gera o cookies.json com a sua sessão da Shopee.

Dois caminhos:

    python export_cookies.py            # lê direto do navegador instalado
    python export_cookies.py --colar    # você cola os cookies, ele formata

O automático depende do `browser-cookie3` e nem sempre funciona: o Chrome no
Windows passou a cifrar o banco de cookies com App-Bound Encryption, e aí só o
próprio Chrome consegue ler. Quando isso acontecer, o script explica e manda
para o modo colar, que funciona sempre.

O modo colar aceita as duas formas que dá para tirar do navegador:

  1. O JSON da extensão Cookie-Editor (botão Export → Export as JSON)
  2. A linha do header `Cookie:` copiada do DevTools (F12 → Network → clique
     numa requisição → Request Headers → Cookie)

A segunda pega até os cookies HttpOnly, que o console do navegador não enxerga.
"""

import argparse
import json
import sys
from pathlib import Path

OUTPUT = Path("cookies.json")
DOMAIN = "shopee.com.br"

# Sem estes a Shopee trata a sessão como anônima.
REQUIRED = ["SPC_U", "SPC_EC", "SPC_SI", "SPC_F"]

MANUAL_HELP = """
Como copiar os cookies (jeito que sempre funciona):

  1. Abra shopee.com.br no navegador, LOGADA na sua conta
  2. Aperte F12 para abrir o DevTools
  3. Vá na aba Network (Rede) e recarregue a página (F5)
  4. Clique em qualquer requisição da lista
  5. Em Request Headers, ache a linha que começa com "Cookie:"
  6. Copie o conteúdo dela inteiro (é longo, tudo numa linha só)

Depois rode:

  python export_cookies.py --colar
"""


def from_browser() -> list[dict]:
    """Lê os cookies do navegador instalado. Pode falhar por criptografia."""
    try:
        import browser_cookie3
    except ImportError:
        raise RuntimeError(
            "O modo automático precisa do pacote browser-cookie3:\n"
            "    python -m pip install browser-cookie3\n"
            "Ou use o modo manual: python export_cookies.py --colar"
        )

    navegadores = [
        ("Chrome", browser_cookie3.chrome),
        ("Edge", browser_cookie3.edge),
        ("Firefox", browser_cookie3.firefox),
        ("Brave", browser_cookie3.brave),
    ]

    falhas = []
    for nome, carregar in navegadores:
        try:
            jar = carregar(domain_name=DOMAIN)
            cookies = [
                {"name": c.name, "value": c.value, "domain": c.domain} for c in jar
            ]
            if cookies:
                print(f"[+] {nome}: {len(cookies)} cookies encontrados")
                return cookies
            falhas.append(f"{nome}: nenhum cookie da Shopee (não logada nele?)")
        except Exception as e:
            falhas.append(f"{nome}: {type(e).__name__}")

    raise RuntimeError("Nenhum navegador entregou os cookies.\n  " + "\n  ".join(falhas))


def parse_header(texto: str) -> list[dict]:
    """Converte a linha `Cookie: a=1; b=2` do DevTools em lista de cookies."""
    texto = texto.strip()
    if texto.lower().startswith("cookie:"):
        texto = texto.split(":", 1)[1].strip()

    cookies = []
    for pedaco in texto.split(";"):
        pedaco = pedaco.strip()
        if "=" not in pedaco:
            continue
        nome, valor = pedaco.split("=", 1)
        nome, valor = nome.strip(), valor.strip()
        if nome:
            cookies.append({"name": nome, "value": valor, "domain": f".{DOMAIN}"})
    return cookies


def parse_json_export(texto: str) -> list[dict]:
    """Aceita o export da extensão Cookie-Editor, com ou sem o embrulho."""
    dados = json.loads(texto)
    if isinstance(dados, dict) and "cookies" in dados:
        dados = dados["cookies"]
    if not isinstance(dados, list):
        raise ValueError("o JSON não é uma lista de cookies")

    return [
        {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", f".{DOMAIN}"),
        }
        for c in dados
        if isinstance(c, dict) and c.get("name")
    ]


def read_pasted() -> list[dict]:
    print(MANUAL_HELP)
    print("Cole o conteúdo abaixo e aperte Enter duas vezes (ou Ctrl+Z e Enter):\n")

    linhas = []
    try:
        while True:
            linha = input()
            if not linha.strip() and linhas:
                break
            if linha.strip():
                linhas.append(linha)
    except EOFError:
        pass

    texto = "\n".join(linhas).strip()
    if not texto:
        raise ValueError("nada foi colado")

    # JSON e header se distinguem pelo primeiro caractere.
    if texto.lstrip().startswith(("[", "{")):
        return parse_json_export(texto)
    return parse_header(texto)


def salvar(cookies: list[dict]) -> int:
    if not cookies:
        print("Nenhum cookie para gravar.", file=sys.stderr)
        return 1

    presentes = {c["name"] for c in cookies}
    faltando = [n for n in REQUIRED if n not in presentes]

    OUTPUT.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✓ {OUTPUT.resolve()} gravado com {len(cookies)} cookies.")

    if faltando:
        print(f"\n⚠ Faltam cookies de sessão: {', '.join(faltando)}")
        print("  Isso costuma significar que a captura veio de uma aba deslogada,")
        print("  ou que você copiou o header de uma requisição para outro domínio.")
        print("  Confira que está logada na Shopee e repita.")
        return 1

    print("  Todos os cookies de sessão estão presentes.")
    print("\nAgora teste se a sessão é aceita de verdade:")
    print(f"  {Path(sys.executable).stem} cookie_helper.py --test")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Gera o cookies.json da sessão da Shopee")
    p.add_argument(
        "--colar",
        action="store_true",
        help="colar os cookies na mão em vez de ler do navegador",
    )
    args = p.parse_args()

    if OUTPUT.exists():
        resposta = input(f"{OUTPUT} já existe. Sobrescrever? (s/N) ").strip().lower()
        if resposta not in ("s", "sim", "y"):
            print("Cancelado, nada foi alterado.")
            return 0

    try:
        cookies = read_pasted() if args.colar else from_browser()
    except RuntimeError as e:
        print(f"\nModo automático não funcionou: {e}", file=sys.stderr)
        print(MANUAL_HELP, file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as e:
        print(f"\nNão consegui interpretar o que foi colado: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 1

    return salvar(cookies)


if __name__ == "__main__":
    sys.exit(main())

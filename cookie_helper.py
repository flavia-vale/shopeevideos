"""
Cookie Helper — valida e inspeciona cookies de sessão da Shopee.

Uso:
    python cookie_helper.py
    python cookie_helper.py --export-from-browser
"""

import argparse
import json
import sys
import time
from pathlib import Path

REQUIRED_COOKIES = ["SPC_U", "SPC_EC", "SPC_SI", "SPC_F"]
SHOPEE_DOMAINS   = [".shopee.com.br", "shopee.com.br"]


def load(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    if not isinstance(data, list):
        raise ValueError("cookies.json deve ser uma lista de objetos")
    return data


def validate(cookies: list[dict]) -> None:
    by_name = {c["name"]: c for c in cookies}
    now = time.time()

    print(f"\n{'Cookie':<15} {'Presente':>10} {'Expirado':>10}  Domínio")
    print("-" * 60)

    all_ok = True
    for name in REQUIRED_COOKIES:
        c = by_name.get(name)
        present = c is not None
        expires = c.get("expires", -1) if c else -1
        expired = (expires != -1 and expires < now) if present else False
        domain  = c.get("domain", "?") if c else "—"

        ok = present and not expired
        if not ok:
            all_ok = False

        status_present = "OK" if present else "AUSENTE"
        status_expired = "SIM" if expired else ("N/A" if not present else "nao")
        flag = "  <-- PROBLEMA" if not ok else ""
        print(f"{name:<15} {status_present:>10} {status_expired:>10}  {domain}{flag}")

    print()
    if all_ok:
        print("Todos os cookies obrigatorios presentes e validos.")
    else:
        print("AVISO: cookies invalidos. Exporte novamente do browser logado.")
        sys.exit(1)

    print(f"\nTotal de cookies no arquivo: {len(cookies)}")
    extras = [c["name"] for c in cookies if c["name"] not in REQUIRED_COOKIES]
    if extras:
        print(f"Cookies extras (nao obrigatorios): {', '.join(extras)}")


def show_export_instructions() -> None:
    print("""
Como exportar cookies do Chrome (metodo manual):
-------------------------------------------------
1. Acesse https://shopee.com.br e faca login
2. Abra DevTools (F12) > Application > Cookies > https://shopee.com.br
3. Copie os valores de: SPC_U, SPC_EC, SPC_SI, SPC_F
4. Edite cookies.json substituindo os valores de exemplo

Metodo automatico (extensao Chrome):
-------------------------------------
1. Instale "EditThisCookie" ou "Cookie-Editor"
2. Na pagina da Shopee logada, exporte como JSON
3. Salve como cookies.json neste diretorio

Duracao tipica dos cookies: 4-24 horas
Renove sempre que o scraper retornar status "expired".
""")


def test_live(cookies_path: str) -> None:
    """
    Bate na API de verdade com um produto conhecido.

    O arquivo pode estar com todos os cookies certos e a sessão já ter morrido —
    só a chamada real diz. Vale rodar antes de varrer uma lista longa.
    """
    import asyncio

    import affiliate_scan

    print("\nTestando a sessão contra a API...")
    resultado = asyncio.run(
        affiliate_scan.run(
            ["303419140/57563387424"],
            cookies_path=cookies_path,
            min_sales=0,
            max_affiliates=10**9,
            delay=0,
        )
    )[0]

    if resultado.status == "expired":
        print(f"\nSessao RECUSADA: {resultado.error}")
        print("Exporte os cookies de novo com o navegador logado.")
        sys.exit(1)
    if resultado.status == "error":
        print(f"\nFalha no teste: {resultado.error}")
        sys.exit(1)

    print("\nSessao ACEITA pela Shopee.")
    if resultado.affiliates is None:
        print("A contagem de afiliados ainda nao veio — falta configurar o endpoints.json")
        print("(veja ABORDAGEM_AFILIADOS.md). Os cookies em si estao bons.")
    else:
        print(f"Afiliados: {resultado.affiliates} | Vendas: {resultado.sales}")


def main() -> None:
    p = argparse.ArgumentParser(description="Valida cookies de sessao da Shopee")
    p.add_argument("--cookies", default="cookies.json", help="Caminho para o arquivo de cookies (padrao: cookies.json)")
    p.add_argument("--export-from-browser", action="store_true",
                   help="Exibir instrucoes de exportacao")
    p.add_argument("--test", action="store_true",
                   help="Alem de validar o arquivo, faz uma chamada real a API")
    args = p.parse_args()

    if args.export_from_browser:
        show_export_instructions()
        return

    try:
        cookies = load(args.cookies)
    except FileNotFoundError:
        print(f"Arquivo nao encontrado: {args.cookies}")
        print("Certifique-se de que o arquivo cookies.json existe na raiz do projeto.")
        sys.exit(1)
    except Exception as exc:
        print(f"Erro ao ler {args.cookies}: {exc}")
        sys.exit(1)

    validate(cookies)

    if args.test:
        test_live(args.cookies)


if __name__ == "__main__":
    main()
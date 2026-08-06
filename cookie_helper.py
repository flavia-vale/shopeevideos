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

REQUIRED_COOKIES = ["SPC_U", "SPC_SI", "SPC_F"]

# O token de sessao mudou de nome: exports antigos trazem SPC_EC, os atuais
# trazem SPC_ST. Basta um dos dois estar presente.
SESSION_TOKENS   = ["SPC_ST", "SPC_EC"]

SHOPEE_DOMAINS   = [".shopee.com.br", "shopee.com.br"]


def expiry_of(cookie: dict) -> float:
    """Cada exportador nomeia a validade de um jeito; -1 quando nao ha."""
    for campo in ("expires", "expirationDate", "expiry"):
        valor = cookie.get(campo)
        if isinstance(valor, (int, float)):
            return float(valor)
    return -1.0


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

    # O token de sessao entra na conferencia pelo nome que o export usou.
    token = next((t for t in SESSION_TOKENS if t in by_name), None)
    a_conferir = REQUIRED_COOKIES + [token or " ou ".join(SESSION_TOKENS)]

    all_ok = True
    for name in a_conferir:
        c = by_name.get(name)
        present = c is not None
        expires = expiry_of(c) if c else -1
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
    extras = [c["name"] for c in cookies if c["name"] not in a_conferir]
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


def check_session(cookies_path: str) -> bool:
    """
    Pergunta a Shopee quem esta logado.

    E um endpoint do site normal, que responde a cookie de navegador. Se ele
    reconhece a sessao, os cookies estao bons — e um 403 mais adiante e problema
    do outro endpoint, nao do arquivo.
    """
    import httpx

    import affiliate_scan

    cookies = affiliate_scan.load_cookies(cookies_path)

    print("\n[1] A Shopee reconhece a sessao?")
    try:
        resp = httpx.get(
            "https://shopee.com.br/api/v4/account/basic/get_account_info",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://shopee.com.br/",
                "X-Requested-With": "XMLHttpRequest",
            },
            cookies=cookies,
            timeout=20.0,
            follow_redirects=True,
        )
    except Exception as e:
        print(f"    Falha de rede: {e}")
        return False

    if resp.status_code != 200:
        print(f"    HTTP {resp.status_code} — nem essa chamada passou.")
        print("    Costuma ser bloqueio por IP. Tente pelo 4G do celular.")
        return False

    try:
        dados = resp.json().get("data") or {}
    except Exception:
        print("    Resposta ilegivel.")
        return False

    if dados.get("userid") or dados.get("username"):
        print(f"    SIM — logada como '{dados.get('username', '?')}'. Cookies OK.")
        return True

    print("    NAO — a Shopee respondeu como visitante anonimo.")
    print("    Reexporte com o navegador logado.")
    return False


def test_live(cookies_path: str) -> None:
    """
    Testa as duas coisas que podem estar erradas, separadamente.

    Um 403 na API de afiliados nao prova que os cookies estao ruins: aquele
    endpoint e do app e pode recusar a sessao do navegador de qualquer jeito.
    Sem separar, todo problema vira "renove os cookies" — que foi o que essa
    ferramenta dizia antes, mandando renovar cookies que estavam perfeitos.
    """
    import asyncio

    import affiliate_scan

    sessao_ok = check_session(cookies_path)

    print("\n[2] A API de afiliados responde?")
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
        print(f"    NAO — {resultado.error}")
        if sessao_ok:
            print("\nDiagnostico: seus cookies estao BONS (o passo 1 passou).")
            print("O endpoint da aba de criadores e que recusa a sessao do navegador.")
            print("Ele so vai funcionar depois da captura do trafego do app —")
            print("veja o passo 1 do ABORDAGEM_AFILIADOS.md.")
        else:
            print("\nDiagnostico: a sessao nao foi reconhecida no passo 1.")
            print("Reexporte os cookies com o navegador logado.")
        sys.exit(1)

    if resultado.status == "error":
        print(f"    Falha: {resultado.error}")
        sys.exit(1)

    print("    SIM — a API respondeu.")
    if resultado.affiliates is None:
        print("\nA contagem de afiliados nao veio no corpo da resposta.")
        print("Falta configurar o endpoints.json (veja ABORDAGEM_AFILIADOS.md).")
    else:
        print(f"\nAfiliados: {resultado.affiliates} | Vendas: {resultado.sales}")


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
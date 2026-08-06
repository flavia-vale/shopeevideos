"""
Cria o arquivo .env com as credenciais da Open API.

Escrever o .env na mão dá errado por bobagem — aspas sobrando, espaço em volta
do "=", o Bloco de Notas salvando como .env.txt. Este script pergunta, grava no
formato certo e já testa a credencial contra a API.

A chave é digitada às escondidas (não aparece na tela nem no histórico do
terminal) e vai só para o .env, que está no .gitignore.

Uso:
    python setup_env.py
"""

import sys
from getpass import getpass
from pathlib import Path

ENV_PATH = Path(".env")


def ask(prompt: str, secret: bool = False) -> str:
    value = (getpass(prompt) if secret else input(prompt)).strip()
    # Colar do painel da Shopee costuma trazer aspas junto.
    return value.strip("'\"")


def main() -> int:
    print("\n=== Credenciais da Shopee Affiliate Open API ===\n")
    print("Pegue as duas no painel de afiliado, seção Open API.")
    print("A chave secreta não aparece enquanto você digita — é o esperado.\n")

    if ENV_PATH.exists():
        print(f"Já existe um {ENV_PATH.resolve()}")
        if ask("Sobrescrever? (s/N) ").lower() not in ("s", "sim", "y"):
            print("Cancelado, nada foi alterado.")
            return 0
        print()

    app_id = ask("App ID: ")
    if not app_id:
        print("App ID vazio. Cancelado.", file=sys.stderr)
        return 1

    secret = ask("Chave secreta (não aparece na tela): ", secret=True)
    if not secret:
        print("Chave vazia. Cancelado.", file=sys.stderr)
        return 1

    ENV_PATH.write_text(
        f"SHOPEE_APP_ID={app_id}\nSHOPEE_SECRET={secret}\n",
        encoding="utf-8",
    )
    print(f"\n✓ {ENV_PATH.resolve()} criado ({len(secret)} caracteres na chave).")
    print("  Está no .gitignore — não vai para o GitHub.\n")

    print("Testando a credencial na API...")
    try:
        import shopee_openapi

        # O .env acabou de nascer; recarrega para o processo enxergar.
        from dotenv import load_dotenv

        load_dotenv(override=True)

        produtos = shopee_openapi.fetch_products(keyword=None, pages=1, limit=5)
        print(f"\n✓ Credencial válida — a API devolveu {len(produtos)} produtos.")
        print("\nPróximo passo:")
        print('  python shopee_openapi.py --keyword "tenis feminino" --min-sales 300 --output lista.txt')
    except ImportError as e:
        print(f"\nDependência faltando ({e}). Rode:")
        print("  python -m pip install -r requirements.txt")
        return 1
    except Exception as e:
        print(f"\n✗ A API recusou: {e}")
        print("\nO .env foi criado mesmo assim — corrija o valor e rode de novo.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

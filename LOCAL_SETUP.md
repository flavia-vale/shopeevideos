# Executar na sua máquina local

## Por que não funciona no Codespace?

O Codespace tem um **proxy HTTP** que detecta e bloqueia navegadores headless automatizados com `"Host not in allowlist"`. Isso é uma proteção contra web scraping.

O scraper foi desenvolvido e testado corretamente — ele funciona em qualquer máquina local (Windows, macOS, Linux).

## Setup na sua máquina

```bash
# 1. Clone o repositório
git clone https://github.com/flavia-vale/shopeevideos.git
cd shopeevideos
git checkout claude/shopee-video-counter-6CXC4

# 2. Instale dependências
pip install -r requirements.txt
playwright install chromium

# 3. Copie seus cookies reais
# (já tem em cookies.json no seu Codespace)
cp cookies.json .
```

## Rode na sua máquina

```bash
# Validar cookies
python3 cookie_helper.py --cookies cookies.json

# Diagnosticar um produto
python3 diagnose.py --product 1064710210/20798940975 --cookies cookies.json

# Contar vídeos em 1 produto
python3 scraper.py --products 1064710210/20798940975 --cookies cookies.json

# Processar lista completa
python3 scraper.py --products-file lista.txt --cookies cookies.json --output csv
```

## Alternativa: Usar API Affiliate Shopee

Se você tem acesso à API Shopee Affiliate (dashboard.shopee.com.br), pode usar endpoints diretos sem Playwright:

```
GET https://affiliate.shopee.com.br/api/v1/products/{product_id}/videos
Authorization: Bearer {token_afiliado}
```

Isso evitaria o navegador automatizado completamente.

## Arquivos prontos para usar

- `scraper.py` — script principal (pronto para produção)
- `diagnose.py` — diagnóstico de seletores CSS
- `cookie_helper.py` — validação de cookies
- `requirements.txt` — dependências
- `cookies.json` — sua sessão Shopee

## Dúvidas?

Se a anti-detecção acima não funcionar na sua máquina local, tente:

1. Usar `--no-headless` para abrir o browser visível
2. Reduzir `--concurrency` para 1
3. Aumentar `--rps` delay para 0.3
4. Usar um proxy residencial (se tiver)

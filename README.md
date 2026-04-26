# Shopee Video Counter

Identifica **Oceanos Azuis** contando vídeos na aba "Aprender com criadores" de produtos Shopee.

## Arquitetura

```
cookie_helper.py   — valida/inspeciona cookies de sessão
diagnose.py        — sonda seletores CSS/Shadow DOM em tempo real
scraper.py         — scraper principal com retry, logging e saída CSV/JSON
```

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp cookies.json.example cookies.json
```

## 1. Exportar Cookies

```bash
python cookie_helper.py --cookies cookies.json --export-from-browser
```

Preencha `cookies.json` com seus valores reais de `SPC_U`, `SPC_EC`, `SPC_SI`, `SPC_F`.
Valide antes de rodar o scraper:

```bash
python cookie_helper.py --cookies cookies.json
```

## 2. Diagnosticar Seletores (opcional, mas recomendado)

Execute em um produto de referência para confirmar que os seletores CSS estão ativos:

```bash
python diagnose.py --product shop_id/item_id --cookies cookies.json
```

A saída mostra:
- Quais seletores encontram elementos (`<-- ATIVO`)
- Se há Shadow DOM e quantos filhos
- Textos das abas (`<-- CRIADORES`)
- Re-contagem pós-scroll

Se todos os seletores retornarem `0`, atualize `VIDEO_ITEM_SELECTORS` em `scraper.py`
com o seletor identificado no diagnóstico.

## 3. Rodar o Scraper

```bash
# Produtos avulsos (IDs separados por vírgula)
python scraper.py --products shop_id/item_id,shop_id/item_id2 --cookies cookies.json

# A partir de arquivo (um ID por linha)
python scraper.py --products-file minha_lista.txt --cookies cookies.json

# Saída CSV
python scraper.py --products-file ids.txt --cookies cookies.json --output csv

# Saída JSON em arquivo
python scraper.py --products-file ids.txt --cookies cookies.json --output json --output-file resultado.json

# Controle fino
python scraper.py \
  --products-file ids.txt \
  --cookies cookies.json \
  --concurrency 2 \
  --rps 0.5 \
  --threshold 3 \
  --screenshot-on-error \
  --debug
```

### Parâmetros

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--concurrency` | 3 | Abas paralelas |
| `--rps` | 1.0 | Requisições por segundo |
| `--threshold` | 5 | Videos < N = Oceano Azul |
| `--screenshot-on-error` | off | Salva PNG de páginas com erro |
| `--no-headless` | off | Abre browser visível (debug) |
| `--debug` | off | Logging verboso |

## Saída (tabela)

```
ID do Produto                Videos  Status                Detalhe
---------------------------------------------------------------------------
123456/789012                    2  Oceano Azul           [data-sqe='video-item']
654321/987654                   18  Competido             [data-sqe='video-item']
111111/222222                  N/A  Sem aba criadores     aba 'Aprender com criadores' nao encontrada
```

## Status possíveis

| Status | Significado |
|---|---|
| `blue_ocean` | Videos < threshold — baixa competição |
| `competed` | Videos >= threshold — mercado saturado |
| `no_tab` | Produto sem aba de criadores (categoria sem suporte) |
| `expired` | Cookies expirados — renove `cookies.json` |
| `error` | Falha de rede, timeout ou seletor não encontrado |

## Logs e Depuração

- `scraper.log` — log completo de cada execução
- `error_<id>_<ts>.png` — screenshots de falhas (com `--screenshot-on-error`)
- Use `--debug` para ver seletores tentados e contagens intermediárias

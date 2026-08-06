# Shopee Oceano Azul

Acha produtos com demanda comprovada e pouca gente divulgando.

Há duas abordagens no repositório:

| Abordagem | Métrica | Onde |
|---|---|---|
| **Vendas x afiliados** (atual) | `vendas ÷ afiliados promovendo` | painel web + `affiliate_scan.py` |
| Contagem de vídeos (anterior) | vídeos na aba de criadores | `scraper.py` |

A primeira é a recomendada — "Afiliados promoveram" é a concorrência dita pela
própria Shopee, enquanto a contagem de vídeos era só um proxy dela. O passo a
passo está em **[ABORDAGEM_AFILIADOS.md](ABORDAGEM_AFILIADOS.md)**.

## Painel web

```bash
pip install -r requirements.txt
npm install && npm run build
python3 main.py                  # -> http://localhost:10000
```

Cole os links (um por linha, quantos quiser), ajuste os cortes de vendas e
afiliados e mande analisar. A tabela sai ordenada pela razão vendas/afiliado,
com exportação em CSV.

Roda local de propósito: as chamadas usam o **seu** `cookies.json` e o anti-bot
da Shopee bloqueia IP de datacenter. Hospedar não ajudaria.

Para mexer no front com hot reload, deixe o `python3 main.py` de pé e rode
`npm run dev` em outro terminal (porta 3000, com proxy para o backend).

## Arquitetura

```
main.py                  — servidor do painel (Flask + front React)
shopee_ids.py            — resolve links/IDs e converte "1,2mil+" em 1200
affiliate_scan.py        — varredura vendas x afiliados (CLI)
find_affiliate_field.py  — acha o campo de afiliados numa captura de tráfego
cookie_helper.py         — valida/inspeciona cookies de sessão
scraper.py, diagnose.py  — abordagem antiga, contagem de vídeos
```

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp cookies.json.example cookies.json
```

## Contagem de vídeos (abordagem antiga)

### 1. Exportar Cookies

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

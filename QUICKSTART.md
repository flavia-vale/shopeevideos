# Quick Start

Seus cookies foram validados ✅. Aqui estão os comandos prontos para usar:

## 1. Diagnosticar um produto (escolha um de seus favoritos)

```bash
# Exemplo: produto com ID shop_id=123456789, item_id=234567890
python diagnose.py --product 123456789/234567890 --cookies cookies.json
```

**Saída esperada:**
- Lista qual seletor CSS está ativo (`<-- ATIVO`)
- Quantas abas foram encontradas
- Se há Shadow DOM
- Recontagem pós-scroll

Use este resultado para validar que `scraper.py` conseguirá contar os vídeos.

## 2. Contar vídeos em 1 produto

```bash
python scraper.py --products 123456789/234567890 --cookies cookies.json
```

**Saída:**
```
ID do Produto                Videos  Status                Detalhe
---------------------------------------------------------------------------
123456789/234567890              2  Oceano Azul           [data-sqe='video-item']
```

## 3. Processar sua lista de produtos

```bash
# Tabela no console
python scraper.py \
  --products-file example_products.txt \
  --cookies cookies.json \
  --threshold 3

# Salvar em CSV
python scraper.py \
  --products-file example_products.txt \
  --cookies cookies.json \
  --output csv \
  --output-file resultado.csv

# Saída JSON
python scraper.py \
  --products-file example_products.txt \
  --cookies cookies.json \
  --output json \
  --output-file resultado.json
```

## 4. Scrapar com mais controle

```bash
python scraper.py \
  --products-file example_products.txt \
  --cookies cookies.json \
  --concurrency 2 \
  --rps 0.5 \
  --threshold 3 \
  --screenshot-on-error \
  --debug
```

**Parâmetros:**
- `--concurrency 2`: máximo 2 abas paralelas (padrão 3)
- `--rps 0.5`: meia requisição por segundo (mais lento, menos suspeito)
- `--threshold 3`: marca como "Oceano Azul" se < 3 vídeos
- `--screenshot-on-error`: salva PNG de falhas em `error_<id>_<ts>.png`
- `--debug`: mostra detalhes de cada tentativa

## 5. Monitorar progresso

```bash
# Abrir browser visível (para debugging)
python scraper.py \
  --products 123456789 \
  --cookies cookies.json \
  --no-headless
```

Tail do log em tempo real:
```bash
tail -f scraper.log
```

## Formatos de saída

### Tabela (padrão)
```
ID do Produto                Videos  Status                Detalhe
---------------------------------------------------------------------------
123456789/234567890              2  Oceano Azul           [data-sqe='video-item']
234567890/345678901             15  Competido             [data-sqe='video-item']
345678901/456789012            N/A  Erro                  timeout ao navegar
```

### CSV
```csv
product_id,video_count,status,error,selector_used,elapsed_s,timestamp
123456789/234567890,2,blue_ocean,,data-sqe='video-item',3.45,2026-04-26T10:30:00
```

### JSON
```json
[
  {
    "product_id": "123456789/234567890",
    "video_count": 2,
    "status": "blue_ocean",
    "error": null,
    "selector_used": "[data-sqe='video-item']",
    "elapsed_s": 3.45,
    "timestamp": "2026-04-26T10:30:00"
  }
]
```

## Status possíveis

| Status | Significado | Ação |
|---|---|---|
| `blue_ocean` | < threshold vídeos | 🎯 Oportunidade! |
| `competed` | >= threshold vídeos | ❌ Mercado saturado |
| `no_tab` | Sem aba de criadores | ℹ️ Categoria sem suporte |
| `expired` | Cookies expirados | 🔄 Renove `cookies.json` |
| `error` | Falha de rede/timeout | 🔧 Veja `scraper.log` |

## Próximos passos

1. Substitua IDs em `example_products.txt` com seus produtos reais
2. Rode `diagnose.py` em 2-3 produtos para validar os seletores
3. Processe toda a lista com `scraper.py --products-file ... --output csv`
4. Filtre e priorize os `blue_ocean` para suas estratégias de afiliado

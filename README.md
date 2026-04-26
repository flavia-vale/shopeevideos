# Shopee Video Counter

Conta vídeos na aba **"Aprender com criadores"** para identificar produtos em Oceano Azul.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp cookies.json.example cookies.json   # preencha com seus cookies reais
```

## Como exportar os cookies

1. Acesse `shopee.com.br` logado no Chrome
2. Abra DevTools → Application → Cookies → `https://shopee.com.br`
3. Copie os valores de `SPC_U`, `SPC_EC`, `SPC_SI`, `SPC_F`
4. Cole em `cookies.json` (use `cookies.json.example` como base)

## Uso

```bash
# Produtos individuais
python scraper.py --products 1234567890,9876543210 --cookies cookies.json

# A partir de arquivo (um ID por linha)
python scraper.py --products-file minha_lista.txt --cookies cookies.json --output json

# Controle de paralelismo
python scraper.py --products 111,222,333 --cookies cookies.json --concurrency 2
```

## Saída (tabela)

```
Product ID             Videos  Status
--------------------------------------------------
1234567890                  2  oceano azul
9876543210                 18  competido
```

## Critério de Oceano Azul

Produtos com **menos de 5 vídeos** são marcados como `oceano azul`.
Ajuste o threshold no `print_table()` conforme sua estratégia.

## Diagnóstico de Seletores / Shadow DOM

Se `video_count` retornar `None`, o scraper já tenta automaticamente varrer
1 nível de Shadow DOM. Para investigar manualmente, abra o produto no Chrome e
execute no console:

```js
document.querySelectorAll("[data-sqe='video-item']").length
// ou
document.querySelectorAll("._3X5KM").length
```

Se `0`, inspecione se há `#shadow-root` nos nós pai — nesse caso atualize
`VIDEO_ITEM_SELECTORS` em `scraper.py` com o seletor correto.

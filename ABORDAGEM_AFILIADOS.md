# Nova abordagem: vendas x afiliados

## Por que trocar de métrica

Contar vídeos na aba de criadores era um **proxy** da concorrência. O campo
"Afiliados promoveram" é a concorrência: é o número de afiliados que já pegaram
o link daquele produto, dito pela própria Shopee.

O sinal que interessa é a razão entre os dois números da página:

```
vendas / afiliados promovendo
```

No produto do exemplo (`https://s.shopee.com.br/4LILktFNEi`):

```
557 vendas ÷ 1.200 afiliados = 0,46 venda por afiliado  → saturado
```

Os mesmos 557 com 30 afiliados dariam 18,6 — aí sim vale gravar. A meta é
achar produtos onde a demanda já existe mas a oferta de divulgação ainda não.

Vantagens sobre a contagem de vídeos:

- é **um número por produto**, não uma lista paginada;
- cobre divulgação fora do vídeo (link em bio, grupo de Whats, story);
- não depende de a aba de criadores existir na categoria.

## Estado da implementação

| Peça | Situação |
|---|---|
| Resolver link curto → `shop_id/item_id` | ✅ funciona, sem cookies e sem browser |
| Parser dos números abreviados (`1,2mil+` → 1200) | ✅ pronto |
| Pipeline de varredura, ranking e saída CSV/JSON | ✅ pronto |
| Endpoint que devolve a contagem de afiliados | ⚠️ **falta capturar** |

O único bloqueio é o último item. Aquela contagem só aparece na tela de
afiliado dentro do app, e o endpoint que a serve não é adivinhável — testei os
candidatos óbvios e todos deram 404 ou 403:

```
sv.shopee.com.br/api/v1/product/detail            404
affiliate.shopee.com.br/api/v3/offer/...          404
shopee.com.br/api/v4/item/get                     403 (anti-bot)
shopee.com.br/api/v4/pdp/get_pc                   403 (anti-bot)
open-api.affiliate.shopee.com.br/graphql          200 — API oficial, ver abaixo
```

Por isso o `find_affiliate_field.py`: em vez de continuar chutando, ele acha o
endpoint a partir de uma captura de tráfego do app.

## Passo a passo

### 1. Capturar o campo (uma vez só)

1. Suba o mitmproxy e aponte o celular para ele (é o mesmo setup que você já
   usou nas capturas `.mitm` anteriores).
2. No app, abra a página de afiliado do produto — a tela do "Compartilhe para
   Ganhar", onde aparece "1,2mil+ Afiliados promoveram".
3. Salve o fluxo e rode, informando **o número que apareceu na tela**:

```bash
python find_affiliate_field.py --dump captura.mitm --valor "1,2mil+"
```

Ele varre todos os JSON do dump, acha qual campo tem aquele valor e imprime o
caminho, algo como:

```
Provável campo dos afiliados:
   "affiliate_count_path": "data.product.affiliate_promoted_count"  (valor 1247)
```

> Contagens abreviadas são arredondadas para baixo, então o script aceita
> qualquer valor entre 1200 e 1299 para um "1,2mil+".

### 2. Configurar

```bash
cp endpoints.json.example endpoints.json
```

Preencha `url`, `payload` e `affiliate_count_path` com o que a captura mostrou.
A URL e o payload aceitam `{shop_id}` e `{item_id}`.

### 3. Varrer

```bash
# um produto
python affiliate_scan.py --products https://s.shopee.com.br/4LILktFNEi

# lista de links, exportando CSV
python affiliate_scan.py --products-file lista.txt --output csv --output-file achados.csv

# afrouxando o critério
python affiliate_scan.py --products-file lista.txt --min-sales 300 --max-affiliates 100
```

Aceita link curto, URL completa (`...-i.123.456`) ou `shop_id/item_id` na mesma
lista.

```
Produto                      Vendas  Afiliados   V/Afil  Status
---------------------------------------------------------------
303419140/57563387424           557       1247     0.45  Competido
1064710210/20798940975          890         23    38.70  Oceano Azul
```

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--min-sales` | 100 | vendas mínimas para o produto interessar |
| `--max-affiliates` | 50 | teto de afiliados para chamar de oceano azul |
| `--delay` | 2.0 | pausa entre produtos, contra o anti-bot |
| `--cookies` | `cookies.json` | sessão exportada do navegador |

### Status possíveis

| Status | Significado |
|---|---|
| `blue_ocean` | vendas ≥ `min-sales` e afiliados ≤ `max-affiliates` |
| `competed` | vende bem, mas já tem afiliado demais |
| `low_demand` | poucos afiliados porque o produto não vende |
| `no_data` | resposta sem o campo de afiliados — volte ao passo 1 |
| `expired` | 403/418: renove os cookies ou troque de IP |

## Rotina do dia a dia

Não existe página hospedada: o painel roda na sua máquina, em
`http://localhost:10000`.

```bash
python main.py
```

Isso é escolha de projeto, não preguiça. As chamadas vão com o **seu**
`cookies.json`, e o anti-bot da Shopee derruba requisição vinda de IP de
datacenter — foi exatamente o que aconteceu nos testes (403 em toda chamada).
Num servidor hospedado seria 403 o tempo todo; da sua internet, com sua sessão,
passa.

O ciclo é em lote, não um link por vez:

1. **Junte candidatos** durante a semana — do feed de afiliado, dos "Mais
   Vendidos" da categoria, do que vê rendendo no TikTok. Um link por linha num
   bloco de notas.
2. **Cole tudo de uma vez** no painel (aceita link curto, URL completa ou
   `shop_id/item_id` misturados na mesma lista) e mande analisar.
3. **Deixe rodando.** São ~3,5s por produto por causa da pausa anti-bot: 50
   produtos levam uns 3 minutos. A barra de progresso mostra o andamento e a
   tabela vai preenchendo.
4. **Olhe o topo da tabela.** Ela sai ordenada pela razão vendas/afiliado — os
   melhores achados ficam em cima, marcados como Oceano Azul.
5. **Exporte o CSV** para guardar o histórico e comparar semana que vem: um
   produto que estava em 20 e foi para 400 afiliados fechou a janela.

Os campos "Vendas mínimas" e "Máx. de afiliados" só mudam o rótulo — a tabela
mostra todos os produtos analisados de qualquer jeito. Comece frouxo
(`min 100 / máx 50`) e vá apertando conforme conhecer a sua categoria.

Para automatizar (rodar de madrugada, alimentar planilha), use o CLI, que faz o
mesmo sem o painel:

```bash
python affiliate_scan.py --products-file lista.txt --output csv --output-file achados.csv
```

## Antes de capturar

Sem `endpoints.json`, o `affiliate_scan.py` chama o endpoint da aba de
criadores (`timeline/unify/common`, com `need_product_v2`) e procura no JSON
qualquer campo cujo nome case com `affiliate.*count` ou `promoter`. Se a
contagem estiver naquele payload, já funciona sem configurar nada; se não
estiver, o produto sai como `no_data` e a captura do passo 1 é necessária.

## Gerando candidatos: Affiliate Open API

O `shopee_openapi.py` fala com a API oficial, que entrega catálogo, vendas e
comissão **em escala e sem anti-bot**. Ela resolve o lado "muitas vendas" da
conta; o que ela **não** expõe é a contagem de afiliados. Daí o fluxo em dois
tempos:

```bash
# 1. a API oficial gera os candidatos, já filtrados por vendas
python shopee_openapi.py --keyword "tenis feminino" --min-sales 300 --output lista.txt

# 2. o scan mede a concorrência só em quem passou
python affiliate_scan.py --products-file lista.txt
```

Assim a chamada cara (com cookie e risco de 418) roda em dezenas de produtos,
não em milhares.

### Credenciais

```bash
python setup_env.py
```

Ele pergunta o App ID e a chave, grava o `.env` no formato certo e já testa a
credencial na API. A chave é digitada às escondidas e não fica no histórico do
terminal.

Quem preferir na mão: copie o `.env.example` para `.env` e preencha
`SHOPEE_APP_ID` e `SHOPEE_SECRET` — sem aspas e sem espaço em volta do `=`.

De qualquer jeito o `.env` está no `.gitignore`, então a chave nunca vai para o
repositório. Pegue as duas no painel de afiliado, em Open API.

A autenticação é `SHA256(app_id + timestamp + corpo + secret)` no header
`Authorization`. Dois erros comuns e o que significam:

| Mensagem | Causa |
|---|---|
| `Invalid Signature` | secret errado — o App ID em si foi aceito |
| `Request Expired` | relógio da máquina fora de hora; a API rejeita timestamp velho |

## Arquivos

```
shopee_ids.py            resolve links/IDs e converte "1,2mil+" em 1200
shopee_openapi.py        busca candidatos na Affiliate Open API oficial
setup_env.py             cria o .env com as credenciais e testa na API
find_affiliate_field.py  acha o campo de afiliados numa captura de tráfego
affiliate_scan.py        varredura, ranking e saída table/CSV/JSON
endpoints.json.example   modelo de configuração do endpoint
```

Os scripts antigos (`scraper.py`, `diagnose.py`) continuam funcionando para a
contagem de vídeos.

# Por que travou antes, e o que mudou

## O diagnóstico

O objetivo sempre foi o mesmo: achar produto com **comissão boa** e **poucos
vídeos de afiliado**. As tentativas anteriores pararam num ponto só — a
contagem de vídeos.

O endpoint que a Shopee usa para montar a aba "Aprenda com criadores" é:

```
POST https://sv.shopee.com.br/api/v2/timeline/unify/common
```

Chamado de fora do navegador, com os cookies exportados por extensão, ele
responde:

```json
403 {"is_login": false, "action_type": 2, "error": 90309999, ...}
```

`is_login: false` **mesmo com os cookies certos**. Foi por isso que nada
resolveu: nem trocar Playwright por `httpx`, nem User-Agent de iPhone, nem
HTTP/2, nem visitar a página antes para pegar `csrftoken`, nem trocar de IP.
O 418/403 não era rate limit nem cookie velho.

A causa é que a Shopee não valida só o cookie. Ela valida um conjunto:
fingerprint de TLS, ordem exata dos headers, e sobretudo headers que o SDK
anti-bot da própria página **injeta em tempo de execução via JavaScript**.
Copiar cookie para dentro de um cliente HTTP reproduz um sinal e nenhum dos
outros. Essa corrida não se ganha reconstruindo a requisição: cada header
adivinhado é seguido de outro que muda na semana seguinte.

## As três fontes novas

Em vez de insistir num único caminho bloqueado, o projeto agora puxa cada
pedaço do dado de onde ele está efetivamente disponível.

### 1. Comissão e demanda — Open API oficial de afiliados

`shopeeops/affiliate_api.py`

```
POST https://open-api.affiliate.shopee.com.br/graphql
Authorization: SHA256 Credential={AppId}, Timestamp={ts}, Signature={sig}
```

API oficial, assinada com HMAC, **sem anti-bot**. Não existe 418 aqui. Dá
`commissionRate`, `sellerCommissionRate`, `sales`, `ratingStar`, `price`,
`offerLink` — e permite varrer o catálogo por maior comissão sem precisar
saber o que procurar (`listType: 1`).

Credenciais no painel de afiliados > Open API.

> A assinatura é `sha256(AppId + Timestamp + Payload + Secret)` e o `Payload`
> precisa ser **byte a byte** o corpo enviado. Por isso o cliente serializa o
> JSON uma vez e manda com `content=`, nunca com `json=` — o `json=` do httpx
> re-serializa e a assinatura quebra.

### 2. Concorrência pública — SSR do Shopee Video

`shopeeops/sv_public.py`

Esta é a descoberta que destrava o resto. As páginas de vídeo do
sv.shopee.com.br são renderizadas **no servidor** (Next.js,
`getServerSideProps`) e marcadas `robots: index, follow` — a Shopee quer que
o Google as indexe. Consequência: um `GET` sem cookie nenhum devolve 200 com
o `__NEXT_DATA__` inteiro dentro do HTML.

```
https://sv.shopee.com.br/web/@{qualquer}/video/{postId}
```

De lá saem, de graça:

| campo | de onde |
|---|---|
| produto anunciado (shopId, itemId, nome) | `content.productV2` |
| preço, vendas recentes e históricas, nota | `content.productV2.sellStat` |
| views, likes, comentários do vídeo | `meta.countInfo` |
| criador e data da postagem | `meta.userName`, `meta.ctime` |
| hashtags usadas | `content.hashtags` |

Dois detalhes achados na marra:

- O apelido no caminho é **decorativo**. A Shopee resolve pelo `postId`, então
  `/web/@x/video/{postId}` funciona mesmo sem saber quem postou.
- A rota `/share-video/{postId}` **não serve**: ela é uma página mais magra,
  só com mídia e legenda, sem o produto. O código normaliza tudo para a rota
  `/web/`.

**Limite honesto:** não existe rota pública para *listar* os vídeos de um
produto nem o perfil de um criador — as duas dão 404. Então este módulo
enriquece vídeos que você já tem a URL (concorrentes que você acompanha,
vídeos que apareceram no seu feed), e monta o índice invertido
produto → nº de vídeos, views medianas, último post. Ele responde
"esse produto engaja?" muito bem, e "quantos vídeos existem no total?" só
dentro do corpus que você juntou.

### 3. Contagem total — o navegador logado faz a chamada

`shopeeops/video_count.py`

Para o número absoluto, a virada conceitual: **parar de imitar a requisição e
passar a emiti-la de dentro da página.**

Abre-se um Chrome real com perfil persistente, já logado, e dispara-se o
`fetch` com `page.evaluate` — dentro do contexto da página, na origem certa,
com `credentials: 'include'`. O navegador anexa tudo sozinho: cookies, tokens
do SDK anti-bot, fingerprint de TLS. Do ponto de vista da Shopee a requisição
é indistinguível da que a própria interface faz, porque é literalmente o mesmo
navegador fazendo.

Isso também mata o outro problema antigo: não dependemos mais de seletor CSS
nenhum. A versão anterior tentava sete seletores e Shadow DOM porque lia o
DOM; aqui lemos o JSON da API, que muda muito menos que o HTML.

O login é manual e uma vez só:

```bash
python -m shopeeops.video_count login
```

O perfil fica em `~/.shopeeops/chrome-profile` e vale para as execuções
seguintes.

## Como as três se juntam

`oportunidades.py` orquestra, e a ordem importa por custo:

```
Open API (rápido, milhares de produtos)
        ↓  filtra por comissão e vendas mínimas
Navegador logado (lento, dezenas de produtos)
        ↓  conta vídeos só do que sobrou
Score
```

Contar vídeo de produto que já foi descartado por comissão baixa é desperdício
de um recurso caro. Por isso o filtro vem antes do navegador, e existe um teto
explícito (`--max-contagens`).

## O score

```
score ∝ (comissão em R$)  ×  log(1 + vendas)  ÷  (1 + vídeos)
```

Três decisões deliberadas:

- **Comissão em reais, não em porcentagem.** 30% de R$ 9,90 é R$ 2,97. 8% de
  R$ 300 é R$ 24. A porcentagem sozinha engana.
- **Log na demanda.** A diferença entre 10 e 100 vendas importa muito mais que
  entre 5.000 e 5.090. Sem o log, os campeões de venda — que são justamente os
  mais saturados — dominariam o ranking.
- **`1 +` no denominador.** Faz "zero vídeos" ser o melhor caso possível em vez
  de uma divisão por zero.

Produto sem contagem de vídeo coletada não vira o primeiro colocado por
omissão: ele entra assumindo o limite do oceano azul (5 vídeos), então falta de
dado nunca vira vantagem.

Um caso que o score marca à parte: comissão alta + zero vídeo + quase nenhuma
venda geralmente **não** é oportunidade. É produto ruim que ninguém quis
anunciar. Sai rotulado como `oceano azul (sem demanda comprovada)`.

## O que ficou para trás

`scraper.py`, `diagnose.py` e `cookie_helper.py` continuam no repositório como
histórico da investigação. Eles dependem de cookie exportado do navegador e
vão continuar dando 403 — o problema não era a implementação deles.

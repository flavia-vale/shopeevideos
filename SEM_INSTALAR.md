# Rodar sem instalar nada

Duas peças, nenhuma delas exige instalar coisa alguma no seu computador:

| o quê | onde roda | dá o quê |
|---|---|---|
| **Script do console** | seu navegador, já logado | quantos vídeos cada produto tem |
| **GitHub Actions** | nuvem do GitHub | comissão, vendas e o ranking final |

Elas se conversam por um CSV. Dá para usar só uma das duas, se preferir.

---

## Parte 1 — Contar vídeos no navegador

O bloqueio antigo (`403 is_login: false`) acontecia porque a Shopee checa
fingerprint de TLS e tokens que o JavaScript da página injeta — coisas que um
script de fora não consegue forjar. No console do navegador esse problema
simplesmente não existe: a requisição sai de dentro da página, do seu Chrome
logado. Para a Shopee é indistinguível de você clicando na interface.

1. Abra **https://sv.shopee.com.br** e confirme que está logada.
2. `F12` → aba **Console**.
3. Se o Chrome reclamar de colar, digite `allow pasting` e aperte ENTER.
4. Abra [`console/contar_videos.js`](console/contar_videos.js), copie tudo.
5. Antes de colar, edite a lista `PRODUTOS` no topo:

```js
const PRODUTOS = [
  "862915940/18399230627",
  "https://shopee.com.br/product/402625806/18499214488",
];
```

Aceita `shopId/itemId`, URL de produto ou `i.SHOP.ITEM`.

6. Cole no console e aperte ENTER.

Ele mostra o progresso, imprime uma tabela e **baixa um CSV** com
`chave, nome, videos, criadores, views, status`.

**Se algo der errado**

| aparece | o que fazer |
|---|---|
| "Abra https://sv.shopee.com.br antes" | você está em outro site; a API só aceita a chamada da mesma origem |
| `sem_login` | entre na sua conta na Shopee e rode de novo |
| `bloqueado` | aumente `PAUSA_MS` para 3000 ou mais |
| contagem parece errada | rode `copy(window.__shopeeRaw)` no console e me mande — é a resposta crua da API |

> Sobre a última linha: a lógica de contagem foi testada contra respostas
> simuladas, mas eu nunca consegui uma resposta real de 200 daqui (preciso da
> sua sessão para isso). Se o formato da resposta da Shopee for diferente do
> esperado, `window.__shopeeRaw` é o que permite consertar sem adivinhação.

---

## Parte 2 — Comissão e ranking no GitHub Actions

Roda nos servidores do GitHub. Você só clica.

### Preparo (uma vez só)

1. Pegue `App ID` e `App Secret` no painel de afiliados → **Open API**.
2. No GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
   - `SHOPEE_APP_ID`
   - `SHOPEE_APP_SECRET`

Os secrets ficam guardados pelo GitHub e não aparecem no log nem no chat.

### Rodar

Aba **Actions** → **Buscar oportunidades** → **Run workflow**.

| campo | para quê |
|---|---|
| `keyword` | nicho; vazio varre o catálogo de maior comissão |
| `limit` | quantas ofertas puxar |
| `min_comissao` | descarta comissão abaixo disso (%) |
| `min_vendas` | descarta produto sem demanda |
| `contagens` | caminho do CSV da Parte 1, se você já tiver |

No fim, baixe o artefato **oportunidades**:

- `oportunidades.csv` — ranking completo, abre no Excel
- `produtos.txt` — lista de candidatos pronta para colar na Parte 1
- `resultado.txt` — a tabela que apareceu no log

---

## O ciclo completo

```
Actions (sem contagens)
   ↓  produtos.txt  — os candidatos com boa comissão
Console do navegador
   ↓  CSV de vídeos  — quantos já postaram cada um
Actions (com contagens)
   ↓  ranking final
```

Para fechar o ciclo, o CSV da Parte 1 precisa estar no repositório. Sem
instalar nada: no GitHub, **Add file → Upload files**, arraste o CSV, faça o
commit. Depois rode o workflow de novo preenchendo `contagens` com o nome do
arquivo (ex.: `videos_shopee_2026-07-29.csv`).

A ordem importa por custo: contar vídeo é o passo lento, então só vale a pena
fazer isso com os produtos que já passaram no filtro de comissão.

## Se preferir pular a Parte 2

Dá para usar só o console. Você perde a comissão automática e o ranking, mas
ganha o dado que estava faltando — quantos vídeos cada produto já tem. É só
colar sua lista de produtos e ler a coluna `videos`: menos de 5 é oceano azul.

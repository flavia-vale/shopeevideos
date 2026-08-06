# Shopee Video — caçador de oportunidades

Acha produto com **comissão boa** e **poucos vídeos de afiliado** publicados.

O caminho antigo (copiar cookie e chamar a API interna) batia em `403 is_login:
false` e não tinha conserto. A abordagem atual puxa cada dado de onde ele
realmente está disponível — o raciocínio completo está em
[ESTRATEGIA.md](ESTRATEGIA.md).

```
shopeeops/affiliate_api.py   comissão + vendas   Open API oficial, assinada
shopeeops/sv_public.py       concorrência        SSR público, sem login
shopeeops/video_count.py     nº de vídeos        Chrome logado, fetch na página
shopeeops/scoring.py         ranking             ganho × demanda ÷ disputa
oportunidades.py             orquestra os três
```

> **Não pode instalar nada na sua máquina?** Veja
> **[SEM_INSTALAR.md](SEM_INSTALAR.md)** — script de console do navegador
> (conta os vídeos) + GitHub Actions (comissão e ranking). Zero instalação.

## Instalação

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Credenciais da Open API (painel de afiliados > Open API), num `.env`:

```
SHOPEE_APP_ID=...
SHOPEE_APP_SECRET=...
```

Login do navegador — manual, uma vez só:

```bash
python -m shopeeops.video_count login
```

Abre um Chrome visível. Entre na Shopee (QR code pelo app é o mais rápido) e
confirme abrindo um vídeo, ex.
`https://sv.shopee.com.br/web/@x/video/CGVdk7T6BwD4JYM_AAAAAA==`. A home do
sv.shopee.com.br só mostra "baixe o app" no desktop — isso é normal. Volte ao
terminal e aperte ENTER.

> **Se o captcha não carregar** ("Erro de Carregamento", `generate captcha
> error`): a Shopee detectou o navegador automatizado. Use o modo CDP, em que
> o Playwright **não abre** navegador nenhum e sim se conecta a um Chrome comum
> que você mesma abriu — sem flags de automação, o captcha funciona:
>
> ```bash
> python -m shopeeops.video_count login --cdp   # imprime o passo a passo
> ```
>
> Depois de logar no Chrome que ele mandou abrir, deixe-o aberto e acrescente
> `--cdp` aos outros comandos.

Para testar a sessão sem gastar uma varredura inteira:

```bash
python -m shopeeops.video_count check        # ou: check --cdp
```

## Uso

### Ranking de oportunidades

```bash
# varre o catálogo de maior comissão e conta os vídeos dos melhores
python oportunidades.py --limit 60

# nicho específico
python oportunidades.py --keyword "organizador de cozinha" --limit 40

# só comissão e demanda, sem abrir navegador — bem mais rápido
python oportunidades.py --keyword fone --sem-contagem

# salva para abrir no Excel
python oportunidades.py --limit 100 --csv oportunidades.csv
```

Saída:

```
  #   SCORE   COMIS    R$/VD     VEND    VÍD  PRODUTO
  1   100.0   20.0%    12.00      500      0  Suporte Articulado para Monitor
  2    41.2   15.0%     8.40      890      3  Kit Organizador de Gavetas 6 pçs
  3     0.6   20.0%    12.00      500    180  Fone Bluetooth TWS i12

Detalhe dos melhores:

  [100.0] Suporte Articulado para Monitor
      oceano azul — comissão de 20% | R$ 12.00 por venda | 500 vendas | nenhum vídeo publicado
      1234567/89012345  https://s.shopee.com.br/...
```

Parâmetros que mais importam:

| flag | padrão | o que faz |
|---|---|---|
| `--limit` | 50 | quantas ofertas puxar da Open API |
| `--min-comissao` | 8.0 | descarta comissão abaixo disso (%) |
| `--min-vendas` | 20 | descarta produto sem demanda comprovada |
| `--max-contagens` | 40 | teto de produtos para contar vídeo (passo caro) |
| `--sem-contagem` | off | pula o navegador |
| `--list-type` | 1 | 0=recomendados 1=maior comissão 2=melhor performance |
| `--delay` | 2.0 | segundos entre contagens |

### Contar vídeos de produtos específicos

```bash
python -m shopeeops.video_count count --products 862915940/18399230627
python -m shopeeops.video_count count --products-file lista.txt --json
```

Aceita `shop_id/item_id`, URL de produto ou `i.123.456`.

| status | significado |
|---|---|
| `ok` / `no_videos` | contagem obtida |
| `not_logged_in` | rode `python -m shopeeops.video_count login` |
| `blocked` | 418/429 — aumente `--delay` |
| `error` | falha de rede ou ID inválido |

### Espiar vídeos de concorrentes (sem login)

Dá o produto anunciado, views, likes e vendas de qualquer vídeo público:

```bash
python -m shopeeops.sv_public "https://sv.shopee.com.br/web/@alguem/video/POSTID"
python -m shopeeops.sv_public --file videos.txt --json corpus.json
```

Aceita URL completa, link `/share-video/...` ou só o `postId`. Junte as URLs
dos criadores que você acompanha e o comando monta o índice
produto → nº de vídeos, criadores, views medianas — útil para responder
"esse produto engaja?" antes de gastar tempo gravando.

## Como ler o resultado

- **`oceano azul` com vendas boas** — é o alvo.
- **`oceano azul (sem demanda comprovada)`** — cuidado. Zero vídeo e quase
  nenhuma venda costuma ser produto ruim, não oportunidade descoberta.
- **`saturado`** — mesmo com comissão ótima, seu vídeo vai competir com dezenas.
- **`?` na coluna VÍD** — o produto passou do teto `--max-contagens` ou a
  contagem falhou; ele foi ranqueado assumindo 5 vídeos.

## Legado

`scraper.py`, `diagnose.py` e `cookie_helper.py` são da investigação anterior.
Continuam aqui como histórico e vão continuar dando 403 — o problema nunca foi
a implementação deles. Veja [ESTRATEGIA.md](ESTRATEGIA.md).

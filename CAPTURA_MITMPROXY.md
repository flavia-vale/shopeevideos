# Captura do campo "Afiliados promoveram"

Objetivo: descobrir qual requisição do app da Shopee devolve aquele número.
É **uma vez só** — depois de descoberto, o endpoint fica no `endpoints.json` e
todo o resto do fluxo já está pronto.

O caminho é interceptar o tráfego do celular com o computador no meio. Você já
fez capturas `.mitm` antes, então o setup não é novo; a diferença é que agora o
`mitm_finder.py` aponta o campo sozinho, ao vivo, em vez de você garimpar o
dump depois.

Os passos abaixo assumem **iPhone** (é o do print). No fim tem a nota sobre
Android, que é bem mais chato.

---

## 1. Instalar o mitmproxy no PC

```
python -m pip install mitmproxy
```

## 2. Descobrir o IP do PC na rede

```
ipconfig
```

Procure o **Endereço IPv4** do adaptador do Wi-Fi — algo como `192.168.0.15`.
Anote.

O PC e o celular precisam estar **no mesmo Wi-Fi**. Se o seu Wi-Fi tiver
isolamento de clientes ativado (comum em rede de prédio), não vai funcionar;
nesse caso use o roteador de casa ou o hotspot do próprio PC.

## 3. Liberar no Firewall do Windows

Esse é o passo que todo mundo esquece e que faz parecer que nada funciona.

```
netsh advfirewall firewall add rule name="mitmproxy" dir=in action=allow protocol=TCP localport=8080
```

Rode no **Prompt como Administrador**. Sem isso o Windows bloqueia a conexão do
celular em silêncio.

## 4. Subir o proxy já procurando o número

Abra o produto no app **antes**, veja quanto está escrito em "Afiliados
promoveram", e passe esse valor:

```
cd C:\Users\tacia\shopeevideos\shopeevideos
mitmdump -s mitm_finder.py --set alvo="1,2mil+" --listen-port 8080
```

Deixe essa janela aberta.

## 5. Apontar o iPhone para o proxy

1. Ajustes → Wi-Fi → toque no **(i)** azul da sua rede
2. Role até **Proxy HTTP** → **Manual**
3. **Servidor**: o IP do passo 2 · **Porta**: `8080`
4. Salvar

## 6. Instalar o certificado no iPhone

Sem isso o celular recusa todo site em HTTPS.

1. No Safari do iPhone, abra: **http://mitm.it**
   (se essa página não carregar, o proxy não está recebendo — volte ao passo 3)
2. Toque em **iOS** e permita baixar o perfil
3. Ajustes → **Perfil Baixado** → Instalar (pede a senha do aparelho)
4. **Passo obrigatório e fácil de pular:** Ajustes → Geral → Sobre → role até o
   fim → **Ajustes de Confiança do Certificado** → ative a chave do
   **mitmproxy**

Sem o passo 4 o certificado fica instalado mas não confiável, e o app não abre.

## 7. Capturar

No app da Shopee, abra a tela de afiliado do produto — a do "Compartilhe para
Ganhar", onde aparece "1,2mil+ Afiliados promoveram". Se já estiver aberta,
feche e abra de novo, ou puxe para atualizar: só passa pelo proxy o que for
buscado agora (o que veio de cache não gera requisição).

No terminal deve aparecer:

```
======================================================================
ACHEI o valor 1247 em:
  POST https://sv.shopee.com.br/api/vX/alguma/coisa
  caminho JSON: data.product.affiliate_promoted_count
======================================================================
Config gravada em C:\...\endpoints.json.sugerido
```

## 8. Ativar

```
copy endpoints.json.sugerido endpoints.json
```

Abra o `endpoints.json` e troque os IDs fixos do `payload` pelos marcadores:

```json
"payload": {
  "item_id": "{item_id}",
  "shop_id": "{shop_id}"
}
```

O `mitm_finder` não faz essa troca sozinho porque não tem como saber quais
números do payload são os IDs do produto e quais são outra coisa.

## 9. Desfazer o proxy

Terminada a captura, **volte o Proxy HTTP do iPhone para Desligado**. Enquanto
estiver apontado para o PC, o celular só navega com o `mitmdump` rodando.

## 10. Testar

```
python cookie_helper.py --test
```

Agora o passo [2] deve passar e mostrar a contagem de afiliados. Se passar:

```
python affiliate_scan.py --products-file lista.txt --output csv --output-file achados.csv
```

---

## Se não aparecer nada

**A tela do app abre normal, mas o terminal não mostra a linha "ACHEI".**
O número pode estar vindo num formato que o filtro não pegou. Rode sem o
`--set alvo`, que entra em modo exploratório e lista todo campo com nome
parecido com afiliado/promoção:

```
mitmdump -s mitm_finder.py --listen-port 8080
```

**O app da Shopee não carrega nada, ou dá erro de conexão.**
Isso é *certificate pinning*: o app carrega o certificado esperado dentro dele e
recusa o do mitmproxy. Se for o caso, o app fica inutilizável enquanto o proxy
estiver ligado — e não há solução simples sem jailbreak.

Alternativa quando bate nisso: abrir a **página de afiliado pelo Safari** do
iPhone, com o proxy ligado. O navegador confia no certificado que você instalou,
então a captura funciona. Não sei dizer se aquele número aparece na versão web
da página — vale testar, é rápido.

**Só aparece tráfego que não é da Shopee.**
Confirme que o proxy do Wi-Fi está mesmo salvo (às vezes o iOS descarta ao sair
da tela sem tocar em Salvar) e que o app foi fechado e reaberto de verdade
(deslize para cima para encerrar, não só voltar à tela inicial).

---

## Sobre Android

A partir do Android 7, os apps ignoram certificados instalados pelo usuário —
só confiam nos do sistema. Ou seja, mesmo instalando o certificado direitinho, o
app da Shopee não vai passar pelo proxy sem root.

Se o seu caso for Android, o caminho realista é o Safari/Chrome do próprio
celular (a mesma alternativa da seção anterior) ou capturar de um iPhone
emprestado.

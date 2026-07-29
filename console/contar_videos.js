/* ═══════════════════════════════════════════════════════════════════════════
   CONTADOR DE VÍDEOS DA SHOPEE — roda no console do navegador, sem instalar nada

   COMO USAR
   ---------
   1. Abra  https://sv.shopee.com.br  e confirme que está logada.
   2. Aperte F12 e vá na aba "Console".
   3. Se o Chrome pedir, digite  allow pasting  e aperte ENTER.
   4. Edite a lista PRODUTOS logo abaixo.
   5. Cole este arquivo inteiro no console e aperte ENTER.

   No fim baixa um CSV automaticamente.

   POR QUE ISSO FUNCIONA E O SCRIPT EM PYTHON NÃO FUNCIONAVA
   ---------------------------------------------------------
   A Shopee não checa só o cookie. Ela checa fingerprint de TLS, ordem de
   headers e tokens que o SDK anti-bot injeta via JavaScript. Copiar cookie
   para dentro do httpx reproduz um sinal e nenhum dos outros — daí o
   403 is_login:false.

   Aqui o fetch sai de dentro da própria página, no seu navegador logado.
   O Chrome anexa tudo sozinho. Para a Shopee é indistinguível de você
   clicando na interface, porque literalmente é.
   ═══════════════════════════════════════════════════════════════════════════ */

// ── EDITE AQUI ──────────────────────────────────────────────────────────────
// Aceita "shopId/itemId", URL do produto, ou o formato i.SHOP.ITEM
const PRODUTOS = [
  "862915940/18399230627",
  "1566455712/22494667561",
  "https://shopee.com.br/product/402625806/18499214488",
];

const PAUSA_MS = 1500;   // intervalo entre produtos; aumente se tomar bloqueio
// ────────────────────────────────────────────────────────────────────────────

(async () => {
  "use strict";

  const API = "https://sv.shopee.com.br/api/v2/timeline/unify/common";
  const TAMANHO_PAGINA = 30;
  const MAX_PAGINAS = 20;

  if (location.hostname !== "sv.shopee.com.br") {
    console.error(
      "%c Abra https://sv.shopee.com.br antes de colar isto. ",
      "background:#c00;color:#fff;font-size:14px;padding:4px"
    );
    console.error(
      "O fetch precisa sair da mesma origem da API, senão o navegador bloqueia por CORS."
    );
    return;
  }

  const dorme = (ms) => new Promise((r) => setTimeout(r, ms));

  function extrairIds(bruto) {
    const m = String(bruto).match(/(?:i\.|product\/|product-i\.)?(\d{6,})[/.](\d{6,})/);
    if (!m) throw new Error(`não consegui ler shopId/itemId de "${bruto}"`);
    return { shopId: Number(m[1]), itemId: Number(m[2]) };
  }

  function montarPayload(shopId, itemId, offset) {
    return {
      limit: TAMANHO_PAGINA,
      page_context: JSON.stringify({
        item_id: itemId,
        shop_id: shopId,
        offset,
        template_tab_id: "5",        // aba "Aprenda com criadores"
        order_type: 1,
      }),
      request_type: 0,
      lang: "pt-BR",
      page_no: Math.floor(offset / TAMANHO_PAGINA) + 1,
      need_product_v2: true,
      product_v2_scene: "affiliate_video_common_timeline",
    };
  }

  // A resposta já mudou de formato algumas vezes — procuramos a lista onde ela estiver.
  function extrairItens(body) {
    const d = body && body.data;
    if (!d || typeof d !== "object") return [];
    for (const k of ["list", "items", "sections", "feeds", "data"]) {
      if (Array.isArray(d[k]) && d[k].length) return d[k];
    }
    return [];
  }

  function extrairTotal(body) {
    const d = body && body.data;
    if (!d || typeof d !== "object") return null;
    for (const k of ["total_count", "total", "count", "video_count"]) {
      if (Number.isInteger(d[k]) && d[k] >= 0) return d[k];
    }
    return null;
  }

  function resumir(itens) {
    const criadores = new Set();
    let views = 0;
    for (const it of itens) {
      const meta = it && it.meta;
      if (!meta) continue;
      if (meta.userId) criadores.add(meta.userId);
      views += Number((meta.countInfo && meta.countInfo.views) || 0);
    }
    return { criadores: criadores.size, views };
  }

  async function contar(bruto) {
    const { shopId, itemId } = extrairIds(bruto);
    const chave = `${shopId}/${itemId}`;
    const vistos = [];
    let offset = 0;
    let totalInformado = null;
    let nome = "";

    for (let p = 0; p < MAX_PAGINAS; p++) {
      const resp = await fetch(API, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify(montarPayload(shopId, itemId, offset)),
      });

      let body = null;
      try {
        body = await resp.json();
      } catch (e) {
        return { chave, nome, videos: null, status: "resposta_ilegivel", detalhe: String(e) };
      }

      // guarda a primeira resposta crua: se o formato tiver mudado, é o que
      // permite consertar o parser sem adivinhar
      if (!window.__shopeeRaw) window.__shopeeRaw = { chave, status: resp.status, body };

      if (resp.status === 403 || resp.status === 401 || body.is_login === false) {
        return {
          chave, nome, videos: null, status: "sem_login",
          detalhe: "faça login em sv.shopee.com.br e rode de novo",
        };
      }
      if (resp.status === 418 || resp.status === 429) {
        return {
          chave, nome, videos: null, status: "bloqueado",
          detalhe: `HTTP ${resp.status} — aumente PAUSA_MS`,
        };
      }
      if (!resp.ok) {
        return { chave, nome, videos: null, status: "erro", detalhe: `HTTP ${resp.status}` };
      }

      if (totalInformado === null) totalInformado = extrairTotal(body);

      const itens = extrairItens(body);
      if (!nome && itens.length) {
        const c = itens[0].content || {};
        nome = (c.productV2 && c.productV2.itemName) ||
               (c.products && c.products.anchorProduct && c.products.anchorProduct.name) || "";
      }
      vistos.push(...itens);
      if (itens.length < TAMANHO_PAGINA) break;
      offset += TAMANHO_PAGINA;
      await dorme(400);
    }

    // o total que a própria API informa vale mais que a contagem por paginação,
    // mas nem toda versão da resposta traz esse campo
    const total = totalInformado !== null ? totalInformado : vistos.length;
    const { criadores, views } = resumir(vistos);
    return {
      chave, nome,
      videos: total,
      criadores,
      views,
      status: total ? "ok" : "sem_videos",
      detalhe: totalInformado !== null ? "total da API" : "contagem por paginação",
    };
  }

  function baixarCSV(linhas) {
    const cols = ["chave", "nome", "videos", "criadores", "views", "status", "detalhe"];
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv = "﻿" + [
      cols.join(","),
      ...linhas.map((l) => cols.map((c) => esc(l[c])).join(",")),
    ].join("\n");

    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `videos_shopee_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  console.log(
    `%c Contando vídeos de ${PRODUTOS.length} produto(s)… `,
    "background:#ee4d2d;color:#fff;font-size:14px;padding:4px"
  );

  const resultados = [];
  for (let i = 0; i < PRODUTOS.length; i++) {
    let r;
    try {
      r = await contar(PRODUTOS[i]);
    } catch (e) {
      r = { chave: PRODUTOS[i], nome: "", videos: null, status: "erro", detalhe: String(e) };
    }
    resultados.push(r);
    console.log(
      `[${i + 1}/${PRODUTOS.length}] ${r.chave}  →  ${r.videos ?? "—"} vídeos  (${r.status})` +
        (r.nome ? `  ${r.nome.slice(0, 50)}` : "")
    );

    if (r.status === "sem_login") {
      console.error("Parando: sessão ausente. Faça login e rode de novo.");
      break;
    }
    if (i + 1 < PRODUTOS.length) await dorme(PAUSA_MS);
  }

  console.table(
    resultados.map((r) => ({
      produto: r.chave,
      videos: r.videos,
      criadores: r.criadores,
      views: r.views,
      status: r.status,
      nome: (r.nome || "").slice(0, 40),
    }))
  );

  window.__shopeeResultados = resultados;
  baixarCSV(resultados);

  console.log(
    "%c Pronto. CSV baixado. ",
    "background:#0a0;color:#fff;font-size:14px;padding:4px"
  );
  console.log(
    "Resultados também em window.__shopeeResultados — e a primeira resposta crua " +
      "da API em window.__shopeeRaw (útil se a contagem vier errada)."
  );
})();

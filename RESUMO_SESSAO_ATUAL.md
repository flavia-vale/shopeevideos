# Resumo da Sessão - Shopee Video Counter 🚀

**Data:** 26 de Abril de 2026
**Objetivo:** Identificar "Oceanos Azuis" contando vídeos na aba de criadores da Shopee.

---

## 🛠️ O que foi implementado hoje

### 1. Mudança de Estratégia (Playwright -> API)
Abandonamos a automação de navegador (Playwright) por ser pesada e facilmente detectada. Agora usamos **chamadas diretas de API** com a biblioteca `httpx`, simulando um dispositivo móvel (iPhone).

### 2. Scripts Atualizados
- **`scraper.py` (v2.2):** Versão "Super Stealth". Agora ele visita a página do produto antes da API para tentar capturar o `csrftoken` dinamicamente. Suporta HTTP/2.
- **`diagnose.py` (v3.2):** Ferramenta de teste rápido. Verifica se a sessão está viva e se a API de vídeos está acessível.
- **`cookie_helper.py`:** Validador de sanidade para o arquivo `cookies.json`.

### 3. Técnicas de Anti-Detecção
- Uso de **User-Agent** de iPhone real.
- Implementação de **HTTP/2** para mimetizar navegadores modernos.
- Fluxo de navegação simulado (Visita -> Captura de Token -> Chamada de API).

---

## 🚧 Status Atual e Desafios
- **Bloqueio 418:** A Shopee está retornando "418 I'm a teapot" quando detecta comportamento suspeito ou falta de tokens.
- **csrftoken:** O token de segurança é essencial. Se a extensão não capturar, ele deve ser buscado manualmente no console do navegador (F12 > Network).

---

## 🚀 Como Retomar na Próxima Sessão

1.  **Atualizar Cookies:**
    - Logue na Shopee no Chrome.
    - Adicione um item ao carrinho (força a geração do `csrftoken`).
    - Exporte o JSON para `cookies.json`.
2.  **Validar Conexão:**
    ```bash
    python3 cookie_helper.py
    ```
3.  **Rodar Diagnóstico:**
    ```bash
    python3 diagnose.py --product 1390609298/58252888703
    ```
4.  **Executar Scraper:**
    ```bash
    python3 scraper.py --products 1390609298/58252888703 --debug
    ```

---

## 💡 Dicas de Ouro
- **Troca de IP:** Se o erro 418 persistir, use o 4G do celular roteado.
- **Token Manual:** Se o `csrftoken` não vier no arquivo, procure por `x-csrftoken` nas requisições da aba Network do navegador e adicione manualmente ao `cookies.json`.

---
*Resumo gerado para facilitar a continuidade do desenvolvimento.*
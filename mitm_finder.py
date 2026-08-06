"""
Addon de mitmproxy que acha o campo "Afiliados promoveram" ao vivo.

Em vez de salvar um dump e vasculhar depois, ele inspeciona cada resposta que
passa pelo proxy e avisa na hora em que achar o número que você está vendo na
tela do app — junto com a URL, o método e o caminho JSON exato.

Uso:
    mitmdump -s mitm_finder.py --set alvo="1,2mil+"

Depois abra no app a tela de afiliado do produto (a do "Compartilhe para
Ganhar") e olhe o terminal. Quando ele achar, grava um endpoints.json.sugerido
que é só conferir e renomear.

Sem `--set alvo=...` ele funciona em modo exploratório, listando todo campo com
nome parecido com contagem de afiliados.
"""

import json
from pathlib import Path

from find_affiliate_field import SUSPECT_KEY_RE, matches_target, walk
from shopee_ids import parse_br_number

SUGESTAO = Path("endpoints.json.sugerido")


def analisar(corpo: bytes, alvo: int | None):
    """
    Procura o número no corpo da resposta.

    Devolve (achados_exatos, achados_por_nome) como listas de (caminho, valor).
    """
    try:
        dados = json.loads(corpo)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return [], []

    exatos, por_nome = [], []
    for caminho, chave, valor in walk(dados):
        if alvo is not None and matches_target(valor, alvo):
            exatos.append((caminho, valor))
        elif SUSPECT_KEY_RE.search(chave) and isinstance(valor, (int, float)):
            por_nome.append((caminho, valor))

    return exatos, por_nome


def montar_config(url: str, metodo: str, corpo_req: bytes, caminho: str) -> dict:
    """Monta o endpoints.json a partir da requisição que devolveu o campo."""
    try:
        payload = json.loads(corpo_req) if corpo_req else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}

    return {
        "_comentario": [
            "Gerado pelo mitm_finder. Confira antes de usar:",
            "troque os IDs fixos do payload por {shop_id} e {item_id}.",
        ],
        "affiliate_stats": {
            "method": metodo,
            "url": url,
            "headers": {},
            "payload": payload,
            "payload_json_fields": [],
            "affiliate_count_path": caminho,
            "sales_path": "",
        },
    }


class Localizador:
    def __init__(self):
        self.alvo = None
        self.ja_avisou = False

    def load(self, loader):
        loader.add_option(
            "alvo", str, "", 'número visto na tela do app, ex: "1,2mil+" ou "557"'
        )

    def configure(self, updated):
        from mitmproxy import ctx

        if "alvo" in updated and ctx.options.alvo:
            self.alvo = parse_br_number(ctx.options.alvo)
            if self.alvo is None:
                ctx.log.warn(f"Não entendi o alvo {ctx.options.alvo!r}")
            else:
                ctx.log.info(f"Procurando o valor {self.alvo} nas respostas...")

    def response(self, flow):
        from mitmproxy import ctx

        if "shopee" not in flow.request.pretty_host:
            return
        if not flow.response or not flow.response.content:
            return

        exatos, por_nome = analisar(flow.response.content, self.alvo)

        if exatos:
            caminho, valor = exatos[0]
            ctx.log.alert(
                f"\n{'=' * 70}\n"
                f"ACHEI o valor {valor} em:\n"
                f"  {flow.request.method} {flow.request.pretty_url}\n"
                f"  caminho JSON: {caminho}\n"
                f"{'=' * 70}"
            )

            if not self.ja_avisou:
                config = montar_config(
                    flow.request.pretty_url,
                    flow.request.method,
                    flow.request.content or b"",
                    caminho,
                )
                SUGESTAO.write_text(
                    json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                ctx.log.alert(f"Config gravada em {SUGESTAO.resolve()}")
                self.ja_avisou = True

        elif por_nome:
            achados = ", ".join(f"{c}={v}" for c, v in por_nome[:5])
            ctx.log.info(f"[nome suspeito] {flow.request.path[:60]} → {achados}")


addons = [Localizador()]

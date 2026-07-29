"""
shopeeops — motor de oportunidades para Shopee Video.

Três fontes de dados independentes:

  affiliate_api  comissão + demanda, via Open API oficial de afiliados (assinada)
  sv_public      dados públicos de vídeos, via SSR de sv.shopee.com.br (sem login)
  video_count    contagem de vídeos por produto, via navegador logado real

E um combinador:

  scoring        transforma as três em um ranking de oportunidade
"""

__version__ = "3.0.0"

"""Views do app nucleo (Página Inicial, proxy interno de CEP e entrega de arquivo privado)."""

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.views import View

from nucleo.arquivos import ArquivoService
from nucleo.exceptions import (
    CepInvalido,
    CepNaoEncontrado,
    LimiteTaxaExcedido,
    LinkArquivoExpirado,
    ServicoCepIndisponivel,
)
from nucleo.mixins import AutenticadoAtivoMixin
from nucleo.rate_limit import exigir_limite_taxa, obter_ip_cliente
from nucleo.services import CepService, HomeService

AVISO_RNF13 = "O ReMed não substitui avaliação médica ou farmacêutica."


class HomeView(View):
    """Página Inicial pública do ReMed na rota raiz `/`."""

    template_name = "nucleo/home.html"

    def get(self, request):
        resumo = HomeService.obter_resumo_publico()
        return render(
            request,
            self.template_name,
            {
                "resumo_publico": resumo,
                "aviso_rnf13": AVISO_RNF13,
            },
        )


class CepConsultarView(View):
    """Endpoint JSON interno para preenchimento automático de endereço por CEP."""

    def get(self, request, cep: str):
        try:
            exigir_limite_taxa(
                escopo="cep_consultar",
                identificador=obter_ip_cliente(request),
                limite=settings.REMED_CEP_RATE_LIMIT_IP_MINUTO,
                janela_segundos=60,
                mensagem=(
                    "Muitas consultas de CEP em pouco tempo. "
                    "Aguarde um minuto ou preencha manualmente."
                ),
            )
            dados = CepService.consultar(cep)
        except LimiteTaxaExcedido as erro:
            return JsonResponse({"erro": str(erro), "preenchimento_manual": True}, status=429)
        except CepInvalido as erro:
            return JsonResponse({"erro": str(erro)}, status=400)
        except CepNaoEncontrado as erro:
            return JsonResponse({"erro": str(erro), "preenchimento_manual": True}, status=404)
        except ServicoCepIndisponivel as erro:
            return JsonResponse({"erro": str(erro), "preenchimento_manual": True}, status=503)

        return JsonResponse(
            {
                "cep": dados.cep,
                "logradouro": dados.logradouro,
                "bairro": dados.bairro,
                "municipio": dados.municipio,
                "estado": dados.estado,
            },
            status=200,
        )


class ArquivoPrivadoTemporarioView(AutenticadoAtivoMixin, View):
    """Entrega local de arquivo privado mediante token assinado de 60 s (ADR 0016)."""

    def get(self, request, token: str):
        try:
            arquivo = ArquivoService.abrir_por_token_temporario(
                token,
                usuario_id=request.user.pk,
            )
        except LinkArquivoExpirado as erro:
            raise Http404(str(erro)) from erro

        resposta = FileResponse(
            arquivo.caminho.open("rb"),
            content_type=arquivo.mime_verificado,
            as_attachment=True,
            filename=arquivo.nome_download,
        )
        resposta["X-Content-Type-Options"] = "nosniff"
        resposta["Cache-Control"] = "no-store"
        resposta["Pragma"] = "no-cache"
        return resposta

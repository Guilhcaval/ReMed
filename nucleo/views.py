"""Views do app nucleo (proxy interno de CEP — ADR 0018)."""

from django.conf import settings
from django.http import JsonResponse
from django.views import View

from nucleo.exceptions import (
    CepInvalido,
    CepNaoEncontrado,
    LimiteTaxaExcedido,
    ServicoCepIndisponivel,
)
from nucleo.rate_limit import exigir_limite_taxa, obter_ip_cliente
from nucleo.services import CepService


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

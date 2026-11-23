"""Views baseadas em classe do app notificacoes (Spec 03 / RF017 — sem ORM)."""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from notificacoes.forms import NotificacaoFiltroForm
from notificacoes.services import FiltrosNotificacao, NotificacaoService
from nucleo.exceptions import RecursoNaoEncontrado
from nucleo.mixins import AutenticadoAtivoMixin


def _destino_seguro(request, candidato: str | None) -> str:
    if candidato and url_has_allowed_host_and_scheme(
        url=candidato,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidato
    return reverse("notificacoes:lista")


class NotificacaoListaView(AutenticadoAtivoMixin, View):
    template_name = "notificacoes/notificacao_lista.html"

    def get(self, request):
        form = NotificacaoFiltroForm(request.GET or None)
        if request.GET and form.is_valid():
            filtros = form.para_filtros()
        else:
            filtros = FiltrosNotificacao()

        try:
            pagina_num = max(1, int(request.GET.get("page", "1")))
        except ValueError:
            pagina_num = 1

        resultado = NotificacaoService.listar_do_usuario(
            request.user.id,
            filtros,
            pagina=pagina_num,
        )
        tem_filtros = any(
            [
                filtros.tipo,
                filtros.status,
                filtros.data_inicio is not None,
                filtros.data_fim is not None,
            ]
        )
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "pagina": resultado.pagina,
                "total_nao_lidas": resultado.total_nao_lidas,
                "total_filtradas": resultado.total_filtradas,
                "tem_filtros": tem_filtros,
            },
        )


class NotificacaoMarcarLidaView(AutenticadoAtivoMixin, View):
    """Marca uma notificação do próprio usuário como lida (POST exclusivo com CSRF)."""

    def post(self, request, notificacao_id: int):
        try:
            notificacao = NotificacaoService.marcar_como_lida(notificacao_id, request.user.id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        destino_solicitado = request.POST.get("next") or notificacao.url_destino
        return redirect(_destino_seguro(request, destino_solicitado))


class NotificacaoMarcarTodasLidasView(AutenticadoAtivoMixin, View):
    """Marca todas as notificações não lidas do usuário como lidas (POST exclusivo com CSRF)."""

    def post(self, request):
        quantidade = NotificacaoService.marcar_todas_como_lidas(request.user.id)
        if quantidade > 0:
            messages.success(
                request,
                f"{quantidade} notificação(ões) marcada(s) como lida(s).",
            )
        return redirect("notificacoes:lista")

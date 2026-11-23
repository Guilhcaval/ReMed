"""Views baseadas em classe do app contas (Spec 01 / RF001 — sem consultas ao ORM)."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from contas.exceptions import (
    CpfJaCadastrado,
    EmailJaCadastrado,
    EncerramentoContaBloqueado,
    SenhaAtualInvalida,
    TokenConfirmacaoInvalido,
)
from contas.forms import (
    ReenviarConfirmacaoForm,
    UsuarioCadastroForm,
    UsuarioEncerrarContaForm,
    UsuarioPerfilEditarForm,
)
from contas.services import UsuarioService
from nucleo.exceptions import LimiteTaxaExcedido, RecursoNaoEncontrado, RegraNegocioViolada
from nucleo.mixins import AutenticadoAtivoMixin, VisitanteObrigatorioMixin
from nucleo.rate_limit import exigir_limite_taxa, obter_ip_cliente
from nucleo.validators import formatar_celular, formatar_cep, formatar_cpf

MSG_REENVIO_GENERICA = (
    "Se o e-mail informado estiver cadastrado e pendente de confirmação, "
    "enviaremos um novo link em instantes."
)


def _construtor_url_confirmacao(request):
    def _construir(token: str) -> str:
        caminho = reverse("contas:confirmar_email", kwargs={"token": token})
        return request.build_absolute_uri(caminho)

    return _construir


class UsuarioCadastroView(VisitanteObrigatorioMixin, View):
    template_name = "contas/usuario_cadastro.html"

    def _contexto(self, form: UsuarioCadastroForm) -> dict:
        return {
            "form": form,
            "versao_termos": settings.REMED_TERMOS_VERSAO_ATUAL,
        }

    def get(self, request):
        return render(request, self.template_name, self._contexto(UsuarioCadastroForm()))

    def post(self, request):
        form = UsuarioCadastroForm(request.POST)
        try:
            exigir_limite_taxa(
                escopo="cadastro_usuario_ip",
                identificador=obter_ip_cliente(request),
                limite=settings.REMED_CADASTRO_LIMITE_IP_HORA,
                janela_segundos=3600,
                mensagem=(
                    "Muitas tentativas de cadastro a partir deste endereço. "
                    "Aguarde alguns minutos e tente novamente."
                ),
            )
        except LimiteTaxaExcedido as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(request, self.template_name, self._contexto(form), status=429)

        if not form.is_valid():
            return render(request, self.template_name, self._contexto(form))

        try:
            UsuarioService.cadastrar(
                form.para_dados(),
                construir_url_confirmacao=_construtor_url_confirmacao(request),
            )
        except CpfJaCadastrado as erro:
            form.add_error("cpf", ValidationError(str(erro), code="cpf_duplicado"))
            return render(request, self.template_name, self._contexto(form))
        except EmailJaCadastrado as erro:
            form.add_error("email", ValidationError(str(erro), code="email_duplicado"))
            return render(request, self.template_name, self._contexto(form))
        except RegraNegocioViolada as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(request, self.template_name, self._contexto(form))

        messages.success(
            request,
            "Cadastro realizado com sucesso. Enviamos um link de confirmação para o seu e-mail; "
            "confirme-o antes de entrar na sua conta.",
        )
        return redirect("contas:cadastro")


class ConfirmarEmailView(View):
    template_name = "contas/confirmacao_email_resultado.html"

    def get(self, request, token: str):
        try:
            resultado = UsuarioService.confirmar_email(token)
        except (TokenConfirmacaoInvalido, EmailJaCadastrado) as erro:
            # Retorna HTTP 200 (como PasswordResetConfirmView) para evitar que django.request
            # registre em log a URL contendo o token de confirmação.
            return render(
                request,
                self.template_name,
                {"confirmado": False, "mensagem_erro": str(erro)},
            )

        return render(
            request,
            self.template_name,
            {"confirmado": True, "tipo_confirmacao": resultado.tipo},
        )


class ReenviarConfirmacaoEmailView(View):
    template_name = "contas/reenviar_confirmacao.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ReenviarConfirmacaoForm()})

    def post(self, request):
        form = ReenviarConfirmacaoForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        email = form.cleaned_data["email"]
        limite_hora = settings.REMED_CONFIRMACAO_EMAIL_REENVIO_LIMITE_HORA
        mensagem_429 = (
            "Limite de solicitações de reenvio atingido. Aguarde uma hora e tente novamente."
        )
        try:
            exigir_limite_taxa(
                escopo="reenviar_confirmacao_ip",
                identificador=obter_ip_cliente(request),
                limite=limite_hora,
                janela_segundos=3600,
                mensagem=mensagem_429,
            )
            exigir_limite_taxa(
                escopo="reenviar_confirmacao_email",
                identificador=email,
                limite=limite_hora,
                janela_segundos=3600,
                mensagem=mensagem_429,
            )
        except LimiteTaxaExcedido as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(request, self.template_name, {"form": form}, status=429)

        UsuarioService.reenviar_confirmacao_email(
            email,
            construir_url_confirmacao=_construtor_url_confirmacao(request),
        )
        messages.info(request, MSG_REENVIO_GENERICA)
        return redirect("contas:reenviar_confirmacao")


class UsuarioPerfilEditarView(AutenticadoAtivoMixin, View):
    template_name = "contas/usuario_perfil_editar.html"

    def _dados_iniciais(self, perfil) -> dict:
        usuario = perfil.usuario
        endereco = perfil.endereco
        iniciais = {
            "nome_completo": usuario.nome_completo,
            "data_nascimento": usuario.data_nascimento,
            "email": usuario.email,
            "celular": formatar_celular(usuario.celular),
            "perfil_doador": usuario.perfil_doador,
            "perfil_solicitante": usuario.perfil_solicitante,
            "perfil_cuidador": usuario.perfil_cuidador,
        }
        if endereco is not None:
            iniciais.update(
                {
                    "cep": formatar_cep(endereco.cep),
                    "logradouro": endereco.logradouro,
                    "numero": endereco.numero,
                    "bairro": endereco.bairro,
                    "municipio": endereco.municipio,
                    "estado": endereco.estado,
                    "complemento": endereco.complemento,
                }
            )
        return iniciais

    def _contexto(self, form: UsuarioPerfilEditarForm, perfil) -> dict:
        return {
            "form": form,
            "cpf_formatado": formatar_cpf(perfil.usuario.cpf or ""),
            "email_pendente": perfil.email_pendente,
            "criado_em": perfil.usuario.criado_em,
        }

    def get(self, request):
        try:
            perfil = UsuarioService.obter_perfil(request.user.id)
        except RecursoNaoEncontrado:
            return HttpResponseForbidden("Perfil indisponível.")
        form = UsuarioPerfilEditarForm(initial=self._dados_iniciais(perfil))
        return render(request, self.template_name, self._contexto(form, perfil))

    def post(self, request):
        try:
            perfil = UsuarioService.obter_perfil(request.user.id)
        except RecursoNaoEncontrado:
            return HttpResponseForbidden("Perfil indisponível.")

        form = UsuarioPerfilEditarForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self._contexto(form, perfil))

        try:
            resultado = UsuarioService.atualizar_perfil(
                request.user.id,
                form.para_dados(),
                construir_url_confirmacao=_construtor_url_confirmacao(request),
            )
        except EmailJaCadastrado as erro:
            form.add_error("email", ValidationError(str(erro), code="email_duplicado"))
            return render(request, self.template_name, self._contexto(form, perfil))
        except RegraNegocioViolada as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(request, self.template_name, self._contexto(form, perfil))

        if resultado.troca_email_pendente:
            messages.success(
                request,
                "Dados atualizados com sucesso. Enviamos um link de confirmação para o novo "
                "e-mail informado; seu e-mail atual permanecerá ativo até a confirmação.",
            )
        else:
            messages.success(request, "Dados cadastrais atualizados com sucesso.")
        return redirect("contas:perfil_editar")


class UsuarioEncerrarContaView(AutenticadoAtivoMixin, View):
    template_name = "contas/usuario_encerrar_conta.html"

    def get(self, request):
        return render(request, self.template_name, {"form": UsuarioEncerrarContaForm()})

    def post(self, request):
        form = UsuarioEncerrarContaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        try:
            UsuarioService.encerrar_conta(
                request.user,
                form.cleaned_data["senha_atual"],
            )
        except SenhaAtualInvalida as erro:
            form.add_error("senha_atual", ValidationError(str(erro), code="invalid"))
            return render(request, self.template_name, {"form": form})
        except EncerramentoContaBloqueado as erro:
            return HttpResponseForbidden(str(erro))
        except RegraNegocioViolada as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(request, self.template_name, {"form": form})

        logout(request)
        messages.success(
            request,
            "Sua conta foi encerrada e seus dados pessoais foram eliminados/anonimizados.",
        )
        return redirect("contas:cadastro")

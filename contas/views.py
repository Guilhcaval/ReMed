"""Views baseadas em classe do app contas (Specs 01 e 02 — sem consultas ao ORM)."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from contas.exceptions import (
    AcumuloFuncoesProibido,
    CodigoRecuperacaoInvalido,
    CodigoTotpInvalido,
    ContaAnonimizadaImutavel,
    ContaBloqueadaTemporariamente,
    ContaIndisponivel,
    CpfJaCadastrado,
    CredenciaisInvalidas,
    EmailJaCadastrado,
    EmailNaoConfirmado,
    EncerramentoContaBloqueado,
    MotivoObrigatorio,
    ResetTotpNaoPermitido,
    SenhaAtualInvalida,
    TokenConfirmacaoInvalido,
    TotpBloqueadoTemporariamente,
    TotpJaAtivado,
    TotpNaoConfigurado,
    UltimoAdministradorAtivo,
)
from contas.forms import (
    AdminAlterarFuncoesForm,
    AdminAlterarStatusForm,
    AdminResetar2faForm,
    AdminUsuarioConsultaForm,
    LoginForm,
    ReenviarConfirmacaoForm,
    TotpCodigoForm,
    TotpRecuperacaoForm,
    UsuarioCadastroForm,
    UsuarioEncerrarContaForm,
    UsuarioPerfilEditarForm,
)
from contas.services import (
    ROTULOS_FUNCOES_ADMIN,
    AutenticacaoService,
    FiltrosConsultaUsuarios,
    GestaoUsuariosService,
    SessaoService,
    TotpService,
    UsuarioService,
)
from nucleo.exceptions import (
    LimiteTaxaExcedido,
    PermissaoNegada,
    RecursoNaoEncontrado,
    RegraNegocioViolada,
)
from nucleo.mixins import (
    SESSAO_CHAVE_2FA_VERIFICADO,
    AutenticadoAtivoMixin,
    ContaAdminPendente2faMixin,
    FuncaoAdminObrigatoriaMixin,
    VisitanteObrigatorioMixin,
)
from nucleo.rate_limit import exigir_limite_taxa, obter_ip_cliente
from nucleo.validators import formatar_celular, formatar_cep, formatar_cpf

MSG_REENVIO_GENERICA = (
    "Se o e-mail informado estiver cadastrado e pendente de confirmação, "
    "enviaremos um novo link em instantes."
)
SESSAO_CHAVE_DESTINO_POS_2FA = "destino_pos_2fa"


def _construtor_url_confirmacao(request):
    def _construir(token: str) -> str:
        caminho = reverse("contas:confirmar_email", kwargs={"token": token})
        return request.build_absolute_uri(caminho)

    return _construir


def _resolver_destino_seguro(request, candidato: str | None) -> str:
    """Valida redirecionamento interno contra open redirect (OWASP A01 / CA-02-12)."""
    if candidato and url_has_allowed_host_and_scheme(
        url=candidato,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidato
    return reverse("nucleo:home")


def _eh_destino_cadastro_ponto_coleta(request, candidato: str | None) -> bool:
    """Confirma se `next` corresponde exatamente à rota de cadastro de Ponto de Coleta."""
    if not candidato:
        return False
    destino_ponto_coleta = reverse("pontos_coleta:cadastrar")
    return candidato == destino_ponto_coleta and url_has_allowed_host_and_scheme(
        url=candidato,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )


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
        usuario = perfil.usuario
        return {
            "form": form,
            "cpf_formatado": formatar_cpf(usuario.cpf or ""),
            "email_pendente": perfil.email_pendente,
            "criado_em": usuario.criado_em,
            "exige_2fa": AutenticacaoService.possui_funcao_administrativa(usuario),
            "totp_ativo": AutenticacaoService.possui_totp_ativo(usuario),
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


class LoginView(View):
    """Tela e processamento de login por E-mail ou CPF (Spec 02 / RF002)."""

    template_name = "contas/login.html"

    def _contexto(
        self,
        request,
        form: LoginForm,
        *,
        next_url: str = "",
        mostrar_reenvio_confirmacao: bool = False,
    ) -> dict:
        return {
            "form": form,
            "next_url": next_url,
            "mostrar_reenvio_confirmacao": mostrar_reenvio_confirmacao,
            "aviso_cadastro_ponto_coleta": _eh_destino_cadastro_ponto_coleta(request, next_url),
        }

    def get(self, request):
        if request.user.is_authenticated:
            if (
                AutenticacaoService.possui_funcao_administrativa(request.user)
                and request.session.get(SESSAO_CHAVE_2FA_VERIFICADO) is not True
            ):
                destino_2fa = (
                    "contas:totp_verificar"
                    if AutenticacaoService.possui_totp_ativo(request.user)
                    else "contas:totp_configurar"
                )
                return redirect(destino_2fa)
            return redirect(_resolver_destino_seguro(request, request.GET.get("next")))

        return render(
            request,
            self.template_name,
            self._contexto(request, LoginForm(), next_url=request.GET.get("next", "")),
        )

    def post(self, request):
        form = LoginForm(request.POST)
        next_url = request.POST.get("next") or request.GET.get("next") or ""
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._contexto(request, form, next_url=next_url),
            )

        try:
            resultado = AutenticacaoService.autenticar(
                form.cleaned_data["identificador"],
                form.cleaned_data["senha"],
                obter_ip_cliente(request),
            )
        except ContaBloqueadaTemporariamente as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request,
                self.template_name,
                self._contexto(request, form, next_url=next_url),
                status=429,
            )
        except EmailNaoConfirmado as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request,
                self.template_name,
                self._contexto(
                    request,
                    form,
                    next_url=next_url,
                    mostrar_reenvio_confirmacao=True,
                ),
            )
        except (CredenciaisInvalidas, ContaIndisponivel) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request,
                self.template_name,
                self._contexto(request, form, next_url=next_url),
            )

        login(request, resultado.usuario, backend="contas.backends.EmailOuCpfBackend")
        if not request.session.session_key:
            request.session.save()
        SessaoService.registrar_sessao(resultado.usuario.pk, request.session.session_key)

        destino_seguro = _resolver_destino_seguro(request, next_url)
        if resultado.exige_2fa:
            request.session[SESSAO_CHAVE_2FA_VERIFICADO] = False
            request.session[SESSAO_CHAVE_DESTINO_POS_2FA] = destino_seguro
            if resultado.totp_ativo:
                return redirect("contas:totp_verificar")
            return redirect("contas:totp_configurar")

        return redirect(destino_seguro)


class LogoutView(View):
    """Encerramento de sessão exclusivamente via POST com CSRF (OWASP A07 / CA-02-06)."""

    def post(self, request):
        SessaoService.remover_sessao(request.session.session_key)
        logout(request)
        messages.info(request, "Você saiu da sua conta com segurança.")
        return redirect("contas:login")


class RecuperarSenhaEmBreveView(View):
    """Aviso temporário no MVP para o link 'Esqueci minha senha' (substituído no RF003)."""

    template_name = "contas/recuperar_senha_em_breve.html"

    def get(self, request):
        return render(request, self.template_name)


class TotpConfigurarView(ContaAdminPendente2faMixin, View):
    """Pareamento inicial obrigatório de 2FA TOTP para contas administrativas (ADR 0009)."""

    template_name = "contas/totp_configurar.html"

    def get(self, request):
        try:
            pareamento = TotpService.iniciar_pareamento(request.user)
        except TotpJaAtivado:
            return redirect("contas:totp_verificar")

        return render(
            request,
            self.template_name,
            {
                "form": TotpCodigoForm(),
                "pareamento": pareamento,
                "codigos_recuperacao": None,
                "destino_continuar": _resolver_destino_seguro(
                    request,
                    request.GET.get("next") or request.session.get(SESSAO_CHAVE_DESTINO_POS_2FA),
                ),
            },
        )

    def post(self, request):
        form = TotpCodigoForm(request.POST)
        try:
            pareamento = TotpService.iniciar_pareamento(request.user)
        except TotpJaAtivado:
            return redirect("contas:totp_verificar")

        destino_continuar = _resolver_destino_seguro(
            request,
            request.session.get(SESSAO_CHAVE_DESTINO_POS_2FA),
        )
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "pareamento": pareamento,
                    "codigos_recuperacao": None,
                    "destino_continuar": destino_continuar,
                },
            )

        try:
            codigos_recuperacao = TotpService.confirmar_pareamento(
                request.user,
                form.cleaned_data["codigo"],
                obter_ip_cliente(request),
            )
        except TotpBloqueadoTemporariamente as erro:
            SessaoService.remover_sessao(request.session.session_key)
            logout(request)
            messages.error(request, str(erro))
            return redirect("contas:login")
        except (CodigoTotpInvalido, TotpNaoConfigurado) as erro:
            form.add_error("codigo", ValidationError(str(erro), code="invalid"))
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "pareamento": pareamento,
                    "codigos_recuperacao": None,
                    "destino_continuar": destino_continuar,
                },
            )

        request.session[SESSAO_CHAVE_2FA_VERIFICADO] = True
        request.session.pop(SESSAO_CHAVE_DESTINO_POS_2FA, None)
        return render(
            request,
            self.template_name,
            {
                "form": None,
                "pareamento": None,
                "codigos_recuperacao": codigos_recuperacao,
                "destino_continuar": destino_continuar,
            },
        )


class TotpVerificarView(ContaAdminPendente2faMixin, View):
    """Verificação de código TOTP ou código de recuperação no login administrativo."""

    template_name = "contas/totp_verificar.html"

    def _contexto(
        self,
        *,
        form_totp: TotpCodigoForm,
        form_recuperacao: TotpRecuperacaoForm,
        modo_recuperacao: bool = False,
        next_url: str = "",
    ) -> dict:
        return {
            "form_totp": form_totp,
            "form_recuperacao": form_recuperacao,
            "modo_recuperacao": modo_recuperacao,
            "next_url": next_url,
        }

    def get(self, request):
        if not AutenticacaoService.possui_totp_ativo(request.user):
            return redirect("contas:totp_configurar")

        next_url = request.GET.get("next") or request.session.get(SESSAO_CHAVE_DESTINO_POS_2FA, "")
        if request.session.get(SESSAO_CHAVE_2FA_VERIFICADO) is True:
            return redirect(_resolver_destino_seguro(request, next_url))

        modo_recuperacao = request.GET.get("modo") == "recuperacao"
        return render(
            request,
            self.template_name,
            self._contexto(
                form_totp=TotpCodigoForm(),
                form_recuperacao=TotpRecuperacaoForm(),
                modo_recuperacao=modo_recuperacao,
                next_url=next_url,
            ),
        )

    def post(self, request):
        if not AutenticacaoService.possui_totp_ativo(request.user):
            return redirect("contas:totp_configurar")

        next_url = request.POST.get("next") or request.session.get(SESSAO_CHAVE_DESTINO_POS_2FA, "")
        usar_recuperacao = request.POST.get("modo") == "recuperacao"

        if usar_recuperacao:
            form_recuperacao = TotpRecuperacaoForm(request.POST)
            form_totp = TotpCodigoForm()
            if not form_recuperacao.is_valid():
                return render(
                    request,
                    self.template_name,
                    self._contexto(
                        form_totp=form_totp,
                        form_recuperacao=form_recuperacao,
                        modo_recuperacao=True,
                        next_url=next_url,
                    ),
                )
            try:
                restantes = TotpService.consumir_codigo_recuperacao(
                    request.user,
                    form_recuperacao.cleaned_data["codigo_recuperacao"],
                    obter_ip_cliente(request),
                )
            except TotpBloqueadoTemporariamente as erro:
                SessaoService.remover_sessao(request.session.session_key)
                logout(request)
                messages.error(request, str(erro))
                return redirect("contas:login")
            except CodigoRecuperacaoInvalido as erro:
                form_recuperacao.add_error(
                    "codigo_recuperacao", ValidationError(str(erro), code="invalid")
                )
                return render(
                    request,
                    self.template_name,
                    self._contexto(
                        form_totp=form_totp,
                        form_recuperacao=form_recuperacao,
                        modo_recuperacao=True,
                        next_url=next_url,
                    ),
                )

            request.session[SESSAO_CHAVE_2FA_VERIFICADO] = True
            request.session.pop(SESSAO_CHAVE_DESTINO_POS_2FA, None)
            messages.warning(
                request,
                f"Código de recuperação utilizado com sucesso. Restam {restantes} código(s) "
                "de recuperação disponíveis.",
            )
            return redirect(_resolver_destino_seguro(request, next_url))

        form_totp = TotpCodigoForm(request.POST)
        form_recuperacao = TotpRecuperacaoForm()
        if not form_totp.is_valid():
            return render(
                request,
                self.template_name,
                self._contexto(
                    form_totp=form_totp,
                    form_recuperacao=form_recuperacao,
                    modo_recuperacao=False,
                    next_url=next_url,
                ),
            )
        try:
            TotpService.verificar_codigo(
                request.user,
                form_totp.cleaned_data["codigo"],
                obter_ip_cliente(request),
            )
        except TotpBloqueadoTemporariamente as erro:
            SessaoService.remover_sessao(request.session.session_key)
            logout(request)
            messages.error(request, str(erro))
            return redirect("contas:login")
        except CodigoTotpInvalido as erro:
            form_totp.add_error("codigo", ValidationError(str(erro), code="invalid"))
            return render(
                request,
                self.template_name,
                self._contexto(
                    form_totp=form_totp,
                    form_recuperacao=form_recuperacao,
                    modo_recuperacao=False,
                    next_url=next_url,
                ),
            )

        request.session[SESSAO_CHAVE_2FA_VERIFICADO] = True
        request.session.pop(SESSAO_CHAVE_DESTINO_POS_2FA, None)
        return redirect(_resolver_destino_seguro(request, next_url))


class TotpRegenerarCodigosView(ContaAdminPendente2faMixin, View):
    """Regeneração dos 8 códigos de recuperação mediante step-up de 2FA (RN-02-08)."""

    template_name = "contas/totp_regenerar_codigos.html"

    def dispatch(self, request, *args, **kwargs):
        resposta = super().dispatch(request, *args, **kwargs)
        if getattr(resposta, "status_code", 200) in {302, 403}:
            return resposta
        return resposta

    def _garantir_2fa_ativo_e_verificado(self, request):
        if not AutenticacaoService.possui_totp_ativo(request.user):
            return redirect("contas:totp_configurar")
        if request.session.get(SESSAO_CHAVE_2FA_VERIFICADO) is not True:
            return redirect("contas:totp_verificar")
        return None

    def get(self, request):
        redirecionamento = self._garantir_2fa_ativo_e_verificado(request)
        if redirecionamento is not None:
            return redirecionamento
        return render(
            request,
            self.template_name,
            {"form": TotpCodigoForm(), "novos_codigos": None},
        )

    def post(self, request):
        redirecionamento = self._garantir_2fa_ativo_e_verificado(request)
        if redirecionamento is not None:
            return redirecionamento

        form = TotpCodigoForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "novos_codigos": None})

        try:
            novos_codigos = TotpService.regenerar_codigos_recuperacao(
                request.user,
                form.cleaned_data["codigo"],
                obter_ip_cliente(request),
            )
        except TotpBloqueadoTemporariamente as erro:
            SessaoService.remover_sessao(request.session.session_key)
            logout(request)
            messages.error(request, str(erro))
            return redirect("contas:login")
        except (CodigoTotpInvalido, TotpNaoConfigurado) as erro:
            form.add_error("codigo", ValidationError(str(erro), code="invalid"))
            return render(request, self.template_name, {"form": form, "novos_codigos": None})

        return render(
            request,
            self.template_name,
            {"form": None, "novos_codigos": novos_codigos},
        )


def _contexto_detalhe_admin(
    detalhe,
    *,
    form_status: AdminAlterarStatusForm | None = None,
    form_funcoes: AdminAlterarFuncoesForm | None = None,
    form_reset_2fa: AdminResetar2faForm | None = None,
) -> dict:
    return {
        "detalhe": detalhe,
        "resumo": detalhe.resumo,
        "rotulos_funcoes": ROTULOS_FUNCOES_ADMIN,
        "form_status": form_status
        if form_status is not None
        else AdminAlterarStatusForm(initial={"novo_status": detalhe.resumo.status}),
        "form_funcoes": form_funcoes
        if form_funcoes is not None
        else AdminAlterarFuncoesForm(initial={"funcoes": list(detalhe.resumo.funcoes_admin)}),
        "form_reset_2fa": form_reset_2fa if form_reset_2fa is not None else AdminResetar2faForm(),
    }


class AdminUsuarioListaView(FuncaoAdminObrigatoriaMixin, View):
    """Consulta paginada de usuários para gestao_usuarios ou gestao_administradores (+ 2FA)."""

    funcoes_admin_permitidas = ("gestao_usuarios", "gestao_administradores")
    template_name = "contas/admin_usuario_lista.html"

    def get(self, request):
        form = AdminUsuarioConsultaForm(request.GET or None)
        if request.GET and form.is_valid():
            filtros = form.para_filtros()
        else:
            filtros = FiltrosConsultaUsuarios()

        try:
            pagina_num = max(1, int(request.GET.get("page", "1")))
        except ValueError:
            pagina_num = 1

        try:
            resultado = GestaoUsuariosService.consultar(request.user, filtros, pagina=pagina_num)
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except RegraNegocioViolada as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            resultado = GestaoUsuariosService.consultar(
                request.user, FiltrosConsultaUsuarios(), pagina=1
            )

        tem_filtros = any(
            [
                filtros.termo,
                filtros.email,
                filtros.perfil,
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
                "total_encontrados": resultado.total_encontrados,
                "tem_filtros": tem_filtros,
                "rotulos_funcoes": ROTULOS_FUNCOES_ADMIN,
            },
        )


class AdminUsuarioDetalheView(FuncaoAdminObrigatoriaMixin, View):
    """Detalhe minimizado do usuário para gestao_usuarios ou gestao_administradores (+ 2FA)."""

    funcoes_admin_permitidas = ("gestao_usuarios", "gestao_administradores")
    template_name = "contas/admin_usuario_detalhe.html"

    def get(self, request, usuario_id: int):
        try:
            detalhe = GestaoUsuariosService.obter_resumo_gestao(request.user, usuario_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))

        return render(request, self.template_name, _contexto_detalhe_admin(detalhe))


class AdminUsuarioAlterarStatusView(FuncaoAdminObrigatoriaMixin, View):
    """Altera status de conta (POST exclusivo, exige função gestao_usuarios + 2FA)."""

    funcao_admin = "gestao_usuarios"
    template_name = "contas/admin_usuario_detalhe.html"

    def post(self, request, usuario_id: int):
        try:
            detalhe = GestaoUsuariosService.obter_resumo_gestao(request.user, usuario_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        form = AdminAlterarStatusForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                _contexto_detalhe_admin(detalhe, form_status=form),
            )

        try:
            GestaoUsuariosService.alterar_status(
                request.user,
                usuario_id,
                form.cleaned_data["novo_status"],
                form.cleaned_data["motivo"],
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except (
            MotivoObrigatorio,
            UltimoAdministradorAtivo,
            ContaAnonimizadaImutavel,
            RegraNegocioViolada,
        ) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request,
                self.template_name,
                _contexto_detalhe_admin(detalhe, form_status=form),
            )

        messages.success(request, "Status do usuário alterado com sucesso")
        return redirect("contas:admin_usuario_detalhe", usuario_id=usuario_id)


class AdminUsuarioFuncoesView(FuncaoAdminObrigatoriaMixin, View):
    """Atribui/remove as 8 funções administrativas (POST, gestao_administradores + step-up)."""

    funcao_admin = "gestao_administradores"
    template_name = "contas/admin_usuario_detalhe.html"

    def post(self, request, usuario_id: int):
        try:
            detalhe = GestaoUsuariosService.obter_resumo_gestao(request.user, usuario_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        if request.user.pk == usuario_id:
            return HttpResponseForbidden(
                "Um Administrador não pode atribuir ou alterar as próprias funções administrativas."
            )

        form = AdminAlterarFuncoesForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                _contexto_detalhe_admin(detalhe, form_funcoes=form),
            )

        try:
            GestaoUsuariosService.atualizar_funcoes_administrativas(
                request.user,
                usuario_id,
                form.cleaned_data["funcoes"],
                form.cleaned_data["codigo_step_up"],
                form.cleaned_data["motivo"],
                obter_ip_cliente(request),
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except TotpBloqueadoTemporariamente as erro:
            SessaoService.remover_sessao(request.session.session_key)
            logout(request)
            messages.error(request, str(erro))
            return redirect("contas:login")
        except (
            AcumuloFuncoesProibido,
            UltimoAdministradorAtivo,
            CodigoTotpInvalido,
            MotivoObrigatorio,
            ContaAnonimizadaImutavel,
            RegraNegocioViolada,
        ) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request,
                self.template_name,
                _contexto_detalhe_admin(detalhe, form_funcoes=form),
            )

        messages.success(request, "Funções administrativas atualizadas com sucesso.")
        return redirect("contas:admin_usuario_detalhe", usuario_id=usuario_id)


class AdminUsuarioResetar2faView(FuncaoAdminObrigatoriaMixin, View):
    """Reset de 2FA de outro Administrador (POST exclusivo, gestao_administradores + step-up)."""

    funcao_admin = "gestao_administradores"
    template_name = "contas/admin_usuario_detalhe.html"

    def post(self, request, usuario_id: int):
        try:
            detalhe = GestaoUsuariosService.obter_resumo_gestao(request.user, usuario_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        if request.user.pk == usuario_id:
            return HttpResponseForbidden("Um Administrador não pode resetar o próprio 2FA.")

        form = AdminResetar2faForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                _contexto_detalhe_admin(detalhe, form_reset_2fa=form),
            )

        try:
            alvo = UsuarioService.obter_perfil(usuario_id).usuario
            TotpService.resetar_por_administrador(
                request.user,
                alvo,
                form.cleaned_data["codigo_step_up"],
                obter_ip_cliente(request),
                motivo=form.cleaned_data["motivo"],
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except (ResetTotpNaoPermitido, PermissaoNegada) as erro:
            return HttpResponseForbidden(str(erro))
        except TotpBloqueadoTemporariamente as erro:
            SessaoService.remover_sessao(request.session.session_key)
            logout(request)
            messages.error(request, str(erro))
            return redirect("contas:login")
        except (CodigoTotpInvalido, MotivoObrigatorio, RegraNegocioViolada) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request,
                self.template_name,
                _contexto_detalhe_admin(detalhe, form_reset_2fa=form),
            )

        messages.success(
            request,
            "Autenticação em dois fatores (2FA) do Administrador resetada com sucesso.",
        )
        return redirect("contas:admin_usuario_detalhe", usuario_id=usuario_id)

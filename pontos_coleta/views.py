"""Views baseadas em classe do app pontos_coleta (Specs 05, 06 e 07 — zero ORM)."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views import View

from contas.services import AutenticacaoService
from nucleo.exceptions import (
    ArquivoFormatoInvalido,
    ArquivoMalwareDetectado,
    ArquivoScannerIndisponivel,
    ArquivoTamanhoExcedido,
    PermissaoNegada,
    RecursoNaoEncontrado,
    RegraNegocioViolada,
)
from nucleo.mixins import (
    SESSAO_CHAVE_2FA_VERIFICADO,
    AutenticadoAtivoMixin,
    FuncaoAdminObrigatoriaMixin,
)
from nucleo.validators import formatar_celular, formatar_cep, formatar_cnpj, formatar_cpf
from pontos_coleta.exceptions import (
    CnpjJaCadastrado,
    DocumentosObrigatoriosPendentes,
    DocumentoVencido,
    HorarioInvalido,
    MotivoAnaliseObrigatorio,
    UltimoResponsavelAtivo,
)
from pontos_coleta.forms import (
    AdminAlterarCnpjForm,
    AdminAnalisePontoForm,
    AdminDocumentoFiltroForm,
    AdminPontoColetaFiltroForm,
    AdminRevisaoPontoForm,
    AdminSituacaoPontoForm,
    ConvidarResponsavelForm,
    DocumentoPontoForm,
    HorarioFuncionamentoFormSet,
    PontoColetaCadastroForm,
    PontoColetaEditarForm,
    PontoColetaFiltroPublicoForm,
    agrupar_horarios_para_blocos,
)
from pontos_coleta.services import (
    AprovacaoPontoService,
    DocumentoPontoService,
    FiltrosDocumentosAdmin,
    FiltrosPontoColeta,
    PontoColetaService,
)

MSG_CONVITE_NEUTRA = (
    "Se houver uma conta ativa e confirmada para o identificador informado, o convite foi enviado."
)


def _dados_responsavel_autenticado(usuario) -> dict:
    return {
        "cpf": formatar_cpf(usuario.cpf or ""),
        "nome": usuario.nome_completo,
        "email": usuario.email or "",
        "celular": formatar_celular(usuario.celular or ""),
    }


def _pagina_int(request) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


class PontoColetaCadastrarView(AutenticadoAtivoMixin, View):
    """Passo 1 do cadastro de ponto de coleta (RF005 -> redireciona para RF006)."""

    template_name = "pontos_coleta/ponto_cadastrar.html"

    def get(self, request):
        tipos = PontoColetaService.listar_tipos_estabelecimento_ativos()
        return render(
            request,
            self.template_name,
            {
                "form": PontoColetaCadastroForm(tipos_estabelecimento=tipos),
                "formset_horarios": HorarioFuncionamentoFormSet(prefix="horarios"),
                "responsavel_atual": _dados_responsavel_autenticado(request.user),
            },
        )

    def post(self, request):
        tipos = PontoColetaService.listar_tipos_estabelecimento_ativos()
        form = PontoColetaCadastroForm(request.POST, tipos_estabelecimento=tipos)
        formset_horarios = HorarioFuncionamentoFormSet(request.POST, prefix="horarios")

        if not (form.is_valid() and formset_horarios.is_valid()):
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "formset_horarios": formset_horarios,
                    "responsavel_atual": _dados_responsavel_autenticado(request.user),
                },
            )

        convidado = (form.cleaned_data.get("convidar_responsavel") or "").strip()
        try:
            ponto = PontoColetaService.cadastrar(
                request.user,
                form.para_dados(),
                formset_horarios.para_itens(),
                responsaveis_adicionais=(convidado,) if convidado else (),
            )
        except CnpjJaCadastrado as erro:
            form.add_error("cnpj", ValidationError(str(erro), code="regra_negocio"))
        except (HorarioInvalido, RegraNegocioViolada) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
        else:
            messages.success(
                request,
                "Ponto de coleta cadastrado com sucesso. Envie os documentos obrigatórios "
                "para análise.",
            )
            return redirect("pontos_coleta:documentos", ponto_id=ponto.pk)

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "formset_horarios": formset_horarios,
                "responsavel_atual": _dados_responsavel_autenticado(request.user),
            },
        )


class MeusPontosColetaView(AutenticadoAtivoMixin, View):
    """Lista pontos sob responsabilidade ativa e convites pendentes do usuário."""

    template_name = "pontos_coleta/ponto_meus.html"

    def get(self, request):
        resumo = PontoColetaService.listar_meus_pontos(request.user)
        return render(
            request,
            self.template_name,
            {
                "pontos_itens": resumo.pontos,
                "convites_pendentes": resumo.convites_pendentes,
            },
        )


class PontoColetaEditarView(AutenticadoAtivoMixin, View):
    """Edição dos dados do ponto pelo responsável ativo (CNPJ somente leitura — RN-05-08)."""

    template_name = "pontos_coleta/ponto_editar.html"

    def _iniciais_ponto(self, ponto) -> dict:
        return {
            "razao_social": ponto.razao_social,
            "nome_fantasia": ponto.nome_fantasia,
            "tipo_estabelecimento": str(ponto.tipo_estabelecimento_id),
            "email": ponto.email,
            "telefone": formatar_celular(ponto.telefone),
            "cep": formatar_cep(ponto.cep),
            "logradouro": ponto.logradouro,
            "numero": ponto.numero,
            "bairro": ponto.bairro,
            "municipio": ponto.municipio,
            "estado": ponto.estado,
            "complemento": ponto.complemento,
            "possui_refrigeracao": "sim" if ponto.possui_refrigeracao else "nao",
            "observacoes": ponto.observacoes,
        }

    def get(self, request, ponto_id: int):
        try:
            ponto = PontoColetaService.obter_para_responsavel(ponto_id, request.user)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        tipos = PontoColetaService.listar_tipos_estabelecimento_ativos()
        blocos = agrupar_horarios_para_blocos(ponto.horarios.all())
        formset_cls = HorarioFuncionamentoFormSet
        formset = formset_cls(initial=blocos, prefix="horarios")
        return render(
            request,
            self.template_name,
            {
                "ponto": ponto,
                "cnpj_formatado": formatar_cnpj(ponto.cnpj),
                "form": PontoColetaEditarForm(
                    initial=self._iniciais_ponto(ponto),
                    tipos_estabelecimento=tipos,
                ),
                "formset_horarios": formset,
            },
        )

    def post(self, request, ponto_id: int):
        try:
            ponto = PontoColetaService.obter_para_responsavel(ponto_id, request.user)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        tipos = PontoColetaService.listar_tipos_estabelecimento_ativos()
        form = PontoColetaEditarForm(request.POST, tipos_estabelecimento=tipos)
        formset = HorarioFuncionamentoFormSet(request.POST, prefix="horarios")
        if not (form.is_valid() and formset.is_valid()):
            return render(
                request,
                self.template_name,
                {
                    "ponto": ponto,
                    "cnpj_formatado": formatar_cnpj(ponto.cnpj),
                    "form": form,
                    "formset_horarios": formset,
                },
            )

        try:
            resultado = PontoColetaService.atualizar(
                ponto.pk,
                request.user,
                form.para_dados(),
                formset.para_itens(),
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except (HorarioInvalido, RegraNegocioViolada) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request,
                self.template_name,
                {
                    "ponto": ponto,
                    "cnpj_formatado": formatar_cnpj(ponto.cnpj),
                    "form": form,
                    "formset_horarios": formset,
                },
            )

        if resultado.remetido_reaprovacao:
            messages.warning(
                request,
                "Endereço atualizado. O ponto retornou para Pendente de aprovação até nova "
                "conferência do Administrador.",
            )
        else:
            messages.success(request, "Dados do ponto de coleta atualizados com sucesso.")
        return redirect("pontos_coleta:editar", ponto_id=ponto.pk)


class PontoColetaInativarView(AutenticadoAtivoMixin, View):
    """Inativação voluntária do ponto pelo responsável ativo (POST — acréscimo Spec 05)."""

    def post(self, request, ponto_id: int):
        if request.POST.get("confirmar_inativacao") != "sim":
            messages.error(request, "Confirme a inativação do ponto de coleta antes de prosseguir.")
            return redirect("pontos_coleta:meus_pontos")

        try:
            PontoColetaService.inativar_pelo_responsavel(ponto_id, request.user)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except RegraNegocioViolada as erro:
            messages.error(request, str(erro))
            return redirect("pontos_coleta:meus_pontos")

        messages.info(
            request,
            "Ponto de coleta inativado. Para reativá-lo futuramente, solicite reativação ao "
            "Administrador.",
        )
        return redirect("pontos_coleta:meus_pontos")


class PontoColetaResponsaveisView(AutenticadoAtivoMixin, View):
    """Gestão de responsáveis vinculados e convites do ponto (RF005 / FA-04)."""

    template_name = "pontos_coleta/ponto_responsaveis.html"

    def get(self, request, ponto_id: int):
        try:
            ponto, responsaveis = PontoColetaService.listar_responsaveis_para_gestao(
                ponto_id, request.user
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        return render(
            request,
            self.template_name,
            {
                "ponto": ponto,
                "responsaveis": responsaveis,
                "form_convite": ConvidarResponsavelForm(),
            },
        )

    def post(self, request, ponto_id: int):
        acao = request.POST.get("acao", "convidar")
        if acao == "desvincular":
            try:
                responsavel_id = int(request.POST.get("responsavel_id", "0"))
            except ValueError:
                raise Http404("Responsável inválido.") from None
            try:
                PontoColetaService.desvincular_responsavel(ponto_id, request.user, responsavel_id)
            except RecursoNaoEncontrado as erro:
                raise Http404(str(erro)) from erro
            except UltimoResponsavelAtivo as erro:
                messages.error(request, str(erro))
                return redirect("pontos_coleta:responsaveis", ponto_id=ponto_id)

            messages.success(request, "Vínculo de responsável encerrado com sucesso.")
            return redirect("pontos_coleta:responsaveis", ponto_id=ponto_id)

        try:
            ponto, responsaveis = PontoColetaService.listar_responsaveis_para_gestao(
                ponto_id, request.user
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        form = ConvidarResponsavelForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"ponto": ponto, "responsaveis": responsaveis, "form_convite": form},
            )

        try:
            PontoColetaService.convidar_responsavel(
                ponto.pk, request.user, form.cleaned_data["identificador"]
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except RegraNegocioViolada as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request,
                self.template_name,
                {"ponto": ponto, "responsaveis": responsaveis, "form_convite": form},
            )

        # Resposta neutra anti-enumeração (RS005)
        messages.info(request, MSG_CONVITE_NEUTRA)
        return redirect("pontos_coleta:responsaveis", ponto_id=ponto.pk)


class PontoColetaConviteResponderView(AutenticadoAtivoMixin, View):
    """Aceita ou recusa convite de responsabilidade (POST exclusivo com CSRF)."""

    def post(self, request, convite_id: int):
        decisao = request.POST.get("decisao", "")
        if decisao not in {"aceitar", "recusar"}:
            messages.error(request, "Ação de convite inválida.")
            return redirect("pontos_coleta:meus_pontos")

        try:
            PontoColetaService.responder_convite(
                convite_id,
                request.user,
                aceitar=(decisao == "aceitar"),
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        if decisao == "aceitar":
            messages.success(request, "Convite aceito. Você agora é responsável ativo pelo ponto.")
        else:
            messages.info(request, "Convite recusado.")
        return redirect("pontos_coleta:meus_pontos")


class PontoColetaListaPublicaView(View):
    """Pesquisa pública de pontos de coleta exclusivamente com status ativo (RN-05-05)."""

    template_name = "pontos_coleta/ponto_lista_publica.html"

    def get(self, request):
        tipos = PontoColetaService.listar_tipos_estabelecimento_ativos()
        form = PontoColetaFiltroPublicoForm(request.GET or None, tipos_estabelecimento=tipos)
        filtros = form.para_filtros() if (request.GET and form.is_valid()) else FiltrosPontoColeta()
        resultado = PontoColetaService.pesquisar(
            request.user if request.user.is_authenticated else None,
            filtros,
            apenas_ativos=True,
            pagina=_pagina_int(request),
        )
        tem_filtros = any([filtros.termo, filtros.tipo_estabelecimento_id, filtros.municipio])
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "pagina": resultado.pagina,
                "total_encontrados": resultado.total_encontrados,
                "tem_filtros": tem_filtros,
            },
        )


class PontoDocumentoListaEnviarView(AutenticadoAtivoMixin, View):
    """Passo 2 contínuo (RF006): listar versões e enviar/substituir documentos do ponto."""

    template_name = "pontos_coleta/ponto_documentos.html"

    def get(self, request, ponto_id: int):
        try:
            ponto, situacao, documentos = DocumentoPontoService.listar_do_ponto(
                ponto_id, request.user
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        tipos = DocumentoPontoService.listar_tipos_documento_ativos()
        return render(
            request,
            self.template_name,
            {
                "ponto": ponto,
                "situacao": situacao,
                "documentos": documentos,
                "form": DocumentoPontoForm(tipos_documento=tipos),
            },
        )

    def post(self, request, ponto_id: int):
        try:
            ponto, situacao, documentos = DocumentoPontoService.listar_do_ponto(
                ponto_id, request.user
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        tipos = DocumentoPontoService.listar_tipos_documento_ativos()
        form = DocumentoPontoForm(request.POST, request.FILES, tipos_documento=tipos)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"ponto": ponto, "situacao": situacao, "documentos": documentos, "form": form},
            )

        arquivo = form.cleaned_data["arquivo"]
        conteudo = arquivo.read()
        try:
            DocumentoPontoService.enviar(
                ponto.pk,
                request.user,
                tipo_documento_id=int(form.cleaned_data["tipo_documento"]),
                numero_documento=form.cleaned_data["numero_documento"],
                data_validade=form.cleaned_data["data_validade"],
                conteudo=conteudo,
                nome_original=arquivo.name,
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except (
            DocumentoVencido,
            ArquivoTamanhoExcedido,
            ArquivoFormatoInvalido,
            ArquivoMalwareDetectado,
            ArquivoScannerIndisponivel,
            RegraNegocioViolada,
        ) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request,
                self.template_name,
                {"ponto": ponto, "situacao": situacao, "documentos": documentos, "form": form},
            )

        messages.success(request, "Documento enviado com sucesso. O cadastro está em análise")
        return redirect("pontos_coleta:documentos", ponto_id=ponto.pk)


class PontoDocumentoAcessarView(AutenticadoAtivoMixin, View):
    """Gera URL temporária de 60 s após checar vínculo ativo ou aprovacao_pontos_coleta (+ 2FA)."""

    def get(self, request, doc_id: int):
        # Se o usuário acessa como Admin de aprovação, exige 2FA concluído na sessão (ADR 0009).
        if (
            AutenticacaoService.possui_funcao(request.user, "aprovacao_pontos_coleta")
            and request.session.get(SESSAO_CHAVE_2FA_VERIFICADO) is not True
        ):
            destino_2fa = (
                "contas:totp_verificar"
                if AutenticacaoService.possui_totp_ativo(request.user)
                else "contas:totp_configurar"
            )
            return redirect(destino_2fa)

        try:
            url_temporaria = DocumentoPontoService.gerar_acesso_temporario(doc_id, request.user)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))

        return redirect(url_temporaria)


def _contexto_detalhe_admin(
    detalhe,
    *,
    form_analise: AdminAnalisePontoForm | None = None,
    form_situacao: AdminSituacaoPontoForm | None = None,
    form_revisao: AdminRevisaoPontoForm | None = None,
    form_cnpj: AdminAlterarCnpjForm | None = None,
) -> dict:
    return {
        "detalhe": detalhe,
        "ponto": detalhe.ponto,
        "form_analise": form_analise if form_analise is not None else AdminAnalisePontoForm(),
        "form_situacao": form_situacao if form_situacao is not None else AdminSituacaoPontoForm(),
        "form_revisao": form_revisao if form_revisao is not None else AdminRevisaoPontoForm(),
        "form_cnpj": form_cnpj if form_cnpj is not None else AdminAlterarCnpjForm(),
    }


class AdminPontoColetaListaView(FuncaoAdminObrigatoriaMixin, View):
    """Fila e pesquisa administrativa de pontos de coleta (aprovacao_pontos_coleta + 2FA)."""

    funcao_admin = "aprovacao_pontos_coleta"
    template_name = "pontos_coleta/admin_ponto_lista.html"

    def get(self, request):
        tipos = PontoColetaService.listar_tipos_estabelecimento_ativos()
        form = AdminPontoColetaFiltroForm(request.GET or None, tipos_estabelecimento=tipos)
        filtros = form.para_filtros() if (request.GET and form.is_valid()) else FiltrosPontoColeta()
        resultado = PontoColetaService.pesquisar(
            request.user,
            filtros,
            apenas_ativos=False,
            pagina=_pagina_int(request),
        )
        tem_filtros = any(
            [
                filtros.termo,
                filtros.cnpj,
                filtros.tipo_estabelecimento_id,
                filtros.municipio,
                filtros.status,
                filtros.revisao_vencida,
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
            },
        )


class AdminPontoColetaDetalheView(FuncaoAdminObrigatoriaMixin, View):
    """Detalhe administrativo consolidado para análise, situação, revisão e CNPJ (RF007)."""

    funcao_admin = "aprovacao_pontos_coleta"
    template_name = "pontos_coleta/admin_ponto_detalhe.html"

    def get(self, request, ponto_id: int):
        try:
            detalhe = AprovacaoPontoService.obter_detalhe_admin(request.user, ponto_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))

        return render(request, self.template_name, _contexto_detalhe_admin(detalhe))


class AdminPontoColetaAlterarCnpjView(FuncaoAdminObrigatoriaMixin, View):
    """Alteração de CNPJ exclusiva de aprovacao_pontos_coleta + 2FA (POST — RN-05-08)."""

    funcao_admin = "aprovacao_pontos_coleta"
    template_name = "pontos_coleta/admin_ponto_detalhe.html"

    def post(self, request, ponto_id: int):
        try:
            detalhe = AprovacaoPontoService.obter_detalhe_admin(request.user, ponto_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        form = AdminAlterarCnpjForm(request.POST)
        if not form.is_valid():
            return render(
                request, self.template_name, _contexto_detalhe_admin(detalhe, form_cnpj=form)
            )

        try:
            PontoColetaService.alterar_cnpj(
                request.user,
                ponto_id,
                form.cleaned_data["novo_cnpj"],
                form.cleaned_data["motivo"],
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except (CnpjJaCadastrado, RegraNegocioViolada) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request, self.template_name, _contexto_detalhe_admin(detalhe, form_cnpj=form)
            )

        messages.success(request, "CNPJ do ponto de coleta atualizado com sucesso.")
        return redirect("pontos_coleta:admin_detalhe", ponto_id=ponto_id)


class AdminPontoColetaAnalisarView(FuncaoAdminObrigatoriaMixin, View):
    """Registra aprovação, reprovação ou pendência de documentação (POST — RF007)."""

    funcao_admin = "aprovacao_pontos_coleta"
    template_name = "pontos_coleta/admin_ponto_detalhe.html"

    def post(self, request, ponto_id: int):
        try:
            detalhe = AprovacaoPontoService.obter_detalhe_admin(request.user, ponto_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        form = AdminAnalisePontoForm(request.POST)
        if not form.is_valid():
            return render(
                request, self.template_name, _contexto_detalhe_admin(detalhe, form_analise=form)
            )

        try:
            AprovacaoPontoService.analisar_cadastro(
                request.user,
                ponto_id,
                form.cleaned_data["resultado"],
                form.cleaned_data["motivo"],
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except (
            MotivoAnaliseObrigatorio,
            DocumentosObrigatoriosPendentes,
            RegraNegocioViolada,
        ) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request, self.template_name, _contexto_detalhe_admin(detalhe, form_analise=form)
            )

        messages.success(request, "Situação do ponto de coleta atualizada com sucesso")
        return redirect("pontos_coleta:admin_detalhe", ponto_id=ponto_id)


class AdminPontoColetaSituacaoView(FuncaoAdminObrigatoriaMixin, View):
    """Suspende, inativa ou reativa ponto de coleta (POST — RF007)."""

    funcao_admin = "aprovacao_pontos_coleta"
    template_name = "pontos_coleta/admin_ponto_detalhe.html"

    def post(self, request, ponto_id: int):
        try:
            detalhe = AprovacaoPontoService.obter_detalhe_admin(request.user, ponto_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        form = AdminSituacaoPontoForm(request.POST)
        if not form.is_valid():
            return render(
                request, self.template_name, _contexto_detalhe_admin(detalhe, form_situacao=form)
            )

        try:
            AprovacaoPontoService.alterar_situacao(
                request.user,
                ponto_id,
                form.cleaned_data["novo_status"],
                form.cleaned_data["motivo"],
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except (
            MotivoAnaliseObrigatorio,
            DocumentosObrigatoriosPendentes,
            RegraNegocioViolada,
        ) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request, self.template_name, _contexto_detalhe_admin(detalhe, form_situacao=form)
            )

        messages.success(request, "Situação do ponto de coleta atualizada com sucesso")
        return redirect("pontos_coleta:admin_detalhe", ponto_id=ponto_id)


class AdminPontoColetaRevisarView(FuncaoAdminObrigatoriaMixin, View):
    """Registra revisão periódica de ponto ativo (POST — RF007 / RN-07-04)."""

    funcao_admin = "aprovacao_pontos_coleta"
    template_name = "pontos_coleta/admin_ponto_detalhe.html"

    def post(self, request, ponto_id: int):
        try:
            detalhe = AprovacaoPontoService.obter_detalhe_admin(request.user, ponto_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

        form = AdminRevisaoPontoForm(request.POST)
        if not form.is_valid():
            return render(
                request, self.template_name, _contexto_detalhe_admin(detalhe, form_revisao=form)
            )

        try:
            AprovacaoPontoService.registrar_revisao_periodica(
                request.user,
                ponto_id,
                form.cleaned_data.get("motivo", ""),
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except (DocumentosObrigatoriosPendentes, RegraNegocioViolada) as erro:
            form.add_error(None, ValidationError(str(erro), code="regra_negocio"))
            return render(
                request, self.template_name, _contexto_detalhe_admin(detalhe, form_revisao=form)
            )

        messages.success(request, "Situação do ponto de coleta atualizada com sucesso")
        return redirect("pontos_coleta:admin_detalhe", ponto_id=ponto_id)


class AdminDocumentoListaView(FuncaoAdminObrigatoriaMixin, View):
    """Pesquisa administrativa de documentos de pontos de coleta (RF006)."""

    funcao_admin = "aprovacao_pontos_coleta"
    template_name = "pontos_coleta/admin_documento_lista.html"

    def get(self, request):
        tipos = DocumentoPontoService.listar_tipos_documento_ativos()
        form = AdminDocumentoFiltroForm(request.GET or None, tipos_documento=tipos)
        filtros = (
            form.para_filtros() if (request.GET and form.is_valid()) else FiltrosDocumentosAdmin()
        )
        resultado = DocumentoPontoService.pesquisar_admin(
            request.user,
            filtros,
            pagina=_pagina_int(request),
        )
        tem_filtros = any(
            [
                filtros.ponto_coleta_id,
                filtros.tipo_documento_id,
                filtros.status,
                filtros.validade_ate is not None,
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
            },
        )

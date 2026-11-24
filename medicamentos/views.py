"""Views baseadas em classe (CBVs) do app medicamentos (Specs 08, 09, 10, 11, 14 e 23)."""

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from medicamentos.exceptions import ServicoIaIndisponivel
from medicamentos.forms import (
    AdminConferenciaFiltroForm,
    ConferenciaDoacaoForm,
    DefinirLocalizacaoBuscaForm,
    DoacaoCadastroForm,
    DoacaoEditarForm,
    MedicamentoBuscaForm,
    MinhasDoacoesFiltroForm,
    ParametroVencimentoForm,
)
from medicamentos.ia_embalagem import (
    AVISO_LGPD_IA_EMBALAGEM,
    LeituraEmbalagemIaService,
)
from medicamentos.models import CondicaoConservacao
from medicamentos.services import (
    ArquivoFotoEntrada,
    BuscaMedicamentoService,
    ConferenciaDoacaoService,
    DadosDoacao,
    DoacaoService,
    FiltrosBuscaMedicamento,
    FiltrosConferenciaAdmin,
    FiltrosMinhasDoacoes,
    LocalizacaoBuscaSessao,
    VencimentoService,
)
from nucleo.exceptions import (
    CepInvalido,
    CepNaoEncontrado,
    ErroDominio,
    LimiteTaxaExcedido,
    PermissaoNegada,
    RecursoNaoEncontrado,
    ServicoCepIndisponivel,
)
from nucleo.mixins import (
    SESSAO_CHAVE_2FA_VERIFICADO,
    AutenticadoAtivoMixin,
    FuncaoAdminObrigatoriaMixin,
    PerfilObrigatorioMixin,
)
from nucleo.services import GeolocalizacaoService

SESSAO_CHAVE_BUSCA_LOCALIZACAO = "busca_localizacao"
AVISO_RNF13 = "O ReMed não substitui avaliação médica ou farmacêutica."


def _ler_localizacao_sessao(request) -> LocalizacaoBuscaSessao | None:
    bruto = request.session.get(SESSAO_CHAVE_BUSCA_LOCALIZACAO)
    if not isinstance(bruto, dict):
        return None
    try:
        lat = Decimal(str(bruto["lat"]))
        lon = Decimal(str(bruto["lon"]))
    except KeyError, InvalidOperation, ValueError:
        return None
    return LocalizacaoBuscaSessao(
        origem=str(bruto.get("origem") or "cep"),
        rotulo_aproximado=str(bruto.get("rotulo_aproximado") or "Localização atual"),
        latitude_aprox=lat,
        longitude_aprox=lon,
        cep=str(bruto.get("cep") or ""),
    )


def _construir_dados_doacao(cleaned: dict) -> DadosDoacao:
    ponto_str = (cleaned.get("ponto_coleta") or "").strip()
    return DadosDoacao(
        nome_medicamento=cleaned["nome_medicamento"],
        principio_ativo=cleaned["principio_ativo"],
        concentracao_dosagem=cleaned["concentracao_dosagem"],
        forma_farmaceutica_id=int(cleaned["forma_farmaceutica"]),
        quantidade=int(cleaned["quantidade"]),
        fabricante=cleaned["fabricante"],
        lote=cleaned["lote"],
        data_validade=cleaned["data_validade"],
        embalagem_integra=cleaned["embalagem_integra"] == "sim",
        controle_especial=cleaned["controle_especial"] == "sim",
        condicao_conservacao=cleaned["condicao_conservacao"],
        sujeito_receita=cleaned["sujeito_receita"] == "sim",
        ponto_coleta_id=int(ponto_str) if ponto_str else None,
        observacoes=cleaned.get("observacoes") or "",
        faixa_temperatura_bula=cleaned.get("faixa_temperatura_bula") or "",
        declaracao_doador_conservacao=bool(cleaned.get("declaracao_doador_conservacao")),
        auxilio_ia=(cleaned.get("ia_sugestao_utilizada") or "").strip().lower() == "sim",
    )


def _redirect_busca_seguro(request) -> str:
    destino = (request.POST.get("next") or "").strip()
    if destino and url_has_allowed_host_and_scheme(
        destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return destino
    return reverse("medicamentos:busca")


class MedicamentoBuscaView(View):
    """Busca pública e autenticada de medicamentos disponíveis (Spec 14 / RF015)."""

    template_name = "medicamentos/busca.html"

    def get(self, request):
        formas = DoacaoService.listar_formas_farmaceuticas_ativas()
        form = MedicamentoBuscaForm(request.GET or None, formas_farmaceuticas=formas)
        filtros = FiltrosBuscaMedicamento()
        if form.is_valid():
            forma_str = (form.cleaned_data.get("forma_farmaceutica") or "").strip()
            filtros = FiltrosBuscaMedicamento(
                termo=form.cleaned_data.get("termo") or "",
                forma_farmaceutica_id=int(forma_str) if forma_str else None,
                concentracao=form.cleaned_data.get("concentracao") or "",
                distancia_max_km=form.cleaned_data.get("distancia_max_km"),
                validade_minima=form.cleaned_data.get("validade_minima"),
                condicao_conservacao=form.cleaned_data.get("condicao_conservacao") or "",
            )

        localizacao = _ler_localizacao_sessao(request)
        try:
            pagina_num = max(1, int(request.GET.get("page", "1")))
        except ValueError:
            pagina_num = 1

        resultado = BuscaMedicamentoService.buscar(
            filtros,
            localizacao=localizacao,
            pagina=pagina_num,
        )
        tem_filtros = any(
            [
                filtros.termo,
                filtros.forma_farmaceutica_id,
                filtros.concentracao,
                filtros.distancia_max_km,
                filtros.validade_minima,
                filtros.condicao_conservacao,
            ]
        )
        form_localizacao = DefinirLocalizacaoBuscaForm(
            initial={"cep": localizacao.cep} if localizacao and localizacao.cep else None
        )
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "form_localizacao": form_localizacao,
                "pagina": resultado.pagina,
                "total_encontrados": resultado.total_encontrados,
                "ordenado_por_proximidade": resultado.ordenado_por_proximidade,
                "localizacao_atual": localizacao,
                "tem_filtros": tem_filtros,
                "aviso_rnf13": AVISO_RNF13,
            },
        )


class DefinirLocalizacaoBuscaView(View):
    """Salva localização aproximada exclusivamente na sessão HTTP (RS010 / ADR 0017)."""

    def post(self, request):
        form = DefinirLocalizacaoBuscaForm(request.POST)
        destino = _redirect_busca_seguro(request)
        if not form.is_valid():
            for msg in form.non_field_errors():
                messages.error(request, msg)
            return redirect(destino)

        modo = form.cleaned_data["modo"]
        if modo == "gps":
            lat_aprox = GeolocalizacaoService.arredondar_coordenada(
                form.cleaned_data["lat_decimal"]
            )
            lon_aprox = GeolocalizacaoService.arredondar_coordenada(
                form.cleaned_data["lon_decimal"]
            )
            request.session[SESSAO_CHAVE_BUSCA_LOCALIZACAO] = {
                "origem": "gps",
                "rotulo_aproximado": "Localização aproximada do dispositivo",
                "lat": str(lat_aprox),
                "lon": str(lon_aprox),
            }
            messages.success(
                request,
                "Localização aproximada ativada para esta sessão. "
                "Resultados ordenados por proximidade.",
            )
            return redirect(destino)

        cep_limpo = form.cleaned_data["cep_limpo"]
        try:
            dados_loc = GeolocalizacaoService.obter_coordenadas_por_cep(cep_limpo)
        except CepInvalido, CepNaoEncontrado, ServicoCepIndisponivel:
            messages.warning(
                request,
                "Não foi possível localizar o CEP informado no momento. "
                "Você ainda pode buscar usando os outros filtros.",
            )
            return redirect(destino)

        if dados_loc.latitude_aprox is None or dados_loc.longitude_aprox is None:
            messages.warning(
                request,
                "Não foi possível localizar o CEP informado no momento. "
                "Você ainda pode buscar usando os outros filtros.",
            )
            return redirect(destino)

        rotulo = (
            f"{dados_loc.bairro} · {dados_loc.municipio}/{dados_loc.estado}"
            if dados_loc.bairro
            else f"{dados_loc.municipio}/{dados_loc.estado}"
        )
        request.session[SESSAO_CHAVE_BUSCA_LOCALIZACAO] = {
            "origem": "cep",
            "cep": dados_loc.cep,
            "rotulo_aproximado": rotulo,
            "lat": str(dados_loc.latitude_aprox),
            "lon": str(dados_loc.longitude_aprox),
        }
        messages.success(
            request,
            f"Localização aproximada definida para {rotulo}.",
        )
        return redirect(destino)


class LimparLocalizacaoBuscaView(View):
    """Revoga/remove a localização aproximada da sessão do usuário (RS010)."""

    def post(self, request):
        request.session.pop(SESSAO_CHAVE_BUSCA_LOCALIZACAO, None)
        messages.info(request, "Localização removida desta sessão.")
        return redirect(_redirect_busca_seguro(request))


class DoacaoCriarView(PerfilObrigatorioMixin, View):
    """Cadastro de nova doação de medicamento pelo Doador (Spec 08 / Spec 09)."""

    perfis_permitidos = ("doador",)
    template_name = "medicamentos/doacao_form.html"

    def _contexto(self, form):
        parametros = VencimentoService.obter_parametros()
        return {
            "form": form,
            "modo_edicao": False,
            "validade_minima_dias": parametros.validade_minima_restante_dias,
            "aviso_rnf13": AVISO_RNF13,
            "aviso_lgpd_ia": AVISO_LGPD_IA_EMBALAGEM,
            "ia_configurada": LeituraEmbalagemIaService.ia_configurada(),
            "confianca_minima_ia": settings.REMED_IA_CONFIANCA_MINIMA,
        }

    def get(self, request):
        formas = DoacaoService.listar_formas_farmaceuticas_ativas()
        pontos = DoacaoService.listar_pontos_coleta_ativos(priorizar_refrigeracao=True)
        form = DoacaoCadastroForm(
            initial={
                "embalagem_integra": "sim",
                "controle_especial": "nao",
                "condicao_conservacao": CondicaoConservacao.TEMPERATURA_AMBIENTE,
                "sujeito_receita": "nao",
            },
            formas_farmaceuticas=formas,
            pontos_coleta=pontos,
        )
        return render(request, self.template_name, self._contexto(form))

    def post(self, request):
        formas = DoacaoService.listar_formas_farmaceuticas_ativas()
        pontos = DoacaoService.listar_pontos_coleta_ativos(priorizar_refrigeracao=True)
        form = DoacaoCadastroForm(
            request.POST,
            request.FILES,
            formas_farmaceuticas=formas,
            pontos_coleta=pontos,
        )
        if not form.is_valid():
            return render(request, self.template_name, self._contexto(form))

        dados = _construir_dados_doacao(form.cleaned_data)
        fotos: list[ArquivoFotoEntrada] = []
        for campo_foto in ("foto_1", "foto_2"):
            arq = form.cleaned_data.get(campo_foto)
            if arq is not None:
                fotos.append(ArquivoFotoEntrada(conteudo=arq.read(), nome_original=arq.name))

        try:
            DoacaoService.cadastrar(request.user, dados, fotos)
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except ErroDominio as erro:
            form.add_error(None, str(erro))
            return render(request, self.template_name, self._contexto(form))

        messages.success(
            request,
            f"Doação cadastrada com sucesso e enviada para conferência. {AVISO_RNF13}",
        )
        return redirect("medicamentos:minhas_doacoes")


class DoacaoLerEmbalagemIaView(PerfilObrigatorioMixin, View):
    """Endpoint JSON interno para sugestão assistida por IA da embalagem (Spec 23 / ADR 0021)."""

    perfis_permitidos = ("doador",)

    def post(self, request):
        arquivo = request.FILES.get("foto")
        if arquivo is None:
            return JsonResponse(
                {
                    "sucesso": False,
                    "erro": "Selecione primeiro a Foto 1 da embalagem em JPG ou PNG.",
                    "fallback_manual": True,
                },
                status=400,
            )

        consentimento = (request.POST.get("consentimento_ia") or "").strip().lower() in {
            "1",
            "true",
            "sim",
            "on",
        }
        try:
            resultado = LeituraEmbalagemIaService.extrair_sugestoes(
                request.user,
                conteudo_imagem=arquivo.read(),
                nome_arquivo=getattr(arquivo, "name", "") or "",
                consentimento_envio=consentimento,
            )
        except PermissaoNegada as erro:
            return JsonResponse({"sucesso": False, "erro": str(erro)}, status=403)
        except LimiteTaxaExcedido as erro:
            return JsonResponse(
                {"sucesso": False, "erro": str(erro), "fallback_manual": True},
                status=429,
            )
        except ServicoIaIndisponivel as erro:
            return JsonResponse(
                {"sucesso": False, "erro": str(erro), "fallback_manual": True},
                status=503,
            )
        except ErroDominio as erro:
            return JsonResponse(
                {"sucesso": False, "erro": str(erro), "fallback_manual": True},
                status=400,
            )

        return JsonResponse(resultado.para_dict(), status=200)


class MinhasDoacoesListaView(PerfilObrigatorioMixin, View):
    """Consulta e gestão das próprias doações pelo Doador (Spec 08)."""

    perfis_permitidos = ("doador",)
    template_name = "medicamentos/minhas_doacoes_lista.html"

    def get(self, request):
        form = MinhasDoacoesFiltroForm(request.GET or None)
        filtros = FiltrosMinhasDoacoes()
        if form.is_valid():
            filtros = FiltrosMinhasDoacoes(
                termo=form.cleaned_data.get("termo") or "",
                status=form.cleaned_data.get("status") or "",
                data_inicio=form.cleaned_data.get("data_inicio"),
                data_fim=form.cleaned_data.get("data_fim"),
            )
        try:
            pagina_num = max(1, int(request.GET.get("page", "1")))
        except ValueError:
            pagina_num = 1

        resultado = DoacaoService.listar_do_doador(request.user, filtros, pagina=pagina_num)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "pagina": resultado.pagina,
                "total_encontrados": resultado.total_encontrados,
                "aviso_rnf13": AVISO_RNF13,
            },
        )


class DoacaoEditarView(PerfilObrigatorioMixin, View):
    """Edição de doação pelo próprio Doador em em_analise ou disponivel (Spec 08 / Spec 09)."""

    perfis_permitidos = ("doador",)
    template_name = "medicamentos/doacao_form.html"

    def _carregar_doacao(self, request, doacao_id: int):
        try:
            return DoacaoService.obter_para_doador(doacao_id, request.user)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro

    def _initial_doacao(self, doacao) -> dict:
        try:
            refrig = doacao.dados_refrigeracao
        except Exception:
            refrig = None
        return {
            "nome_medicamento": doacao.nome_medicamento,
            "principio_ativo": doacao.principio_ativo,
            "concentracao_dosagem": doacao.concentracao_dosagem,
            "forma_farmaceutica": str(doacao.forma_farmaceutica_id),
            "quantidade": doacao.quantidade_inicial,
            "fabricante": doacao.fabricante,
            "lote": doacao.lote,
            "data_validade": doacao.data_validade,
            "embalagem_integra": "sim",
            "controle_especial": "nao",
            "condicao_conservacao": doacao.condicao_conservacao,
            "sujeito_receita": "sim" if doacao.sujeito_receita else "nao",
            "ponto_coleta": str(doacao.ponto_coleta_id) if doacao.ponto_coleta_id else "",
            "observacoes": doacao.observacoes,
            "faixa_temperatura_bula": refrig.faixa_temperatura_bula if refrig else "",
            "declaracao_doador_conservacao": bool(refrig and refrig.declaracao_doador_conservacao),
        }

    def get(self, request, doacao_id: int):
        doacao = self._carregar_doacao(request, doacao_id)
        formas = DoacaoService.listar_formas_farmaceuticas_ativas()
        pontos = DoacaoService.listar_pontos_coleta_ativos(priorizar_refrigeracao=True)
        form = DoacaoEditarForm(
            initial=self._initial_doacao(doacao),
            formas_farmaceuticas=formas,
            pontos_coleta=pontos,
        )
        parametros = VencimentoService.obter_parametros()
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "doacao": doacao,
                "fotos_existentes": list(doacao.fotos.all()),
                "modo_edicao": True,
                "validade_minima_dias": parametros.validade_minima_restante_dias,
                "aviso_rnf13": AVISO_RNF13,
            },
        )

    def post(self, request, doacao_id: int):
        doacao = self._carregar_doacao(request, doacao_id)
        formas = DoacaoService.listar_formas_farmaceuticas_ativas()
        pontos = DoacaoService.listar_pontos_coleta_ativos(priorizar_refrigeracao=True)
        form = DoacaoEditarForm(
            request.POST,
            request.FILES,
            formas_farmaceuticas=formas,
            pontos_coleta=pontos,
        )
        parametros = VencimentoService.obter_parametros()
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "doacao": doacao,
                    "fotos_existentes": list(doacao.fotos.all()),
                    "modo_edicao": True,
                    "validade_minima_dias": parametros.validade_minima_restante_dias,
                    "aviso_rnf13": AVISO_RNF13,
                },
            )

        dados = _construir_dados_doacao(form.cleaned_data)
        fotos_novas: dict[int, ArquivoFotoEntrada] = {}
        for ordem, campo in ((1, "foto_1"), (2, "foto_2")):
            arq = form.cleaned_data.get(campo)
            if arq is not None:
                fotos_novas[ordem] = ArquivoFotoEntrada(conteudo=arq.read(), nome_original=arq.name)

        try:
            resultado = DoacaoService.atualizar(
                doacao.pk, request.user, dados, fotos_novas=fotos_novas
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except ErroDominio as erro:
            form.add_error(None, str(erro))
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "doacao": doacao,
                    "fotos_existentes": list(doacao.fotos.all()),
                    "modo_edicao": True,
                    "validade_minima_dias": parametros.validade_minima_restante_dias,
                    "aviso_rnf13": AVISO_RNF13,
                },
            )

        if resultado.remetida_reanalise:
            messages.warning(
                request,
                "Doação atualizada e enviada novamente para conferência devido à alteração "
                "de dados críticos.",
            )
        else:
            messages.success(request, "Doação atualizada com sucesso.")
        return redirect("medicamentos:minhas_doacoes")


class DoacaoCancelarView(PerfilObrigatorioMixin, View):
    """Cancelamento lógico (sem exclusão física) da doação via POST (Spec 08)."""

    perfis_permitidos = ("doador",)

    def post(self, request, doacao_id: int):
        try:
            DoacaoService.cancelar(doacao_id, request.user)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except ErroDominio as erro:
            messages.error(request, str(erro))
            return redirect("medicamentos:minhas_doacoes")

        messages.success(request, "Doação cancelada com sucesso.")
        return redirect("medicamentos:minhas_doacoes")


class DoacaoFotoAcessarView(AutenticadoAtivoMixin, View):
    """Gera URL temporária de 60 s para foto da doação com controle de perfil e auditoria."""

    def get(self, request, foto_id: int):
        sessao_2fa = request.session.get(SESSAO_CHAVE_2FA_VERIFICADO) is True
        try:
            url_temporaria = DoacaoService.gerar_acesso_foto(
                foto_id,
                request.user,
                sessao_2fa_verificado=sessao_2fa,
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        return redirect(url_temporaria)


class AdminConferenciaListaView(FuncaoAdminObrigatoriaMixin, View):
    """Fila administrativa de doações em análise (Spec 10 / RF011)."""

    funcao_admin = "conferencia_doacoes"
    template_name = "medicamentos/admin_conferencia_lista.html"

    def get(self, request):
        form = AdminConferenciaFiltroForm(request.GET or None)
        filtros = FiltrosConferenciaAdmin()
        if form.is_valid():
            filtros = FiltrosConferenciaAdmin(
                termo=form.cleaned_data.get("termo") or "",
                condicao_conservacao=form.cleaned_data.get("condicao_conservacao") or "",
                sujeito_receita=form.cleaned_data.get("sujeito_receita") or "",
                data_inicio=form.cleaned_data.get("data_inicio"),
                data_fim=form.cleaned_data.get("data_fim"),
            )
        try:
            pagina_num = max(1, int(request.GET.get("page", "1")))
        except ValueError:
            pagina_num = 1

        try:
            resultado = ConferenciaDoacaoService.listar_pendentes(
                request.user, filtros, pagina=pagina_num
            )
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "pagina": resultado.pagina,
                "total_encontrados": resultado.total_encontrados,
                "aviso_rnf13": AVISO_RNF13,
            },
        )


class AdminConferenciaDetalheView(FuncaoAdminObrigatoriaMixin, View):
    """Detalhe de doação para conferência de validade e fotos (Spec 10 / RF011)."""

    funcao_admin = "conferencia_doacoes"
    template_name = "medicamentos/admin_conferencia_detalhe.html"

    def get(self, request, doacao_id: int):
        try:
            detalhe = ConferenciaDoacaoService.obter_detalhe(request.user, doacao_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))

        return render(
            request,
            self.template_name,
            {
                "detalhe": detalhe,
                "form": ConferenciaDoacaoForm(),
                "aviso_rnf13": AVISO_RNF13,
            },
        )


class AdminConferenciaRegistrarView(FuncaoAdminObrigatoriaMixin, View):
    """Registra aprovação ou reprovação da conferência via POST (Spec 10 / RF011)."""

    funcao_admin = "conferencia_doacoes"

    def post(self, request, doacao_id: int):
        form = ConferenciaDoacaoForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Selecione um resultado válido para registrar a conferência.")
            return redirect("medicamentos:admin_conferencia_detalhe", doacao_id=doacao_id)

        try:
            ConferenciaDoacaoService.registrar_conferencia(
                request.user,
                doacao_id,
                form.cleaned_data["resultado"],
                form.cleaned_data.get("motivo") or "",
            )
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except ErroDominio as erro:
            messages.error(request, str(erro))
            return redirect("medicamentos:admin_conferencia_detalhe", doacao_id=doacao_id)

        messages.success(request, "Conferência registrada com sucesso")
        return redirect("medicamentos:admin_conferencia_lista")


class AdminConferenciaMarcarVencidaView(FuncaoAdminObrigatoriaMixin, View):
    """Marca doação em análise abaixo da validade mínima diretamente como vencida (RN-10-03)."""

    funcao_admin = "conferencia_doacoes"

    def post(self, request, doacao_id: int):
        try:
            ConferenciaDoacaoService.marcar_vencida_na_conferencia(request.user, doacao_id)
        except RecursoNaoEncontrado as erro:
            raise Http404(str(erro)) from erro
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except ErroDominio as erro:
            messages.error(request, str(erro))
            return redirect("medicamentos:admin_conferencia_detalhe", doacao_id=doacao_id)

        messages.success(
            request,
            "Doação marcada como vencida e doador notificado com orientação de descarte sanitário.",
        )
        return redirect("medicamentos:admin_conferencia_lista")


class AdminVencimentoParametrosView(FuncaoAdminObrigatoriaMixin, View):
    """Edição dos parâmetros da rotina diária de vencimento (Spec 11 / RF012)."""

    funcao_admin = "metricas_e_parametros"
    template_name = "medicamentos/admin_vencimento_parametros.html"

    def get(self, request):
        parametros = VencimentoService.obter_parametros()
        form = ParametroVencimentoForm(
            initial={
                "validade_minima_restante_dias": parametros.validade_minima_restante_dias,
                "antecedencia_aviso_dias": parametros.antecedencia_aviso_dias,
            }
        )
        return render(request, self.template_name, {"form": form, "parametros": parametros})

    def post(self, request):
        parametros = VencimentoService.obter_parametros()
        form = ParametroVencimentoForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "parametros": parametros})

        try:
            VencimentoService.atualizar_parametros(
                request.user,
                validade_minima_restante_dias=form.cleaned_data["validade_minima_restante_dias"],
                antecedencia_aviso_dias=form.cleaned_data["antecedencia_aviso_dias"],
            )
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))
        except ErroDominio as erro:
            form.add_error(None, str(erro))
            return render(request, self.template_name, {"form": form, "parametros": parametros})

        messages.success(request, "Parâmetros de vencimento atualizados com sucesso")
        return redirect("medicamentos:admin_vencimento_parametros")


class AdminVencimentoExecucoesView(FuncaoAdminObrigatoriaMixin, View):
    """Histórico paginado das execuções da rotina de vencimento (Spec 11 / RF012)."""

    funcao_admin = "metricas_e_parametros"
    template_name = "medicamentos/admin_vencimento_execucoes.html"

    def get(self, request):
        try:
            pagina_num = max(1, int(request.GET.get("page", "1")))
        except ValueError:
            pagina_num = 1

        try:
            resultado = VencimentoService.listar_execucoes(request.user, pagina=pagina_num)
        except PermissaoNegada as erro:
            return HttpResponseForbidden(str(erro))

        return render(
            request,
            self.template_name,
            {
                "pagina": resultado.pagina,
                "total_encontrados": resultado.total_encontrados,
            },
        )

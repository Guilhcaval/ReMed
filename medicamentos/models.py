"""Models do app medicamentos (Specs 08, 09, 10, 11 e 14)."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from nucleo.models import ExecucaoRotina, FormaFarmaceutica, ResultadoRotina
from pontos_coleta.models import PontoColeta

TAMANHO_MAXIMO_FOTO_BYTES = 5 * 1024 * 1024


class CondicaoConservacao(models.TextChoices):
    TEMPERATURA_AMBIENTE = "temperatura_ambiente", "Temperatura ambiente"
    REFRIGERADO = "refrigerado", "Refrigerado"


class StatusDoacao(models.TextChoices):
    EM_ANALISE = "em_analise", "Em análise"
    DISPONIVEL = "disponivel", "Disponível"
    RESERVADO = "reservado", "Reservado"
    ENTREGUE = "entregue", "Entregue"
    VENCIDO = "vencido", "Vencido"
    REPROVADO = "reprovado", "Reprovado"
    CANCELADO = "cancelado", "Cancelado"


class ResultadoConferenciaDoacao(models.TextChoices):
    APROVADA = "aprovada", "Aprovada"
    REPROVADA = "reprovada", "Reprovada"


class Doacao(models.Model):
    """Oferta de medicamento não vencido para doação responsável (RF008 / RF010 / RF012 / RF015)."""

    doador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="doacoes",
        db_index=True,
    )
    nome_medicamento = models.CharField(max_length=150, db_index=True)
    principio_ativo = models.CharField(max_length=150, db_index=True)
    concentracao_dosagem = models.CharField(max_length=80)
    forma_farmaceutica = models.ForeignKey(
        FormaFarmaceutica,
        on_delete=models.PROTECT,
        related_name="doacoes",
    )
    quantidade_inicial = models.PositiveIntegerField()
    quantidade_disponivel = models.PositiveIntegerField()
    fabricante = models.CharField(max_length=120)
    lote = models.CharField(max_length=60)
    data_validade = models.DateField(db_index=True)
    embalagem_integra = models.BooleanField()
    condicao_conservacao = models.CharField(
        max_length=25,
        choices=CondicaoConservacao.choices,
        db_index=True,
    )
    sujeito_receita = models.BooleanField(default=False)
    ponto_coleta = models.ForeignKey(
        PontoColeta,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="doacoes",
    )
    observacoes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=StatusDoacao.choices,
        default=StatusDoacao.EM_ANALISE,
        db_index=True,
    )

    # Localização aproximada para busca por proximidade (Spec 14 / ADR 0017 / RS002 / RS010).
    regiao_bairro = models.CharField(max_length=100, blank=True)
    regiao_municipio = models.CharField(max_length=100, blank=True)
    regiao_uf = models.CharField(max_length=2, blank=True)
    latitude_aprox = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, db_index=True
    )
    longitude_aprox = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, db_index=True
    )

    # Controle de idempotência do aviso prévio de vencimento (Spec 11 / RN-11-02).
    aviso_vencimento_enviado_em = models.DateTimeField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Doação de medicamento"
        verbose_name_plural = "Doações de medicamentos"
        ordering = ["-criado_em", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantidade_inicial__gt=0),
                name="ck_doacao_qtd_inicial_positiva",
            ),
            models.CheckConstraint(
                condition=Q(quantidade_disponivel__gte=0)
                & Q(quantidade_disponivel__lte=F("quantidade_inicial")),
                name="ck_doacao_qtd_disponivel_valida",
            ),
            models.CheckConstraint(
                condition=Q(embalagem_integra=True),
                name="ck_doacao_embalagem_integra",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "data_validade"], name="idx_doacao_status_validade"),
            models.Index(fields=["status", "criado_em"], name="idx_doacao_status_criado"),
            models.Index(
                fields=["doador", "status", "criado_em"],
                name="idx_doacao_doador_status_dt",
            ),
            models.Index(fields=["latitude_aprox", "longitude_aprox"], name="idx_doacao_lat_lon"),
        ]

    def __str__(self) -> str:
        return f"Doação #{self.pk} · {self.nome_medicamento} ({self.status})"


class FotoDoacao(models.Model):
    """Foto privada da embalagem vinculada à doação (RF008 / ADR 0016)."""

    doacao = models.ForeignKey(
        Doacao,
        on_delete=models.PROTECT,
        related_name="fotos",
    )
    ordem = models.PositiveSmallIntegerField()
    arquivo_chave = models.CharField(max_length=255, unique=True)
    mime_verificado = models.CharField(max_length=40)
    tamanho_bytes = models.PositiveIntegerField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Foto da doação"
        verbose_name_plural = "Fotos das doações"
        ordering = ["ordem", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["doacao", "ordem"],
                name="uq_foto_doacao_ordem",
            ),
            models.CheckConstraint(
                condition=Q(ordem__in=[1, 2]),
                name="ck_foto_doacao_ordem_1_ou_2",
            ),
            models.CheckConstraint(
                condition=Q(tamanho_bytes__gt=0, tamanho_bytes__lte=TAMANHO_MAXIMO_FOTO_BYTES),
                name="ck_foto_doacao_tamanho_5mb",
            ),
            models.CheckConstraint(
                condition=Q(mime_verificado__in=["image/jpeg", "image/png"]),
                name="ck_foto_doacao_mime_imagem",
            ),
        ]

    def __str__(self) -> str:
        return f"Foto #{self.ordem} · Doação #{self.doacao_id}"


class DadosRefrigeracaoDoacao(models.Model):
    """Dados obrigatórios de conservação de medicamentos refrigerados (Spec 09 / RF010)."""

    doacao = models.OneToOneField(
        Doacao,
        on_delete=models.CASCADE,
        related_name="dados_refrigeracao",
    )
    faixa_temperatura_bula = models.CharField(max_length=80)
    declaracao_doador_conservacao = models.BooleanField()
    declaracao_doador_em = models.DateTimeField()

    class Meta:
        verbose_name = "Dados de refrigeração da doação"
        verbose_name_plural = "Dados de refrigeração das doações"
        constraints = [
            models.CheckConstraint(
                condition=Q(declaracao_doador_conservacao=True),
                name="ck_refrig_declaracao_doador_true",
            ),
            models.CheckConstraint(
                condition=Q(faixa_temperatura_bula__regex=r"[^[:space:]]"),
                name="ck_refrig_faixa_temp_nao_vazia",
            ),
        ]

    def __str__(self) -> str:
        return f"Refrigeração · Doação #{self.doacao_id} ({self.faixa_temperatura_bula})"


class ConferenciaDoacao(models.Model):
    """Registro imutável append-only da conferência de validade/integridade (Spec 10 / RF011)."""

    doacao = models.ForeignKey(
        Doacao,
        on_delete=models.PROTECT,
        related_name="conferencias",
        db_index=True,
    )
    resultado = models.CharField(max_length=20, choices=ResultadoConferenciaDoacao.choices)
    motivo = models.TextField(blank=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="conferencias_doacao_executadas",
    )
    conferido_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Conferência de doação"
        verbose_name_plural = "Conferências de doações"
        ordering = ["-conferido_em", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(resultado=ResultadoConferenciaDoacao.REPROVADA)
                | Q(motivo__regex=r"[^[:space:]]"),
                name="ck_conf_doacao_motivo_reprovacao",
            ),
        ]
        indexes = [
            models.Index(fields=["doacao", "conferido_em"], name="idx_conf_doacao_dt"),
        ]

    def __str__(self) -> str:
        return f"Conferência #{self.pk} · Doação #{self.doacao_id} ({self.resultado})"


class ParametroVencimento(models.Model):
    """Parâmetros configuráveis da rotina diária de vencimento (Spec 11 / RF012 / ADR 0014)."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    # Valor inicial provisório de 30 dias — pendência com o professor (Questão 4 do PRD).
    validade_minima_restante_dias = models.PositiveIntegerField(default=30)
    antecedencia_aviso_dias = models.PositiveIntegerField(default=15)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="parametros_vencimento_atualizados",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parâmetro de vencimento"
        verbose_name_plural = "Parâmetros de vencimento"
        constraints = [
            models.CheckConstraint(
                condition=Q(id=1),
                name="ck_param_vencimento_singleton",
            ),
            models.CheckConstraint(
                condition=Q(validade_minima_restante_dias__gte=0),
                name="ck_param_vencimento_validade_min",
            ),
            models.CheckConstraint(
                condition=Q(antecedencia_aviso_dias__gte=1),
                name="ck_param_vencimento_aviso_min",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Parâmetros RF012 (validade_min={self.validade_minima_restante_dias}d, "
            f"aviso={self.antecedencia_aviso_dias}d)"
        )


class ExecucaoVencimento(models.Model):
    """Resumo imutável append-only de cada execução da rotina diária (Spec 11 / RF012)."""

    execucao_rotina = models.OneToOneField(
        ExecucaoRotina,
        on_delete=models.PROTECT,
        related_name="execucao_vencimento",
    )
    executado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    doacoes_verificadas = models.PositiveIntegerField(default=0)
    doacoes_marcadas_vencidas = models.PositiveIntegerField(default=0)
    reservas_agendamentos_cancelados = models.PositiveIntegerField(default=0)
    notificacoes_enviadas = models.PositiveIntegerField(default=0)
    resultado = models.CharField(
        max_length=20,
        choices=ResultadoRotina.choices,
        db_index=True,
    )
    resumo_erro = models.TextField(blank=True)

    class Meta:
        verbose_name = "Execução de vencimento"
        verbose_name_plural = "Execuções de vencimento"
        ordering = ["-executado_em", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    resultado__in=[
                        ResultadoRotina.SUCESSO,
                        ResultadoRotina.PARCIAL,
                        ResultadoRotina.FALHA,
                    ]
                ),
                name="ck_exec_vencimento_resultado_final",
            ),
        ]

    def __str__(self) -> str:
        return f"Execução vencimento #{self.pk} ({self.resultado})"

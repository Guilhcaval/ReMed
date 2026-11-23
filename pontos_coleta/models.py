"""Models do app pontos_coleta (Specs 05, 06 e 07 — RF005, RF006 e RF007)."""

from django.conf import settings
from django.db import models

from nucleo.models import TipoDocumentoPonto, TipoEstabelecimento

TAMANHO_MAXIMO_DOCUMENTO_BYTES = 5 * 1024 * 1024

DIAS_SEMANA_ROTULOS: dict[int, str] = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}

DIAS_SEMANA_CURTOS: tuple[tuple[int, str], ...] = (
    (0, "Seg"),
    (1, "Ter"),
    (2, "Qua"),
    (3, "Qui"),
    (4, "Sex"),
    (5, "Sáb"),
    (6, "Dom"),
)


class StatusPontoColeta(models.TextChoices):
    PENDENTE_APROVACAO = "pendente_aprovacao", "Pendente de aprovação"
    ATIVO = "ativo", "Ativo"
    SUSPENSO = "suspenso", "Suspenso"
    INATIVO = "inativo", "Inativo"


class StatusResponsavelPonto(models.TextChoices):
    CONVITE_PENDENTE = "convite_pendente", "Convite pendente"
    ATIVO = "ativo", "Ativo"
    RECUSADO = "recusado", "Recusado"
    INATIVO = "inativo", "Inativo"


class StatusDocumentoPonto(models.TextChoices):
    ENVIADO = "enviado", "Enviado"
    EM_ANALISE = "em_analise", "Em análise"
    APROVADO = "aprovado", "Aprovado"
    REPROVADO = "reprovado", "Reprovado"
    VENCIDO = "vencido", "Vencido"


class TipoAcaoAnalisePonto(models.TextChoices):
    ANALISE_CADASTRO = "analise_cadastro", "Análise de cadastro"
    ALTERACAO_SITUACAO = "alteracao_situacao", "Alteração de situação"
    REVISAO_PERIODICA = "revisao_periodica", "Revisão periódica"


class ResultadoAnalisePonto(models.TextChoices):
    APROVADO = "aprovado", "Aprovado"
    REPROVADO = "reprovado", "Reprovado"
    PENDENTE_DOCUMENTACAO = "pendente_documentacao", "Pendente de documentação"


class PontoColeta(models.Model):
    """Instituição parceira cadastrada como local seguro de encontro para retirada (RF005)."""

    cnpj = models.CharField(max_length=14)
    razao_social = models.CharField(max_length=150)
    nome_fantasia = models.CharField(max_length=150, db_index=True)
    tipo_estabelecimento = models.ForeignKey(
        TipoEstabelecimento,
        on_delete=models.PROTECT,
        related_name="pontos_coleta",
    )
    email = models.EmailField(max_length=254)
    telefone = models.CharField(max_length=11)
    possui_refrigeracao = models.BooleanField()
    observacoes = models.TextField(blank=True)

    # Endereço público do ponto de coleta (RN-05-06 / ADR 0017 / ADR 0018)
    cep = models.CharField(max_length=8)
    logradouro = models.CharField(max_length=150)
    numero = models.CharField(max_length=20)
    bairro = models.CharField(max_length=100)
    municipio = models.CharField(max_length=100, db_index=True)
    estado = models.CharField(max_length=2)
    complemento = models.CharField(max_length=100, blank=True)
    latitude_aprox = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, db_index=True
    )
    longitude_aprox = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, db_index=True
    )

    status = models.CharField(
        max_length=25,
        choices=StatusPontoColeta.choices,
        default=StatusPontoColeta.PENDENTE_APROVACAO,
        db_index=True,
    )
    ultima_revisao_em = models.DateTimeField(null=True, blank=True, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ponto de coleta"
        verbose_name_plural = "Pontos de coleta"
        ordering = ["nome_fantasia", "id"]
        constraints = [
            models.UniqueConstraint(fields=["cnpj"], name="uq_ponto_coleta_cnpj"),
            models.CheckConstraint(
                condition=models.Q(cnpj__regex=r"^[0-9]{14}$"),
                name="ck_ponto_coleta_cnpj_14_digitos",
            ),
            models.CheckConstraint(
                condition=models.Q(cep__regex=r"^[0-9]{8}$"),
                name="ck_ponto_coleta_cep_8_digitos",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "municipio"], name="idx_ponto_status_municipio"),
            models.Index(fields=["status", "ultima_revisao_em"], name="idx_ponto_status_revisao"),
        ]

    def __str__(self) -> str:
        return f"{self.nome_fantasia} ({self.municipio}/{self.estado})"


class HorarioFuncionamentoPonto(models.Model):
    """Faixa de dia e horário disponível para retirada em um ponto de coleta (RN-05-03)."""

    ponto_coleta = models.ForeignKey(
        PontoColeta,
        on_delete=models.CASCADE,
        related_name="horarios",
    )
    dia_semana = models.SmallIntegerField()
    hora_abertura = models.TimeField()
    hora_fechamento = models.TimeField()

    class Meta:
        verbose_name = "Horário de funcionamento do ponto"
        verbose_name_plural = "Horários de funcionamento dos pontos"
        ordering = ["dia_semana", "hora_abertura"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(dia_semana__gte=0, dia_semana__lte=6),
                name="ck_horario_ponto_dia_semana_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(hora_abertura__lt=models.F("hora_fechamento")),
                name="ck_horario_ponto_abertura_menor_fechamento",
            ),
        ]
        indexes = [
            models.Index(
                fields=["ponto_coleta", "dia_semana", "hora_abertura"],
                name="idx_horario_ponto_dia",
            ),
        ]

    def __str__(self) -> str:
        dia = DIAS_SEMANA_ROTULOS.get(self.dia_semana, str(self.dia_semana))
        return f"{dia}: {self.hora_abertura:%H:%M}–{self.hora_fechamento:%H:%M}"


class PontoColetaResponsavel(models.Model):
    """Vínculo entre usuário pessoa física e ponto de coleta (RN-05-07 / ADR 0010)."""

    ponto_coleta = models.ForeignKey(
        PontoColeta,
        on_delete=models.PROTECT,
        related_name="responsaveis",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="vinculos_pontos_coleta",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=StatusResponsavelPonto.choices,
        default=StatusResponsavelPonto.CONVITE_PENDENTE,
        db_index=True,
    )
    convidado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="convites_ponto_enviados",
        null=True,
        blank=True,
    )
    vinculado_em = models.DateTimeField(auto_now_add=True)
    desvinculado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Responsável pelo ponto de coleta"
        verbose_name_plural = "Responsáveis pelos pontos de coleta"
        ordering = ["-vinculado_em", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["ponto_coleta", "usuario"],
                condition=models.Q(
                    status__in=[
                        StatusResponsavelPonto.CONVITE_PENDENTE,
                        StatusResponsavelPonto.ATIVO,
                    ]
                ),
                name="uq_ponto_responsavel_ativo_ou_pendente",
            ),
        ]
        indexes = [
            models.Index(fields=["usuario", "status"], name="idx_ponto_resp_usuario_status"),
        ]

    def __str__(self) -> str:
        return f"Responsável #{self.usuario_id} · Ponto #{self.ponto_coleta_id} ({self.status})"


class DocumentoPontoColeta(models.Model):
    """Documento comprobatório versionado de ponto de coleta (RF006 / ADR 0016)."""

    ponto_coleta = models.ForeignKey(
        PontoColeta,
        on_delete=models.PROTECT,
        related_name="documentos",
        db_index=True,
    )
    tipo_documento = models.ForeignKey(
        TipoDocumentoPonto,
        on_delete=models.PROTECT,
        related_name="documentos_enviados",
    )
    versao = models.PositiveIntegerField()
    arquivo_chave = models.CharField(max_length=255, unique=True)
    mime_verificado = models.CharField(max_length=60)
    tamanho_bytes = models.PositiveIntegerField()
    numero_documento = models.CharField(max_length=80)
    data_validade = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=StatusDocumentoPonto.choices,
        default=StatusDocumentoPonto.ENVIADO,
        db_index=True,
    )
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="documentos_ponto_enviados",
    )
    enviado_em = models.DateTimeField(auto_now_add=True)
    aviso_vencimento_enviado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Documento de ponto de coleta"
        verbose_name_plural = "Documentos de pontos de coleta"
        ordering = ["-enviado_em", "-versao"]
        constraints = [
            models.UniqueConstraint(
                fields=["ponto_coleta", "tipo_documento", "versao"],
                name="uq_documento_ponto_tipo_versao",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    tamanho_bytes__gt=0,
                    tamanho_bytes__lte=TAMANHO_MAXIMO_DOCUMENTO_BYTES,
                ),
                name="ck_documento_ponto_tamanho_5mb",
            ),
            models.CheckConstraint(
                condition=models.Q(versao__gte=1),
                name="ck_documento_ponto_versao_positiva",
            ),
        ]
        indexes = [
            models.Index(
                fields=["ponto_coleta", "tipo_documento", "status"],
                name="idx_doc_ponto_tipo_status",
            ),
        ]

    def __str__(self) -> str:
        return f"Doc #{self.pk} v{self.versao} · Ponto #{self.ponto_coleta_id} ({self.status})"


class AnalisePontoColeta(models.Model):
    """Histórico imutável append-only de análises e mudanças de situação (RF007 / RNF14)."""

    ponto_coleta = models.ForeignKey(
        PontoColeta,
        on_delete=models.PROTECT,
        related_name="analises",
        db_index=True,
    )
    tipo_acao = models.CharField(max_length=30, choices=TipoAcaoAnalisePonto.choices, db_index=True)
    resultado = models.CharField(
        max_length=30,
        choices=ResultadoAnalisePonto.choices,
        blank=True,
    )
    status_anterior = models.CharField(max_length=25, choices=StatusPontoColeta.choices)
    status_novo = models.CharField(max_length=25, choices=StatusPontoColeta.choices)
    motivo = models.TextField(blank=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="analises_ponto_executadas",
    )
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Análise de ponto de coleta"
        verbose_name_plural = "Análises de pontos de coleta"
        ordering = ["-criado_em"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~(
                        models.Q(
                            resultado__in=[
                                ResultadoAnalisePonto.REPROVADO,
                                ResultadoAnalisePonto.PENDENTE_DOCUMENTACAO,
                            ]
                        )
                        | models.Q(
                            status_novo__in=[
                                StatusPontoColeta.SUSPENSO,
                                StatusPontoColeta.INATIVO,
                            ]
                        )
                    )
                    | models.Q(motivo__regex=r"[^[:space:]]")
                ),
                name="ck_analise_ponto_motivo_obrigatorio",
            ),
        ]
        indexes = [
            models.Index(fields=["ponto_coleta", "criado_em"], name="idx_analise_ponto_dt"),
        ]

    def __str__(self) -> str:
        return f"Análise #{self.pk} ({self.tipo_acao}) · Ponto #{self.ponto_coleta_id}"

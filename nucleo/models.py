from django.db import models


class FonteCep(models.TextChoices):
    BRASILAPI = "brasilapi", "BrasilAPI"
    VIACEP = "viacep", "ViaCEP"
    NOMINATIM = "nominatim", "Nominatim"


class ResultadoRotina(models.TextChoices):
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    SUCESSO = "sucesso", "Sucesso"
    PARCIAL = "parcial", "Parcial"
    FALHA = "falha", "Falha"


class CacheCep(models.Model):
    cep = models.CharField(max_length=8, primary_key=True)
    logradouro = models.CharField(max_length=150, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    municipio = models.CharField(max_length=100)
    estado = models.CharField(max_length=2)
    latitude_aprox = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude_aprox = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    fonte = models.CharField(max_length=20, choices=FonteCep.choices)
    atualizado_em = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        verbose_name = "Cache de CEP"
        verbose_name_plural = "Cache de CEPs"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cep__regex=r"^[0-9]{8}$"),
                name="ck_cache_cep_oito_digitos",
            ),
        ]

    def __str__(self) -> str:
        return f"CEP {self.cep} ({self.municipio}/{self.estado})"


class ExecucaoRotina(models.Model):
    nome_rotina = models.CharField(max_length=80, db_index=True)
    iniciada_em = models.DateTimeField(db_index=True)
    finalizada_em = models.DateTimeField(null=True, blank=True)
    tentativa = models.PositiveSmallIntegerField(default=1)
    resultado = models.CharField(
        max_length=20,
        choices=ResultadoRotina.choices,
        default=ResultadoRotina.EM_ANDAMENTO,
        db_index=True,
    )
    contadores = models.JSONField(default=dict, blank=True)
    resumo_erro = models.TextField(blank=True)

    class Meta:
        verbose_name = "Execução de rotina"
        verbose_name_plural = "Execuções de rotinas"
        ordering = ["-iniciada_em"]
        indexes = [
            models.Index(fields=["nome_rotina", "iniciada_em"], name="idx_rotina_nome_inicio"),
        ]

    def __str__(self) -> str:
        return f"{self.nome_rotina} ({self.resultado})"


class TipoEstabelecimento(models.Model):
    """Cadastro auxiliar de tipos de estabelecimento para pontos de coleta (RF005 / RN-05-02)."""

    nome = models.CharField(max_length=80, unique=True)
    ativo = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Tipo de estabelecimento"
        verbose_name_plural = "Tipos de estabelecimento"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.nome


class TipoDocumentoPonto(models.Model):
    """Cadastro auxiliar de documentos de pontos de coleta (RF006 / RN-06-01)."""

    nome = models.CharField(max_length=100, unique=True)
    obrigatorio = models.BooleanField(default=True)
    ativo = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Tipo de documento de ponto de coleta"
        verbose_name_plural = "Tipos de documentos de pontos de coleta"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.nome

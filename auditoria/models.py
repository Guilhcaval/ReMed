from django.conf import settings
from django.db import models


class OrigemAuditoria(models.TextChoices):
    WEB = "web", "Web"
    ROTINA_AUTOMATICA = "rotina_automatica", "Rotina automática"
    TERMINAL = "terminal", "Terminal"


class RegistroAuditoria(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    ator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="registros_auditoria",
    )
    acao = models.CharField(max_length=80, db_index=True)
    entidade_tipo = models.CharField(max_length=60)
    entidade_id = models.CharField(max_length=64)
    motivo = models.TextField(blank=True)
    detalhes = models.JSONField(default=dict, blank=True)
    origem = models.CharField(
        max_length=25,
        choices=OrigemAuditoria.choices,
        default=OrigemAuditoria.WEB,
        db_index=True,
    )

    class Meta:
        verbose_name = "Registro de auditoria"
        verbose_name_plural = "Registros de auditoria"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["entidade_tipo", "entidade_id"], name="idx_auditoria_entidade"),
        ]

    def __str__(self) -> str:
        return f"{self.acao} ({self.entidade_tipo}#{self.entidade_id})"

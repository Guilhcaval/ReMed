from django.conf import settings
from django.db import models
from django.db.models import Q


class TipoNotificacao(models.TextChoices):
    CONFIRMACAO_EMAIL = "confirmacao_email", "Confirmação de e-mail"
    SEGURANCA_CONTA = "seguranca_conta", "Segurança da conta"
    NOVA_CORRESPONDENCIA = "nova_correspondencia", "Nova correspondência"
    CORRESPONDENCIA_ACEITA = "correspondencia_aceita", "Correspondência aceita"
    AGENDAMENTO_PROPOSTO = "agendamento_proposto", "Agendamento proposto"
    AGENDAMENTO_CONFIRMADO = "agendamento_confirmado", "Agendamento confirmado"
    AGENDAMENTO_ALTERADO = "agendamento_alterado", "Agendamento alterado"
    AGENDAMENTO_CANCELADO = "agendamento_cancelado", "Agendamento cancelado"
    LEMBRETE_RETIRADA_24H = "lembrete_retirada_24h", "Lembrete 24h antes da retirada"
    ENTREGA_CONFIRMADA = "entrega_confirmada", "Entrega confirmada"
    DOACAO_CONFERIDA = "doacao_conferida", "Resultado da conferência da doação"
    DOACAO_PRESTES_VENCER = "doacao_prestes_vencer", "Doação prestes a vencer"
    DOACAO_VENCIDA = "doacao_vencida", "Doação vencida"
    NOVA_MENSAGEM = "nova_mensagem", "Nova mensagem"
    PONTO_ANALISADO = "ponto_analisado", "Resultado da análise do ponto de coleta"
    DOCUMENTO_PRESTES_VENCER = "documento_prestes_vencer", "Documento prestes a vencer"
    SOLICITACAO_PRESTES_EXPIRAR = "solicitacao_prestes_expirar", "Solicitação prestes a expirar"
    SOLICITACAO_EXPIRADA = "solicitacao_expirada", "Solicitação expirada"
    RECEITA_VERIFICADA = "receita_verificada", "Resultado da verificação da receita"
    DENUNCIA_RESULTADO = "denuncia_resultado", "Resultado de denúncia"
    ALERTA_OPERACIONAL = "alerta_operacional", "Alerta operacional"


class CanalNotificacao(models.TextChoices):
    PLATAFORMA = "plataforma", "Plataforma"
    EMAIL = "email", "E-mail"


class StatusNotificacao(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    ENVIADA = "enviada", "Enviada"
    LIDA = "lida", "Lida"
    FALHA = "falha", "Falha"


class StatusOutboxEmail(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    ENVIADA = "enviada", "Enviada"
    FALHA = "falha", "Falha"
    SUPRIMIDA = "suprimida", "Suprimida"


class Notificacao(models.Model):
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notificacoes",
    )
    tipo = models.CharField(max_length=40, choices=TipoNotificacao.choices, db_index=True)
    canal = models.CharField(max_length=20, choices=CanalNotificacao.choices)
    obrigatoria = models.BooleanField(default=False)
    titulo = models.CharField(max_length=140)
    mensagem = models.TextField()
    url_destino = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=StatusNotificacao.choices,
        default=StatusNotificacao.PENDENTE,
        db_index=True,
    )
    criada_em = models.DateTimeField(auto_now_add=True, db_index=True)
    enviada_em = models.DateTimeField(null=True, blank=True)
    lida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Notificação"
        verbose_name_plural = "Notificações"
        ordering = ["-criada_em"]
        indexes = [
            models.Index(
                fields=["destinatario", "canal", "status", "criada_em"],
                name="idx_notif_dest_canal_st_dt",
            ),
        ]

    def __str__(self) -> str:
        return f"Notificação #{self.pk} ({self.tipo})"


class OutboxEmail(models.Model):
    notificacao = models.OneToOneField(
        Notificacao,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="outbox_email",
    )
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emails_outbox",
    )
    email_destino = models.EmailField(max_length=254)
    tipo = models.CharField(max_length=40, choices=TipoNotificacao.choices)
    critico_seguranca = models.BooleanField(default=False)
    assunto = models.CharField(max_length=160)
    corpo_texto = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=StatusOutboxEmail.choices,
        default=StatusOutboxEmail.PENDENTE,
        db_index=True,
    )
    tentativas = models.PositiveSmallIntegerField(default=0)
    proxima_tentativa_em = models.DateTimeField(db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    enviado_em = models.DateTimeField(null=True, blank=True)
    erro_ultimo = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "E-mail na fila (outbox)"
        verbose_name_plural = "E-mails na fila (outbox)"
        ordering = ["proxima_tentativa_em", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(tentativas__lte=4),
                name="ck_outbox_email_max_tentativas",
            ),
        ]

    def __str__(self) -> str:
        return f"OutboxEmail #{self.pk} ({self.tipo} - {self.status})"

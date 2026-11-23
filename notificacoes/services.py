"""Base mínima do Transactional Outbox de e-mails (ADR 0015 / pré-requisito da Spec 01)."""

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from notificacoes.models import (
    OutboxEmail,
    StatusNotificacao,
    StatusOutboxEmail,
    TipoNotificacao,
)

MAX_TENTATIVAS_ENVIO_EMAIL = 4  # 1 tentativa inicial + 3 novas tentativas (Spec 03 / RNF15)
INTERVALO_RETENTATIVA_MINUTOS = 1  # Backoff fixo de 1 min cabendo nos 5 min do RNF15


@dataclass(frozen=True)
class ResultadoDespachoOutbox:
    processados: int
    enviados: int
    reagendados: int
    falhas_definitivas: int


class NotificacaoService:
    @staticmethod
    def enfileirar_email_confirmacao(
        *,
        destinatario,
        email_destino: str,
        link_confirmacao: str,
    ) -> OutboxEmail:
        agora = timezone.now()
        assunto = "ReMed — Confirme seu e-mail"
        corpo_texto = (
            "Olá,\n\n"
            "Para ativar ou confirmar seu e-mail no ReMed, acesse o link abaixo "
            "(válido por tempo limitado e de uso único):\n\n"
            f"{link_confirmacao}\n\n"
            "Se você não solicitou esta ação, ignore esta mensagem.\n"
            "Equipe ReMed"
        )
        return OutboxEmail.objects.create(
            destinatario=destinatario,
            email_destino=email_destino,
            tipo=TipoNotificacao.CONFIRMACAO_EMAIL,
            critico_seguranca=True,
            assunto=assunto,
            corpo_texto=corpo_texto,
            status=StatusOutboxEmail.PENDENTE,
            tentativas=0,
            proxima_tentativa_em=agora,
        )

    @staticmethod
    def despachar_outbox_pendentes(*, limite_lote: int = 50) -> ResultadoDespachoOutbox:
        agora = timezone.now()
        with transaction.atomic():
            ids_lote = list(
                OutboxEmail.objects.select_for_update(skip_locked=True)
                .filter(
                    status=StatusOutboxEmail.PENDENTE,
                    proxima_tentativa_em__lte=agora,
                )
                .order_by("proxima_tentativa_em", "id")
                .values_list("id", flat=True)[:limite_lote]
            )

        enviados = 0
        reagendados = 0
        falhas_definitivas = 0

        for item_id in ids_lote:
            with transaction.atomic():
                item = (
                    OutboxEmail.objects.select_for_update(skip_locked=True, of=("self",))
                    .select_related("notificacao")
                    .filter(
                        id=item_id,
                        status=StatusOutboxEmail.PENDENTE,
                    )
                    .first()
                )
                if item is None:
                    continue

                item.tentativas += 1
                try:
                    send_mail(
                        subject=item.assunto,
                        message=item.corpo_texto,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[item.email_destino],
                        fail_silently=False,
                    )
                except Exception as erro:
                    item.erro_ultimo = str(erro)[:255]
                    if item.tentativas >= MAX_TENTATIVAS_ENVIO_EMAIL:
                        item.status = StatusOutboxEmail.FALHA
                        falhas_definitivas += 1
                        if item.notificacao_id is not None:
                            item.notificacao.status = StatusNotificacao.FALHA
                            item.notificacao.save(update_fields=["status"])
                    else:
                        item.proxima_tentativa_em = timezone.now() + timedelta(
                            minutes=INTERVALO_RETENTATIVA_MINUTOS
                        )
                        reagendados += 1
                    item.save(
                        update_fields=[
                            "tentativas",
                            "status",
                            "proxima_tentativa_em",
                            "erro_ultimo",
                        ]
                    )
                else:
                    momento_envio = timezone.now()
                    item.status = StatusOutboxEmail.ENVIADA
                    item.enviado_em = momento_envio
                    item.erro_ultimo = ""
                    item.save(update_fields=["tentativas", "status", "enviado_em", "erro_ultimo"])
                    if item.notificacao_id is not None:
                        item.notificacao.status = StatusNotificacao.ENVIADA
                        item.notificacao.enviada_em = momento_envio
                        item.notificacao.save(update_fields=["status", "enviada_em"])
                    enviados += 1

        return ResultadoDespachoOutbox(
            processados=len(ids_lote),
            enviados=enviados,
            reagendados=reagendados,
            falhas_definitivas=falhas_definitivas,
        )

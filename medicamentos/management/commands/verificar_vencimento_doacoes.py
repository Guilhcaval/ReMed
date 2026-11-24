"""Rotina diária automática de vencimento e aviso prévio de doações (Spec 11 / ADR 0014)."""

import logging

from django.core.management.base import BaseCommand

from medicamentos.services import NOME_ROTINA_VENCIMENTO, VencimentoService
from nucleo.rotinas import adquirir_lock_rotina

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Verifica diariamente a validade das doações em andamento, marca vencidas/abaixo "
        "do mínimo, envia avisos prévios idempotentes e reexecuta até 3 vezes em falha/parcial."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-retentativas",
            type=int,
            default=None,
            help="Sobrescreve o limite de novas tentativas em falha/parcial (padrão em settings).",
        )
        parser.add_argument(
            "--intervalo-retry",
            type=int,
            default=None,
            help="Intervalo em segundos entre retentativas (padrão: 900 s / 15 min).",
        )

    def handle(self, *args, **options):
        _ = args
        with adquirir_lock_rotina(NOME_ROTINA_VENCIMENTO) as adquirido:
            if not adquirido:
                logger.info(
                    "Rotina %s já está em execução; encerrando sem duplicar.",
                    NOME_ROTINA_VENCIMENTO,
                )
                self.stdout.write(
                    "Outra instância de verificar_vencimento_doacoes já está em execução."
                )
                return

            resultados = VencimentoService.executar_com_retentativas(
                max_retentativas=options["max_retentativas"],
                intervalo_segundos=options["intervalo_retry"],
            )
            ultimo = resultados[-1]
            self.stdout.write(
                "Rotina concluída: "
                f"tentativas={len(resultados)}, "
                f"resultado={ultimo.resultado}, "
                f"verificadas={ultimo.doacoes_verificadas}, "
                f"vencidas={ultimo.doacoes_marcadas_vencidas}, "
                f"avisos={ultimo.avisos_enviados}, "
                f"cancelados={ultimo.reservas_agendamentos_cancelados}, "
                f"notificacoes={ultimo.notificacoes_enviadas}."
            )

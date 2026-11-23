"""Comando agendado para despacho do Transactional Outbox de e-mails (ADRs 0014 e 0015)."""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from notificacoes.services import NotificacaoService
from nucleo.models import ExecucaoRotina, ResultadoRotina
from nucleo.rotinas import adquirir_lock_rotina

logger = logging.getLogger(__name__)

NOME_ROTINA = "despachar_emails"


class Command(BaseCommand):
    help = "Despacha e-mails pendentes no Transactional Outbox (até 3 novas tentativas em falha)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limite-lote",
            type=int,
            default=50,
            help="Quantidade máxima de e-mails processados por execução (padrão: 50).",
        )

    def handle(self, *args, **options):
        limite_lote = max(1, int(options["limite_lote"]))

        with adquirir_lock_rotina(NOME_ROTINA) as adquirido:
            if not adquirido:
                logger.info("Rotina %s já está em execução; encerrando sem duplicar.", NOME_ROTINA)
                self.stdout.write("Outra instância de despachar_emails já está em execução.")
                return

            execucao = ExecucaoRotina.objects.create(
                nome_rotina=NOME_ROTINA,
                iniciada_em=timezone.now(),
                resultado=ResultadoRotina.EM_ANDAMENTO,
            )
            try:
                resultado = NotificacaoService.despachar_outbox_pendentes(limite_lote=limite_lote)
            except Exception as erro:
                execucao.finalizada_em = timezone.now()
                execucao.resultado = ResultadoRotina.FALHA
                execucao.resumo_erro = str(erro)[:500]
                execucao.save(update_fields=["finalizada_em", "resultado", "resumo_erro"])
                logger.exception("Falha sistêmica ao executar rotina %s.", NOME_ROTINA)
                raise

            if resultado.falhas_definitivas > 0 or resultado.reagendados > 0:
                status_final = ResultadoRotina.PARCIAL
            else:
                status_final = ResultadoRotina.SUCESSO

            execucao.finalizada_em = timezone.now()
            execucao.resultado = status_final
            execucao.contadores = {
                "processados": resultado.processados,
                "enviados": resultado.enviados,
                "reagendados": resultado.reagendados,
                "falhas_definitivas": resultado.falhas_definitivas,
            }
            execucao.save(update_fields=["finalizada_em", "resultado", "contadores"])

            self.stdout.write(
                "Despacho concluído: "
                f"processados={resultado.processados}, "
                f"enviados={resultado.enviados}, "
                f"reagendados={resultado.reagendados}, "
                f"falhas_definitivas={resultado.falhas_definitivas}."
            )

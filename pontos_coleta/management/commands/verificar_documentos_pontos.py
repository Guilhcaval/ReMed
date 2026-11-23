"""Rotina diária de aviso prévio e vencimento de documentos de pontos (Spec 06 / ADR 0014)."""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from notificacoes.services import NotificacaoService
from nucleo.models import ExecucaoRotina, ResultadoRotina
from nucleo.rotinas import adquirir_lock_rotina
from pontos_coleta.services import DocumentoPontoService

logger = logging.getLogger(__name__)

NOME_ROTINA = "verificar_documentos_pontos"


class Command(BaseCommand):
    help = (
        "Notifica responsáveis sobre documentos de pontos prestes a vencer e marca "
        "documentos vencidos devolvendo pontos ativos para pendente_aprovacao."
    )

    def handle(self, *args, **options):
        _ = (args, options)
        with adquirir_lock_rotina(NOME_ROTINA) as adquirido:
            if not adquirido:
                logger.info("Rotina %s já está em execução; encerrando sem duplicar.", NOME_ROTINA)
                self.stdout.write(
                    "Outra instância de verificar_documentos_pontos já está em execução."
                )
                return

            execucao = ExecucaoRotina.objects.create(
                nome_rotina=NOME_ROTINA,
                iniciada_em=timezone.now(),
                resultado=ResultadoRotina.EM_ANDAMENTO,
            )
            try:
                resultado = DocumentoPontoService.processar_vencimentos_diarios()
            except Exception as erro:
                execucao.finalizada_em = timezone.now()
                execucao.resultado = ResultadoRotina.FALHA
                execucao.resumo_erro = str(erro)[:500]
                execucao.save(update_fields=["finalizada_em", "resultado", "resumo_erro"])
                NotificacaoService.alertar_administradores_operacional(
                    nome_rotina=NOME_ROTINA,
                    resumo_tecnico=f"Falha na rotina de documentos de pontos: {str(erro)[:140]}",
                    enviar_email=False,
                )
                logger.exception("Falha sistêmica ao executar rotina %s.", NOME_ROTINA)
                raise

            execucao.finalizada_em = timezone.now()
            execucao.resultado = ResultadoRotina.SUCESSO
            execucao.contadores = {
                "avisos_enviados": resultado.avisos_enviados,
                "documentos_vencidos": resultado.documentos_vencidos,
                "pontos_remetidos_reaprovacao": resultado.pontos_remetidos_reaprovacao,
            }
            execucao.save(update_fields=["finalizada_em", "resultado", "contadores"])

            self.stdout.write(
                "Verificação concluída: "
                f"avisos_enviados={resultado.avisos_enviados}, "
                f"documentos_vencidos={resultado.documentos_vencidos}, "
                f"pontos_remetidos_reaprovacao={resultado.pontos_remetidos_reaprovacao}."
            )

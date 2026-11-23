"""Utilitários de lock distribuído para rotinas agendadas no PostgreSQL (ADR 0014)."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection


def _chave_lock_inteiro(nome_rotina: str) -> int:
    digest = hashlib.sha256(f"remed.rotina.{nome_rotina}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False) & 0x7FFFFFFFFFFFFFFF


@contextmanager
def adquirir_lock_rotina(nome_rotina: str) -> Iterator[bool]:
    """Tenta adquirir um advisory lock por sessão no PostgreSQL sem bloquear."""
    chave = _chave_lock_inteiro(nome_rotina)
    adquirido = False
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [chave])
        linha = cursor.fetchone()
        adquirido = bool(linha and linha[0])
    try:
        yield adquirido
    finally:
        if adquirido:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [chave])

"""Backend de e-mail legível no terminal para desenvolvimento local (ADR 0015).

Evita que `Content-Transfer-Encoding: quoted-printable` quebre URLs longas (> 76 chars)
com `=\\n` ao imprimir e-mails UTF-8 no console durante o desenvolvimento.
"""

from django.core.mail.backends.console import EmailBackend as DjangoConsoleEmailBackend


class ConsoleEmailBackend(DjangoConsoleEmailBackend):
    """Imprime o e-mail decodificado em UTF-8 no terminal sem quebra quoted-printable."""

    def write_message(self, message):
        destinatarios = ", ".join(message.to)
        cabecalhos = [
            f"From: {message.from_email}",
            f"To: {destinatarios}",
            f"Subject: {message.subject}",
        ]
        if message.cc:
            cabecalhos.append(f"Cc: {', '.join(message.cc)}")
        if message.reply_to:
            cabecalhos.append(f"Reply-To: {', '.join(message.reply_to)}")

        bloco = "\n".join(cabecalhos) + "\n\n" + (message.body or "")
        if not bloco.endswith("\n"):
            bloco += "\n"
        self.stream.write(bloco)
        self.stream.write("-" * 79)
        self.stream.write("\n")

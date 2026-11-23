"""Validadores e formatadores puros reutilizáveis entre apps (sem ORM)."""

from datetime import date

from django.utils import timezone

UFS_BRASIL: tuple[tuple[str, str], ...] = (
    ("AC", "AC — Acre"),
    ("AL", "AL — Alagoas"),
    ("AP", "AP — Amapá"),
    ("AM", "AM — Amazonas"),
    ("BA", "BA — Bahia"),
    ("CE", "CE — Ceará"),
    ("DF", "DF — Distrito Federal"),
    ("ES", "ES — Espírito Santo"),
    ("GO", "GO — Goiás"),
    ("MA", "MA — Maranhão"),
    ("MT", "MT — Mato Grosso"),
    ("MS", "MS — Mato Grosso do Sul"),
    ("MG", "MG — Minas Gerais"),
    ("PA", "PA — Pará"),
    ("PB", "PB — Paraíba"),
    ("PR", "PR — Paraná"),
    ("PE", "PE — Pernambuco"),
    ("PI", "PI — Piauí"),
    ("RJ", "RJ — Rio de Janeiro"),
    ("RN", "RN — Rio Grande do Norte"),
    ("RS", "RS — Rio Grande do Sul"),
    ("RO", "RO — Rondônia"),
    ("RR", "RR — Roraima"),
    ("SC", "SC — Santa Catarina"),
    ("SP", "SP — São Paulo"),
    ("SE", "SE — Sergipe"),
    ("TO", "TO — Tocantins"),
)

SIGLAS_UF_VALIDAS: frozenset[str] = frozenset(sigla for sigla, _ in UFS_BRASIL)

IDADE_MINIMA_CADASTRO = 18


def somente_digitos(valor: str) -> str:
    return "".join(ch for ch in (valor or "") if ch.isdigit())


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def validar_cpf(valor: str) -> str:
    digitos = somente_digitos(valor)
    if len(digitos) != 11 or len(set(digitos)) == 1:
        raise ValueError("Informe um CPF válido com 11 dígitos.")

    soma_1 = sum(int(digitos[indice]) * (10 - indice) for indice in range(9))
    dv_1 = (soma_1 * 10) % 11
    dv_1 = 0 if dv_1 == 10 else dv_1

    soma_2 = sum(int(digitos[indice]) * (11 - indice) for indice in range(10))
    dv_2 = (soma_2 * 10) % 11
    dv_2 = 0 if dv_2 == 10 else dv_2

    if dv_1 != int(digitos[9]) or dv_2 != int(digitos[10]):
        raise ValueError("Informe um CPF válido com dígitos verificadores corretos.")

    return digitos


def formatar_cpf(cpf_digitos: str) -> str:
    digitos = somente_digitos(cpf_digitos)
    if len(digitos) != 11:
        return cpf_digitos
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def mascarar_cpf(cpf_digitos: str | None) -> str:
    """Retorna CPF parcialmente oculto no formato 123.***.***-01 (RF004 / RN-04-07)."""
    if not cpf_digitos:
        return "—"
    digitos = somente_digitos(cpf_digitos)
    if len(digitos) != 11:
        return "***.***.***-**"
    return f"{digitos[:3]}.***.***-{digitos[9:]}"


def validar_cep(valor: str) -> str:
    digitos = somente_digitos(valor)
    if len(digitos) != 8:
        raise ValueError("Informe um CEP válido com 8 dígitos (00000-000).")
    return digitos


def formatar_cep(cep_digitos: str) -> str:
    digitos = somente_digitos(cep_digitos)
    if len(digitos) != 8:
        return cep_digitos
    return f"{digitos[:5]}-{digitos[5:]}"


def validar_celular(valor: str) -> str:
    digitos = somente_digitos(valor)
    if len(digitos) not in {10, 11} or len(set(digitos)) == 1:
        raise ValueError("Informe um celular válido com DDD (10 ou 11 dígitos).")
    ddd = int(digitos[:2])
    if ddd < 11 or ddd > 99:
        raise ValueError("Informe um DDD válido para o celular.")
    return digitos


def formatar_celular(celular_digitos: str) -> str:
    digitos = somente_digitos(celular_digitos)
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return celular_digitos


def validar_uf(valor: str) -> str:
    uf = (valor or "").strip().upper()
    if uf not in SIGLAS_UF_VALIDAS:
        raise ValueError("Selecione uma UF brasileira válida.")
    return uf


def validar_maioridade(data_nascimento: date, *, referencia: date | None = None) -> date:
    hoje = referencia if referencia is not None else timezone.localdate()
    if data_nascimento > hoje:
        raise ValueError("A data de nascimento não pode estar no futuro.")

    idade = (
        hoje.year
        - data_nascimento.year
        - ((hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day))
    )
    if idade < IDADE_MINIMA_CADASTRO:
        raise ValueError(
            "Cadastro permitido apenas para maiores de 18 anos. "
            "Menores de 18 anos devem ser representados por um cuidador ou familiar."
        )
    return data_nascimento

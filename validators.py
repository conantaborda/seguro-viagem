"""Regras de validação de nome, CPF e data de nascimento."""
import re
from datetime import date, datetime

import pandas as pd

PARTICULAS = {"de", "da", "do", "das", "dos", "e", "di", "du", "van", "von", "bin", "al"}
NOME_REGEX = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ'’\-\. ]+$")


def so_digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor)) if valor is not None else ""


def normalizar_cpf(valor, completar_zeros: bool = True) -> str:
    """Remove máscara; completa zeros à esquerda (Excel costuma remover)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    d = so_digitos(valor)
    if completar_zeros and d and len(d) < 11:
        d = d.zfill(11)
    return d


def validar_cpf(valor, completar_zeros: bool = True) -> tuple[bool, str]:
    cpf = normalizar_cpf(valor, completar_zeros)
    if not cpf:
        return False, "CPF vazio"
    if len(cpf) != 11:
        return False, f"CPF com {len(cpf)} dígitos (esperado 11)"
    if cpf == cpf[0] * 11:
        return False, "CPF com todos os dígitos iguais"
    for i in (9, 10):
        soma = sum(int(cpf[n]) * (i + 1 - n) for n in range(i))
        dv = (soma * 10 % 11) % 10
        if dv != int(cpf[i]):
            return False, "Dígito verificador inválido"
    return True, ""


def formatar_cpf(valor, completar_zeros: bool = True) -> str:
    c = normalizar_cpf(valor, completar_zeros)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}" if len(c) == 11 else str(valor)


def validar_nome(valor, exigir_sobrenome: bool = True) -> tuple[bool, str]:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return False, "Nome vazio"
    nome = re.sub(r"\s+", " ", str(valor)).strip()
    if not nome:
        return False, "Nome vazio"
    if re.search(r"\d", nome):
        return False, "Nome contém números"
    if not NOME_REGEX.match(nome):
        return False, "Nome contém caracteres inválidos"
    partes = nome.split(" ")
    if exigir_sobrenome and len(partes) < 2:
        return False, "Informe nome e sobrenome"
    if any(len(p.strip(".'’-")) < 2 and p.lower() not in PARTICULAS for p in partes
           if len(partes) > 1 and p.lower() != "e"):
        # iniciais isoladas (ex.: "J Silva") são suspeitas
        return False, "Nome contém abreviação/inicial isolada"
    if re.search(r"(.)\1{3,}", nome.lower()):
        return False, "Nome com caracteres repetidos em excesso"
    return True, ""


def parse_data(valor) -> date | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (datetime, pd.Timestamp)):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)):  # serial do Excel
        try:
            return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(valor))).date()
        except Exception:
            return None
    texto = str(valor).strip()
    texto = re.split(r"[ T]", texto)[0]  # ignora horário ("1990-03-15 00:00:00")
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def validar_data_nascimento(valor, idade_max: int = 120, hoje: date | None = None) -> tuple[bool, str]:
    hoje = hoje or date.today()
    if valor is None or (isinstance(valor, float) and pd.isna(valor)) or str(valor).strip() == "":
        return False, "Data vazia"
    d = parse_data(valor)
    if d is None:
        return False, "Data em formato inválido"
    if d > hoje:
        return False, "Data no futuro"
    idade = hoje.year - d.year - ((hoje.month, hoje.day) < (d.month, d.day))
    if idade > idade_max:
        return False, f"Idade acima de {idade_max} anos"
    return True, ""

"""Separa e renomeia vouchers GTA em PDF.

Cada voucher começa numa página "VOUCHER DE ASSISTÊNCIA DE VIAGEM", que traz "Voucher: nº" e "Nome:".
As páginas seguintes sem esse cabeçalho (bilhete, encarte de benefícios) pertencem ao mesmo voucher.
Um PDF com vários vouchers é separado em um PDF por voucher.

Nome do arquivo:  NOME_INICIOaFIM_PLANO.pdf   ex.: FABIO GARCIA_22.11.26a30.11.26_10487-NACIONAL 30.000.pdf
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime

import pypdf

# --------------------------------------------------------------------------- leitura dos campos
_RE_VOUCHER = re.compile(r"Voucher\s*:\s*(\d+)")
_RE_NOME_ROTULO = re.compile(r"Nome\s*:")
_RE_NOME = re.compile(r"Nome\s*:\s*(.+?)(?=\s+(?:Documento|Dt\.?\s*Nasc|Endere[cç]o)\s*:)")
_RE_PLANO = re.compile(
    r"Plano\s*:\s*(.+?)(?=\s+(?:Forma\s+de\s+pagamento|Periodicidade|Data\s+de|Valor\s+Total)\b)")
# "." tolera acento/sem acento (início/inicio, término/termino, vigência/vigencia)
_RE_INICIO = re.compile(r"Data\s+de\s+in.cio\s+da\s+vig.ncia\s*:\s*(\d{1,2}/\d{1,2}/\d{4})")
_RE_FIM = re.compile(r"Data\s+de\s+t.rmino\s+da\s+vig.ncia\s*:\s*(\d{1,2}/\d{1,2}/\d{4})")


@dataclass
class Voucher:
    arquivo: str                      # nome do PDF de origem
    indice_arquivo: int = 0           # posição do PDF na lista enviada
    paginas: list[int] = field(default_factory=list)  # índices (base 0) das páginas no PDF de origem
    numero: str = ""
    nome: str = ""
    inicio: str = ""                  # DD/MM/AAAA, como no voucher
    fim: str = ""
    plano: str = ""
    avisos: list[str] = field(default_factory=list)

    @property
    def intervalo_paginas(self) -> str:
        return intervalo(self.paginas)


def intervalo(paginas: list[int]) -> str:
    """[0,1,2,3,4] -> '1-5'; [0,2] -> '1, 3'."""
    if not paginas:
        return ""
    partes, ini, ant = [], paginas[0], paginas[0]
    for p in paginas[1:] + [None]:
        if p is not None and p == ant + 1:
            ant = p
            continue
        partes.append(f"{ini + 1}" if ini == ant else f"{ini + 1}-{ant + 1}")
        if p is not None:
            ini = ant = p
    return ", ".join(partes)


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFC", (texto or "").replace("\xa0", " "))
    return re.sub(r"\s+", " ", texto).strip()


def _eh_inicio(texto: str) -> bool:
    return bool(_RE_VOUCHER.search(texto) and _RE_NOME_ROTULO.search(texto))


def _abrir(conteudo: bytes) -> pypdf.PdfReader:
    reader = pypdf.PdfReader(io.BytesIO(conteudo))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF protegido por senha")
    return reader


def analisar_pdf(arquivo: str, conteudo: bytes, indice: int = 0) -> list[Voucher]:
    """Um PDF -> lista de vouchers (um por cabeçalho "Voucher: nº" encontrado)."""
    try:
        reader = _abrir(conteudo)
        textos = [_normalizar(p.extract_text()) for p in reader.pages]
    except Exception as e:  # PDF corrompido, protegido, não é PDF...
        return [Voucher(arquivo, indice, avisos=[f"Não foi possível abrir o PDF ({e})"])]
    if not textos:
        return [Voucher(arquivo, indice, avisos=["PDF sem páginas"])]

    grupos: list[list[int]] = []
    for i, t in enumerate(textos):
        if _eh_inicio(t) or not grupos:
            grupos.append([i])
        else:
            grupos[-1].append(i)

    vouchers = []
    for g in grupos:
        inicio_txt, resto = textos[g[0]], " ".join(textos[i] for i in g[1:])

        def achar(rx):
            for fonte in (inicio_txt, resto):  # a 1ª página manda; o bilhete é reserva
                m = rx.search(fonte)
                if m:
                    return m.group(1).strip()
            return ""

        m_num = _RE_VOUCHER.search(inicio_txt)
        v = Voucher(arquivo, indice, g, numero=m_num.group(1) if m_num else "",
                    nome=achar(_RE_NOME), inicio=achar(_RE_INICIO), fim=achar(_RE_FIM), plano=achar(_RE_PLANO))
        if not any(textos[i] for i in g):
            v.avisos.append("PDF sem texto legível (imagem?): preencha os campos manualmente")
        else:
            faltam = [rot for rot, val in (("nome", v.nome), ("início da vigência", v.inicio),
                                           ("término da vigência", v.fim), ("plano", v.plano)) if not val]
            if faltam:
                v.avisos.append("Não encontrei: " + ", ".join(faltam))
            if not m_num:
                v.avisos.append("Cabeçalho do voucher não encontrado nesta(s) página(s)")
        vouchers.append(v)
    return vouchers


def analisar_pdfs(arquivos: list[tuple[str, bytes]]) -> list[Voucher]:
    """Vários PDFs -> vouchers; marca como repetido o mesmo nº de voucher que aparece mais de uma vez."""
    todos: list[Voucher] = []
    for i, (nome, conteudo) in enumerate(arquivos):
        todos += analisar_pdf(nome, conteudo, i)
    vistos: set[str] = set()
    for v in todos:
        if v.numero:
            if v.numero in vistos:
                v.avisos.append(f"Voucher {v.numero} repetido (já aparece em outro PDF/trecho)")
            vistos.add(v.numero)
    return todos


# --------------------------------------------------------------------------- nome do arquivo
_PROIBIDOS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def data_curta(valor: str) -> str | None:
    """'22/11/2026' -> '22.11.26'. None se não for uma data que exista."""
    m = re.fullmatch(r"\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})\s*", valor or "")
    if not m:
        return None
    d, mes, ano = int(m[1]), int(m[2]), int(m[3])
    if ano < 100:
        ano += 2000
    try:
        datetime(ano, mes, d)
    except ValueError:
        return None
    return f"{d:02d}.{mes:02d}.{ano % 100:02d}"


def _data(valor: str) -> datetime | None:
    m = re.fullmatch(r"\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})\s*", valor or "")
    if not m:
        return None
    ano = int(m[3]) + (2000 if int(m[3]) < 100 else 0)
    try:
        return datetime(ano, int(m[2]), int(m[1]))
    except ValueError:
        return None


def _limpar(texto: str, sem_acentos: bool) -> str:
    s = unicodedata.normalize("NFC", str(texto or ""))
    if sem_acentos:
        s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
        s = s.encode("ascii", "ignore").decode("ascii")
    s = _PROIBIDOS.sub("-", s)
    return " ".join(s.split())


def montar_nome_arquivo(nome: str, inicio: str, fim: str, plano: str,
                        sem_acentos: bool = True) -> tuple[str, list[str], list[str]]:
    """(nome do arquivo com .pdf, erros, avisos). Com erro, o nome vem vazio."""
    erros, avisos = [], []
    n, p = _limpar(nome, sem_acentos), _limpar(plano, sem_acentos)
    ini, fi = data_curta(inicio), data_curta(fim)
    if not n:
        erros.append("Nome vazio")
    if not p:
        erros.append("Plano vazio")
    if not ini:
        erros.append("Início da vigência inválido (use DD/MM/AAAA)")
    if not fi:
        erros.append("Término da vigência inválido (use DD/MM/AAAA)")
    if erros:
        return "", erros, avisos
    d_ini, d_fim = _data(inicio), _data(fim)
    if d_ini and d_fim and d_fim < d_ini:
        avisos.append("Término anterior ao início da vigência")
    base = f"{n}_{ini}a{fi}_{p}"[:180].rstrip(" .")
    return f"{base}.pdf", erros, avisos


def nomes_unicos(nomes: list[str]) -> list[str]:
    """Evita nomes repetidos (sem diferenciar maiúsculas, como no Windows): 'X.pdf', 'X (2).pdf'... Vazios ficam vazios."""
    usados: set[str] = set()
    saida = []
    for nome in nomes:
        if not nome:
            saida.append(nome)
            continue
        base, ext = nome[:-4], nome[-4:]
        candidato, k = nome, 1
        while candidato.lower() in usados:
            k += 1
            candidato = f"{base} ({k}){ext}"
        usados.add(candidato.lower())
        saida.append(candidato)
    return saida


# --------------------------------------------------------------------------- saída
def dividir_pdf(conteudo: bytes, paginas: list[int]) -> bytes:
    """PDF só com as páginas indicadas (base 0). Se for o PDF inteiro, devolve o original intacto."""
    reader = _abrir(conteudo)
    if paginas == list(range(len(reader.pages))):
        return conteudo
    writer = pypdf.PdfWriter()
    for i in paginas:
        writer.add_page(reader.pages[i])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def gerar_zip(itens: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:  # PDFs já são comprimidos
        for nome, dados in itens:
            z.writestr(nome, dados)
    return buf.getvalue()

"""Detecção automática das colunas de uma planilha e conversão para o modelo de emissão.

Fluxo:
  ler_arquivo_bruto -> detectar_linha_cabecalho -> montar_df -> detectar_mapeamento -> converter -> para_csv
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from validators import (
    parse_data,
    so_digitos,
    validar_cpf,
    validar_data_nascimento,
    validar_nome,
)

# --------------------------------------------------------------------------- modelo
COLUNAS_MODELO = [
    "Pax (nome e sobrenome)",
    "Data de Nascimento (DD/MM/AAAA)",
    "CPF (000.000.000.00)",
    "E-mail",
    "Celular (00-000000000)",
    "cep (00000-000)",
    "Rua",
    "Numero",
    "Bairro",
    "Complemento",
    "Cidade",
    "UF",
    "Sexo",
    "file",
    "grupo",
]
CAMPOS = [
    "nome", "nascimento", "cpf", "email", "celular", "cep", "rua", "numero",
    "bairro", "complemento", "cidade", "uf", "sexo", "file", "grupo",
]
ROTULO = dict(zip(CAMPOS, COLUNAS_MODELO))

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}

FORMATOS_CPF = {
    "modelo": "000.000.000.00  (igual ao cabeçalho do modelo)",
    "padrao": "000.000.000-00  (padrão)",
    "numeros": "00000000000  (somente números)",
}


# --------------------------------------------------------------------------- utilidades
def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def sem_acento_maiusculo(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).upper()


_SUBST_ASCII = str.maketrans({
    "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...", "\u00a0": " ",
    "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
})


def corrigir_mojibake(s: str) -> str:
    """Desfaz texto UTF-8 lido como ANSI ("SÃ£o Paulo" -> "São Paulo"); só age se o resultado for UTF-8 válido."""
    if "Ã" not in s and "Â" not in s:
        return s
    for enc in ("cp1252", "latin-1"):
        try:
            return s.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return s


def limpar_texto_csv(valor) -> str:
    """Texto seguro para o CSV do modelo: só ASCII, sem acentos, sem ';' nem quebras de linha."""
    s = "" if valor is None else str(valor)
    s = corrigir_mojibake(s).translate(_SUBST_ASCII)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.replace(";", ",")
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", s)
    return " ".join(s.split())


def letra_coluna(i: int) -> str:
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _tem_valor(v) -> bool:
    if v is None:
        return False
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        pass
    return str(v).strip() != ""


def _txt(v) -> str:
    if not _tem_valor(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).split())


# --------------------------------------------------------------------------- leitura
def ler_csv_bruto(conteudo: bytes) -> pd.DataFrame:
    texto = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        delim = csv.Sniffer().sniff(texto[:5000], delimiters=";,\t|").delimiter
    except csv.Error:
        delim = ";"
    linhas = list(csv.reader(io.StringIO(texto), delimiter=delim))
    n = max((len(l) for l in linhas), default=0)
    linhas = [l + [None] * (n - len(l)) for l in linhas]
    df = pd.DataFrame(linhas, dtype=object)
    return df.where(df != "", None)


def ler_arquivo_bruto(conteudo: bytes, nome_arquivo: str) -> dict[str, pd.DataFrame]:
    """Devolve {aba: DataFrame sem cabeçalho (header=None)}. CSV vira uma única aba."""
    if nome_arquivo.lower().endswith(".csv"):
        return {"CSV": ler_csv_bruto(conteudo)}
    return pd.read_excel(io.BytesIO(conteudo), sheet_name=None, header=None, dtype=object)


# --------------------------------------------------------------------------- cabeçalhos
# (sinônimos fortes, sinônimos fracos)
SINONIMOS = {
    "nome": (["nome completo", "nome", "pax", "passageiro", "nome e sobrenome", "nome do passageiro", "viajante"], []),
    "nascimento": (["data de nascimento", "nascimento", "data nasc", "dt nasc", "dtnasc", "nasc",
                    "aniversario", "birth", "birthdate", "dob"], []),
    "cpf": (["cpf"], ["documento", "doc"]),
    "email": (["email", "e mail", "mail"], []),
    "celular": (["celular", "telefone", "fone", "whatsapp", "cel", "tel", "mobile"], ["contato"]),
    "cep": (["cep", "codigo postal"], []),
    "rua": (["rua", "logradouro", "endereco", "avenida"], []),
    "numero": (["numero", "num", "nro", "nr"], []),
    "bairro": (["bairro", "distrito"], []),
    "complemento": (["complemento", "compl"], []),
    "cidade": (["cidade", "municipio", "localidade"], []),
    "uf": (["uf", "estado", "sigla"], []),
    "sexo": (["sexo", "genero"], []),
    "file": (["file", "pnr", "localizador", "reserva"], []),
    "grupo": (["grupo", "turma", "equipe"], []),
}
# palavras que, junto de um sinônimo parcial, indicam que a coluna é OUTRA coisa
EXCLUSOES = {
    "nome": {"mae", "pai", "empresa", "responsavel", "companhia", "aeroporto", "hotel", "contato",
             "razao", "fantasia", "cia", "arquivo", "evento", "curso", "escola", "unidade"},
    "numero": {"cpf", "cep", "celular", "telefone", "fone", "documento", "rg", "cartao", "voo",
               "passaporte", "matricula", "protocolo", "contato", "whatsapp", "file", "pnr", "reserva"},
    "cidade": {"nascimento", "natal", "aeroporto", "origem", "destino"},
    "uf": {"civil", "nascimento", "natal", "aeroporto"},
    "rua": {"email", "mail", "aeroporto", "ip"},
}


def score_cabecalho(cabecalho, campo: str) -> int:
    if not isinstance(cabecalho, str):
        return 0
    h = norm(cabecalho)
    if not h:
        return 0
    toks, hj = h.split(), h.replace(" ", "")
    fortes, fracos = SINONIMOS[campo]
    melhor = 0
    for lista, base in ((fortes, 80), (fracos, 50)):
        for s in lista:
            sn = norm(s)
            sj = sn.replace(" ", "")
            if h == sn or hj == sj:
                melhor = max(melhor, 100 if base == 80 else 50)
            elif len(sj) <= 4:  # sinônimos curtos só valem como palavra inteira
                if all(t in toks for t in sn.split()):
                    melhor = max(melhor, base)
            elif sj in hj:
                melhor = max(melhor, base)
    if melhor and melhor < 100 and EXCLUSOES.get(campo, set()).intersection(toks):
        return 0
    return melhor


# --------------------------------------------------------------------------- conteúdo
_RE_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_RE_CPF_FMT = re.compile(r"\d{3}\.\d{3}\.\d{3}[-.]\d{2}")
_RE_DATA = re.compile(r"\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}(\s+\d{1,2}:\d{2}(:\d{2})?)?")
_RE_CEP = re.compile(r"\d{5}-?\d{3}")
_RE_NOME = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ'’\-\. ]+")
_SEXO = {"m", "f", "masculino", "feminino", "masc", "fem", "homem", "mulher", "male", "female"}


def eh_email(v) -> bool:
    return bool(_RE_EMAIL.fullmatch(_txt(v)))


def eh_cpf(v) -> bool:
    t = _txt(v)
    if _RE_CPF_FMT.fullmatch(t):
        return True
    return t.isdigit() and 9 <= len(t) <= 11 and validar_cpf(t)[0]


def eh_celular(v) -> bool:
    t = _txt(v)
    if not t or _RE_CPF_FMT.fullmatch(t) or "@" in t or "/" in t:
        return False
    d = so_digitos(t)
    if len(d) >= 12 and d.startswith("55"):
        d = d[2:]
    if len(d) in (11, 12) and d.startswith("0"):
        d = d[1:]
    if len(d) not in (10, 11) or int(d[:2]) < 11:
        return False
    return d[2] == "9" if len(d) == 11 else d[2] in "2345678"


def eh_data(v) -> bool:
    if isinstance(v, (datetime, date)):  # pd.Timestamp é subclasse de datetime
        d = v.date() if isinstance(v, datetime) else v
    else:
        t = _txt(v)
        if not _RE_DATA.fullmatch(t):
            return False
        d = parse_data(t)
    return d is not None and 1900 <= d.year <= date.today().year


def eh_cep(v) -> bool:
    return bool(_RE_CEP.fullmatch(_txt(v)))


def eh_uf(v) -> bool:
    return _txt(v).upper() in UFS


def eh_sexo(v) -> bool:
    return norm(_txt(v)) in _SEXO


def eh_nome(v) -> bool:
    t = _txt(v)
    return bool(_RE_NOME.fullmatch(t)) and len(t.split()) >= 2


CONTEUDO = {
    "nome": eh_nome, "nascimento": eh_data, "cpf": eh_cpf, "email": eh_email,
    "celular": eh_celular, "cep": eh_cep, "uf": eh_uf, "sexo": eh_sexo,
}


def _amostra(serie: pd.Series, n: int = 200) -> list:
    return [v for v in serie.tolist() if _tem_valor(v)][:n]


def score_conteudo(valores: list, campo: str) -> int:
    if not valores or campo not in CONTEUDO:
        return 0
    fn = CONTEUDO[campo]
    frac = sum(1 for v in valores if fn(v)) / len(valores)
    if frac < 0.6:  # abaixo disso é ruído
        return 0
    pts = round(frac * 100)
    return min(pts, 80) if campo == "nome" else pts  # nome é fraco: muita coisa parece nome


# --------------------------------------------------------------------------- estrutura da planilha
def detectar_linha_cabecalho(raw: pd.DataFrame, max_linhas: int = 25) -> int:
    """Índice (base 0) da linha de cabeçalho, ou -1 se a planilha não tem cabeçalho."""
    melhor_n, melhor_i = 0, -1
    for i in range(min(max_linhas, len(raw))):
        campos = set()
        for cel in raw.iloc[i].tolist():
            if not isinstance(cel, str):
                continue
            for campo in CAMPOS:
                if score_cabecalho(cel, campo) >= 80:
                    campos.add(campo)
                    break
        if len(campos) > melhor_n:
            melhor_n, melhor_i = len(campos), i
    if melhor_n >= 2:
        return melhor_i
    if len(raw):
        sinais = sum(1 for c in raw.iloc[0].tolist()
                     if _tem_valor(c) and (eh_cpf(c) or eh_data(c) or eh_email(c)))
        if sinais >= 2:
            return -1
    return 0


def montar_df(raw: pd.DataFrame, linha_cab: int) -> tuple[pd.DataFrame, list[int]]:
    """Aplica o cabeçalho, remove linhas vazias e devolve também o nº da linha no Excel de cada registro."""
    if linha_cab >= 0:
        nomes = []
        for j, c in enumerate(raw.iloc[linha_cab].tolist()):
            nomes.append(" ".join(c.split()) if isinstance(c, str) and c.strip() else f"Coluna {letra_coluna(j)}")
        dados, primeira = raw.iloc[linha_cab + 1:], linha_cab + 2
    else:
        nomes = [f"Coluna {letra_coluna(j)}" for j in range(raw.shape[1])]
        dados, primeira = raw, 1
    dados = dados.copy()
    dados.columns = nomes
    linhas = [primeira + i for i in range(len(dados))]
    manter = [any(_tem_valor(x) for x in row) for row in dados.itertuples(index=False)]
    dados = dados[manter].reset_index(drop=True)
    return dados, [l for l, m in zip(linhas, manter) if m]


# --------------------------------------------------------------------------- mapeamento
@dataclass
class Deteccao:
    coluna: int | None
    score: float = 0
    cabecalho: int = 0
    conteudo: int = 0

    @property
    def confianca(self) -> str:
        if self.coluna is None:
            return "nenhuma"
        return "alta" if self.score >= 110 else "média" if self.score >= 70 else "baixa"

    @property
    def motivo(self) -> str:
        if self.coluna is None:
            return "não encontrada"
        if self.cabecalho and self.conteudo:
            return "cabeçalho + conteúdo"
        return "cabeçalho" if self.cabecalho else "conteúdo"


def detectar_mapeamento(df: pd.DataFrame, limiar: float = 45) -> dict[str, Deteccao]:
    amostras = [_amostra(df.iloc[:, j]) for j in range(df.shape[1])]
    cand = []
    for campo in CAMPOS:
        for j in range(df.shape[1]):
            h = score_cabecalho(df.columns[j], campo)
            c = score_conteudo(amostras[j], campo)
            s = h + 0.7 * c
            if s >= limiar:
                cand.append((s, campo, j, h, c))
    cand.sort(key=lambda x: (-x[0], CAMPOS.index(x[1]), x[2]))
    usados_c, res = set(), {}
    for s, campo, j, h, c in cand:
        if campo in res or j in usados_c:
            continue
        res[campo] = Deteccao(j, s, h, c)
        usados_c.add(j)
    for campo in CAMPOS:
        res.setdefault(campo, Deteccao(None))
    return res


def pontuar(mapa: dict[str, Deteccao]) -> float:
    return sum(d.score for d in mapa.values())


# --------------------------------------------------------------------------- conversão
def _fmt_cpf(c11: str, formato: str) -> str:
    if formato == "numeros":
        return c11
    sep = "-" if formato == "padrao" else "."
    return f"{c11[:3]}.{c11[3:6]}.{c11[6:9]}{sep}{c11[9:]}"


def normalizar_celular(v) -> tuple[str, bool]:
    t = _txt(v)
    d = so_digitos(t)
    if len(d) >= 12 and d.startswith("55"):
        d = d[2:]
    if len(d) in (11, 12) and d.startswith("0"):
        d = d[1:]
    ok = len(d) in (10, 11) and int(d[:2]) >= 11 and (len(d) == 10 or d[2] == "9")
    return (f"{d[:2]}-{d[2:]}" if ok else t), ok


def normalizar_cep(v) -> tuple[str, bool]:
    t = _txt(v)
    d = so_digitos(t)
    if len(d) == 7:
        d = d.zfill(8)
    return (f"{d[:5]}-{d[5:]}" if len(d) == 8 else t), len(d) == 8


def email_valido(v) -> bool:
    return bool(_RE_EMAIL.fullmatch(_txt(v)))


def converter(
    df: pd.DataFrame,
    linhas: list[int],
    mapa: dict[str, int | None],
    *,
    formato_cpf: str = "modelo",
    nome_maiusculo: bool = False,
    completar_zeros: bool = True,
    exigir_sobrenome: bool = True,
    idade_max: int = 120,
    marcar_duplicados: bool = True,
    file_fixo: str = "",
    grupo_fixo: str = "",
    # --- padrões. Modos: "vazios" (só onde a planilha não tem o dado) ou "todas" (todas as linhas)
    cep_padrao: str = "",
    cep_modo: str = "vazios",
    endereco_padrao: dict | None = None,  # rua, bairro, cidade, uf (e complemento) do CEP padrão
    numero_padrao: str = "",
    complemento_padrao: str = "",
    email_padrao: str = "",
    email_modo: str = "vazios",
    celular_padrao: str = "",
    celular_modo: str = "vazios",
    # --- consulta de CEP: função(cep 8 dígitos) -> dict | None; pode levantar exceção se a API cair
    buscar_cep=None,
    completar_pelo_cep: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devolve (saida no formato do modelo, relatório de validação). `mapa`: campo -> posição da coluna ou None."""

    def bruto(campo, i):
        c = mapa.get(campo)
        return None if c is None else df.iat[i, c]

    # padrões já normalizados (padrão inválido é ignorado; a interface avisa o operador)
    cep_padrao_fmt, cep_padrao_ok = normalizar_cep(cep_padrao) if _tem_valor(cep_padrao) else ("", False)
    end_padrao = endereco_padrao or {}
    email_padrao = _txt(email_padrao).lower()
    if email_padrao and not _RE_EMAIL.fullmatch(email_padrao):
        email_padrao = ""
    cel_padrao, cel_padrao_ok = normalizar_celular(celular_padrao) if _tem_valor(celular_padrao) else ("", False)

    memo: dict[str, tuple] = {}
    estado = {"falhas": 0}

    def consultar(cep_fmt: str):
        """(info, erro): info=None e erro=None significa CEP inexistente."""
        d = so_digitos(cep_fmt)
        if d in memo:
            return memo[d]
        if estado["falhas"] >= 3:  # API fora do ar: para de tentar
            return None, "Consulta de CEP indisponível"
        try:
            r = (buscar_cep(d), None)
        except Exception:
            estado["falhas"] += 1
            r = (None, "Falha ao consultar o CEP na API")
        memo[d] = r
        return r

    saida, rel, cpfs = [], [], []
    for i in range(len(df)):
        avisos = []

        # --- núcleo: nome, nascimento, CPF
        v_nome = bruto("nome", i)
        ok_n, e_n = validar_nome(v_nome, exigir_sobrenome)
        nome = _txt(v_nome)
        if nome_maiusculo:
            nome = sem_acento_maiusculo(nome)

        v_nasc = bruto("nascimento", i)
        ok_d, e_d = validar_data_nascimento(v_nasc, idade_max)
        d = parse_data(v_nasc)
        nasc = d.strftime("%d/%m/%Y") if d else _txt(v_nasc)

        v_cpf = bruto("cpf", i)
        ok_c, e_c = validar_cpf(v_cpf, completar_zeros)
        if ok_c:
            c11 = so_digitos(_txt(v_cpf)).zfill(11) if completar_zeros else so_digitos(_txt(v_cpf))
            cpf, cpf_norm = _fmt_cpf(c11, formato_cpf), c11
        else:
            cpf, cpf_norm = _txt(v_cpf), None
        cpfs.append(cpf_norm)

        # --- contato: padrão só onde vazio, ou em todas as linhas
        email = _txt(bruto("email", i)).lower()
        if email_padrao and (email_modo == "todas" or not email):
            email = email_padrao
        elif email and not _RE_EMAIL.fullmatch(email):
            avisos.append("E-mail em formato inválido")

        celular, v_cel = "", bruto("celular", i)
        if cel_padrao_ok and (celular_modo == "todas" or not _tem_valor(v_cel)):
            celular = cel_padrao
        elif _tem_valor(v_cel):
            celular, ok_cel = normalizar_celular(v_cel)
            if not ok_cel:
                avisos.append("Celular fora do padrão DDD + número")

        # --- CEP e endereço
        v_cep = bruto("cep", i)
        tem_cep = _tem_valor(v_cep)
        usar_padrao = cep_padrao_ok and (cep_modo == "todas" or (cep_modo == "vazios" and not tem_cep))
        origem_end = "planilha"
        if usar_padrao:
            cep = cep_padrao_fmt
            end = {k: _txt(end_padrao.get(k, "")) for k in ("rua", "bairro", "cidade", "uf")}
            end["uf"] = end["uf"].upper()
            numero = _txt(numero_padrao)
            complemento = _txt(complemento_padrao) or _txt(end_padrao.get("complemento", ""))
            origem_end = "CEP padrão"
        else:
            end = {k: _txt(bruto(k, i)) for k in ("rua", "bairro", "cidade", "uf")}
            end["uf"] = end["uf"].upper()
            numero, complemento = _txt(bruto("numero", i)), _txt(bruto("complemento", i))
            cep = ""
            if tem_cep:
                cep, ok_cep = normalizar_cep(v_cep)
                if not ok_cep:
                    avisos.append("CEP fora do padrão (8 dígitos)")
                elif buscar_cep is not None:
                    info, erro = consultar(cep)
                    if erro:
                        avisos.append(erro)
                    elif info is None:
                        avisos.append("CEP não encontrado nas APIs de consulta")
                    else:
                        if completar_pelo_cep:
                            completou = False
                            for k in end:
                                if not end[k] and info.get(k):
                                    end[k] = info[k].upper() if k == "uf" else info[k]
                                    completou = True
                            if completou:
                                origem_end = "completado pelo CEP"
                        if end["uf"] and info.get("uf") and end["uf"] != info["uf"].upper():
                            avisos.append("UF diverge do CEP")
                        if end["cidade"] and info.get("cidade") and norm(end["cidade"]) != norm(info["cidade"]):
                            avisos.append("Cidade diverge do CEP")
        if end["uf"] and end["uf"] not in UFS:
            avisos.append("UF não reconhecida")

        saida.append(dict(zip(COLUNAS_MODELO, map(limpar_texto_csv, [
            nome, nasc, cpf, email, celular, cep,
            end["rua"], numero, end["bairro"], complemento, end["cidade"], end["uf"],
            _txt(bruto("sexo", i)),
            _txt(bruto("file", i)) if mapa.get("file") is not None else file_fixo,
            _txt(bruto("grupo", i)) if mapa.get("grupo") is not None else grupo_fixo,
        ]))))
        rel.append({
            "Linha": linhas[i], "Nome": nome, "CPF": cpf, "Data de Nascimento": nasc,
            "Nome OK": ok_n, "CPF OK": ok_c, "Data OK": ok_d,
            "Erro Nome": e_n, "Erro CPF": e_c, "Erro Data": e_d, "Avisos": "; ".join(avisos),
            "Origem do endereço": origem_end,
        })

    saida_df = pd.DataFrame(saida, columns=COLUNAS_MODELO, dtype=object)
    rel_df = pd.DataFrame(rel)

    if marcar_duplicados and len(rel_df):
        serie = pd.Series(cpfs, dtype=object)
        dup = serie.notna() & serie.duplicated(keep=False)
        rel_df.loc[dup, "Erro CPF"] = "CPF duplicado na planilha"
        rel_df.loc[dup, "CPF OK"] = False

    if len(rel_df):
        rel_df["Status"] = (rel_df["Nome OK"] & rel_df["CPF OK"] & rel_df["Data OK"]).map(
            {True: "Válido", False: "Inválido"})
    else:
        rel_df["Status"] = []
    return saida_df, rel_df


def para_csv(saida: pd.DataFrame, encoding: str = "utf-8") -> bytes:
    """CSV no padrão do modelo: separador ';', quebra de linha CRLF e texto só em ASCII (sem acentos)."""
    limpo = saida.fillna("").astype(str).apply(lambda col: col.map(limpar_texto_csv))
    texto = limpo.to_csv(sep=";", index=False, lineterminator="\r\n")
    return texto.encode(encoding, errors="replace")

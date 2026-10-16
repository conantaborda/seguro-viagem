"""Testes do mapeamento/conversão. Todos os dados são fictícios."""
import io
from datetime import datetime

import pandas as pd
from openpyxl import Workbook

from mapper import (
    COLUNAS_MODELO, converter, detectar_linha_cabecalho, detectar_mapeamento,
    ler_arquivo_bruto, montar_df, para_csv,
)


def cpf_valido(base9: str) -> str:
    n = [int(c) for c in base9]
    for _ in range(2):
        n.append((sum(d * (len(n) + 1 - i) for i, d in enumerate(n)) * 10 % 11) % 10)
    return "".join(map(str, n))


def fmt(c): return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"


C1, C2, C3 = cpf_valido("123456789"), cpf_valido("987654321"), cpf_valido("012345678")


def xlsx_bytes(linhas):
    wb = Workbook(); ws = wb.active
    for l in linhas:
        ws.append(l)
    b = io.BytesIO(); wb.save(b); return b.getvalue()


def processar(conteudo, nome):
    abas = ler_arquivo_bruto(conteudo, nome)
    raw = next(iter(abas.values()))
    li = detectar_linha_cabecalho(raw)
    df, linhas = montar_df(raw, li)
    det = detectar_mapeamento(df)
    mapa = {k: d.coluna for k, d in det.items()}
    return df, linhas, det, mapa, li


def test_layout_do_print_com_titulo_acima():
    dados = [
        ["Lista de passageiros - turma 1", None, None, None, None, None],
        [None] * 6,
        ["Nome Completo", "Data de nascimento", "CPF", "E-mail técnico", "Celular Técnico", "Aeroporto mais próximo"],
        ["Ana  Souza Lima", datetime(2009, 8, 5), fmt(C1), "tec@exemplo.org", "(18) 98120-1061", "Aeroporto Estadual de Presidente Prudente (PPB)"],
        ["Bruno Alves de Oliveira", datetime(2008, 12, 10), fmt(C2), "tec@exemplo.org", "(18) 98120-1061", "Aeroporto Estadual de Presidente Prudente (PPB)"],
    ]
    df, linhas, det, mapa, li = processar(xlsx_bytes(dados), "a.xlsx")
    assert li == 2 and linhas == [4, 5]
    assert mapa["nome"] == 0 and mapa["nascimento"] == 1 and mapa["cpf"] == 2
    assert mapa["email"] == 3 and mapa["celular"] == 4
    assert mapa["cidade"] is None and mapa["rua"] is None  # aeroporto não deve ser mapeado
    saida, rel = converter(df, linhas, mapa, file_fixo="F1", grupo_fixo="G1")
    assert list(saida.columns) == COLUNAS_MODELO
    r = saida.iloc[0]
    assert r["Pax (nome e sobrenome)"] == "Ana Souza Lima"
    assert r["Data de Nascimento (DD/MM/AAAA)"] == "05/08/2009"
    assert r["CPF (000.000.000.00)"] == f"{C1[:3]}.{C1[3:6]}.{C1[6:9]}.{C1[9:]}"
    assert r["Celular (00-000000000)"] == "18-981201061"
    assert r["file"] == "F1" and r["grupo"] == "G1"
    assert list(rel["Status"]) == ["Válido", "Válido"]


def test_colunas_embaralhadas_e_formatos_do_excel():
    dados = [
        ["Aeroporto", "CPF", "Telefone", "Passageiro", "Nascimento", "Email", "UF", "CEP"],
        ["PPB", int(C3), "5518981201061", "Carla Mendes", "1990-03-15 00:00:00", "CARLA@X.COM", "sp", 19015000],
        ["PPB", fmt(C2), "(11) 3222-1234", "Diego", "31/02/1990", "ruim", "XX", "123"],
    ]
    df, linhas, det, mapa, li = processar(xlsx_bytes(dados), "b.xlsx")
    assert (mapa["cpf"], mapa["celular"], mapa["nome"], mapa["nascimento"], mapa["email"]) == (1, 2, 3, 4, 5)
    assert mapa["uf"] == 6 and mapa["cep"] == 7
    saida, rel = converter(df, linhas, mapa, formato_cpf="padrao")
    a = saida.iloc[0]
    assert a["CPF (000.000.000.00)"] == fmt(C3)         # zero à esquerda recuperado
    assert a["Celular (00-000000000)"] == "18-981201061"  # +55 removido
    assert a["E-mail"] == "carla@x.com" and a["UF"] == "SP" and a["cep (00000-000)"] == "19015-000"
    assert rel.iloc[0]["Status"] == "Válido"
    assert rel.iloc[1]["Status"] == "Inválido"
    assert "Diego" not in rel.iloc[1]["Erro Nome"] and rel.iloc[1]["Erro Nome"] == "Informe nome e sobrenome"
    assert rel.iloc[1]["Erro Data"] == "Data em formato inválido"
    assert "E-mail" in rel.iloc[1]["Avisos"] and "UF" in rel.iloc[1]["Avisos"]


def test_sem_cabecalho_csv_detecta_pelo_conteudo():
    csv = (f"Maria Souza Lima;{fmt(C1)};12/05/1985;maria@x.com\n"
           f"João Pedro Alves;{fmt(C2)};01/01/1970;joao@x.com\n").encode()
    df, linhas, det, mapa, li = processar(csv, "c.csv")
    assert li == -1 and linhas == [1, 2]
    assert (mapa["nome"], mapa["cpf"], mapa["nascimento"], mapa["email"]) == (0, 1, 2, 3)


def test_cabecalhos_inuteis_e_cpf_duplicado():
    dados = [["c1", "c2", "c3"],
             ["Ana Souza", fmt(C1), "05/08/2009"],
             ["Ana Souza Dois", fmt(C1), "05/08/2009"]]
    df, linhas, det, mapa, li = processar(xlsx_bytes(dados), "d.xlsx")
    assert (mapa["nome"], mapa["cpf"], mapa["nascimento"]) == (0, 1, 2)
    _, rel = converter(df, linhas, mapa)
    assert list(rel["Erro CPF"]) == ["CPF duplicado na planilha (linhas 2, 3)"] * 2


def test_csv_saida_no_padrao_do_modelo():
    df = pd.DataFrame([["Ana Souza", "05/08/2009", fmt(C1)]], columns=["Nome", "Nascimento", "CPF"])
    _, linhas = df, [2]
    mapa = {k: None for k in ["nome", "nascimento", "cpf"]}
    mapa.update(nome=0, nascimento=1, cpf=2)
    saida, _ = converter(df, linhas, mapa)
    texto = para_csv(saida).decode()
    linhas_csv = texto.split("\r\n")
    assert linhas_csv[0] == ";".join(COLUNAS_MODELO)
    assert linhas_csv[1].count(";") == len(COLUNAS_MODELO) - 1


# ----------------------------------------------------------------------------- padrões e CEP
BASE_CEP = {
    "01001000": {"cep": "01001000", "rua": "Praça da Sé", "bairro": "Sé", "cidade": "São Paulo",
                 "uf": "SP", "complemento": "lado ímpar"},
    "19015000": {"cep": "19015000", "rua": "Rua Exemplo", "bairro": "Centro",
                 "cidade": "Presidente Prudente", "uf": "SP", "complemento": ""},
}
END_SE = {"rua": "Praça da Sé", "bairro": "Sé", "cidade": "São Paulo", "uf": "SP", "complemento": "lado ímpar"}


def fake_buscar(chamadas=None):
    def buscar(cep):
        if chamadas is not None:
            chamadas.append(cep)
        return BASE_CEP.get(cep)
    return buscar


def df_basico(extra: dict | None = None, n=2):
    """DataFrame com nome/nascimento/CPF válidos e colunas extras opcionais."""
    cpfs = [fmt(cpf_valido(f"{100000000 + i * 7919:09d}")) for i in range(n)]
    d = {"Nome": [f"Pessoa Numero{'ab'[i % 2]} Silva" for i in range(n)],
         "Nascimento": ["05/08/1990"] * n, "CPF": cpfs}
    d.update(extra or {})
    df = pd.DataFrame(d, dtype=object)
    mapa = {"nome": 0, "nascimento": 1, "cpf": 2}
    for j, nome in enumerate(list(d)[3:], start=3):
        mapa[nome.lower()] = j
    return df, list(range(2, 2 + n)), mapa


def test_padroes_preenchem_linhas_sem_dado():
    df, linhas, mapa = df_basico()
    saida, rel = converter(
        df, linhas, mapa, cep_padrao="01001-000", endereco_padrao=END_SE, numero_padrao="100",
        email_padrao="Contato@Ex.com", celular_padrao="(18) 98120-1061")
    for _, r in saida.iterrows():
        assert r["cep (00000-000)"] == "01001-000" and r["Rua"] == "Praca da Se"
        assert r["Bairro"] == "Se" and r["Cidade"] == "Sao Paulo" and r["UF"] == "SP"
        assert r["Numero"] == "100" and r["Complemento"] == "lado impar"
        assert r["E-mail"] == "contato@ex.com" and r["Celular (00-000000000)"] == "18-981201061"
    assert set(rel["Origem do endereço"]) == {"CEP padrão"}


def test_modo_vazios_preserva_planilha_e_todas_sobrescreve():
    extra = {"CEP": ["19015-000", None], "Rua": ["Rua Própria", None], "Email": ["a@x.com", None]}
    df, linhas, mapa = df_basico(extra)
    comuns = dict(cep_padrao="01001000", endereco_padrao=END_SE, email_padrao="padrao@x.com")

    s, rel = converter(df, linhas, mapa, **comuns)
    assert (s.loc[0, "cep (00000-000)"], s.loc[0, "Rua"], s.loc[0, "E-mail"]) == ("19015-000", "Rua Propria", "a@x.com")
    assert (s.loc[1, "cep (00000-000)"], s.loc[1, "Rua"], s.loc[1, "E-mail"]) == ("01001-000", "Praca da Se", "padrao@x.com")
    assert list(rel["Origem do endereço"]) == ["planilha", "CEP padrão"]

    s, rel = converter(df, linhas, mapa, cep_modo="todas", email_modo="todas", **comuns)
    assert set(s["cep (00000-000)"]) == {"01001-000"} and set(s["Rua"]) == {"Praca da Se"}
    assert set(s["E-mail"]) == {"padrao@x.com"}


def test_completa_endereco_pelo_cep_e_gera_avisos():
    extra = {"CEP": ["19015-000", "99999-999", "123", "01001-000"],
             "UF": [None, None, None, "RJ"]}
    df, linhas, mapa = df_basico(extra, n=4)
    s, rel = converter(df, linhas, mapa, buscar_cep=fake_buscar())
    assert s.loc[0, "Rua"] == "Rua Exemplo" and s.loc[0, "Cidade"] == "Presidente Prudente" and s.loc[0, "UF"] == "SP"
    assert rel.loc[0, "Origem do endereço"] == "completado pelo CEP"
    assert "não encontrado" in rel.loc[1, "Avisos"]
    assert "fora do padrão" in rel.loc[2, "Avisos"]
    assert "UF diverge" in rel.loc[3, "Avisos"]
    s2, rel2 = converter(df, linhas, mapa, buscar_cep=fake_buscar(), completar_pelo_cep=False)
    assert s2.loc[0, "Rua"] == "" and rel2.loc[0, "Origem do endereço"] == "planilha"


def test_cada_cep_e_consultado_uma_vez():
    extra = {"CEP": ["19015-000"] * 3}
    df, linhas, mapa = df_basico(extra, n=3)
    chamadas = []
    converter(df, linhas, mapa, buscar_cep=fake_buscar(chamadas))
    assert chamadas == ["19015000"]


def test_api_fora_do_ar_para_apos_3_falhas():
    ceps = [f"1901500{i}" for i in range(6)]
    df, linhas, mapa = df_basico({"CEP": ceps}, n=6)
    chamadas = []

    def quebrada(cep):
        chamadas.append(cep)
        raise RuntimeError("API fora do ar")

    _, rel = converter(df, linhas, mapa, buscar_cep=quebrada)
    assert len(chamadas) == 3
    assert all("Falha" in a for a in rel["Avisos"][:3])
    assert all("indisponível" in a for a in rel["Avisos"][3:])
    assert set(rel["Status"]) == {"Válido"}  # CEP é só aviso, não reprova a linha


def test_padrao_invalido_e_ignorado():
    df, linhas, mapa = df_basico()
    s, _ = converter(df, linhas, mapa, cep_padrao="123", endereco_padrao=END_SE,
                     email_padrao="sem-arroba", celular_padrao="123")
    assert set(s["cep (00000-000)"]) == {""} and set(s["E-mail"]) == {""}
    assert set(s["Celular (00-000000000)"]) == {""}


# ----------------------------------------------------------------------------- saída sem caracteres especiais
def test_saida_do_csv_so_ascii():
    extra = {"Cidade": ["São Paulo", "SÃ£o Paulo"], "UF": ["SP", "PR"],
             "Rua": ["Praça da Sé; 2º andar", "Rua Ação"], "Email": ["a@x.com", "b@x.com"]}
    df, linhas, mapa = df_basico(extra)
    df.loc[0, "Nome"] = "José D’Ávila Júnior"
    saida, rel = converter(df, linhas, mapa)
    for col in saida.columns:
        for v in saida[col]:
            assert v.isascii(), (col, v)
    assert saida.loc[0, "Pax (nome e sobrenome)"] == "Jose D'Avila Junior"
    assert list(saida["Cidade"]) == ["Sao Paulo", "Sao Paulo"]
    assert saida.loc[0, "Rua"] == "Praca da Se, 2o andar"
    assert saida.loc[1, "Rua"] == "Rua Acao"
    assert saida.loc[0, "E-mail"] == "a@x.com"
    assert rel.loc[0, "Status"] == "Válido"  # a validação usa o texto original, com acentos
    csv_bytes = para_csv(saida)
    csv_bytes.decode("ascii")  # não pode levantar erro


def test_limpeza_nao_estraga_texto_legitimo():
    from mapper import limpar_texto_csv as L
    assert L("SÃO PAULO") == "SAO PAULO"
    assert L("Paraná") == "Parana"
    assert L("ParanÃ¡") == "Parana"
    assert L("a\nb;c") == "a b,c"
    assert L(None) == ""


def test_padrao_com_endereco_acentuado_sai_sem_acento():
    df, linhas, mapa = df_basico()
    end = {"rua": "Avenida São João", "bairro": "Bela Vista", "cidade": "Maringá", "uf": "PR", "complemento": ""}
    s, _ = converter(df, linhas, mapa, cep_padrao="87020-000", endereco_padrao=end)
    assert set(s["Rua"]) == {"Avenida Sao Joao"} and set(s["Cidade"]) == {"Maringa"}
    assert all(v.isascii() for col in s.columns for v in s[col])


# ----------------------------------------------------------------------------- CSV só com válidos + pendências do cliente
def _rel_misto():
    """0 válido; 1 nome sem sobrenome + CPF inválido; 2 data inexistente; 3 e 4 com CPF repetido."""
    df, linhas, mapa = df_basico(n=5)
    df.loc[1, "Nome"], df.loc[1, "CPF"] = "José", "529.982.247-24"
    df.loc[2, "Nascimento"] = "31/02/1990"
    df.loc[4, "CPF"] = df.loc[3, "CPF"]
    saida, rel = converter(df, linhas, mapa)
    return saida, rel


def test_csv_leva_somente_linhas_validas():
    from mapper import somente_validas
    saida, rel = _rel_misto()
    assert list(rel["Status"]) == ["Válido"] + ["Inválido"] * 4
    ok = somente_validas(saida, rel)
    assert len(ok) == 1 and ok.iloc[0]["Pax (nome e sobrenome)"] == "Pessoa Numeroa Silva"
    csv_linhas = para_csv(ok).decode().strip().split("\r\n")
    assert len(csv_linhas) == 2  # cabeçalho + 1 linha válida


def test_pendencias_listam_dado_incorreto_e_orientacao():
    from mapper import gerar_pendencias
    _, rel = _rel_misto()
    pend = gerar_pendencias(rel)
    assert list(pend["Linha na planilha"]) == [3, 4, 5, 6]
    a, b, c, d = (pend.iloc[i] for i in range(4))
    assert a["Nome informado"] == "José"  # como o cliente informou, com acento
    assert a["CPF informado"] == "529.982.247-24"
    assert a["Dado(s) incorreto(s)"] == "Nome e CPF"
    assert "Nome: Informe nome e sobrenome" in a["Problema"]
    assert "CPF: Dígito verificador inválido" in a["Problema"]
    assert "Informar nome e sobrenome completos." in a["Como corrigir"]
    assert b["Dado(s) incorreto(s)"] == "Data de nascimento"
    assert b["Problema"] == "Data de nascimento: Data em formato inválido"
    assert b["Data de nascimento informada"] == "31/02/1990"
    assert c["Problema"] == d["Problema"] == "CPF: CPF duplicado na planilha (linhas 5, 6)"
    assert 2 not in list(pend["Linha na planilha"])  # a linha 2 é a única válida e não entra


def test_mensagem_e_planilha_de_pendencias():
    from mapper import gerar_pendencias, mensagem_cliente, pendencias_para_xlsx
    _, rel = _rel_misto()
    pend = gerar_pendencias(rel)
    msg = mensagem_cliente(pend, total=len(rel))
    assert "4 de 5 passageiro(s)" in msg and "NÃO foram incluídas" in msg
    assert "Linha 3 - José | CPF: 529.982.247-24" in msg
    assert "    - CPF: Dígito verificador inválido" in msg
    assert "os outros 1 passageiro(s) seguem normalmente" in msg
    lido = pd.read_excel(io.BytesIO(pendencias_para_xlsx(pend)), dtype=object)
    assert list(lido.columns) == list(pend.columns) and len(lido) == 4
    assert lido.loc[0, "CPF informado"] == "529.982.247-24"


def test_sem_pendencias_quando_tudo_valido():
    from mapper import gerar_pendencias, mensagem_cliente
    df, linhas, mapa = df_basico(n=3)
    _, rel = converter(df, linhas, mapa)
    pend = gerar_pendencias(rel)
    assert pend.empty and mensagem_cliente(pend, 3) == ""

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
    assert list(rel["Erro CPF"]) == ["CPF duplicado na planilha"] * 2


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

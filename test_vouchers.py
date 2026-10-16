"""Testes do separador/renomeador de vouchers. PDFs fictícios gerados em memória (sem dados reais)."""
import io

import pypdf

from vouchers import (
    analisar_pdf, analisar_pdfs, data_curta, dividir_pdf, gerar_zip, intervalo, montar_nome_arquivo,
    nomes_unicos,
)


# ----------------------------------------------------------------------------- gerador de PDF mínimo
def _esc(s: str) -> bytes:
    return s.encode("cp1252", "replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def pdf_simples(paginas: list[list[str]]) -> bytes:
    """Uma página por lista de linhas de texto (uma palavra/trecho por linha, como o texto dos vouchers reais)."""
    objs: list[bytes] = []
    n = len(paginas)
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n)).encode()
    objs.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(n).encode() + b" >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for i, linhas in enumerate(paginas):
        conteudo = b"".join(b"BT /F1 9 Tf 30 %d Td (" % (800 - 12 * k) + _esc(l) + b") Tj ET\n"
                            for k, l in enumerate(linhas))
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents %d 0 R "
                    b"/Resources << /Font << /F1 3 0 R >> >> >>" % (5 + 2 * i))
        objs.append(b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"endstream")
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for k, o in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % k + o + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


def pagina_voucher(numero, nome, plano, ini, fim, acentos=True):
    inicio, termino, vigencia = ("início", "término", "vigência") if acentos else ("inicio", "termino", "vigencia")
    return (["VOUCHER DE ASSISTÊNCIA DE VIAGEM", "Voucher:", numero, "Nome:"] + nome.split()
            + ["Documento:", "000.000.000-00", "Dt.", "Nasc.:", "01/01/1990", "Destino", "da", "viagem:", "Brasil"]
            + ["Plano:"] + plano.split() + ["Forma", "de", "pagamento:", "A", "VISTA", "Periodicidade:", "Única"]
            + ["Data", "de", inicio, "da", vigencia + ":", ini]
            + ["Data", "de", termino, "da", vigencia + ":", fim, "Valor", "Total", "(US$):", "66,00"])


def pagina_bilhete(numero, nome):
    return ["Bilhete:", numero, "Nome", ":"] + nome.split() + ["Documento", ":", "000.000.000-00"]


PAGINA_ENCARTE = []  # página sem texto, como o encarte de benefícios


def voucher_completo(numero, nome, plano="10487-NACIONAL 30.000", ini="22/11/2026", fim="30/11/2026"):
    """5 páginas, como o voucher GTA real: voucher + 3 de bilhete + encarte."""
    return [pagina_voucher(numero, nome, plano, ini, fim), pagina_bilhete("9" + numero, nome),
            ["Bilhete:", "9" + numero, "1", "0,20"], ["Bilhete:", "9" + numero, "Sao", "Paulo,", "16/10/2026"],
            PAGINA_ENCARTE]


# ----------------------------------------------------------------------------- extração e separação
def test_um_voucher_de_cinco_paginas_vira_um_so():
    pdf = pdf_simples(voucher_completo("10000001", "MARIA SOUZA"))
    (v,) = analisar_pdf("a.pdf", pdf)
    assert v.paginas == [0, 1, 2, 3, 4] and v.intervalo_paginas == "1-5"
    assert (v.numero, v.nome, v.inicio, v.fim, v.plano) == (
        "10000001", "MARIA SOUZA", "22/11/2026", "30/11/2026", "10487-NACIONAL 30.000")
    assert v.avisos == []
    nome, erros, _ = montar_nome_arquivo(v.nome, v.inicio, v.fim, v.plano)
    assert nome == "MARIA SOUZA_22.11.26a30.11.26_10487-NACIONAL 30.000.pdf" and erros == []


def test_pdf_com_varios_vouchers_e_separado():
    pdf = pdf_simples(voucher_completo("10000001", "MARIA SOUZA")
                      + voucher_completo("10000002", "JOAO PEREIRA LIMA", "20001-INTERNACIONAL 60.000",
                                         "01/12/2026", "15/12/2026")
                      + [pagina_voucher("10000003", "ANA DIAS", "10487-NACIONAL 30.000", "05/01/2027", "09/01/2027")])
    vs = analisar_pdf("lote.pdf", pdf)
    assert [v.numero for v in vs] == ["10000001", "10000002", "10000003"]
    assert [v.paginas for v in vs] == [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [10]]
    assert [v.nome for v in vs] == ["MARIA SOUZA", "JOAO PEREIRA LIMA", "ANA DIAS"]
    assert vs[1].plano == "20001-INTERNACIONAL 60.000"
    # cada PDF separado tem só as páginas do seu voucher e o texto do voucher certo
    partes = [pypdf.PdfReader(io.BytesIO(dividir_pdf(pdf, v.paginas))) for v in vs]
    assert [len(p.pages) for p in partes] == [5, 5, 1]
    assert "JOAO" in partes[1].pages[0].extract_text() and "MARIA" not in partes[1].pages[0].extract_text()


def test_pdf_inteiro_volta_identico():
    pdf = pdf_simples(voucher_completo("10000001", "MARIA SOUZA"))
    assert dividir_pdf(pdf, [0, 1, 2, 3, 4]) == pdf


def test_acentos_opcionais_nos_rotulos():
    for acentos in (True, False):
        pdf = pdf_simples([pagina_voucher("10000001", "MARIA SOUZA", "10487-NACIONAL 30.000", "22/11/2026",
                                          "30/11/2026", acentos)])
        (v,) = analisar_pdf("a.pdf", pdf)
        assert (v.inicio, v.fim) == ("22/11/2026", "30/11/2026"), acentos


def test_campo_faltando_gera_aviso_e_erro_no_nome():
    pagina = [l for l in pagina_voucher("10000001", "MARIA SOUZA", "X", "22/11/2026", "30/11/2026")]
    i = pagina.index("Plano:")
    sem_plano = pagina[:i] + pagina[i + 2:]  # remove "Plano:" e o valor
    (v,) = analisar_pdf("a.pdf", pdf_simples([sem_plano]))
    assert v.plano == "" and "plano" in v.avisos[0]
    assert montar_nome_arquivo(v.nome, v.inicio, v.fim, v.plano)[1] == ["Plano vazio"]


def test_pdf_invalido_ou_sem_texto():
    (v,) = analisar_pdf("quebrado.pdf", b"isto nao e um pdf")
    assert v.paginas == [] and "Não foi possível abrir" in v.avisos[0]
    (v,) = analisar_pdf("imagem.pdf", pdf_simples([PAGINA_ENCARTE]))
    assert v.paginas == [0] and "sem texto" in v.avisos[0]


def test_voucher_repetido_entre_pdfs_e_avisado():
    pdf = pdf_simples(voucher_completo("10000001", "MARIA SOUZA"))
    vs = analisar_pdfs([("a.pdf", pdf), ("b.pdf", pdf)])
    assert vs[0].avisos == [] and "repetido" in vs[1].avisos[0]
    assert [v.indice_arquivo for v in vs] == [0, 1]


# ----------------------------------------------------------------------------- nome do arquivo
def test_data_curta_e_intervalo():
    assert data_curta("22/11/2026") == "22.11.26" and data_curta("2/3/2027") == "02.03.27"
    assert data_curta("22/11/26") == "22.11.26" and data_curta("22.11.2026") == "22.11.26"
    assert data_curta("31/02/2026") is None and data_curta("abc") is None and data_curta("") is None
    assert intervalo([0, 1, 2, 3, 4]) == "1-5" and intervalo([0, 2]) == "1, 3" and intervalo([4]) == "5"
    assert intervalo([0, 1, 3, 4, 5]) == "1-2, 4-6" and intervalo([]) == ""


def test_montar_nome_arquivo_regras():
    assert montar_nome_arquivo("José Ávila", "01/02/2027", "10/02/2027", "10487-NACIONAL 30.000")[0] \
        == "Jose Avila_01.02.27a10.02.27_10487-NACIONAL 30.000.pdf"
    assert montar_nome_arquivo("José Ávila", "01/02/2027", "10/02/2027", "P", sem_acentos=False)[0] \
        == "José Ávila_01.02.27a10.02.27_P.pdf"
    # caracteres proibidos em nome de arquivo viram "-"
    assert montar_nome_arquivo("ANA", "01/02/2027", "10/02/2027", "PLANO 1/2: A*B?")[0] \
        == "ANA_01.02.27a10.02.27_PLANO 1-2- A-B-.pdf"
    nome, erros, _ = montar_nome_arquivo("ANA", "31/02/2027", "xx", "P")
    assert nome == "" and len(erros) == 2
    nome, erros, avisos = montar_nome_arquivo("ANA", "10/02/2027", "01/02/2027", "P")
    assert nome.endswith(".pdf") and erros == [] and avisos == ["Término anterior ao início da vigência"]


def test_nomes_unicos_sem_diferenciar_maiusculas():
    assert nomes_unicos(["A.pdf", "a.pdf", "B.pdf", "", "A.pdf"]) == ["A.pdf", "a (2).pdf", "B.pdf", "", "A (3).pdf"]


def test_zip_ida_e_volta():
    import zipfile
    z = gerar_zip([("a.pdf", b"123"), ("b.pdf", b"456")])
    with zipfile.ZipFile(io.BytesIO(z)) as arq:
        assert arq.namelist() == ["a.pdf", "b.pdf"] and arq.read("b.pdf") == b"456"

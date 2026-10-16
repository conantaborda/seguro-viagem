"""Página: separador e renomeador de vouchers GTA (PDF)."""
import hashlib

import pandas as pd
import streamlit as st

from vouchers import analisar_pdfs, dividir_pdf, gerar_zip, montar_nome_arquivo, nomes_unicos

st.title("📄 Separador e renomeador de vouchers GTA")
st.caption("Envie um ou vários PDFs de vouchers. Cada voucher é separado e o arquivo é renomeado como "
           "NOME_INÍCIOaFIM_PLANO (ex.: FABIO GARCIA_22.11.26a30.11.26_10487-NACIONAL 30.000.pdf).")


@st.cache_data(show_spinner="Lendo os vouchers…", ttl=3600, max_entries=10)
def analisar(arquivos):
    return analisar_pdfs(list(arquivos))


@st.cache_data(show_spinner=False, ttl=3600, max_entries=200)
def separar(conteudo: bytes, paginas: tuple) -> bytes:
    return dividir_pdf(conteudo, list(paginas))


def txt(valor) -> str:
    """Célula da tabela editável -> texto ('' para vazio/NaN)."""
    return "" if valor is None or pd.isna(valor) else str(valor).strip()


arquivos = st.file_uploader("PDFs dos vouchers", type=["pdf"], accept_multiple_files=True)
if not arquivos:
    st.info("Envie um ou mais PDFs para começar. Um PDF com vários vouchers é separado automaticamente.")
    st.stop()

dados = tuple((a.name, a.getvalue()) for a in arquivos)
vouchers = analisar(dados)
assin = hashlib.md5(b"".join(n.encode() + c for n, c in dados)).hexdigest()[:10]

# ------------------------------------------------------------------ 1. conferência
st.subheader("1. Confira os dados lidos")
st.caption("Se algum dado estiver errado ou em branco, corrija direto na tabela. "
           "Desmarque “Incluir” para ignorar um voucher.")

df = pd.DataFrame([{
    "Incluir": bool(v.paginas) and not any("repetido" in a for a in v.avisos),
    "Arquivo de origem": v.arquivo,
    "Páginas": v.intervalo_paginas,
    "Voucher": v.numero,
    "Nome": v.nome,
    "Início": v.inicio,
    "Fim": v.fim,
    "Plano": v.plano,
    "Avisos": "; ".join(v.avisos),
} for v in vouchers])

editado = st.data_editor(
    df, hide_index=True, key=f"editor_{assin}",
    disabled=["Arquivo de origem", "Páginas", "Voucher", "Avisos"],
    column_config={
        "Incluir": st.column_config.CheckboxColumn("Incluir"),
        "Início": st.column_config.TextColumn("Início (DD/MM/AAAA)"),
        "Fim": st.column_config.TextColumn("Fim (DD/MM/AAAA)"),
    },
).reset_index(drop=True)

sem_acentos = st.checkbox("Remover acentos do nome do arquivo", value=True,
                          help="Evita nomes corrompidos ao abrir o .zip em alguns programas. "
                               "O conteúdo do PDF não é alterado.")

# ------------------------------------------------------------------ 2. nomes finais
resultado = []  # (nome do arquivo ou "", erros, avisos, incluir)
for _, r in editado.iterrows():
    nome_arq, erros, avisos = montar_nome_arquivo(
        txt(r["Nome"]), txt(r["Início"]), txt(r["Fim"]), txt(r["Plano"]), sem_acentos)
    incluir = bool(r["Incluir"])
    resultado.append((nome_arq if incluir and not erros else "", erros, avisos, incluir))
finais = nomes_unicos([r[0] for r in resultado])

status = []
for (nome_arq, erros, avisos, incluir), final in zip(resultado, finais):
    if not incluir:
        status.append("Ignorado")
    elif erros:
        status.append("Revisar: " + "; ".join(erros))
    else:
        extra = avisos + (["nome repetido: acrescentado (n)"] if final != nome_arq else [])
        status.append("OK" + (" (" + "; ".join(extra) + ")" if extra else ""))

prontos = sum(1 for s in status if s.startswith("OK"))
revisar = sum(1 for s in status if s.startswith("Revisar"))
m = st.columns(4)
m[0].metric("Vouchers encontrados", len(vouchers))
m[1].metric("Prontos", prontos)
m[2].metric("Para revisar", revisar)
m[3].metric("Ignorados", sum(1 for s in status if s == "Ignorado"))

st.subheader("2. Nomes finais dos arquivos")
st.dataframe(pd.DataFrame({
    "Nome do arquivo": [f or "—" for f in finais],
    "Origem": editado["Arquivo de origem"],
    "Páginas": editado["Páginas"],
    "Status": status,
}), hide_index=True)

# ------------------------------------------------------------------ 3. download
st.subheader("3. Download")
itens = []
try:
    for pos, nome_final in enumerate(finais):
        if nome_final:
            v = vouchers[pos]
            itens.append((nome_final, separar(dados[v.indice_arquivo][1], tuple(v.paginas))))
except Exception as e:
    st.error(f"Não consegui separar um dos PDFs ({e}). Desmarque-o em “Incluir” e tente de novo.")
    itens = []

if not itens:
    st.warning("Nenhum voucher pronto para baixar. Corrija os itens marcados como “Revisar” na tabela acima.")
elif len(itens) == 1:
    st.download_button("⬇️ Baixar PDF renomeado", itens[0][1], file_name=itens[0][0],
                       mime="application/pdf", type="primary")
else:
    st.download_button(f"⬇️ Baixar {len(itens)} vouchers (.zip)", gerar_zip(itens),
                       file_name="vouchers_renomeados.zip", mime="application/zip", type="primary")

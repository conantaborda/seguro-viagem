"""App Streamlit: lê uma planilha qualquer, detecta onde está cada campo e preenche o modelo de emissão.

Executar:  streamlit run app.py
"""
import hashlib
import io

import pandas as pd
import streamlit as st

from mapper import (
    CAMPOS, FORMATOS_CPF, ROTULO, converter, detectar_linha_cabecalho, detectar_mapeamento,
    email_valido, ler_arquivo_bruto, letra_coluna, montar_df, normalizar_celular, normalizar_cep,
    para_csv, pontuar, so_digitos,
)
from cep import consultar_cep

st.set_page_config(page_title="Planilha → Modelo de Emissão", page_icon="🧾", layout="wide")
st.title("🧾 Planilha → Modelo de emissão")
st.caption("Envie qualquer planilha (.xlsx, .xls ou .csv). O app detecta onde está cada campo, "
           "você confere o mapeamento e baixa o CSV no formato do modelo.")

ICONE = {"alta": "🟢", "média": "🟡", "baixa": "🟠", "nenhuma": "⚪"}


@st.cache_data(show_spinner="Lendo planilha…")
def carregar(conteudo: bytes, nome: str):
    abas = ler_arquivo_bruto(conteudo, nome)
    pontos = {}
    for aba, raw in abas.items():
        df, _ = montar_df(raw, detectar_linha_cabecalho(raw))
        pontos[aba] = pontuar(detectar_mapeamento(df)) if len(df) else 0
    return abas, pontos


@st.cache_data(ttl=86400, show_spinner=False)
def buscar_cep_cache(cep: str):
    """Consulta a API uma vez por CEP (exceção da API não é guardada em cache)."""
    return consultar_cep(cep)


arquivo = st.file_uploader("Planilha de origem", type=["xlsx", "xls", "csv"])
if not arquivo:
    st.stop()

conteudo = arquivo.getvalue()
abas, pontos = carregar(conteudo, arquivo.name)
nomes_abas = list(abas)
melhor = max(pontos, key=pontos.get)

aba = (st.selectbox("Aba da planilha", nomes_abas, index=nomes_abas.index(melhor))
       if len(nomes_abas) > 1 else nomes_abas[0])
raw = abas[aba]
assin = hashlib.md5(conteudo + aba.encode()).hexdigest()[:10]

auto = detectar_linha_cabecalho(raw)
linha_cab = st.number_input(
    "Linha do cabeçalho na planilha (0 = não há cabeçalho)", min_value=0, max_value=max(len(raw), 1),
    value=auto + 1 if auto >= 0 else 0, step=1, key=f"cab_{assin}",
    help="Detectada automaticamente. Ajuste se a planilha tiver títulos acima da tabela.")
df, linhas = montar_df(raw, linha_cab - 1 if linha_cab > 0 else -1)
if df.empty:
    st.error("Nenhuma linha de dados encontrada abaixo do cabeçalho.")
    st.stop()

st.write(f"**{len(df)} linhas de dados** · {df.shape[1]} colunas")
st.dataframe(df.head(8))

# ------------------------------------------------------------------ mapeamento
st.subheader("1. Mapeamento das colunas")
st.caption("🟢 alta confiança · 🟡 média · 🟠 baixa (confira) · ⚪ não encontrada. "
           "Ajuste qualquer campo; escolha “não preencher” para deixá-lo vazio.")
det = detectar_mapeamento(df)
opcoes = [None] + list(range(df.shape[1]))


def nome_opcao(j):
    return "— não preencher —" if j is None else f"{letra_coluna(j)} · {df.columns[j]}"


mapa = {}
grade = st.columns(3)
for k, campo in enumerate(CAMPOS):
    d = det[campo]
    with grade[k % 3]:
        mapa[campo] = st.selectbox(
            f"{ICONE[d.confianca]} {ROTULO[campo]}", opcoes, format_func=nome_opcao,
            index=0 if d.coluna is None else d.coluna + 1, key=f"map_{campo}_{assin}_{linha_cab}",
            help=f"Detecção: {d.motivo}" if d.coluna is not None else "Não encontrei esta coluna.")

repetidas = [j for j in set(mapa.values()) if j is not None and list(mapa.values()).count(j) > 1]
if repetidas:
    st.warning("A mesma coluna está sendo usada em mais de um campo: "
               + ", ".join(nome_opcao(j) for j in repetidas))

# ------------------------------------------------------------------ padrões
st.subheader("2. Padrões para preencher as linhas")
st.caption("Opcional. Preenche CEP/endereço, e-mail e celular quando a planilha não tiver o dado "
           "— ou em todas as linhas, se você escolher.")
MODOS = {"vazios": "Somente onde estiver vazio", "todas": "Em todas as linhas (ignora a planilha)"}
padroes_ok = True

with st.container(border=True):
    st.markdown("**CEP e endereço**")
    a1, a2, a3, a4 = st.columns([1, 1, 1, 1.6])
    cep_padrao = a1.text_input("CEP padrão", placeholder="00000-000")
    numero_padrao = a2.text_input("Número padrão")
    complemento_padrao = a3.text_input("Complemento padrão")
    cep_modo = a4.radio("Aplicar o CEP padrão", list(MODOS), format_func=MODOS.get, key="cep_modo")
    endereco_padrao = {}
    cep_fmt, cep_ok = normalizar_cep(cep_padrao) if cep_padrao.strip() else ("", False)
    if cep_padrao.strip() and not cep_ok:
        st.error("CEP padrão inválido: informe os 8 dígitos.")
        padroes_ok = False
    elif cep_ok:
        info, falha_api = None, False
        try:
            info = buscar_cep_cache(so_digitos(cep_fmt))
        except Exception:
            falha_api = True
        if falha_api:
            st.warning("Não consegui consultar a API de CEP agora. Preencha o endereço manualmente abaixo.")
        elif info is None:
            st.warning("CEP não encontrado nas APIs. Confira o número ou preencha o endereço manualmente.")
        else:
            st.success(f"{info['rua'] or '(CEP geral, sem logradouro)'} · {info['bairro']} · "
                       f"{info['cidade']}/{info['uf']}")
        info = info or {}
        k = f"{cep_fmt}_{bool(info)}"
        e1, e2, e3, e4 = st.columns([2, 1.2, 1.2, 0.6])
        endereco_padrao = {
            "rua": e1.text_input("Rua", value=info.get("rua", ""), key=f"end_rua_{k}"),
            "bairro": e2.text_input("Bairro", value=info.get("bairro", ""), key=f"end_bairro_{k}"),
            "cidade": e3.text_input("Cidade", value=info.get("cidade", ""), key=f"end_cidade_{k}"),
            "uf": e4.text_input("UF", value=info.get("uf", ""), max_chars=2, key=f"end_uf_{k}"),
            "complemento": info.get("complemento", ""),
        }

with st.container(border=True):
    st.markdown("**Contato**")
    b1, b2, b3, b4 = st.columns(4)
    email_padrao = b1.text_input("E-mail padrão")
    email_modo = b2.radio("Aplicar o e-mail padrão", list(MODOS), format_func=MODOS.get, key="email_modo")
    celular_padrao = b3.text_input("Celular padrão", placeholder="(00) 90000-0000")
    celular_modo = b4.radio("Aplicar o celular padrão", list(MODOS), format_func=MODOS.get, key="cel_modo")
    if email_padrao.strip() and not email_valido(email_padrao):
        st.error("E-mail padrão inválido.")
        padroes_ok = False
    if celular_padrao.strip() and not normalizar_celular(celular_padrao)[1]:
        st.error("Celular padrão inválido: use DDD + número (ex.: (18) 98120-1061).")
        padroes_ok = False

# ------------------------------------------------------------------ opções
with st.expander("Opções de formato e validação", expanded=False):
    o1, o2 = st.columns(2)
    formato_cpf = o1.selectbox("Formato do CPF na saída", list(FORMATOS_CPF),
                               format_func=FORMATOS_CPF.get,
                               help="O cabeçalho do modelo mostra 000.000.000.00 (ponto antes dos 2 últimos "
                                    "dígitos). Se o seu sistema espera hífen, escolha o padrão.")
    codificacao = o2.selectbox("Codificação do CSV", ["utf-8", "cp1252"],
                               format_func=lambda x: {"utf-8": "UTF-8", "cp1252": "Windows (ANSI)"}[x])
    p1, p2, p3 = st.columns(3)
    nome_maiusculo = p1.checkbox("Nome em MAIÚSCULAS sem acento", value=False)
    zeros = p2.checkbox("Completar zeros à esquerda no CPF", value=True,
                        help="O Excel remove zeros iniciais de CPFs salvos como número.")
    sobrenome = p3.checkbox("Exigir nome e sobrenome", value=True)
    q1, q2, q3 = st.columns(3)
    idade_max = q1.number_input("Idade máxima aceita", 50, 150, 120)
    dup = q2.checkbox("Reprovar CPF duplicado", value=True)
    file_fixo = q3.text_input("Valor fixo para “file” (se não houver coluna)")
    grupo_fixo = st.text_input("Valor fixo para “grupo” (se não houver coluna)")
    consultar = st.checkbox("Consultar na API os CEPs da planilha (valida se existem)", value=True,
                            help="Uma consulta por CEP distinto, com cache. Desmarque para não usar a API.")
    completar = st.checkbox("Completar rua/bairro/cidade/UF pelo CEP quando estiverem vazios", value=True)

# ------------------------------------------------------------------ geração
if st.button("3. Gerar planilha no modelo", type="primary", disabled=not padroes_ok):
    saida, rel = converter(
        df, linhas, mapa, formato_cpf=formato_cpf, nome_maiusculo=nome_maiusculo,
        completar_zeros=zeros, exigir_sobrenome=sobrenome, idade_max=int(idade_max),
        marcar_duplicados=dup, file_fixo=file_fixo, grupo_fixo=grupo_fixo,
        cep_padrao=cep_padrao, cep_modo=cep_modo, endereco_padrao=endereco_padrao,
        numero_padrao=numero_padrao, complemento_padrao=complemento_padrao,
        email_padrao=email_padrao, email_modo=email_modo,
        celular_padrao=celular_padrao, celular_modo=celular_modo,
        buscar_cep=buscar_cep_cache if consultar else None, completar_pelo_cep=completar)
    st.session_state["resultado"] = (assin, saida, rel, codificacao)

res = st.session_state.get("resultado")
if not res or res[0] != assin:
    st.stop()
_, saida, rel, codificacao = res

total = len(rel)
validos = int((rel["Status"] == "Válido").sum())
invalidos = total - validos
m = st.columns(4)
m[0].metric("Total", total)
m[1].metric("Válidos", validos)
m[2].metric("Inválidos", invalidos)
m[3].metric("Com avisos", int((rel["Avisos"] != "").sum()))
if invalidos:
    st.warning(f"{invalidos} linha(s) com erro em nome, CPF ou data. Corrija na planilha de origem "
               "ou exporte somente as válidas.")

st.subheader("Prévia no formato do modelo")
st.dataframe(saida.head(20))

st.subheader("Validação")
filtro = st.radio("Mostrar", ["Somente com problemas", "Todos"], horizontal=True)
vis = rel if filtro == "Todos" else rel[(rel["Status"] == "Inválido") | (rel["Avisos"] != "")]
cols_vis = ["Linha", "Nome", "CPF", "Data de Nascimento", "Status", "Erro Nome", "Erro CPF", "Erro Data", "Avisos", "Origem do endereço"]
st.dataframe(vis[cols_vis].style.apply(
    lambda s: ["background-color:#fde2e2" if v == "Inválido" else "" for v in s], subset=["Status"]),
    hide_index=True)

# ------------------------------------------------------------------ downloads
st.subheader("4. Downloads")
escopo = st.radio("Linhas no CSV", ["Todas as linhas", "Somente linhas válidas"], horizontal=True)
saida_exp = saida if escopo == "Todas as linhas" else saida[rel["Status"] == "Válido"]

d1, d2 = st.columns(2)
d1.download_button("⬇️ CSV no modelo", para_csv(saida_exp, codificacao),
                   file_name="emissao_planilha_preenchida.csv", mime="text/csv", type="primary")

buf = io.BytesIO()
rel_x = rel.drop(columns=["Nome OK", "CPF OK", "Data OK"])
with pd.ExcelWriter(buf, engine="openpyxl") as xw:
    rel_x.to_excel(xw, sheet_name="Relatório", index=False)
    rel_x[rel_x["Status"] == "Inválido"].to_excel(xw, sheet_name="Somente inválidos", index=False)
d2.download_button("⬇️ Relatório de validação (.xlsx)", buf.getvalue(),
                   file_name="relatorio_validacao.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

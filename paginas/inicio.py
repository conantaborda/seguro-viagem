"""Página inicial: escolha da ação."""
import streamlit as st

st.title("🧭 Painel de operações")
st.caption("Escolha o que você quer fazer.")

col1, col2 = st.columns(2)

with col1, st.container(border=True):
    st.markdown("### 🧾 Planilha de emissão de seguro viagem")
    st.write("Envie a planilha do cliente. O app detecta as colunas, valida nome, CPF e data de nascimento, "
             "completa endereço pelo CEP e gera o CSV no modelo de emissão, com as pendências para o cliente.")
    st.page_link("paginas/emissao_seguro.py", label="Abrir planilha de emissão", icon="➡️")

with col2, st.container(border=True):
    st.markdown("### 📄 Separador e renomeador de vouchers GTA")
    st.write("Envie um ou vários PDFs de vouchers. O app separa cada voucher e renomeia o arquivo como "
             "`NOME_INÍCIOaFIM_PLANO`, pronto para baixar.")
    st.page_link("paginas/vouchers.py", label="Abrir separador de vouchers", icon="➡️")

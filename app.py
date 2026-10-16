"""Painel de operações GTA. Executar:  streamlit run app.py

Roteador: a página inicial permite escolher a ação; cada ação é uma página em `paginas/`.
"""
import streamlit as st

st.set_page_config(page_title="Painel GTA", page_icon="🧭", layout="wide")

pagina = st.navigation([
    st.Page("paginas/inicio.py", title="Início", icon="🏠", default=True),
    st.Page("paginas/emissao_seguro.py", title="Planilha de emissão", icon="🧾"),
    st.Page("paginas/vouchers.py", title="Vouchers GTA", icon="📄"),
])
pagina.run()

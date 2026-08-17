import streamlit as st

from diagnostico_fase import render_fase_diagnostic

st.set_page_config(page_title="Diagnóstico da Fase", page_icon="📊", layout="wide")
st.title("📊 Diagnóstico da Fase — Série B")
st.caption("Analisa somente o JSON da fase já carregado pelo laboratório. Nenhuma chamada adicional à API é feita nesta página.")

data = st.session_state.get("fase_detail")
if data is None:
    st.warning("Primeiro abra o laboratório principal, consulte a fase 1112 e depois volte para esta página.")
else:
    render_fase_diagnostic(data)

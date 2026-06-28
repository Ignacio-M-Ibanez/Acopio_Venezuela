import streamlit as st

from dashboard import render_dashboard


st.set_page_config(page_title="Inventario", layout="wide")

vista = st.sidebar.radio("Vista", ["Total", "Solo CA-11"], horizontal=True)
render_dashboard(filtrar_ca11=vista == "Solo CA-11")

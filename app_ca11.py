import streamlit as st

from dashboard import render_dashboard


st.set_page_config(page_title="Inventario CA-11", layout="wide")
render_dashboard(filtrar_ca11=True)

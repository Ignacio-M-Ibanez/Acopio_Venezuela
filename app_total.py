import streamlit as st

from dashboard import render_dashboard


st.set_page_config(page_title="Inventario total", layout="wide")
render_dashboard(filtrar_ca11=False)

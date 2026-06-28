from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from inventario_core import (
    aplicar_filtro_centros,
    dataframe_a_csv_bytes,
    detalle_cajas_duplicadas,
    google_sheet_csv_url,
    leer_csv_robusto,
    preparar_base,
    resumen_eda,
    tabla_insumo_global,
)


REFRESH_SECONDS = 60


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def cargar_desde_url(url_csv: str) -> pd.DataFrame:
    return leer_csv_robusto(url_csv)


def obtener_url_inicial() -> str:
    url = os.getenv("GOOGLE_SHEET_URL", "").strip()
    if url:
        return url

    try:
        url = st.secrets.get("GOOGLE_SHEET_URL", "").strip()
        if url:
            return url
    except Exception:
        pass

    try:
        from config import GOOGLE_SHEET_URL

        return (GOOGLE_SHEET_URL or "").strip()
    except Exception:
        return ""


def cargar_base_desde_ui() -> pd.DataFrame | None:
    url_inicial = obtener_url_inicial()
    with st.sidebar:
        st.header("Fuente")
        url_sheet = st.text_input(
            "Google Sheets publico",
            value=url_inicial,
            placeholder="https://docs.google.com/spreadsheets/d/...",
        )
        archivo = st.file_uploader("CSV manual", type=["csv"])

        if st.button("Actualizar ahora", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    if archivo is not None:
        return leer_csv_robusto(archivo)

    url_csv = google_sheet_csv_url(url_sheet)
    if url_csv:
        return cargar_desde_url(url_csv)

    return None


def mostrar_metricas(resumen: dict):
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total de registros", f"{resumen['registros_totales']:,}")
    col2.metric("Cajas unicas", f"{resumen['cajas_unicas']:,}")
    col3.metric("Centros", f"{resumen['centros']:,}")
    col4.metric("Cajas duplicadas", f"{resumen['cajas_duplicadas']:,}")
    col5.metric("campo vac\u00edo", f"{resumen['categorias_vacias']:,}")
    st.caption("campo vac\u00edo en Categor\u00eda de insumo (posible carga en proceso)")


def mostrar_tabla_duplicados(base: pd.DataFrame):
    duplicados = detalle_cajas_duplicadas(base)
    with st.expander("Detalle de cajas duplicadas", expanded=not duplicados.empty):
        if duplicados.empty:
            st.success("No se detectaron cajas duplicadas por N\u00b0 de Caja en la vista actual.")
        else:
            st.dataframe(duplicados, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar duplicados CSV",
                data=dataframe_a_csv_bytes(duplicados),
                file_name="cajas_duplicadas.csv",
                mime="text/csv",
                use_container_width=True,
            )


def mostrar_insumos(tabla: pd.DataFrame):
    st.subheader("Insumos normalizados")

    if tabla.empty:
        st.warning("No hay insumos analizables en la vista actual.")
        return

    tabla_vista = tabla[
        [
            "insumo_norm",
            "cantidad_cajas",
            "cantidad_instancias",
            "cantidad_centros",
            "cajas",
            "centros",
        ]
    ].rename(
        columns={
            "insumo_norm": "Insumo normalizado",
            "cantidad_cajas": "Cantidad de cajas",
            "cantidad_instancias": "Cantidad de instancias",
            "cantidad_centros": "Cantidad de centros",
            "cajas": "Cajas",
            "centros": "Centros",
        }
    )

    st.dataframe(tabla_vista, use_container_width=True, hide_index=True)
    st.download_button(
        "Descargar insumos CSV",
        data=dataframe_a_csv_bytes(tabla_vista),
        file_name="insumos_normalizados.csv",
        mime="text/csv",
        use_container_width=True,
    )

    top_n = st.slider("Cantidad de insumos en grafico", min_value=5, max_value=60, value=25, step=5)
    datos_grafico = tabla.head(top_n).sort_values("cantidad_cajas", ascending=True)

    fig = px.bar(
        datos_grafico,
        x="cantidad_cajas",
        y="insumo_norm",
        orientation="h",
        text="cantidad_cajas",
        hover_data=["cantidad_instancias", "cantidad_centros", "centros"],
        labels={
            "cantidad_cajas": "Cantidad de cajas",
            "insumo_norm": "Insumo normalizado",
            "cantidad_instancias": "Instancias",
            "cantidad_centros": "Centros",
        },
        title="Cantidad de cajas por insumo normalizado",
        height=max(460, top_n * 24),
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        yaxis_title="",
        xaxis_title="Cantidad de cajas",
        margin=dict(l=20, r=40, t=60, b=30),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_dashboard(filtrar_ca11: bool):
    titulo = "Inventario filtrado CA-11" if filtrar_ca11 else "Inventario total"
    st.title(titulo)

    df = cargar_base_desde_ui()
    if df is None:
        st.info("Carga un CSV o pega el enlace publico de Google Sheets en la barra lateral.")
        return

    try:
        base = preparar_base(df, filtrar_ca11=filtrar_ca11)
    except ValueError as exc:
        st.error(str(exc))
        return

    with st.sidebar:
        st.header("Filtros")
        centros = sorted(base["centro_norm"].dropna().unique().tolist())
        centros_sel = st.multiselect("Centro de Acopio", options=centros, default=centros)
        auto_refresh = st.toggle("Actualizar cada 60 segundos", value=False)

    base_filtrada = aplicar_filtro_centros(base, centros_sel)
    resumen = resumen_eda(base_filtrada)
    tabla_insumos = tabla_insumo_global(base_filtrada)

    mostrar_metricas(resumen)
    mostrar_tabla_duplicados(base_filtrada)
    mostrar_insumos(tabla_insumos)

    with st.expander("Base normalizada en memoria"):
        columnas = ["caja", "centro_norm", "categoria_norm", "categoria_vacia"]
        st.dataframe(base_filtrada[columnas], use_container_width=True, hide_index=True)

    if auto_refresh:
        components.html(
            f"""
            <script>
            setTimeout(function() {{
                window.parent.location.reload();
            }}, {REFRESH_SECONDS * 1000});
            </script>
            """,
            height=0,
        )

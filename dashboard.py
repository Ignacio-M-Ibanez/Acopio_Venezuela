from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

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
    tabla_peso_por_caja,
    tabla_peso_por_centro,
)


REFRESH_SECONDS = 60

# ════════════════════════════════════════════════════════════════════
# CACHE EN DISCO DEL CSV CARGADO
# ════════════════════════════════════════════════════════════════════
# El archivo subido se persiste en disco del servidor para que sobreviva
# a reruns, refresh y nuevas sesiones. Se pierde solo en redeploys.
#
# IMPORTANTE: esto NO escribe nada a Google Drive ni al CSV original.
# Es un archivo local de la app, completamente bajo nuestro control.

CACHE_DIR = Path(__file__).parent / "_cache_csv"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_FILE = CACHE_DIR / "inventario_cargado.csv"
CACHE_META = CACHE_DIR / "metadata.txt"


def _guardar_csv_en_cache(archivo_subido) -> None:
    """Persiste el contenido del UploadedFile en disco del servidor."""
    archivo_subido.seek(0)
    contenido = archivo_subido.read()
    if isinstance(contenido, str):
        contenido = contenido.encode("utf-8")
    CACHE_FILE.write_bytes(contenido)
    CACHE_META.write_text(
        f"{archivo_subido.name}\n{datetime.now().isoformat(timespec='seconds')}\n",
        encoding="utf-8",
    )


def _info_cache() -> tuple[str | None, str | None]:
    """Devuelve (nombre_original, timestamp_iso) o (None, None) si no hay cache."""
    if not CACHE_FILE.exists() or not CACHE_META.exists():
        return None, None
    try:
        partes = CACHE_META.read_text(encoding="utf-8").strip().splitlines()
        nombre = partes[0] if partes else None
        ts = partes[1] if len(partes) > 1 else None
        return nombre, ts
    except Exception:
        return None, None


def _borrar_cache() -> None:
    """Elimina el CSV cacheado y su metadata."""
    CACHE_FILE.unlink(missing_ok=True)
    CACHE_META.unlink(missing_ok=True)


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def _cargar_desde_disco_cacheado(ruta: str, mtime: float) -> pd.DataFrame:
    """
    Lee el CSV cacheado en disco. El parametro mtime se incluye en la
    firma para que el cache de Streamlit se invalide cuando el archivo
    se reemplace (mtime cambia -> cache miss -> re-lectura).
    """
    _ = mtime  # solo cumple rol de clave de cache
    return leer_csv_robusto(ruta)


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
    nombre_cache, ts_cache = _info_cache()

    with st.sidebar:
        st.header("Fuente")
        modo_fuente = st.radio(
            "Origen de datos",
            ["CSV manual", "Google Sheets"],
            horizontal=True,
            help="Usa CSV manual si el acceso al Google Sheet esta restringido.",
        )

        archivo = None
        url_sheet = ""

        if modo_fuente == "CSV manual":
            archivo = st.file_uploader("Cargar CSV", type=["csv"])
            st.caption(
                "El CSV se procesa solo en memoria y se guarda en el servidor "
                "para que persista entre sesiones. La app no modifica el archivo original."
            )

            if nombre_cache:
                ts_legible = ts_cache.replace("T", " ") if ts_cache else "fecha desconocida"
                st.success(
                    f"CSV cargado en el servidor:\n\n"
                    f"**{nombre_cache}**\n\n"
                    f"Guardado: {ts_legible}"
                )
                if st.button("Borrar CSV cargado", use_container_width=True):
                    _borrar_cache()
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.info("Aun no hay CSV cargado. Subi uno arriba.")
        else:
            url_sheet = st.text_input(
                "Google Sheets publico",
                value=url_inicial,
                placeholder="https://docs.google.com/spreadsheets/d/...",
            )

        if st.button("Actualizar ahora", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ─── 1. Archivo recien subido: persistir y usar ───────────────
    if archivo is not None:
        _guardar_csv_en_cache(archivo)
        st.cache_data.clear()  # invalidar lecturas previas del cache anterior
        archivo.seek(0)
        return leer_csv_robusto(archivo)

    # ─── 2. Modo CSV manual sin upload nuevo: usar el cache de disco ──
    if modo_fuente == "CSV manual":
        if CACHE_FILE.exists():
            mtime = CACHE_FILE.stat().st_mtime
            return _cargar_desde_disco_cacheado(str(CACHE_FILE), mtime)
        return None

    # ─── 3. Modo Google Sheets ─────────────────────────────────────
    url_csv = google_sheet_csv_url(url_sheet)
    if url_csv:
        return cargar_desde_url(url_csv)

    return None


def mostrar_error_carga(exc: Exception):
    st.error(str(exc))
    with st.expander("Como corregir la fuente de datos"):
        st.markdown(
            """
            - Verifica que el Google Sheet este compartido como `Cualquier persona con el enlace puede ver`.
            - Si sigue fallando en Streamlit Cloud, usa `Archivo > Compartir > Publicar en la web`.
            - Publica la pestana correcta como CSV o deja que la app convierta el enlace normal de Sheets.
            - Revisa que `GOOGLE_SHEET_URL` en `Secrets` no tenga comillas duplicadas, espacios extra o un enlace incompleto.
            """
        )


def mostrar_metricas(resumen: dict):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de registros", f"{resumen['registros_totales']:,}")
    col2.metric("Cajas unicas", f"{resumen['cajas_unicas']:,}")
    col3.metric("Centros", f"{resumen['centros']:,}")
    col4.metric("Cajas duplicadas", f"{resumen['cajas_duplicadas']:,}")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("campo vac\u00edo", f"{resumen['categorias_vacias']:,}")
    col6.metric("Peso total kg", f"{resumen['peso_total_kg']:,.2f}")
    col7.metric("Registros con peso", f"{resumen['registros_con_peso']:,}")
    col8.metric("Registros sin peso", f"{resumen['registros_peso_vacio']:,}")
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


def mostrar_pesos(base: pd.DataFrame):
    st.subheader("Peso")

    pesos_caja = tabla_peso_por_caja(base)
    pesos_centro = tabla_peso_por_centro(base)

    if pesos_caja.empty:
        st.warning("No hay registros para visualizar peso en la vista actual.")
        return

    tab_cajas, tab_centros = st.tabs(["Por caja", "Por centro de acopio"])

    with tab_cajas:
        tabla_cajas_vista = pesos_caja.rename(
            columns={
                "caja": "Caja",
                "centro_norm": "Centro de Acopio",
                "peso_kg": "Peso kg",
                "registros": "Registros",
                "categorias": "Categorias",
                "peso_cargado": "Peso cargado",
            }
        )
        st.dataframe(tabla_cajas_vista, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar peso por caja CSV",
            data=dataframe_a_csv_bytes(tabla_cajas_vista),
            file_name="peso_por_caja.csv",
            mime="text/csv",
            use_container_width=True,
        )

        cajas_con_peso = pesos_caja[pesos_caja["peso_cargado"]].copy()
        if cajas_con_peso.empty:
            st.info("Todavia no hay pesos cargados para graficar por caja.")
        else:
            top_cajas = st.slider("Cantidad de cajas en grafico de peso", 10, 100, 40, 10)
            datos_caja = cajas_con_peso.head(top_cajas).sort_values("peso_kg", ascending=True)
            fig_cajas = px.bar(
                datos_caja,
                x="peso_kg",
                y="caja",
                color="centro_norm",
                orientation="h",
                hover_data=["registros", "categorias"],
                labels={
                    "peso_kg": "Peso kg",
                    "caja": "Caja",
                    "centro_norm": "Centro de Acopio",
                },
                title="Peso por caja",
                height=max(460, top_cajas * 18),
            )
            fig_cajas.update_layout(yaxis_title="", xaxis_title="Peso kg")
            st.plotly_chart(fig_cajas, use_container_width=True)

            fig_hist = px.histogram(
                cajas_con_peso,
                x="peso_kg",
                nbins=30,
                labels={"peso_kg": "Peso kg"},
                title="Distribucion de pesos por caja",
            )
            st.plotly_chart(fig_hist, use_container_width=True)

    with tab_centros:
        tabla_centros_vista = pesos_centro.rename(
            columns={
                "centro_norm": "Centro de Acopio",
                "peso_total_kg": "Peso total kg",
                "cajas_unicas": "Cajas unicas",
                "registros": "Registros",
                "registros_con_peso": "Registros con peso",
                "registros_sin_peso": "Registros sin peso",
                "peso_promedio_por_caja_kg": "Peso promedio por caja kg",
            }
        )
        st.dataframe(tabla_centros_vista, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar peso por centro CSV",
            data=dataframe_a_csv_bytes(tabla_centros_vista),
            file_name="peso_por_centro.csv",
            mime="text/csv",
            use_container_width=True,
        )

        if pesos_centro["registros_con_peso"].sum() == 0:
            st.info("Todavia no hay pesos cargados para graficar por centro.")
        else:
            datos_centro = pesos_centro.sort_values("peso_total_kg", ascending=True)
            fig_centro = px.bar(
                datos_centro,
                x="peso_total_kg",
                y="centro_norm",
                orientation="h",
                text="peso_total_kg",
                hover_data=[
                    "cajas_unicas",
                    "registros",
                    "registros_con_peso",
                    "registros_sin_peso",
                    "peso_promedio_por_caja_kg",
                ],
                labels={
                    "peso_total_kg": "Peso total kg",
                    "centro_norm": "Centro de Acopio",
                },
                title="Peso total por centro de acopio",
                height=max(420, len(datos_centro) * 45),
            )
            fig_centro.update_traces(texttemplate="%{text:.2f}", textposition="outside", cliponaxis=False)
            fig_centro.update_layout(yaxis_title="", xaxis_title="Peso total kg")
            st.plotly_chart(fig_centro, use_container_width=True)


def render_dashboard(filtrar_ca11: bool):
    titulo = "Inventario filtrado CA-11" if filtrar_ca11 else "Inventario total"
    st.title(titulo)

    try:
        df = cargar_base_desde_ui()
    except Exception as exc:
        mostrar_error_carga(exc)
        return

    if df is None:
        st.info("Carga un CSV o selecciona Google Sheets en la barra lateral.")
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
    tab_insumos, tab_pesos = st.tabs(["Insumos", "Peso"])
    with tab_insumos:
        mostrar_insumos(tabla_insumos)
    with tab_pesos:
        mostrar_pesos(base_filtrada)

    with st.expander("Base normalizada en memoria"):
        columnas = ["caja", "centro_norm", "categoria_norm", "peso_kg", "categoria_vacia", "peso_vacio"]
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

from __future__ import annotations

from io import BytesIO, StringIO
import re
import unicodedata

import pandas as pd


COL_CAJA = "N\u00b0 de Caja"
COL_CENTRO = "Centro de Acopio"
COL_CATEGORIA = "Categor\u00eda de insumo"

PATRON_CA11 = r"^CA-11-"
SEPARADOR_LISTAS = " | "

ALIAS_COLUMNAS = {
    "caja": [
        "N\u00b0 de Caja",
        "Nro de Caja",
        "Numero de Caja",
        "N\u00famero de Caja",
        "N\u00ba de Caja",
        "N\u00ba Caja",
        "Caja",
        "Codigo de Caja",
        "C\u00f3digo de Caja",
        "N\u00c2\u00b0 de Caja",
        "N\u00ef\u00bf\u00bd de Caja",
        "N\ufffd de Caja",
    ],
    "centro": [
        "Centro de Acopio",
        "Centro",
        "Centro de Distribucion",
        "Centro de Distribuci\u00f3n",
    ],
    "categoria": [
        "Categor\u00eda de insumo",
        "Categoria de insumo",
        "Categor\u00c3\u00ada de insumo",
        "Categor\ufffda de insumo",
        "Categoria",
        "Categor\u00eda",
        "Insumo",
    ],
}


def leer_csv_robusto(origen) -> pd.DataFrame:
    """Lee CSV desde ruta, URL, bytes o archivo subido."""
    if hasattr(origen, "read"):
        contenido = origen.read()
        if isinstance(contenido, str):
            contenido = contenido.encode("utf-8")
        return _leer_csv_desde_bytes(contenido)

    if isinstance(origen, bytes):
        return _leer_csv_desde_bytes(origen)

    ultimo_error = None
    for encoding in ["utf-8-sig", "utf-8", "latin1"]:
        try:
            return pd.read_csv(origen, encoding=encoding)
        except UnicodeDecodeError as exc:
            ultimo_error = exc

    raise ultimo_error


def _leer_csv_desde_bytes(contenido: bytes) -> pd.DataFrame:
    ultimo_error = None
    for encoding in ["utf-8-sig", "utf-8", "latin1"]:
        try:
            return pd.read_csv(BytesIO(contenido), encoding=encoding)
        except UnicodeDecodeError as exc:
            ultimo_error = exc
    raise ultimo_error


def quitar_acentos(valor) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    return "".join(caracter for caracter in texto if not unicodedata.combining(caracter))


def normalizar_texto(valor):
    """
    Normaliza sin alterar la fuente original.

    Importante: solo se estandariza el separador "/".
    No se convierten coma, punto y coma, +, Y ni E en separadores.
    """
    if pd.isna(valor):
        return pd.NA

    texto = quitar_acentos(valor).upper().strip()
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\s*/\s*", " / ", texto)
    texto = re.sub(r"(?:\s*/\s*)+", " / ", texto)
    texto = texto.strip(" /")

    return texto if texto else pd.NA


def normalizar_para_match(valor) -> str:
    texto = normalizar_texto(valor)
    if pd.isna(texto):
        return ""
    texto = str(texto).replace("\ufffd", "").replace("�", "")
    texto = re.sub(r"[^A-Z0-9]+", "", texto)
    return texto


def resolver_columna(df: pd.DataFrame, clave: str) -> str:
    candidatas = ALIAS_COLUMNAS[clave]

    for candidata in candidatas:
        if candidata in df.columns:
            return candidata

    objetivos = {normalizar_para_match(candidata) for candidata in candidatas}
    for columna in df.columns:
        if normalizar_para_match(columna) in objetivos:
            return columna

    raise ValueError(
        "No se encontro la columna requerida para "
        + clave
        + ". Columnas disponibles: "
        + ", ".join(map(str, df.columns))
    )


def lista_unicos_ordenados(serie: pd.Series) -> str:
    valores = [str(valor).strip() for valor in serie.dropna() if str(valor).strip()]
    return SEPARADOR_LISTAS.join(sorted(set(valores)))


def preparar_base(df: pd.DataFrame, filtrar_ca11: bool = False) -> pd.DataFrame:
    col_caja = resolver_columna(df, "caja")
    col_centro = resolver_columna(df, "centro")
    col_categoria = resolver_columna(df, "categoria")

    base = df.copy()
    base["caja"] = base[col_caja].astype("string").str.strip()
    base["centro_original"] = base[col_centro]
    base["categoria_original"] = base[col_categoria]
    base["centro_norm"] = base[col_centro].apply(normalizar_texto)
    base["categoria_norm"] = base[col_categoria].apply(normalizar_texto)
    base["categoria_vacia"] = base["categoria_norm"].isna()

    base = base.dropna(subset=["caja", "centro_norm"]).copy()

    if filtrar_ca11:
        base = base[base["caja"].str.contains(PATRON_CA11, regex=True, na=False)].copy()

    return base


def aplicar_filtro_centros(base: pd.DataFrame, centros: list[str]) -> pd.DataFrame:
    if not centros:
        return base.copy()
    return base[base["centro_norm"].isin(centros)].copy()


def desagregar_insumos(base: pd.DataFrame) -> pd.DataFrame:
    analizables = base.dropna(subset=["categoria_norm"]).copy()
    analizables["insumo_norm"] = analizables["categoria_norm"].astype("string").str.split("/")
    desagregada = analizables.explode("insumo_norm", ignore_index=True)
    desagregada["insumo_norm"] = desagregada["insumo_norm"].apply(normalizar_texto)
    desagregada = desagregada.dropna(subset=["insumo_norm"]).copy()
    return desagregada


def tabla_insumo_global(base: pd.DataFrame) -> pd.DataFrame:
    desagregada = desagregar_insumos(base)
    if desagregada.empty:
        return pd.DataFrame(
            columns=[
                "insumo_norm",
                "cantidad_cajas",
                "cantidad_instancias",
                "cantidad_centros",
                "cajas",
                "centros",
            ]
        )

    tabla = (
        desagregada.groupby("insumo_norm", dropna=False)
        .agg(
            cantidad_cajas=("caja", "nunique"),
            cantidad_instancias=("insumo_norm", "size"),
            cantidad_centros=("centro_norm", "nunique"),
            cajas=("caja", lista_unicos_ordenados),
            centros=("centro_norm", lista_unicos_ordenados),
        )
        .reset_index()
        .sort_values(["cantidad_cajas", "cantidad_instancias", "insumo_norm"], ascending=[False, False, True])
    )
    return tabla


def resumen_eda(base: pd.DataFrame) -> dict:
    registros_totales = len(base)
    cajas_no_vacias = base["caja"].dropna()
    cantidad_cajas_unicas = cajas_no_vacias.nunique()
    registros_caja_duplicada = int(cajas_no_vacias.duplicated(keep=False).sum())
    cajas_duplicadas = int(cajas_no_vacias[cajas_no_vacias.duplicated(keep=False)].nunique())
    categorias_vacias = int(base["categoria_vacia"].sum())

    return {
        "registros_totales": registros_totales,
        "cajas_unicas": cantidad_cajas_unicas,
        "cajas_duplicadas": cajas_duplicadas,
        "registros_caja_duplicada": registros_caja_duplicada,
        "categorias_vacias": categorias_vacias,
        "centros": int(base["centro_norm"].nunique()),
    }


def detalle_cajas_duplicadas(base: pd.DataFrame) -> pd.DataFrame:
    conteo = (
        base.groupby("caja", dropna=False)
        .agg(
            cantidad_registros=("caja", "size"),
            centros=("centro_norm", lista_unicos_ordenados),
            categorias=("categoria_norm", lista_unicos_ordenados),
        )
        .reset_index()
    )
    return conteo[conteo["cantidad_registros"] > 1].sort_values(
        ["cantidad_registros", "caja"], ascending=[False, True]
    )


def dataframe_a_csv_bytes(df: pd.DataFrame) -> bytes:
    salida = StringIO()
    df.to_csv(salida, index=False)
    return salida.getvalue().encode("utf-8-sig")


def google_sheet_csv_url(url: str, gid_default: str = "0") -> str:
    """Convierte un enlace publico de Google Sheets a URL de export CSV."""
    url = (url or "").strip()
    if not url:
        return ""
    if "output=csv" in url or "format=csv" in url:
        return url

    match = re.search(r"/spreadsheets/d/([^/]+)", url)
    if not match:
        return url

    sheet_id = match.group(1)
    gid_match = re.search(r"[#&?]gid=([0-9]+)", url)
    gid = gid_match.group(1) if gid_match else gid_default
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

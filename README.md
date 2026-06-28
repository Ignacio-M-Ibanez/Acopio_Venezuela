# Dashboard Streamlit de inventario

Este paquete contiene dos apps:

- `app.py`: una sola app con selector `Total` / `Solo CA-11`.
- `app_total.py`: analiza toda la base.
- `app_ca11.py`: analiza solo cajas cuyo codigo empieza con `CA-11-`.

La app no edita Google Sheets. Lee la hoja publica como CSV, copia los datos en memoria, normaliza y calcula las tablas para visualizacion.

## Ejecutar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

Tambien puedes correr cada vista por separado:

```bash
streamlit run app_total.py
```

Para la version CA-11:

```bash
streamlit run app_ca11.py
```

## Automatizar el enlace de Google Sheets

La app puede funcionar con dos fuentes:

- `CSV manual`: recomendado si restringieron el acceso al Google Sheet.
- `Google Sheets`: recomendado si la hoja esta publica o publicada como CSV.

En modo `CSV manual`, carga el archivo desde la barra lateral. La app lo procesa solo en memoria y no modifica el archivo original.

En modo `Google Sheets`, la app acepta el enlace publico desde la barra lateral, pero para no pegarlo cada vez puedes dejarlo fijo de tres maneras.

Opcion simple local: edita `config.py` y pega el enlace una sola vez:

```python
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/ID_DE_LA_HOJA/edit#gid=0"
```

Opcion recomendada para Streamlit Cloud: usa Secrets. En local crea:

```text
.streamlit/secrets.toml
```

con:

```toml
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/ID_DE_LA_HOJA/edit#gid=0"
```

En Streamlit Community Cloud, pega esa misma variable en `Settings > Secrets`.

Si Streamlit Cloud muestra un error HTTP al leer la hoja, aunque localmente funcione, usa este camino:

1. Abre Google Sheets.
2. Ve a `Archivo > Compartir > Publicar en la web`.
3. Elige la pestana de datos.
4. Elige formato `Valores separados por comas (.csv)` si aparece disponible.
5. Copia el enlace publicado y usalo como `GOOGLE_SHEET_URL`.

La app sigue leyendo solamente. No escribe ni modifica la hoja original.

Tercera opcion: variable de entorno:

```bash
GOOGLE_SHEET_URL="https://docs.google.com/spreadsheets/d/ID_DE_LA_HOJA/edit#gid=0"
```

El orden de prioridad es: variable de entorno, `secrets.toml`, `config.py`, campo manual en la barra lateral.

## Publicar con Streamlit Community Cloud

1. Sube esta carpeta a un repositorio de GitHub.
2. Entra a Streamlit Community Cloud.
3. Crea una nueva app o usa el boton `Deploy`.
4. Elige el repositorio.
5. En `Main file path`, usa:

```text
app.py
```

6. Revisa que `requirements.txt` este en la misma carpeta de la app.
7. En `Settings > Secrets`, agrega:

```toml
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/ID_DE_LA_HOJA/edit#gid=0"
```

8. Despliega. La URL resultante queda accesible desde navegador.

Si quieres dos URLs publicas separadas, crea dos apps en Streamlit Cloud:

- una con `Main file path = app_total.py`
- otra con `Main file path = app_ca11.py`

## Que calcula

- Total de registros de la vista actual.
- Cajas unicas.
- Cantidad de centros.
- Cajas duplicadas segun `N° de Caja`.
- Categorias vacias como `campo vacio` con la aclaracion `(posible carga en proceso)`.
- Filtro por `Centro de Acopio`.
- Tabla de insumos normalizados ordenada de mayor a menor por cantidad de cajas.
- Grafico de barras con cantidad de cajas por insumo normalizado.

## Normalizacion

La normalizacion se hace solo en memoria:

- Mayusculas.
- Sin acentos.
- Espacios colapsados.
- Separador `/` estandarizado.

La desagregacion de insumos usa exclusivamente `/`.

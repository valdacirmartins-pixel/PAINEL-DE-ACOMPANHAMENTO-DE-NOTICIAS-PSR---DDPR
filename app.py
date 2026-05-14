# ============================================================
# IMPORTS
# ============================================================

import os
import traceback
from datetime import datetime
from io import StringIO

import dash
from dash import dcc, html, Input, Output, State, dash_table
from dash.exceptions import PreventUpdate
from dash.dcc import send_data_frame

import pandas as pd
import plotly.express as px

import folium
from folium.plugins import MarkerCluster

from flask import request, session, redirect, url_for, render_template_string
from sqlalchemy import create_engine, text

from gerenciador_usuarios import (
    criar_tabelas_auth,
    criar_admin_inicial,
    autenticar_usuario,
    validar_sessao,
    encerrar_sessao,
    listar_usuarios,
    criar_usuario,
    listar_logs_acesso,
    ativar_usuario,
    desativar_usuario,
    resetar_senha,
)


# ============================================================
# CONFIGURAÇÕES
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não encontrada. Configure essa variável no Railway."
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

ARQ_MAPA_HTML = "/tmp/mapa.html"
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Sao_Paulo")


# ============================================================
# INICIALIZAÇÃO DO BANCO
# ============================================================

def criar_tabela_pop_rua():
    sql = """
    CREATE TABLE IF NOT EXISTS pop_rua (
        id SERIAL PRIMARY KEY,
        titulo TEXT,
        url TEXT UNIQUE,
        municipio TEXT,
        uf VARCHAR(2),
        categoria TEXT,
        latitude DOUBLE PRECISION,
        longitude DOUBLE PRECISION,
        data_coleta TIMESTAMP,
        data_publicacao TIMESTAMP NULL,
        query_origem TEXT,
        criado_em TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS ix_pop_rua_municipio ON pop_rua (municipio);
    CREATE INDEX IF NOT EXISTS ix_pop_rua_uf ON pop_rua (uf);
    CREATE INDEX IF NOT EXISTS ix_pop_rua_categoria ON pop_rua (categoria);
    CREATE INDEX IF NOT EXISTS ix_pop_rua_data_coleta ON pop_rua (data_coleta);
    """

    with engine.begin() as conn:
        conn.execute(text(sql))


def inicializar_banco():
    try:
        criar_tabelas_auth()
        criar_admin_inicial()
        criar_tabela_pop_rua()

        print("✅ Banco inicializado com sucesso.", flush=True)

    except Exception as e:
        print(f"⚠️ Falha ao inicializar banco: {e}", flush=True)
        traceback.print_exc()


inicializar_banco()


# ============================================================
# APP DASH
# ============================================================

app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    title="Painel Pop Rua"
)

server = app.server
server.secret_key = os.getenv(
    "SECRET_KEY",
    "dev-secret-key-change-me"
)


# ============================================================
# ADMIN CSS
# ============================================================

ADMIN_CSS = """
<style>
body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f3f4f6;
    color: #111827;
}

.wrap {
    max-width: 1180px;
    margin: 30px auto;
    padding: 0 18px;
}

.card {
    background: white;
    border-radius: 16px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.08);
    padding: 22px;
    margin-bottom: 18px;
}

.topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    margin-bottom: 18px;
}

h1, h2, h3 {
    margin: 0;
}

.muted {
    color: #6b7280;
    font-size: 14px;
    margin-top: 6px;
}

.grid {
    display: grid;
    grid-template-columns: 1.2fr 1.5fr 1fr 1fr auto;
    gap: 10px;
    align-items: end;
}

label {
    display: block;
    font-size: 13px;
    font-weight: 700;
    color: #374151;
    margin-bottom: 6px;
}

input, select {
    width: 100%;
    height: 40px;
    border: 1px solid #d1d5db;
    border-radius: 10px;
    padding: 0 10px;
    box-sizing: border-box;
}

button, .btn {
    border: none;
    border-radius: 10px;
    padding: 11px 15px;
    cursor: pointer;
    font-weight: 700;
    text-decoration: none;
    display: inline-block;
    font-size: 14px;
}

.btn-primary {
    background: #2563eb;
    color: white;
}

.btn-dark {
    background: #1f2937;
    color: white;
}

.btn-danger {
    background: #b91c1c;
    color: white;
}

.btn-light {
    background: #e5e7eb;
    color: #111827;
}

.btn-warning {
    background: #f59e0b;
    color: #111827;
}

.msg {
    padding: 12px 14px;
    border-radius: 12px;
    margin-bottom: 16px;
    font-weight: 600;
}

.msg.ok {
    background: #ecfdf5;
    color: #047857;
    border: 1px solid #a7f3d0;
}

.msg.err {
    background: #fef2f2;
    color: #b91c1c;
    border: 1px solid #fecaca;
}

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

th, td {
    text-align: left;
    padding: 10px;
    border-bottom: 1px solid #e5e7eb;
    vertical-align: middle;
}

th {
    background: #f9fafb;
    color: #374151;
    font-weight: 800;
}

.pill {
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    display: inline-block;
}

.pill.ok {
    background: #dcfce7;
    color: #166534;
}

.pill.no {
    background: #fee2e2;
    color: #991b1b;
}

.actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
}

.actions form {
    margin: 0;
    display: inline-flex;
    gap: 6px;
}

.login-card {
    max-width: 390px;
    margin: 90px auto;
}

@media (max-width: 900px) {
    .grid {
        grid-template-columns: 1fr;
    }

    .topbar {
        flex-direction: column;
        align-items: flex-start;
    }

    table {
        font-size: 12px;
    }
}
</style>
"""


# ============================================================
# HELPERS
# ============================================================

def log_erro(contexto, erro):
    print(f"❌ ERRO EM {contexto}: {erro}", flush=True)
    traceback.print_exc()


def mensagem_erro_usuario(contexto, erro):
    return (
        f"Ocorreu um erro ao processar {contexto}. "
        f"Resumo: {type(erro).__name__}: {erro}"
    )


def obter_ip_requisicao():
    forwarded_for = request.headers.get("X-Forwarded-For", "")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.remote_addr


def obter_user_agent():
    return request.headers.get("User-Agent", "")


def obter_usuario_por_token(token):
    if not token:
        return None

    try:
        return validar_sessao(token)

    except Exception as e:
        log_erro("validar_sessao", e)
        return None


def usuario_eh_admin(usuario):
    return bool(
        usuario and usuario.get("perfil") == "admin"
    )


def resolver_token(
    token=None,
    token_contexto=None,
    usuario_store=None
):
    if token:
        return token

    if token_contexto:
        return token_contexto

    if isinstance(usuario_store, dict):
        return usuario_store.get("token_sessao")

    return None


def formatar_numero(valor):
    try:
        return f"{int(valor):,}".replace(",", ".")
    except Exception:
        return "0"


def converter_datetime_serie(serie):
    dt = pd.to_datetime(
        serie,
        errors="coerce",
        utc=True
    )

    try:
        dt = dt.dt.tz_convert(APP_TIMEZONE).dt.tz_localize(None)

    except Exception:
        dt = dt.dt.tz_localize(None)

    return dt


def ler_json_dataframe(dados_json):
    if not dados_json:
        return pd.DataFrame()

    return pd.read_json(
        StringIO(dados_json),
        orient="split"
    )


# ============================================================
# BANCO DE DADOS
# ============================================================

def carregar_dados_banco():
    sql = """
    SELECT
        id,
        titulo,
        url,
        municipio,
        uf,
        categoria,
        latitude,
        longitude,
        data_coleta,
        data_publicacao,
        query_origem,
        criado_em
    FROM pop_rua
    ORDER BY data_coleta DESC NULLS LAST, id DESC;
    """

    try:
        df = pd.read_sql(sql, engine)

    except Exception as e:
        log_erro("carregar_dados_banco", e)
        df = pd.DataFrame()

    return tratar_dataframe(df)


def tratar_dataframe(df):
    df = df.copy()

    colunas_necessarias = [
        "id",
        "titulo",
        "url",
        "municipio",
        "uf",
        "categoria",
        "latitude",
        "longitude",
        "data_coleta",
        "data_publicacao",
        "query_origem",
        "criado_em"
    ]

    for coluna in colunas_necessarias:
        if coluna not in df.columns:
            df[coluna] = None

    for coluna in [
        "municipio",
        "uf",
        "categoria",
        "titulo",
        "url",
        "query_origem"
    ]:
        df[coluna] = (
            df[coluna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    df["municipio"] = df["municipio"].replace("", "Não identificado")
    df["uf"] = df["uf"].replace("", "NI")
    df["categoria"] = df["categoria"].replace("", "Outros")

    df["latitude"] = pd.to_numeric(
        df["latitude"],
        errors="coerce"
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"],
        errors="coerce"
    )

    df["data_coleta"] = converter_datetime_serie(df["data_coleta"])
    df["data_publicacao"] = converter_datetime_serie(df["data_publicacao"])
    df["criado_em"] = converter_datetime_serie(df["criado_em"])

    df["data"] = df["data_publicacao"].fillna(df["data_coleta"])

    df["quantidade"] = 1

    return df


# ============================================================
# MAPA E GRÁFICOS
# ============================================================

def gerar_mapa_html(df):

    mapa = folium.Map(
        location=[-14.2350, -51.9253],
        zoom_start=5,
        tiles="CartoDB positron"
    )

    if df.empty:

        mapa.save(ARQ_MAPA_HTML)

        with open(ARQ_MAPA_HTML, encoding="utf-8") as f:
            return f.read()

    marker_cluster = MarkerCluster(
        disableClusteringAtZoom=10
    ).add_to(mapa)

    for _, row in df.iterrows():

        latitude = row.get("latitude")
        longitude = row.get("longitude")

        if pd.isna(latitude) or pd.isna(longitude):
            continue

        popup = f"""
        <b>Município:</b> {row.get('municipio')}<br>
        <b>UF:</b> {row.get('uf')}<br>
        <b>Categoria:</b> {row.get('categoria')}<br>
        """

        folium.CircleMarker(
            location=[latitude, longitude],
            radius=5,
            popup=popup,
            color="#2563eb",
            fill=True,
            fill_color="#3b82f6",
            fill_opacity=0.55
        ).add_to(marker_cluster)

    mapa.save(ARQ_MAPA_HTML)

    with open(ARQ_MAPA_HTML, encoding="utf-8") as f:
        return f.read()


def criar_figura_vazia(titulo):

    fig = px.scatter(title=titulo)

    fig.update_layout(
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": "Sem dados para exibir",
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "font": {"size": 16}
            }
        ]
    )

    return fig


def card_resumo(titulo, valor, subtitulo=None):

    return html.Div(
        [
            html.Div(
                titulo,
                style={
                    "fontSize": "13px",
                    "color": "#666",
                    "marginBottom": "6px"
                }
            ),

            html.Div(
                valor,
                style={
                    "fontSize": "26px",
                    "fontWeight": "700",
                    "color": "#222"
                }
            ),

            html.Div(
                subtitulo or "",
                style={
                    "fontSize": "12px",
                    "color": "#777",
                    "marginTop": "4px"
                }
            )
        ],
        style={
            "backgroundColor": "#ffffff",
            "padding": "18px",
            "borderRadius": "14px",
            "boxShadow": "0 4px 14px rgba(0,0,0,0.08)",
            "minWidth": "180px",
            "flex": "1"
        }
    )


def aplicar_filtros(
    df,
    ufs,
    municipios,
    categorias,
    data_ini,
    data_fim,
    texto_busca
):

    df = df.copy()

    if ufs:
        df = df[df["uf"].isin(ufs)]

    if municipios:
        df = df[df["municipio"].isin(municipios)]

    if categorias:
        df = df[df["categoria"].isin(categorias)]

    if data_ini:

        data_ini = pd.to_datetime(
            data_ini,
            errors="coerce"
        )

        if pd.notna(data_ini):
            df = df[df["data"] >= data_ini]

    if data_fim:

        data_fim = pd.to_datetime(
            data_fim,
            errors="coerce"
        )

        if pd.notna(data_fim):
            data_fim = data_fim + pd.Timedelta(days=1)
            df = df[df["data"] < data_fim]

    if texto_busca:

        texto = str(texto_busca).lower().strip()

        if texto:

            mascara = (
                df["titulo"].astype(str).str.lower().str.contains(
                    texto,
                    na=False,
                    regex=False
                )
                |
                df["municipio"].astype(str).str.lower().str.contains(
                    texto,
                    na=False,
                    regex=False
                )
                |
                df["categoria"].astype(str).str.lower().str.contains(
                    texto,
                    na=False,
                    regex=False
                )
                |
                df["query_origem"].astype(str).str.lower().str.contains(
                    texto,
                    na=False,
                    regex=False
                )
            )

            df = df[mascara]

    return df


# ============================================================
# LAYOUT
# ============================================================

app.layout = html.Div(
    [
        dcc.Location(id="url"),

        dcc.Store(
            id="sessao_token",
            storage_type="local"
        ),

        dcc.Store(
            id="usuario_logado",
            storage_type="session"
        ),

        html.Div(id="pagina_container")
    ]
)


# ============================================================
# CALLBACK: DASHBOARD
# ============================================================

@app.callback(
    [
        Output("mapa_html", "srcDoc"),
        Output("grafico_categoria", "figure"),
        Output("grafico_uf", "figure"),
        Output("grafico_tempo", "figure"),
        Output("tabela", "data"),
        Output("cards_resumo", "children"),
        Output("insight", "children"),
        Output("dados_filtrados", "data")
    ],
    [
        Input("dados_base", "data"),
        Input("filtro_uf", "value"),
        Input("filtro_municipio", "value"),
        Input("filtro_categoria", "value"),
        Input("filtro_data", "start_date"),
        Input("filtro_data", "end_date"),
        Input("filtro_texto", "value")
    ],
    [
        State("sessao_token", "data"),
        State("token_contexto", "data"),
        State("usuario_logado", "data")
    ]
)
def atualizar_dashboard(
    dados_base,
    ufs,
    municipios,
    categorias,
    data_ini,
    data_fim,
    texto_busca,
    token,
    token_contexto,
    usuario_store
):

    try:

        token = resolver_token(
            token,
            token_contexto,
            usuario_store
        )

        if not token:
            raise PreventUpdate

        usuario = obter_usuario_por_token(token)

        if not usuario:
            raise PreventUpdate

        if not dados_base:
            df = carregar_dados_banco()

        else:
            df = ler_json_dataframe(dados_base)
            df = tratar_dataframe(df)

        # ============================================================
        # FILTROS
        # ============================================================

        df_filtrado = aplicar_filtros(
            df=df,
            ufs=ufs,
            municipios=municipios,
            categorias=categorias,
            data_ini=data_ini,
            data_fim=data_fim,
            texto_busca=texto_busca
        )

        # ============================================================
        # MAPA
        # ============================================================

        mapa_html = gerar_mapa_html(df_filtrado)

        # ============================================================
        # GRÁFICO CATEGORIA
        # ============================================================

        if df_filtrado.empty:

            fig_categoria = criar_figura_vazia(
                "Registros por categoria"
            )

        else:

            df_categoria = (
                df_filtrado
                .groupby("categoria")
                .size()
                .reset_index(name="qtd")
                .sort_values("qtd", ascending=True)
            )

            fig_categoria = px.bar(
                df_categoria,
                x="qtd",
                y="categoria",
                orientation="h",
                title="Registros por categoria",
                text="qtd"
            )

        # ============================================================
        # GRÁFICO UF
        # ============================================================

        if df_filtrado.empty:

            fig_uf = criar_figura_vazia(
                "Registros por UF"
            )

        else:

            df_uf = (
                df_filtrado
                .groupby("uf")
                .size()
                .reset_index(name="qtd")
                .sort_values("qtd", ascending=True)
            )

            fig_uf = px.bar(
                df_uf,
                x="qtd",
                y="uf",
                orientation="h",
                title="Registros por UF",
                text="qtd"
            )

        # ============================================================
        # GRÁFICO TEMPO
        # ============================================================

        if df_filtrado.empty:

            fig_tempo = criar_figura_vazia(
                "Evolução no tempo"
            )

        else:

            df_tempo = (
                df_filtrado
                .groupby("data")
                .size()
                .reset_index(name="qtd")
            )

            fig_tempo = px.line(
                df_tempo,
                x="data",
                y="qtd",
                title="Evolução no tempo"
            )

        # ============================================================
        # TABELA
        # ============================================================

        tabela_df = df_filtrado.copy()

        # ============================================================
        # CARDS
        # ============================================================

        cards = [
            card_resumo(
                "Total de registros",
                str(len(df_filtrado))
            ),

            card_resumo(
                "Municípios",
                str(df_filtrado["municipio"].nunique())
            ),

            card_resumo(
                "UFs",
                str(df_filtrado["uf"].nunique())
            ),

            card_resumo(
                "Categorias",
                str(df_filtrado["categoria"].nunique())
            )
        ]

        # ============================================================
        # INSIGHT
        # ============================================================

        if df_filtrado.empty:

            insight = (
                "Sem dados para os filtros selecionados."
            )

        else:

            insight = (
                f"Total filtrado: {len(df_filtrado)} registros."
            )

        # ============================================================
        # JSON FILTRADO
        # ============================================================

        dados_filtrados = df_filtrado.to_json(
            date_format="iso",
            orient="split"
        )

        # ============================================================
        # RETURN
        # ============================================================

        return (
            mapa_html,
            fig_categoria,
            fig_uf,
            fig_tempo,
            tabela_df.to_dict("records"),
            cards,
            insight,
            dados_filtrados
        )

    except PreventUpdate:
        raise

    except Exception as e:

        log_erro("atualizar_dashboard", e)

        df_vazio = pd.DataFrame(
            columns=[
                "data",
                "municipio",
                "uf",
                "categoria",
                "titulo",
                "url",
                "query_origem"
            ]
        )

        return (
            "",
            criar_figura_vazia("Registros por categoria"),
            criar_figura_vazia("Registros por UF"),
            criar_figura_vazia("Evolução no tempo"),
            df_vazio.to_dict("records"),
            [
                card_resumo("Total de registros", "0"),
                card_resumo("Municípios", "0"),
                card_resumo("UFs", "0"),
                card_resumo("Categorias", "0")
            ],
            mensagem_erro_usuario(
                "atualizar dashboard",
                e
            ),
            df_vazio.to_json(
                date_format="iso",
                orient="split"
            )
        )


# ============================================================
# CALLBACK: EXPORTAR CSV
# ============================================================

@app.callback(
    Output("download_csv", "data"),
    Input("btn_exportar", "n_clicks"),
    State("dados_filtrados", "data"),
    State("sessao_token", "data"),
    State("token_contexto", "data"),
    State("usuario_logado", "data"),
    prevent_initial_call=True
)
def exportar_csv(
    n_clicks,
    dados_filtrados,
    token,
    token_contexto,
    usuario_store
):

    try:

        token = resolver_token(
            token,
            token_contexto,
            usuario_store
        )

        if not token:
            raise PreventUpdate

        usuario = obter_usuario_por_token(token)

        if not usuario or not n_clicks:
            raise PreventUpdate

        if dados_filtrados:

            df_export = ler_json_dataframe(
                dados_filtrados
            )

            df_export = tratar_dataframe(df_export)

        else:

            df_export = carregar_dados_banco()

        colunas_export = [
            "id",
            "titulo",
            "url",
            "municipio",
            "uf",
            "categoria",
            "latitude",
            "longitude",
            "data_coleta",
            "data_publicacao",
            "query_origem",
            "criado_em"
        ]

        for coluna in colunas_export:

            if coluna not in df_export.columns:
                df_export[coluna] = None

        df_export = df_export[colunas_export]

        return send_data_frame(
            df_export.to_csv,
            "pop_rua_filtrado.csv",
            index=False,
            sep=";",
            encoding="utf-8-sig"
        )

    except PreventUpdate:
        raise

    except Exception as e:
        log_erro("exportar_csv", e)
        return dash.no_update


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8050)),
        debug=True
    )

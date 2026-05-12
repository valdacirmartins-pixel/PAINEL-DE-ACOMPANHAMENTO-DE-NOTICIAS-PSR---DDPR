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
        data_coleta TIMESTAMP ,
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
server.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")



# ============================================================
# GERENCIADOR DE USUÁRIOS VIA FLASK
# ============================================================
# Esta área evita depender de callbacks dinâmicos do Dash para criar usuários.
# O Dashboard continua igual; apenas a gestão de usuários passa a usar rotas Flask
# protegidas por sessão server-side.

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
    h1, h2, h3 { margin: 0; }
    .muted { color: #6b7280; font-size: 14px; margin-top: 6px; }
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
    .btn-primary { background: #2563eb; color: white; }
    .btn-dark { background: #1f2937; color: white; }
    .btn-danger { background: #b91c1c; color: white; }
    .btn-light { background: #e5e7eb; color: #111827; }
    .btn-warning { background: #f59e0b; color: #111827; }
    .msg {
        padding: 12px 14px;
        border-radius: 12px;
        margin-bottom: 16px;
        font-weight: 600;
    }
    .msg.ok { background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }
    .msg.err { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
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
    .pill.ok { background: #dcfce7; color: #166534; }
    .pill.no { background: #fee2e2; color: #991b1b; }
    .actions {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
    }
    .actions form { margin: 0; display: inline-flex; gap: 6px; }
    .login-card {
        max-width: 390px;
        margin: 90px auto;
    }
    @media (max-width: 900px) {
        .grid { grid-template-columns: 1fr; }
        .topbar { flex-direction: column; align-items: flex-start; }
        table { font-size: 12px; }
    }
</style>
"""


def admin_usuario_atual():
    token = session.get("admin_token")
    if not token:
        return None

    usuario = obter_usuario_por_token(token)
    if not usuario or usuario.get("perfil") != "admin":
        return None

    return usuario


def admin_redirect_se_necessario():
    if not admin_usuario_atual():
        return redirect(url_for("admin_login"))
    return None


@server.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    erro = ""

    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        resultado = autenticar_usuario(
            email=email,
            senha=senha,
            ip=obter_ip_requisicao(),
            user_agent=obter_user_agent()
        )

        if resultado.get("ok") and resultado.get("usuario", {}).get("perfil") == "admin":
            session["admin_token"] = resultado["token_sessao"]
            return redirect(url_for("admin_usuarios"))

        if resultado.get("ok") and resultado.get("token_sessao"):
            encerrar_sessao(resultado["token_sessao"])

        erro = "Acesso negado. Use um usuário com perfil admin."

    return render_template_string(
        """
        <!doctype html>
        <html lang="pt-br">
        <head>
            <meta charset="utf-8">
            <title>Login Admin - Painel Pop Rua</title>
            {{ css|safe }}
        </head>
        <body>
            <div class="wrap">
                <div class="card login-card">
                    <h1>Painel Pop Rua</h1>
                    <p class="muted">Área administrativa de usuários</p>

                    {% if erro %}
                        <div class="msg err">{{ erro }}</div>
                    {% endif %}

                    <form method="post">
                        <label>E-mail</label>
                        <input name="email" type="email" required autocomplete="username">

                        <br><br>

                        <label>Senha</label>
                        <input name="senha" type="password" required autocomplete="current-password">

                        <br><br>

                        <button class="btn btn-dark" type="submit" style="width:100%;">Entrar</button>
                    </form>

                    <p class="muted" style="margin-top:18px;">
                        Voltar para o dashboard:
                        <a href="/" style="color:#2563eb;font-weight:700;">abrir painel</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """,
        css=ADMIN_CSS,
        erro=erro
    )


@server.route("/admin/logout", methods=["POST", "GET"])
def admin_logout():
    token = session.get("admin_token")
    if token:
        encerrar_sessao(token)
    session.pop("admin_token", None)
    return redirect(url_for("admin_login"))


@server.route("/admin/usuarios", methods=["GET", "POST"])
def admin_usuarios():
    redir = admin_redirect_se_necessario()
    if redir:
        return redir

    usuario_admin = admin_usuario_atual()
    msg = ""
    msg_tipo = "ok"

    if request.method == "POST":
        nome = str(request.form.get("nome") or "").strip()
        email = str(request.form.get("email") or "").strip().lower()
        senha = str(request.form.get("senha") or "")
        perfil = str(request.form.get("perfil") or "usuario").strip().lower()

        try:
            novo_id = criar_usuario(
                nome=nome,
                email=email,
                senha=senha,
                perfil=perfil,
                primeiro_acesso=True
            )
            msg = f"Usuário criado com sucesso. ID: {novo_id}."
            msg_tipo = "ok"
        except Exception as e:
            msg = f"Erro ao criar usuário: {e}"
            msg_tipo = "err"

    usuarios = listar_usuarios()
    logs = listar_logs_acesso(limit=20)

    return render_template_string(
        """
        <!doctype html>
        <html lang="pt-br">
        <head>
            <meta charset="utf-8">
            <title>Usuários - Painel Pop Rua</title>
            {{ css|safe }}
        </head>
        <body>
            <div class="wrap">
                <div class="topbar">
                    <div>
                        <h1>Gerenciamento de usuários</h1>
                        <p class="muted">
                            Logado como <strong>{{ admin.nome }}</strong> — {{ admin.email }}
                        </p>
                    </div>

                    <div>
                        <a class="btn btn-light" href="/">Dashboard</a>
                        <a class="btn btn-light" href="{{ url_for('admin_logs') }}">Logs</a>
                        <a class="btn btn-danger" href="{{ url_for('admin_logout') }}">Sair</a>
                    </div>
                </div>

                {% if msg %}
                    <div class="msg {{ msg_tipo }}">{{ msg }}</div>
                {% endif %}

                <div class="card">
                    <h2>Criar novo usuário</h2>
                    <p class="muted">Atenção na criação do usuário.</p>

                    <form method="post" class="grid">
                        <div>
                            <label>Nome</label>
                            <input name="nome" type="text" required>
                        </div>

                        <div>
                            <label>E-mail</label>
                            <input name="email" type="email" required>
                        </div>

                        <div>
                            <label>Senha inicial</label>
                            <input name="senha" type="password" required minlength="6">
                        </div>

                        <div>
                            <label>Perfil</label>
                            <select name="perfil">
                                <option value="usuario">Usuário</option>
                                <option value="visualizador">Visualizador</option>
                                <option value="gestor">Gestor</option>
                                <option value="admin">Admin</option>
                            </select>
                        </div>

                        <div>
                            <button class="btn btn-primary" type="submit">Criar usuário</button>
                        </div>
                    </form>
                </div>

                <div class="card">
                    <h2>Usuários cadastrados</h2>
                    <p class="muted">Total: {{ usuarios|length }}</p>

                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Nome</th>
                                <th>E-mail</th>
                                <th>Perfil</th>
                                <th>Ativo</th>
                                <th>Primeiro acesso</th>
                                <th>Senha expirada</th>
                                <th>Último login</th>
                                <th>Ações</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for u in usuarios %}
                                <tr>
                                    <td>{{ u.id }}</td>
                                    <td>{{ u.nome }}</td>
                                    <td>{{ u.email }}</td>
                                    <td>{{ u.perfil }}</td>
                                    <td>
                                        {% if u.ativo %}
                                            <span class="pill ok">ativo</span>
                                        {% else %}
                                            <span class="pill no">inativo</span>
                                        {% endif %}
                                    </td>
                                    <td>{{ u.primeiro_acesso }}</td>
                                    <td>{{ u.senha_expirada }}</td>
                                    <td>{{ u.ultimo_login or "" }}</td>
                                    <td>
                                        <div class="actions">
                                            {% if u.ativo %}
                                                <form method="post" action="{{ url_for('admin_desativar_usuario', usuario_id=u.id) }}">
                                                    <button class="btn btn-warning" type="submit">Desativar</button>
                                                </form>
                                            {% else %}
                                                <form method="post" action="{{ url_for('admin_ativar_usuario', usuario_id=u.id) }}">
                                                    <button class="btn btn-primary" type="submit">Ativar</button>
                                                </form>
                                            {% endif %}

                                            <form method="post" action="{{ url_for('admin_resetar_senha_usuario', usuario_id=u.id) }}">
                                                <input name="senha_temporaria" type="password" placeholder="Nova senha" minlength="6" required style="width:120px;height:36px;">
                                                <button class="btn btn-light" type="submit">Reset</button>
                                            </form>
                                        </div>
                                    </td>
                                </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

                <div class="card">
                    <h2>Últimos logs de acesso</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Data</th>
                                <th>E-mail</th>
                                <th>Sucesso</th>
                                <th>Motivo</th>
                                <th>IP</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for l in logs %}
                                <tr>
                                    <td>{{ l.criado_em }}</td>
                                    <td>{{ l.email }}</td>
                                    <td>{{ l.sucesso }}</td>
                                    <td>{{ l.motivo }}</td>
                                    <td>{{ l.ip or "" }}</td>
                                </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """,
        css=ADMIN_CSS,
        admin=usuario_admin,
        usuarios=usuarios,
        logs=logs,
        msg=msg,
        msg_tipo=msg_tipo
    )


@server.route("/admin/logs", methods=["GET"])
def admin_logs():
    redir = admin_redirect_se_necessario()
    if redir:
        return redir

    logs = listar_logs_acesso(limit=300)

    return render_template_string(
        """
        <!doctype html>
        <html lang="pt-br">
        <head>
            <meta charset="utf-8">
            <title>Logs - Painel Pop Rua</title>
            {{ css|safe }}
        </head>
        <body>
            <div class="wrap">
                <div class="topbar">
                    <div>
                        <h1>Logs de acesso</h1>
                        <p class="muted">Últimos 300 registros.</p>
                    </div>

                    <div>
                        <a class="btn btn-light" href="{{ url_for('admin_usuarios') }}">Usuários</a>
                        <a class="btn btn-light" href="/">Dashboard</a>
                        <a class="btn btn-danger" href="{{ url_for('admin_logout') }}">Sair</a>
                    </div>
                </div>

                <div class="card">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Usuário ID</th>
                                <th>E-mail</th>
                                <th>Sucesso</th>
                                <th>Motivo</th>
                                <th>IP</th>
                                <th>User Agent</th>
                                <th>Criado em</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for l in logs %}
                                <tr>
                                    <td>{{ l.id }}</td>
                                    <td>{{ l.usuario_id or "" }}</td>
                                    <td>{{ l.email }}</td>
                                    <td>{{ l.sucesso }}</td>
                                    <td>{{ l.motivo }}</td>
                                    <td>{{ l.ip or "" }}</td>
                                    <td>{{ l.user_agent or "" }}</td>
                                    <td>{{ l.criado_em }}</td>
                                </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """,
        css=ADMIN_CSS,
        logs=logs
    )


@server.route("/admin/usuarios/<int:usuario_id>/desativar", methods=["POST"])
def admin_desativar_usuario(usuario_id):
    redir = admin_redirect_se_necessario()
    if redir:
        return redir

    try:
        desativar_usuario(usuario_id)
    except Exception as e:
        print(f"Erro ao desativar usuário {usuario_id}: {e}", flush=True)

    return redirect(url_for("admin_usuarios"))


@server.route("/admin/usuarios/<int:usuario_id>/ativar", methods=["POST"])
def admin_ativar_usuario(usuario_id):
    redir = admin_redirect_se_necessario()
    if redir:
        return redir

    try:
        ativar_usuario(usuario_id)
    except Exception as e:
        print(f"Erro ao ativar usuário {usuario_id}: {e}", flush=True)

    return redirect(url_for("admin_usuarios"))


@server.route("/admin/usuarios/<int:usuario_id>/resetar-senha", methods=["POST"])
def admin_resetar_senha_usuario(usuario_id):
    redir = admin_redirect_se_necessario()
    if redir:
        return redir

    senha_temporaria = request.form.get("senha_temporaria")

    try:
        resetar_senha(usuario_id, senha_temporaria)
    except Exception as e:
        print(f"Erro ao resetar senha do usuário {usuario_id}: {e}", flush=True)

    return redirect(url_for("admin_usuarios"))


# ============================================================
# HELPERS
# ============================================================

def log_erro(contexto, erro):
    print(f"❌ ERRO EM {contexto}: {erro}", flush=True)
    traceback.print_exc()


def mensagem_erro_usuario(contexto, erro):
    return (
        f"Ocorreu um erro ao processar {contexto}. "
        f"Verifique os logs do Railway para o detalhe técnico. "
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
    return bool(usuario and usuario.get("perfil") == "admin")


def resolver_token(token=None, token_contexto=None, usuario_store=None):
    """
    Resolve o token de sessão a partir de múltiplas fontes.

    Motivo:
    Em alguns fluxos do Dash, principalmente ao alternar abas renderizadas dinamicamente,
    o State do dcc.Store global pode chegar vazio em callbacks específicos.
    Por isso mantemos também um token_contexto dentro do layout autenticado.
    """
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
    """
    Converte datas com ou sem timezone para datetime sem timezone em America/Sao_Paulo.
    Isso evita erros de mixed timezone no Pandas/Plotly/Dash.
    """
    dt = pd.to_datetime(serie, errors="coerce", utc=True)

    try:
        dt = dt.dt.tz_convert(APP_TIMEZONE).dt.tz_localize(None)
    except Exception:
        dt = dt.dt.tz_localize(None)

    return dt


def ler_json_dataframe(dados_json):
    if not dados_json:
        return pd.DataFrame()

    return pd.read_json(StringIO(dados_json), orient="split")


# ============================================================
# BANCO DE DADOS - POP RUA
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

    for coluna in ["municipio", "uf", "categoria", "titulo", "url", "query_origem"]:
        df[coluna] = df[coluna].fillna("").astype(str).str.strip()

    df["municipio"] = df["municipio"].replace("", "Não identificado")
    df["uf"] = df["uf"].replace("", "NI")
    df["categoria"] = df["categoria"].replace("", "Outros")

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    df["data_coleta"] = converter_datetime_serie(df["data_coleta"])
    df["data_publicacao"] = converter_datetime_serie(df["data_publicacao"])
    df["criado_em"] = converter_datetime_serie(df["criado_em"])

    df["data"] = df["data_publicacao"].fillna(df["data_coleta"])
    df["quantidade"] = 1

    return df


# ============================================================
# MAPA E GRÁFICOS
# ============================================================

def gerar_mapa(df):
    mapa = folium.Map(
        location=[-14.2350, -51.9253],
        zoom_start=4,
        tiles="OpenStreetMap"
    )

    cluster = MarkerCluster().add_to(mapa)

    if not df.empty:
        for _, row in df.iterrows():
            latitude = row.get("latitude")
            longitude = row.get("longitude")

            if pd.isna(latitude) or pd.isna(longitude):
                continue

            municipio = row.get("municipio", "Não identificado")
            uf = row.get("uf", "NI")
            categoria = row.get("categoria", "Outros")
            quantidade = row.get("quantidade", 1)

            popup = f"""
            <b>Município:</b> {municipio}/{uf}<br>
            <b>Categoria:</b> {categoria}<br>
            <b>Quantidade:</b> {quantidade}
            """

            folium.CircleMarker(
                location=[float(latitude), float(longitude)],
                radius=min(float(quantidade) * 2.5, 18),
                fill=True,
                fill_opacity=0.7,
                popup=folium.Popup(popup, max_width=300)
            ).add_to(cluster)

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
            html.Div(titulo, style={"fontSize": "13px", "color": "#666", "marginBottom": "6px"}),
            html.Div(valor, style={"fontSize": "26px", "fontWeight": "700", "color": "#222"}),
            html.Div(subtitulo or "", style={"fontSize": "12px", "color": "#777", "marginTop": "4px"})
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


def aplicar_filtros(df, ufs, municipios, categorias, data_ini, data_fim, texto_busca):
    df = df.copy()

    if ufs:
        df = df[df["uf"].isin(ufs)]

    if municipios:
        df = df[df["municipio"].isin(municipios)]

    if categorias:
        df = df[df["categoria"].isin(categorias)]

    if data_ini:
        data_ini = pd.to_datetime(data_ini, errors="coerce")
        if pd.notna(data_ini):
            df = df[df["data"] >= data_ini]

    if data_fim:
        data_fim = pd.to_datetime(data_fim, errors="coerce")
        if pd.notna(data_fim):
            data_fim = data_fim + pd.Timedelta(days=1)
            df = df[df["data"] < data_fim]

    if texto_busca:
        texto = str(texto_busca).lower().strip()

        if texto:
            mascara = (
                df["titulo"].astype(str).str.lower().str.contains(texto, na=False, regex=False)
                | df["municipio"].astype(str).str.lower().str.contains(texto, na=False, regex=False)
                | df["categoria"].astype(str).str.lower().str.contains(texto, na=False, regex=False)
                | df["query_origem"].astype(str).str.lower().str.contains(texto, na=False, regex=False)
            )
            df = df[mascara]

    return df


# ============================================================
# LAYOUTS
# ============================================================

def layout_login():
    return html.Div(
        [
            html.Div(
                [
                    html.H1("Painel Pop Rua", style={"margin": "0", "fontSize": "30px", "color": "#111827"}),
                    html.P(
                        "Acesse com seu usuário.",
                        style={"marginTop": "8px", "color": "#6b7280"}
                    ),

                    html.Label("E-mail", style={"fontWeight": "600", "color": "#374151"}),
                    dcc.Input(
                        id="login_email",
                        type="email",
                        placeholder="seu.email@dominio.com",
                        autoComplete="username",
                        style={
                            "width": "100%",
                            "height": "42px",
                            "border": "1px solid #d1d5db",
                            "borderRadius": "10px",
                            "padding": "0 12px",
                            "marginTop": "6px",
                            "marginBottom": "14px",
                            "boxSizing": "border-box"
                        }
                    ),

                    html.Label("Senha", style={"fontWeight": "600", "color": "#374151"}),
                    dcc.Input(
                        id="login_senha",
                        type="password",
                        placeholder="Digite sua senha",
                        autoComplete="current-password",
                        style={
                            "width": "100%",
                            "height": "42px",
                            "border": "1px solid #d1d5db",
                            "borderRadius": "10px",
                            "padding": "0 12px",
                            "marginTop": "6px",
                            "marginBottom": "18px",
                            "boxSizing": "border-box"
                        }
                    ),

                    html.Button(
                        "Entrar",
                        id="btn_login",
                        n_clicks=0,
                        style={
                            "width": "100%",
                            "height": "44px",
                            "backgroundColor": "#1f2937",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "10px",
                            "fontWeight": "700",
                            "cursor": "pointer"
                        }
                    ),

                    html.Div(
                        id="login_mensagem",
                        style={"marginTop": "14px", "fontSize": "14px", "color": "#b91c1c"}
                    )
                ],
                style={
                    "width": "380px",
                    "backgro

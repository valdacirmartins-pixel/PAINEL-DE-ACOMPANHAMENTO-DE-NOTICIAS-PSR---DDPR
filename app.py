import os
import traceback
import pandas as pd
import plotly.express as px
import folium
from datetime import datetime
from io import StringIO
from sqlalchemy import create_engine, text
from flask import request, session, redirect, url_for, render_template_string
from dash import Dash, dcc, html, Input, Output, State, dash_table
from dash.exceptions import PreventUpdate
from folium.plugins import MarkerCluster

# Importações do seu módulo customizado
from gerenciador_usuarios import (
    criar_tabelas_auth, criar_admin_inicial, autenticar_usuario,
    validar_sessao, encerrar_sessao, listar_usuarios, criar_usuario,
    listar_logs_acesso, ativar_usuario, desativar_usuario, resetar_senha
)

# ============================================================
# 1. CONFIGURAÇÕES E INICIALIZAÇÃO
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrada. Configure no Railway.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
ARQ_MAPA_HTML = "/tmp/mapa.html"
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Sao_Paulo")

def inicializar_banco():
    """Cria as tabelas necessárias no PostgreSQL do Railway."""
    try:
        criar_tabelas_auth()
        criar_admin_inicial()
        
        sql_pop_rua = """
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
        """
        with engine.begin() as conn:
            conn.execute(text(sql_pop_rua))
        print("✅ Banco inicializado com sucesso.")
    except Exception as e:
        print(f"⚠️ Falha ao inicializar banco: {e}")
        traceback.print_exc()

inicializar_banco()

# ============================================================
# 2. APP DASH & SERVER FLASK
# ============================================================

app = Dash(__name__, suppress_callback_exceptions=True, title="Painel Pop Rua")
server = app.server
server.secret_key = os.getenv("SECRET_KEY", "chave-secreta-de-producao")

# ============================================================
# 3. ESTILOS CSS (ADMIN)
# ============================================================

ADMIN_CSS = """
<style>
    body { margin: 0; font-family: 'Segoe UI', Arial, sans-serif; background: #f3f4f6; color: #111827; }
    .wrap { max-width: 1180px; margin: 30px auto; padding: 0 18px; }
    .card { background: white; border-radius: 16px; box-shadow: 0 4px 14px rgba(0,0,0,0.08); padding: 22px; margin-bottom: 18px; }
    .topbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 18px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; align-items: end; }
    label { display: block; font-size: 13px; font-weight: 700; color: #374151; margin-bottom: 6px; }
    input, select { width: 100%; height: 40px; border: 1px solid #d1d5db; border-radius: 10px; padding: 0 10px; box-sizing: border-box; }
    button, .btn { border: none; border-radius: 10px; padding: 11px 15px; cursor: pointer; font-weight: 700; text-decoration: none; font-size: 14px; display: inline-block; }
    .btn-primary { background: #2563eb; color: white; }
    .btn-dark { background: #1f2937; color: white; }
    .btn-danger { background: #b91c1c; color: white; }
    .btn-light { background: #e5e7eb; color: #111827; }
    .btn-warning { background: #f59e0b; color: #111827; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }
    th, td { text-align: left; padding: 12px; border-bottom: 1px solid #e5e7eb; }
    th { background: #f9fafb; font-weight: 800; }
    .pill { padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; }
    .pill.ok { background: #dcfce7; color: #166534; }
    .pill.no { background: #fee2e2; color: #991b1b; }
</style>
"""

# ============================================================
# 4. ROTAS ADMINISTRATIVAS (FLASK)
# ============================================================

@server.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    erro = ""
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")
        res = autenticar_usuario(email, senha, request.remote_addr, request.headers.get("User-Agent"))
        
        if res.get("ok") and res.get("usuario", {}).get("perfil") == "admin":
            session["admin_token"] = res["token_sessao"]
            return redirect(url_for("admin_usuarios"))
        erro = "Acesso negado. Apenas administradores."

    return render_template_string("""
        <html><head>{{ css|safe }}</head><body>
        <div class="wrap"><div class="card" style="max-width:400px; margin:auto;">
            <h1>Admin Login</h1>
            {% if erro %}<p style="color:red">{{ erro }}</p>{% endif %}
            <form method="post">
                <label>E-mail</label><input name="email" type="email" required>
                <label>Senha</label><input name="senha" type="password" required><br><br>
                <button class="btn btn-dark" style="width:100%">Entrar</button>
            </form>
        </div></div></body></html>
    """, css=ADMIN_CSS, erro=erro)

@server.route("/admin/usuarios")
def admin_usuarios():
    token = session.get("admin_token")
    user_data = validar_sessao(token) if token else None
    if not user_data or user_data.get("perfil") != "admin":
        return redirect(url_for("admin_login"))
    
    usuarios = listar_usuarios()
    return render_template_string("""
        <html><head>{{ css|safe }}</head><body>
        <div class="wrap">
            <div class="topbar">
                <h1>Gerenciamento de Usuários</h1>
                <a href="/" class="btn btn-light">Voltar ao Painel</a>
            </div>
            <div class="card">
                <table>
                    <thead><tr><th>Nome</th><th>E-mail</th><th>Perfil</th><th>Status</th></tr></thead>
                    <tbody>
                        {% for u in usuarios %}
                        <tr>
                            <td>{{ u.nome }}</td>
                            <td>{{ u.email }}</td>
                            <td>{{ u.perfil }}</td>
                            <td>{{ "Ativo" if u.ativo else "Inativo" }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div></body></html>
    """, css=ADMIN_CSS, usuarios=usuarios)

@server.route("/admin/logout")
def admin_logout():
    token = session.get("admin_token")
    if token: encerrar_sessao(token)
    session.pop("admin_token", None)
    return redirect(url_for("admin_login"))

# ============================================================
# 5. HELPERS DE DADOS
# ============================================================

def carregar_dados():
    try:
        df = pd.read_sql("SELECT * FROM pop_rua", engine)
        if df.empty: return df
        df['data_coleta'] = pd.to_datetime(df['data_coleta']).dt.tz_localize(None)
        return df
    except Exception as e:
        print(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()

# ============================================================
# 6. LAYOUT DASH (PRINCIPAL) - ATUALIZADO
# ============================================================

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
])

def layout_dashboard():
    return html.Div([
        html.Div([
            html.H1("Dashboard Pop Rua", style={'textAlign': 'center', 'color': '#1f2937'}),
            html.P("Análise de notícias e dados coletados no MDHC", style={'textAlign': 'center', 'color': '#6b7280'}),
        ], style={'padding': '20px', 'backgroundColor': '#ffffff', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),

        html.Div([
            # Filtro Simples
            html.Label("Selecione a Categoria:"),
            dcc.Dropdown(
                id='filtro-categoria',
                options=[{'label': 'Todas', 'value': 'TODAS'}],
                value='TODAS',
                clearable=False,
                style={'marginBottom': '20px'}
            ),
            
            # O Gráfico que estava vazio
            dcc.Graph(id='grafico-noticias-municipio')
        ], style={'padding': '30px'})
    ])

# Callback para gerenciar as páginas
@app.callback(Output('page-content', 'children'), [Input('url', 'pathname')])
def display_page(pathname):
    return layout_dashboard()

# CALLBACK PRINCIPAL: Conecta o Banco de Dados ao Gráfico
@app.callback(
    [Output('grafico-noticias-municipio', 'figure'),
     Output('filtro-categoria', 'options')],
    [Input('filtro-categoria', 'value')]
)
def atualizar_grafico(categoria_selecionada):
    df = carregar_dados()
    
    if df.empty:
        # Retorna gráfico vazio com mensagem amigável
        fig = px.bar(title="Nenhum dado encontrado no banco de dados.")
        return fig, [{'label': 'Nenhuma categoria', 'value': 'TODAS'}]

    # Prepara opções do filtro dinamicamente
    categorias = df['categoria'].unique().tolist()
    opcoes = [{'label': 'Todas as Categorias', 'value': 'TODAS'}] + \
             [{'label': c, 'value': c} for c in categorias]

    # Filtra os dados se necessário
    if categoria_selecionada != 'TODAS':
        df = df[df['categoria'] == categoria_selecionada]

    # Cria o gráfico de barras por Município
    contagem = df.groupby('municipio').size().reset_index(name='total')
    fig = px.bar(
        contagem, 
        x='municipio', 
        y='total',
        title=f"Notícias por Município ({categoria_selecionada})",
        labels={'municipio': 'Município', 'total': 'Qtd de Notícias'},
        color='total',
        color_continuous_scale='Blues'
    )
    
    fig.update_layout(template='plotly_white', transition_duration=500)

    return fig, opcoes

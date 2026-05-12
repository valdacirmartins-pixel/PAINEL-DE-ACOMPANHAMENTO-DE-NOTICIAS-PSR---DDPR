import os
import pandas as pd
import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
from sqlalchemy import create_engine

# ============================================================
# 1. CONFIGURAÇÕES E DICIONÁRIOS (27 UFs)
# ============================================================

# Dicionário completo garantindo que nenhuma UF passe batido
UFS_NOMES = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas', 'BA': 'Bahia', 
    'CE': 'Ceará', 'DF': 'Distrito Federal', 'ES': 'Espírito Santo', 'GO': 'Goiás', 
    'MA': 'Maranhão', 'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais', 
    'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná', 'PE': 'Pernambuco', 'PI': 'Piauí', 
    'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte', 'RS': 'Rio Grande do Sul', 
    'RO': 'Rondônia', 'RR': 'Roraima', 'SC': 'Santa Catarina', 'SP': 'São Paulo', 
    'SE': 'Sergipe', 'TO': 'Tocantins'
}

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

# ============================================================
# 2. INICIALIZAÇÃO DO APP
# ============================================================

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
server = app.server

# ============================================================
# 3. LAYOUT DO DASHBOARD
# ============================================================

app.layout = dbc.Container([
    dbc.Row([
        dbc.Col(html.H1("Monitoramento Nacional - População em Situação de Rua", 
                        className="text-center my-4"), width=12)
    ]),

    # Linha de Filtros
    dbc.Row([
        dbc.Col([
            html.Label("Selecione os Estados (Vazio = Brasil Todo):"),
            dcc.Dropdown(
                id='filtro-uf',
                options=[{'label': nome, 'value': sigla} for sigla, nome in UFS_NOMES.items()],
                multi=True,
                placeholder="Ex: TO, SP, DF...",
                className="mb-4"
            ),
        ], width=12)
    ]),

    # Área do Mapa e Cards
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Mapa de Ocorrências e Notícias"),
                dbc.CardBody(dcc.Graph(id='mapa-nacional', style={"height": "600px"}))
            ])
        ], width=12)
    ]),
    
    # Rodapé Técnico
    dbc.Row([
        dbc.Col(html.P("Dados atualizados via DDPR - Ministério dos Direitos Humanos e da Cidadania", 
                        className="text-muted small mt-3"), width=12)
    ])
], fluid=True)

# ============================================================
# 4. LÓGICA DE FILTRAGEM (CALLBACK)
# ============================================================

@app.callback(
    Output('mapa-nacional', 'figure'),
    [Input('filtro-uf', 'value')]
)
def atualizar_mapa(ufs_selecionadas):
    # Busca os dados do banco atualizados pelo seu novo coletor
    query = "SELECT * FROM pop_rua"
    df = pd.read_sql(query, engine)
    
    # Converte para numérico para garantir a plotagem
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    df = df.dropna(subset=['latitude', 'longitude'])

    # Aplica o filtro de Unidades da Federação
    if ufs_selecionadas:
        df = df[df['uf'].isin(ufs_selecionadas)]

    # Gera o mapa dinâmico
    fig = px.scatter_mapbox(
        df,
        lat="latitude",
        lon="longitude",
        color="categoria",
        hover_name="titulo",
        hover_data={"municipio": True, "uf": True, "data_coleta": True, "url": False},
        zoom=3.5 if not ufs_selecionadas else 5,
        center={"lat": -14.235, "lon": -51.925}, # Centro do Brasil
        mapbox_style="carto-positron",
        height=600
    )

    fig.update_layout(
        margin={"r":0,"t":0,"l":0,"b":0},
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    return fig

# ============================================================
# 5. EXECUÇÃO
# ============================================================

if __name__ == '__main__':
    app.run_server(debug=False)

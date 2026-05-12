import os
import pandas as pd
import plotly.express as px
import folium
from sqlalchemy import create_engine
from dash import Dash, dcc, html, Input, Output, dash_table
from folium.plugins import MarkerCluster

# Configurações do Banco no Railway
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

app = Dash(__name__, title="Painel de Notícias - Pop Rua")
server = app.server

# Estilo para os filtros
style_filter = {'padding': '10px', 'flex': '1', 'minWidth': '200px'}

app.layout = html.Div([
    html.Div([
        html.H1("Painel de Notícias - População em Situação de Rua", style={'textAlign': 'center', 'color': '#003366'}),
        html.P("Diretoria de Políticas para a População em Situação de Rua (DDPR)", style={'textAlign': 'center'})
    ], style={'padding': '20px', 'backgroundColor': '#f0f2f5', 'borderBottom': '2px solid #003366'}),

    # Filtros de UF e Município
    html.Div([
        html.Div([
            html.Label("Filtrar por UF:"),
            dcc.Dropdown(id='filtro-uf', placeholder="Selecione a UF", multi=True)
        ], style=style_filter),
        html.Div([
            html.Label("Filtrar por Município:"),
            dcc.Dropdown(id='filtro-municipio', placeholder="Selecione o Município", multi=True)
        ], style=style_filter),
    ], style={'display': 'flex', 'flexWrap': 'wrap', 'padding': '10px'}),

    # Área do Mapa e Gráfico de Barras
    html.Div([
        html.Div([
            html.H4("Mapa de Ocorrências"),
            html.Iframe(id='mapa-folium', srcDoc='', width='100%', height='500', style={'border': 'none'})
        ], style={'width': '60%', 'display': 'inline-block', 'padding': '10px'}),
        
        html.Div([
            html.H4("Notícias por Categoria"),
            dcc.Graph(id='grafico-barras')
        ], style={'width': '38%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '10px'})
    ]),

    # Tabela em Português
    html.Div([
        html.H4("Lista Detalhada de Notícias"),
        dash_table.DataTable(
            id='tabela-noticias',
            columns=[
                {"name": "Título da Notícia", "id": "titulo"},
                {"name": "Município", "id": "municipio"},
                {"name": "UF", "id": "uf"},
                {"name": "Categoria", "id": "categoria"},
                {"name": "Data de Coleta", "id": "data_coleta"}
            ],
            page_size=12,
            sort_action="native",
            filter_action="native",
            style_table={'overflowX': 'auto'},
            style_header={'backgroundColor': '#003366', 'color': 'white', 'fontWeight': 'bold'},
            style_cell={'textAlign': 'left', 'padding': '10px', 'fontFamily': 'sans-serif'},
            locale_format={'separate_4digits': True, 'decimal': ',', 'group': '.'}
        )
    ], style={'padding': '20px'})
])

@app.callback(
    [Output('mapa-folium', 'srcDoc'),
     Output('grafico-barras', 'figure'),
     Output('tabela-noticias', 'data'),
     Output('filtro-uf', 'options'),
     Output('filtro-municipio', 'options')],
    [Input('filtro-uf', 'value'),
     Input('filtro-municipio', 'value')]
)
def atualizar_dashboard(ufs_sel, municipios_sel):
    try:
        df = pd.read_sql("SELECT * FROM pop_rua ORDER BY data_coleta DESC", engine)
    except:
        return "", px.bar(title="Erro ao carregar banco"), [], [], []

    if df.empty:
        return "", px.bar(title="Sem dados disponíveis"), [], [], []

    # Opções dos Dropdowns
    opt_uf = [{'label': i, 'value': i} for i in sorted(df['uf'].unique()) if i]
    opt_mun = [{'label': i, 'value': i} for i in sorted(df['municipio'].unique()) if i]

    # Aplicar Filtros
    dff = df.copy()
    if ufs_sel:
        dff = dff[dff['uf'].isin(ufs_sel)]
    if municipios_sel:
        dff = dff[dff['municipio'].isin(municipios_sel)]

    # 1. Mapa
    mapa = folium.Map(location=[-15.78, -47.93], zoom_start=4) # Brasil Central
    cluster = MarkerCluster().add_to(mapa)
    for _, row in dff.iterrows():
        if pd.notnull(row['latitude']) and pd.notnull(row['longitude']):
            folium.Marker(
                [row['latitude'], row['longitude']],
                popup=f"<b>{row['titulo']}</b>",
                tooltip=row['municipio']
            ).add_to(cluster)
    
    # 2. Gráfico de Barras (como era antes)
    contagem = dff['categoria'].value_counts().reset_index()
    contagem.columns = ['categoria', 'total']
    fig = px.bar(contagem, x='categoria', y='total', color='categoria', 
                 title="Total por Categoria", template="plotly_white")
    
    return mapa._repr_html_(), fig, dff.to_dict('records'), opt_uf, opt_mun

if __name__ == '__main__':
    app.run_server(debug=True)

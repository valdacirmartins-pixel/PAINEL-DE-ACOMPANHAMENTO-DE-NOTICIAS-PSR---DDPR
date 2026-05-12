import os
import pandas as pd
import plotly.express as px
import folium
from sqlalchemy import create_engine
from dash import Dash, dcc, html, Input, Output, dash_table
from folium.plugins import MarkerCluster

# Conexão com o banco do Railway
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

app = Dash(__name__, title="Painel de Notícias - Pop Rua")
server = app.server

app.layout = html.Div([
    html.Div([
        html.H1("Painel de Notícias - População em Situação de Rua", style={'textAlign': 'center'}),
        html.P("Diretoria de Políticas para a População em Situação de Rua (DDPR)", style={'textAlign': 'center'})
    ], style={'padding': '15px', 'backgroundColor': '#f8f9fa', 'borderBottom': '1px solid #ddd'}),

    # Bloco de Filtros (UF e Município)
    html.Div([
        html.Div([
            html.Label("Filtrar por UF:"),
            dcc.Dropdown(id='filtro-uf', multi=True, placeholder="Selecione as UFs")
        ], style={'width': '48%', 'display': 'inline-block', 'padding': '10px'}),
        html.Div([
            html.Label("Filtrar por Município:"),
            dcc.Dropdown(id='filtro-municipio', multi=True, placeholder="Selecione os Municípios")
        ], style={'width': '48%', 'display': 'inline-block', 'padding': '10px'}),
    ]),

    # Mapa e Gráfico de Barras lado a lado
    html.Div([
        html.Div([
            html.Iframe(id='mapa-folium', srcDoc='', width='100%', height='500')
        ], style={'width': '60%', 'display': 'inline-block'}),
        html.Div([
            dcc.Graph(id='grafico-barras-categorias')
        ], style={'width': '38%', 'display': 'inline-block', 'verticalAlign': 'top'})
    ]),

    # Tabela de Dados em Português
    html.Div([
        html.H3("Base de Dados de Notícias"),
        dash_table.DataTable(
            id='tabela-noticias',
            columns=[
                {"name": "Título da Notícia", "id": "titulo"},
                {"name": "Município", "id": "municipio"},
                {"name": "UF", "id": "uf"},
                {"name": "Categoria", "id": "categoria"},
                {"name": "Data da Coleta", "id": "data_coleta"}
            ],
            page_size=10,
            style_table={'overflowX': 'auto'},
            style_header={'backgroundColor': '#003366', 'color': 'white', 'fontWeight': 'bold'},
            style_cell={'textAlign': 'left', 'padding': '5px'}
        )
    ], style={'padding': '20px'})
])

@app.callback(
    [Output('mapa-folium', 'srcDoc'),
     Output('grafico-barras-categorias', 'figure'),
     Output('tabela-noticias', 'data'),
     Output('filtro-uf', 'options'),
     Output('filtro-municipio', 'options')],
    [Input('filtro-uf', 'value'),
     Input('filtro-municipio', 'value')]
)
def update_dashboard(uf_selecionada, mun_selecionado):
    df = pd.read_sql("SELECT * FROM pop_rua ORDER BY data_coleta DESC", engine)
    
    if df.empty:
        return "", px.bar(title="Sem dados"), [], [], []

    # Configura opções dos filtros dinamicamente
    opts_uf = [{'label': i, 'value': i} for i in sorted(df['uf'].unique()) if i]
    opts_mun = [{'label': i, 'value': i} for i in sorted(df['municipio'].unique()) if i]

    # Filtra o DataFrame
    dff = df.copy()
    if uf_selecionada:
        dff = dff[dff['uf'].isin(uf_selecionada)]
    if mun_selecionado:
        dff = dff[dff['municipio'].isin(mun_selecionado)]

    # Criação do Mapa Folium
    m = folium.Map(location=[-15.78, -47.93], zoom_start=4)
    marker_cluster = MarkerCluster().add_to(m)
    for _, row in dff.iterrows():
        if pd.notnull(row['latitude']) and pd.notnull(row['longitude']):
            folium.Marker([row['latitude'], row['longitude']], popup=row['titulo']).add_to(marker_cluster)

    # Gráfico de Barras (Correto)
    fig = px.bar(dff['categoria'].value_counts().reset_index(), 
                 x='index', y='categoria', 
                 labels={'index': 'Categoria', 'categoria': 'Quantidade'},
                 title="Notícias por Categoria")

    return m._repr_html_(), fig, dff.to_dict('records'), opts_uf, opts_mun

if __name__ == '__main__':
    app.run_server(debug=True)

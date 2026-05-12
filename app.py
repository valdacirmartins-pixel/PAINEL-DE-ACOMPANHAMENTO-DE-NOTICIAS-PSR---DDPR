import os
import pandas as pd
import plotly.express as px
import folium
from sqlalchemy import create_engine, text
from dash import Dash, dcc, html, Input, Output, dash_table
from dash.exceptions import PreventUpdate
from folium.plugins import MarkerCluster

# Configurações de Banco de Dados
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

app = Dash(__name__, title="Painel de Notícias - Pop Rua")
server = app.server

# Layout restaurado: Mapa + Tabela + Gráficos
app.layout = html.Div([
    html.Div([
        html.H1("Painel de Notícias - População em Situação de Rua", style={'textAlign': 'center'}),
        html.P("Monitoramento DDPR - MDHC", style={'textAlign': 'center'})
    ], style={'padding': '10px', 'backgroundColor': '#f8f9fa'}),

    html.Div([
        html.Div([
            html.H3("Localização das Notícias"),
            html.Iframe(id='mapa-folium', srcDoc='', width='100%', height='500')
        ], style={'width': '60%', 'display': 'inline-block', 'padding': '10px'}),
        
        html.Div([
            html.H3("Distribuição por Categoria"),
            dcc.Graph(id='grafico-categorias')
        ], style={'width': '35%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '10px'})
    ]),

    html.Div([
        html.H3("Detalhamento das Notícias"),
        dash_table.DataTable(
            id='tabela-noticias',
            columns=[
                {"name": "Título", "id": "titulo"},
                {"name": "Município", "id": "municipio"},
                {"name": "Categoria", "id": "categoria"},
                {"name": "Data", "id": "data_coleta"}
            ],
            page_size=10,
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'left', 'padding': '5px'},
            style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'}
        )
    ], style={'padding': '20px'})
])

@app.callback(
    [Output('mapa-folium', 'srcDoc'),
     Output('grafico-categorias', 'figure'),
     Output('tabela-noticias', 'data')],
    [Input('mapa-folium', 'id')] # Trigger inicial
)
def atualizar_painel(_):
    try:
        df = pd.read_sql("SELECT * FROM pop_rua ORDER BY criado_em DESC", engine)
    except:
        return "", px.box(title="Erro ao acessar banco"), []

    if df.empty:
        return "", px.bar(title="Sem dados"), []

    # 1. Gerar Mapa
    mapa = folium.Map(location=[-10.24, -48.33], zoom_start=5) # Foco em Palmas/TO
    cluster = MarkerCluster().add_to(mapa)
    
    for _, row in df.iterrows():
        if pd.notnull(row['latitude']) and pd.notnull(row['longitude']):
            folium.Marker(
                [row['latitude'], row['longitude']],
                popup=f"<b>{row['titulo']}</b><br>{row['municipio']}",
                tooltip=row['titulo']
            ).add_to(cluster)
    
    # 2. Gráfico
    fig = px.pie(df, names='categoria', hole=.3)
    
    # 3. Dados da Tabela
    dados_tabela = df.to_dict('records')
    
    return mapa._repr_html_(), fig, dados_tabela

if __name__ == '__main__':
    app.run_server(debug=True)

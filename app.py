import dash
from dash import dcc, html, Input, Output
import pandas as pd
import plotly.express as px

# Mantenha o seu dicionário de 27 UFs para o filtro funcionar
UFS_NOMES = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas', 'BA': 'Bahia', 
    'CE': 'Ceará', 'DF': 'Distrito Federal', 'ES': 'Espírito Santo', 'GO': 'Goiás', 
    'MA': 'Maranhão', 'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais', 
    'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná', 'PE': 'Pernambuco', 'PI': 'Piauí', 
    'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte', 'RS': 'Rio Grande do Sul', 
    'RO': 'Rondônia', 'RR': 'Roraima', 'SC': 'Santa Catarina', 'SP': 'São Paulo', 
    'SE': 'Sergipe', 'TO': 'Tocantins'
}

app = dash.Dash(__name__) # Voltando para o Dash simples
server = app.server

app.layout = html.Div([
    html.H1("Meu Painel de Notícias"),
    
    html.Div([
        html.Label("Selecione os Estados:"),
        dcc.Dropdown(
            id='filtro-uf',
            # Usa o dicionário para criar as 27 opções
            options=[{'label': nome, 'value': sigla} for sigla, nome in UFS_NOMES.items()],
            multi=True,
            placeholder="Brasil Todo"
        ),
    ], style={'padding': '10px'}),

    dcc.Graph(id='mapa-nacional')
])

@app.callback(
    Output('mapa-nacional', 'figure'),
    [Input('filtro-uf', 'value')]
)
def atualizar_mapa(ufs_selecionadas):
    df = pd.read_sql("SELECT * FROM pop_rua", engine)
    
    # Filtra apenas se houver seleção, senão mostra tudo (as 27 UFs)
    if ufs_selecionadas:
        df = df[df['uf'].isin(ufs_selecionadas)]

    fig = px.scatter_mapbox(
        df,
        lat="latitude",
        lon="longitude",
        hover_name="titulo",
        zoom=3,
        mapbox_style="open-street-map" # Estilo padrão do Dash/Plotly
    )
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    return fig

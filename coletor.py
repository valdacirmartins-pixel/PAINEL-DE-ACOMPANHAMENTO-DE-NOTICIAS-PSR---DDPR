import os
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from ddgs import DDGS
from newspaper import Article, Config
from sqlalchemy import create_engine, text

# ============================================================
# CONFIGURAÇÃO DE VARREDURA EXAUSTIVA V2
# ============================================================

APP_TIMEZONE = "America/Sao_Paulo"
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Dicionário para busca mais completa (Sigla: Nome Extenso)
UFS_NOMES = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas', 'BA': 'Bahia', 
    'CE': 'Ceará', 'DF': 'Distrito Federal', 'ES': 'Espírito Santo', 'GO': 'Goiás', 
    'MA': 'Maranhão', 'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais', 
    'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná', 'PE': 'Pernambuco', 'PI': 'Piauí', 
    'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte', 'RS': 'Rio Grande do Sul', 
    'RO': 'Rondônia', 'RR': 'Roraima', 'SC': 'Santa Catarina', 'SP': 'São Paulo', 
    'SE': 'Sergipe', 'TO': 'Tocantins'
}

COORD_ESTADOS = {
    'AC': (-9.02, -70.81), 'AL': (-9.57, -36.78), 'AP': (0.03, -51.07), 'AM': (-3.41, -64.03),
    'BA': (-12.51, -41.70), 'CE': (-5.20, -39.53), 'DF': (-15.80, -47.86), 'ES': (-19.18, -40.30),
    'GO': (-15.82, -49.83), 'MA': (-4.96, -45.27), 'MT': (-12.68, -55.42), 'MS': (-20.77, -54.78),
    'MG': (-18.51, -44.51), 'PA': (-1.99, -52.14), 'PB': (-7.23, -36.78), 'PR': (-24.89, -51.55),
    'PE': (-8.81, -36.95), 'PI': (-7.71, -42.72), 'RJ': (-22.84, -43.15), 'RN': (-5.22, -36.52),
    'RS': (-30.03, -51.21), 'RO': (-11.50, -63.58), 'RR': (2.73, -62.07), 'SC': (-27.24, -50.21),
    'SP': (-23.55, -46.63), 'SE': (-10.57, -37.45), 'TO': (-10.17, -48.33)
}

categorias_expansao = [
    "População em situação de rua segurança alimentar",
    "Acolhimento institucional pessoas em situação de rua",
    "Direitos humanos população de rua Brasil",
    "Saúde mental consultório na rua",
    "Censo população de rua 2026",
    "Políticas públicas DDPR MDHC"
]
DICIONARIO_BUSCA = {
    "Morte": [
        "morador de rua morto", "corpo encontrado situação de rua", 
        "homicídio morador de rua", "pessoa sem teto falecida"
    ],
    "Violência": [
        "morador de rua espancado", "ataque a morador de rua", 
        "violência contra população de rua", "agressão pessoa em situação de rua"
    ],
    "Impacto Positivo": [
        "doação moradores de rua", "projeto social população de rua", 
        "acolhimento morador de rua", "solidariedade pessoas de rua"
    ],
    "Ação Política/Jurídica": [
        "prefeitura moradores de rua", "MPF população de rua", 
        "decisão judicial morador de rua", "políticas públicas situação de rua"
    ],
    "Saúde/Acidente": [
        "atendimento médico morador de rua", "frio morador de rua", 
        "hipotermia população de rua", "surto saúde situação de rua"
    ]
}

config = Config()
config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
config.request_timeout = 20

def salvar_no_banco(dados):
    sql = """
    INSERT INTO pop_rua (titulo, url, municipio, uf, categoria, latitude, longitude, data_coleta, data_publicacao)
    VALUES (:titulo, :url, :municipio, :uf, :categoria, :latitude, :longitude, :data_coleta, :data_publicacao)
    ON CONFLICT (url) DO NOTHING;
    """
    with engine.begin() as conn:
        return conn.execute(text(sql), dados).rowcount

def main():
    print(f"🛰️ INICIANDO VARREDURA EXAUSTIVA - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    total_sucesso = 0
    urls_vistas = set()

    with DDGS() as ddgs:
        for uf, nome_extenso in UFS_NOMES.items():
            lat_fixa, lon_fixa = COORD_ESTADOS.get(uf)
            
            for categoria, termos in DICIONARIO_BUSCA.items():
                for termo_base in termos:
                    # Busca alternada entre Sigla e Nome do Estado para maximizar resultados
                    query = f'"{termo_base}" {nome_extenso}' 
                    print(f"🔍 [{categoria}] -> {query}")
                    
                    try:
                        # timelimit='m' busca resultados do último mês (mais volume que 'd', mais atual que 'y')
                        resultados = ddgs.text(query, region="br-pt", max_results=20, timelimit='m')
                        
                        if not resultados: continue

                        for r in resultados:
                            link = r.get("href")
                            if not link or link in urls_vistas: continue
                            urls_vistas.add(link)

                            try:
                                art = Article(link, language="pt", config=config)
                                art.download()
                                art.parse()

                                if len(art.text) < 200: continue

                                registro = {
                                    "titulo": art.title[:250],
                                    "url": link,
                                    "municipio": f"Área de {uf}",
                                    "uf": uf,
                                    "categoria": categoria,
                                    "latitude": lat_fixa,
                                    "longitude": lon_fixa,
                                    "data_coleta": datetime.now(ZoneInfo(APP_TIMEZONE)),
                                    "data_publicacao": art.publish_date
                                }

                                if salvar_no_banco(registro):
                                    total_sucesso += 1
                                    print(f"    ✅ Salvo: {art.title[:45]}...")
                            
                            except Exception:
                                continue
                        
                        # Pausa dinâmica para evitar bloqueio do pato (DDG)
                        time.sleep(random.uniform(3, 6))

                    except Exception as e:
                        print(f"⚠️ Erro na busca: {e}")
                        time.sleep(15)

    print(f"🏁 Fim da rodada. Sucesso: {total_sucesso} novos registros.")

if __name__ == "__main__":
    while True:
        try:
            main()
            # Reduzi para 4 horas para manter o Dash sempre fresco
            print("💤 Aguardando 4 horas...")
            time.sleep(14400)
        except Exception as e:
            print(f"❌ Erro no loop principal: {e}")
            time.sleep(600)

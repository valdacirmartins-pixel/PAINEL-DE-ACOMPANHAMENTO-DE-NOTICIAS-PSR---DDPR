import os
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from ddgs import DDGS
from newspaper import Article, Config
from sqlalchemy import create_engine, text

# ============================================================
# CONFIGURAÇÃO NACIONAL
# ============================================================

APP_TIMEZONE = "America/Sao_Paulo"
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Lista completa de UFs para busca nacional
UFS_BRASIL = [
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA',
    'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN',
    'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
]

# Coordenadas centrais de cada estado para o MAPA funcionar
COORD_CENTRAIS = {
    'AC': (-9.02, -70.81), 'AL': (-9.57, -36.78), 'AP': (0.03, -51.07),
    'AM': (-3.41, -64.03), 'BA': (-12.51, -41.70), 'CE': (-5.20, -39.53),
    'DF': (-15.80, -47.86), 'ES': (-19.18, -40.30), 'GO': (-15.82, -49.83),
    'MA': (-4.96, -45.27), 'MT': (-12.68, -55.42), 'MS': (-20.77, -54.78),
    'MG': (-18.51, -44.51), 'PA': (-1.99, -52.14), 'PB': (-7.23, -36.78),
    'PR': (-24.89, -51.55), 'PE': (-8.81, -36.95), 'PI': (-7.71, -42.72),
    'RJ': (-22.84, -43.15), 'RN': (-5.22, -36.52), 'RS': (-30.03, -51.21),
    'RO': (-11.50, -63.58), 'RR': (2.73, -62.07), 'SC': (-27.24, -50.21),
    'SP': (-23.55, -46.63), 'SE': (-10.57, -37.45), 'TO': (-10.17, -48.33)
}

config = Config()
config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
config.request_timeout = 10 

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def inserir_registro(registro):
    # ATUALIZADO: Agora inclui latitude e longitude no SQL
    sql = """
    INSERT INTO pop_rua (titulo, url, municipio, uf, categoria, latitude, longitude, data_coleta, data_publicacao)
    VALUES (:titulo, :url, :municipio, :uf, :categoria, :latitude, :longitude, :data_coleta, :data_publicacao)
    ON CONFLICT (url) DO NOTHING;
    """
    with engine.begin() as conn:
        return conn.execute(text(sql), registro).rowcount

def extrair_municipio(texto, uf_alvo):
    return f"Estado de {uf_alvo}"

# ============================================================
# MAIN
# ============================================================

def main():
    print("🌍 INICIANDO COLETA NACIONAL COM COORDENADAS...")
    
    with DDGS() as ddgs:
        for uf in UFS_BRASIL:
            query = f"morador de rua morreu {uf} 2026"
            print(f"🔎 Buscando em: {uf}")
            
            try:
                resultados = ddgs.text(query, region="br-pt", max_results=10)
                
                for r in resultados:
                    url = r.get("href")
                    try:
                        art = Article(url, language="pt", config=config)
                        art.download()
                        art.parse()

                        if len(art.text or "") < 150: continue

                        # PEGA AS COORDENADAS DO DICIONÁRIO
                        lat, lon = COORD_CENTRAIS.get(uf, (None, None))

                        registro = {
                            "titulo": art.title,
                            "url": url,
                            "municipio": extrair_municipio(art.text, uf),
                            "uf": uf,
                            "categoria": "Morte",
                            "latitude": lat,   # <--- AGORA VAI PARA O BANCO
                            "longitude": lon,  # <--- AGORA VAI PARA O BANCO
                            "data_coleta": datetime.now(ZoneInfo(APP_TIMEZONE)),
                            "data_publicacao": art.publish_date
                        }

                        if inserir_registro(registro):
                            print(f"✅ Salvo [{uf}]: {art.title[:50]}...")
                            time.sleep(0.5)

                    except:
                        continue
            except Exception as e:
                print(f"⚠️ Erro ao buscar {uf}: {e}")
                continue

    print("✨ Coleta nacional finalizada.")

if __name__ == "__main__":
    main()

import os
import time
import random
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from ddgs import DDGS
from newspaper import Article, Config
from sqlalchemy import create_engine, text

# ============================================================
# CONFIGURAÇÃO AVANÇADA
# ============================================================

APP_TIMEZONE = "America/Sao_Paulo"
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

UFS_BRASIL = [
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA',
    'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN',
    'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
]

# Ampliando os termos de busca para encontrar MAIS notícias
TERMOS_BUSCA = [
    "morador de rua morto {local}",
    "pessoa em situação de rua morreu {local}",
    "corpo encontrado morador de rua {local}",
    "homicídio pessoa em situação de rua {local}",
    "atropelamento morador de rua {local}"
]

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
config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
config.request_timeout = 15 

# ============================================================
# LÓGICA DE EXTRAÇÃO E BANCO
# ============================================================

def inserir_registro(registro):
    sql = """
    INSERT INTO pop_rua (titulo, url, municipio, uf, categoria, latitude, longitude, data_coleta, data_publicacao)
    VALUES (:titulo, :url, :municipio, :uf, :categoria, :latitude, :longitude, :data_coleta, :data_publicacao)
    ON CONFLICT (url) DO NOTHING;
    """
    with engine.begin() as conn:
        return conn.execute(text(sql), registro).rowcount

def classificar_categoria(texto):
    texto = texto.lower()
    if any(x in texto for x in ["morto", "morreu", "óbito", "corpo", "homicídio"]): return "Morte"
    if any(x in texto for x in ["agredido", "violência", "esfaqueado", "baleado"]): return "Violência"
    if any(x in texto for x in ["atropelado", "acidente", "incêndio"]): return "Acidente"
    return "Outros"

# ============================================================
# MAIN
# ============================================================

def main():
    print(f"🚀 INICIANDO SUPER COLETA: {len(UFS_BRASIL)} estados x {len(TERMOS_BUSCA)} termos")
    
    urls_vistas = set()
    total_novos = 0

    with DDGS() as ddgs:
        for uf in UFS_BRASIL:
            for termo in TERMOS_BUSCA:
                query = termo.format(local=uf)
                print(f"🔍 Buscando: {query}")
                
                try:
                    # Aumentamos para 20 resultados por combinação
                    resultados = ddgs.text(query, region="br-pt", max_results=20)
                    if not resultados: continue

                    for r in resultados:
                        url = r.get("href")
                        if not url or url in urls_vistas: continue
                        urls_vistas.add(url)

                        try:
                            art = Article(url, language="pt", config=config)
                            art.download()
                            art.parse()

                            texto_completo = (art.title + " " + art.text).lower()
                            
                            # Filtro básico de qualidade
                            if len(art.text) < 200: continue

                            # Coordenadas e Categoria
                            lat, lon = COORD_CENTRAIS.get(uf, (-14.23, -51.92))
                            cat = classificar_categoria(texto_completo)

                            registro = {
                                "titulo": art.title[:250],
                                "url": url,
                                "municipio": f"Busca Regional {uf}",
                                "uf": uf,
                                "categoria": cat,
                                "latitude": lat,
                                "longitude": lon,
                                "data_coleta": datetime.now(ZoneInfo(APP_TIMEZONE)),
                                "data_publicacao": art.publish_date
                            }

                            if inserir_registro(registro):
                                total_novos += 1
                                print(f"✅ [{uf}] {art.title[:50]}...")
                        
                        except Exception:
                            continue
                    
                    # Pausa estratégica para evitar bloqueio do pato (DuckDuckGo)
                    time.sleep(random.uniform(1, 2))

                except Exception as e:
                    print(f"⚠️ Erro na busca {uf}: {e}")
                    time.sleep(5)

    print(f"✨ FIM. Total de novos registros nesta rodada: {total_novos}")

if __name__ == "__main__":
    main()

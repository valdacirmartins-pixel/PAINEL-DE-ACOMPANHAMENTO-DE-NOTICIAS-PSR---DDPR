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

config = Config()
config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
config.request_timeout = 10 

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def inserir_registro(registro):
    sql = """
    INSERT INTO pop_rua (titulo, url, municipio, uf, categoria, data_coleta, data_publicacao)
    VALUES (:titulo, :url, :municipio, :uf, :categoria, :data_coleta, :data_publicacao)
    ON CONFLICT (url) DO NOTHING;
    """
    with engine.begin() as conn:
        return conn.execute(text(sql), registro).rowcount

def extrair_municipio(texto, uf_alvo):
    # Lógica simples: se não achar cidade específica, marca como 'Geral [UF]'
    # Você pode expandir isso com uma lista de capitais se desejar
    return f"Estado de {uf_alvo}"

# ============================================================
# MAIN
# ============================================================

def main():
    print("🌍 INICIANDO COLETA NACIONAL (BRASIL)...")
    
    with DDGS() as ddgs:
        # O loop agora percorre cada estado do Brasil
        for uf in UFS_BRASIL:
            query = f"morador de rua morreu {uf} 2026" # Foco em notícias recentes
            print(f"🔎 Buscando em: {uf}")
            
            try:
                # Pegamos os 10 melhores resultados de cada estado para não estourar o timeout
                resultados = ddgs.text(query, region="br-pt", max_results=10)
                
                for r in resultados:
                    url = r.get("href")
                    try:
                        art = Article(url, language="pt", config=config)
                        art.download()
                        art.parse()

                        if len(art.text or "") < 150: continue

                        registro = {
                            "titulo": art.title,
                            "url": url,
                            "municipio": extrair_municipio(art.text, uf),
                            "uf": uf, # <--- AQUI: Preenche com a UF da busca
                            "categoria": "Morte", # Ou use sua função classificar()
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

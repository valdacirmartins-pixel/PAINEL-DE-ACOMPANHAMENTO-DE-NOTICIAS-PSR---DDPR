import os
import time
from sqlalchemy import create_engine, text
from duckduckgo_search import DDGS
from newspaper import Article
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def capturar_noticias():
    queries = [
        "população em situação de rua Palmas TO",
        "assistência social Palmas notícias",
        "direitos humanos população de rua"
    ]
    
    with DDGS() as ddgs:
        for q in queries:
            print(f"Buscando por: {q}")
            results = ddgs.text(q, max_results=5)
            
            for r in results:
                try:
                    # Tenta extrair detalhes com newspaper
                    article = Article(r['href'])
                    article.download()
                    article.parse()
                    
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO pop_rua (titulo, url, municipio, categoria, data_coleta)
                            VALUES (:titulo, :url, :municipio, :categoria, :data)
                            ON CONFLICT (url) DO NOTHING
                        """), {
                            "titulo": r['title'],
                            "url": r['href'],
                            "municipio": "Palmas", # Padrão conforme seu trabalho atual
                            "categoria": "Geral",
                            "data": datetime.now()
                        })
                except Exception as e:
                    print(f"Erro ao processar {r['href']}: {e}")

if __name__ == "__main__":
    while True:
        capturar_noticias()
        print("Aguardando próxima coleta...")
        time.sleep(3600) # Roda a cada hora

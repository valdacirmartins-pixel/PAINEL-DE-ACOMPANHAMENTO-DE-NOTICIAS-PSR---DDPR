import os
import time
from sqlalchemy import create_engine, text
from duckduckgo_search import DDGS
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def coletar():
    with DDGS() as ddgs:
        # Suas queries de pesquisa focadas no seu trabalho no DDPR
        queries = ["população em situação de rua notícias", "MDHC população de rua"]
        for q in queries:
            results = ddgs.text(q, max_results=10)
            for r in results:
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO pop_rua (titulo, url, municipio, uf, categoria, data_coleta) 
                        VALUES (:t, :u, :m, :uf, :c, :d) 
                        ON CONFLICT (url) DO NOTHING
                    """), {
                        "t": r['title'], "u": r['href'], "m": "Palmas", 
                        "uf": "TO", "c": "Geral", "d": datetime.now()
                    })
    print("Coleta concluída.")

if __name__ == "__main__":
    while True:
        coletar()
        time.sleep(3600)

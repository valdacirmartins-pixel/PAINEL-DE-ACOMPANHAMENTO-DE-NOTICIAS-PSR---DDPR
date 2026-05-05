import os
import re
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from ddgs import DDGS
from newspaper import Article

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# ============================================================
# CONFIG
# ============================================================

APP_TIMEZONE = "America/Sao_Paulo"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não configurada")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# ============================================================
# BANCO
# ============================================================

def criar_tabela():
    sql = """
    CREATE TABLE IF NOT EXISTS pop_rua (
        id SERIAL PRIMARY KEY,
        titulo TEXT,
        url TEXT UNIQUE,
        municipio TEXT,
        uf VARCHAR(2),
        categoria TEXT,
        latitude DOUBLE PRECISION,
        longitude DOUBLE PRECISION,
        data_coleta TIMESTAMP,
        data_publicacao TIMESTAMP NULL,
        criado_em TIMESTAMP DEFAULT NOW()
    );
    """
    with engine.begin() as conn:
        conn.execute(text(sql))


def inserir_registro(registro):
    sql = """
    INSERT INTO pop_rua (
        titulo, url, municipio, uf, categoria,
        latitude, longitude, data_coleta, data_publicacao
    )
    VALUES (
        :titulo, :url, :municipio, :uf, :categoria,
        :latitude, :longitude, :data_coleta, :data_publicacao
    )
    ON CONFLICT (url) DO NOTHING;
    """

    with engine.begin() as conn:
        result = conn.execute(text(sql), registro)
        return result.rowcount


def resumo():
    with engine.begin() as conn:
        r = conn.execute(text("SELECT COUNT(*) FROM pop_rua")).scalar()

    print(f"📊 Total no banco: {r}")


# ============================================================
# CONFIG DADOS
# ============================================================

CIDADES = ["São Paulo", "Rio de Janeiro", "Brasília", "Salvador"]

CATEGORIAS = {
    "Morte": ["morto", "morreu", "óbito"],
    "Violência": ["assassinado", "agredido"],
    "Acidente": ["atropelado", "acidente"],
}

QUERIES = [
    "morador de rua morto {cidade}",
    "morador de rua morreu {cidade}",
    "pessoa em situação de rua morta {cidade}",
]

# ============================================================
# FUNÇÕES
# ============================================================

def agora():
    return datetime.now(ZoneInfo(APP_TIMEZONE))


def classificar(texto):
    for cat, palavras in CATEGORIAS.items():
        if any(p in texto for p in palavras):
            return cat
    return "Outros"


def detectar_cidade(texto):
    for c in CIDADES:
        if c.lower() in texto:
            return c
    return "Não identificado"


# ============================================================
# MAIN
# ============================================================

def main():

    print("🚀 INICIANDO COLETOR...")

    criar_tabela()

    urls = set()
    total_inseridos = 0
    total_duplicados = 0

    with DDGS() as ddgs:

        for cidade in CIDADES:
            for q in QUERIES:

                query = q.format(cidade=cidade)

                resultados = ddgs.text(query, region="br-pt", max_results=20)

                for r in resultados:

                    url = r["href"]

                    if url in urls:
                        continue

                    urls.add(url)

                    try:
                        art = Article(url, language="pt")
                        art.download()
                        art.parse()

                        texto = (art.text or "").lower()
                        titulo = art.title or ""

                        if not texto:
                            continue

                        categoria = classificar(texto)
                        municipio = detectar_cidade(texto)

                        registro = {
                            "titulo": titulo,
                            "url": url,
                            "municipio": municipio,
                            "uf": "",
                            "categoria": categoria,
                            "latitude": None,
                            "longitude": None,
                            "data_coleta": agora(),
                            "data_publicacao": art.publish_date,
                        }

                        try:
                            inseriu = inserir_registro(registro)

                            if inseriu:
                                total_inseridos += 1
                                print("💾 Inserido:", titulo[:60])

                            else:
                                total_duplicados += 1

                        except SQLAlchemyError as e:
                            print("❌ ERRO DB:", e)

                        time.sleep(random.uniform(1, 2))

                    except Exception:
                        continue

    print("\n========== RESULTADO ==========")
    print(f"Inseridos: {total_inseridos}")
    print(f"Duplicados: {total_duplicados}")

    resumo()


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()

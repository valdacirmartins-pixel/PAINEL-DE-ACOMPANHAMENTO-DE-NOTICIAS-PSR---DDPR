import os
import re
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from ddgs import DDGS
from newspaper import Article, Config  # Importado Config para melhorar a extração

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

# Configuração para evitar bloqueios e melhorar qualidade da extração
config = Config()
config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
config.request_timeout = 10  # Limite de 10 segundos por download

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
    "Morte": ["morto", "morreu", "óbito", "falecimento", "cadáver"],
    "Violência": ["assassinado", "agredido", "esfaqueado", "baleado", "espancado"],
    "Acidente": ["atropelado", "acidente", "incêndio", "queimado"],
}

QUERIES = [
    "morador de rua morto {cidade}",
    "pessoa em situação de rua morreu {cidade}",
    "notícia violência morador de rua {cidade}",
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

    urls_processadas = set()
    total_inseridos = 0
    total_duplicados = 0

    with DDGS() as ddgs:
        for cidade in CIDADES:
            for q in QUERIES:
                query = q.format(cidade=cidade)
                print(f"🔍 Buscando: {query}")
                
                try:
                    resultados = ddgs.text(query, region="br-pt", max_results=25)
                except Exception as e:
                    print(f"⚠️ Erro na busca DuckDuckGo: {e}")
                    continue

                for r in resultados:
                    url = r.get("href")
                    if not url or url in urls_processadas:
                        continue

                    urls_processadas.add(url)

                    try:
                        # Aplica as configurações de timeout e User-Agent
                        art = Article(url, language="pt", config=config)
                        art.download()
                        art.parse()

                        texto = (art.text or "").lower()
                        titulo = art.title or ""

                        # Qualidade: Ignora se o texto for muito curto (provável erro de carregamento ou paywall)
                        if len(texto) < 150:
                            continue

                        categoria = classificar(texto + " " + titulo.lower())
                        municipio = detectar_cidade(texto + " " + titulo.lower())

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
                                print(f"✅ Salvo: {titulo[:50]}...")
                                # Delay apenas se houve sucesso para evitar sobrecarga
                                time.sleep(random.uniform(0.5, 1.5))
                            else:
                                total_duplicados += 1
                        except SQLAlchemyError as e:
                            print(f"❌ Erro de Banco: {e}")

                    except Exception as e:
                        # Pula silenciosamente erros de download/parse de sites específicos
                        continue

    print("\n" + "="*30)
    print(f"✨ FIM DA COLETA")
    print(f"📥 Novos registros: {total_inseridos}")
    print(f"🔄 Já existiam: {total_duplicados}")
    resumo()
    print("="*30)


if __name__ == "__main__":
    main()

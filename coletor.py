import os
import re
import time
import random
import unicodedata
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from ddgs import DDGS
from newspaper import Article

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


# ============================================================
# CONFIGURAÇÕES
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não encontrada. "
        "Configure essa variável de ambiente no Railway."
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=30
)

URL_IBGE = (
    "https://raw.githubusercontent.com/kelvins/"
    "Municipios-Brasileiros/master/csv/municipios.csv"
)

QUERIES = [

    "morador de rua morto",
    "morador de rua morreu",
    "morador de rua assassinado",
    "morador de rua agredido",
    "morador de rua espancado",
    "morador de rua queimado",
    "morador de rua incendiado",
    "morador de rua baleado",
    "morador de rua esfaqueado",
    "morador de rua atropelado",
    "morador de rua encontrado morto",

    "pessoa em situação de rua morta",
    "pessoa em situação de rua assassinada",
    "pessoa em situação de rua agredida",
    "pessoa em situação de rua baleada",

    "homem em situação de rua morto",
    "mulher em situação de rua morta",

    "sem teto morto",
    "sem teto assassinado",
    "sem teto agredido",

    "violência contra morador de rua",
    "ataque contra morador de rua",
    "crime contra morador de rua",

    "população de rua morta",
    "população em situação de rua",

    "homicídio morador de rua",
    "morador de rua vítima",
    "morador de rua corpo encontrado",
]

CATEGORIAS = {
    "Morte": [
        "morto",
        "morta",
        "morreu",
        "óbito",
        "obito",
        "falecimento",
        "morte",
        "corpo encontrado",
        "encontrado morto",
        "encontrada morta",
    ],
    "Violência": [
        "assassinado",
        "assassinada",
        "agredido",
        "agredida",
        "espancado",
        "espancada",
        "violência",
        "violencia",
        "homicídio",
        "homicidio",
        "facada",
        "tiro",
        "queimado",
        "queimada",
        "baleado",
        "esfaqueado",
    ],
    "Acidente": [
        "acidente",
        "atropelado",
        "atropelada",
        "atropelamento",
    ],
    "Outros": []
}

MAPA_UF = {
    11: "RO",
    12: "AC",
    13: "AM",
    14: "RR",
    15: "PA",
    16: "AP",
    17: "TO",
    21: "MA",
    22: "PI",
    23: "CE",
    24: "RN",
    25: "PB",
    26: "PE",
    27: "AL",
    28: "SE",
    29: "BA",
    31: "MG",
    32: "ES",
    33: "RJ",
    35: "SP",
    41: "PR",
    42: "SC",
    43: "RS",
    50: "MS",
    51: "MT",
    52: "GO",
    53: "DF",
}


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_texto(valor):

    texto = str(valor or "").lower().strip()

    texto = unicodedata.normalize("NFKD", texto)

    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )

    texto = re.sub(r"\s+", " ", texto)

    return texto


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
        query_origem TEXT,
        criado_em TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS ix_pop_rua_municipio
        ON pop_rua (municipio);

    CREATE INDEX IF NOT EXISTS ix_pop_rua_uf
        ON pop_rua (uf);

    CREATE INDEX IF NOT EXISTS ix_pop_rua_categoria
        ON pop_rua (categoria);

    CREATE INDEX IF NOT EXISTS ix_pop_rua_data_coleta
        ON pop_rua (data_coleta);
    """

    with engine.begin() as conn:
        conn.execute(text(sql))


def inserir_registro(registro):

    sql = """
    INSERT INTO pop_rua (
        titulo,
        url,
        municipio,
        uf,
        categoria,
        latitude,
        longitude,
        data_coleta,
        data_publicacao,
        query_origem
    )
    VALUES (
        :titulo,
        :url,
        :municipio,
        :uf,
        :categoria,
        :latitude,
        :longitude,
        :data_coleta,
        :data_publicacao,
        :query_origem
    )
    ON CONFLICT (url) DO NOTHING;
    """

    with engine.begin() as conn:
        result = conn.execute(text(sql), registro)
        return result.rowcount


# ============================================================
# MUNICÍPIOS
# ============================================================

def carregar_municipios():

    print("📍 Carregando municípios...")

    df = pd.read_csv(URL_IBGE)

    df["nome_norm"] = (
        df["nome"]
        .astype(str)
        .apply(normalizar_texto)
    )

    coords_local = {}

    for _, row in df.iterrows():

        try:

            codigo_uf = int(row["codigo_uf"])

            municipio_norm = row["nome_norm"]

            nome_original = str(row["nome"]).strip()

            coords_local[municipio_norm] = {
                "nome_original": nome_original,
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "uf": MAPA_UF.get(codigo_uf, "NI")
            }

        except Exception:
            continue

    lista_local = sorted(
        coords_local.keys(),
        key=len,
        reverse=True
    )

    print(f"✅ Municípios carregados: {len(lista_local)}")

    return coords_local, lista_local


COORDS, LISTA_MUNICIPIOS = carregar_municipios()


# ============================================================
# DETECTAR MUNICÍPIO
# ============================================================

def detectar_municipio(titulo, texto, url=""):

    titulo_norm = normalizar_texto(titulo)
    texto_norm = normalizar_texto(texto)
    url_norm = normalizar_texto(url)

    # =====================================================
    # PRIORIDADE 1 - TÍTULO
    # =====================================================

    for municipio_norm in LISTA_MUNICIPIOS:

        if len(municipio_norm) < 3:
            continue

        padrao = rf"\b{re.escape(municipio_norm)}\b"

        if re.search(padrao, titulo_norm):
            return municipio_norm

    # =====================================================
    # PRIORIDADE 2 - URL
    # =====================================================

    for municipio_norm in LISTA_MUNICIPIOS:

        if len(municipio_norm) < 3:
            continue

        municipio_url = municipio_norm.replace(" ", "-")

        if municipio_url in url_norm:
            return municipio_norm

    # =====================================================
    # PRIORIDADE 3 - TEXTO
    # =====================================================

    trecho = texto_norm[:8000]

    for municipio_norm in LISTA_MUNICIPIOS:

        if len(municipio_norm) < 3:
            continue

        padrao = rf"\b{re.escape(municipio_norm)}\b"

        if re.search(padrao, trecho):
            return municipio_norm

    return None


# ============================================================
# CLASSIFICAÇÃO
# ============================================================

def classificar(texto):

    texto_norm = normalizar_texto(texto)

    for categoria, palavras in CATEGORIAS.items():

        if categoria == "Outros":
            continue

        for palavra in palavras:

            palavra_norm = normalizar_texto(palavra)

            if palavra_norm in texto_norm:
                return categoria

    return "Outros"


# ============================================================
# PROCESSAR NOTÍCIA
# ============================================================

def processar_noticia(item):

    url, query_origem = item

    try:

        artigo = Article(
            url,
            language="pt",
            request_timeout=15
        )

        artigo.download()
        artigo.parse()

        titulo = artigo.title or ""
        texto = artigo.text or ""

        if len(texto) < 100:
            return None

        municipio_norm = detectar_municipio(
             titulo=titulo,
             texto=texto,
             url=url
        )

        if municipio_norm:

            info = COORDS.get(municipio_norm)

            municipio = str(info["nome_original"]).title()
            uf = info["uf"]
            latitude = info["latitude"]
            longitude = info["longitude"]

        else:

            municipio = "Não identificado"
            uf = "NI"
            latitude = None
            longitude = None

        categoria = classificar(texto)

        data_publicacao = artigo.publish_date

        if (
            data_publicacao is not None
            and data_publicacao.tzinfo is not None
        ):
            data_publicacao = data_publicacao.replace(
                tzinfo=None
            )

        return {
            "titulo": titulo[:1000],
            "url": url,
            "municipio": municipio,
            "uf": uf,
            "categoria": categoria,
            "latitude": latitude,
            "longitude": longitude,
            "data_coleta": datetime.now(),
            "data_publicacao": data_publicacao,
            "query_origem": query_origem,
        }

    except Exception:
        return None


# ============================================================
# BUSCA TURBINADA
# ============================================================

def buscar_urls():

    urls_encontradas = {}

    print("🔎 Iniciando buscas avançadas...")

    anos = [
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
        "2026",
    ]

    estados = [
        "SP", "RJ", "MG", "BA", "PR",
        "RS", "SC", "GO", "DF", "PE",
        "CE", "PA"
    ]

    sites = [
        "site:g1.globo.com",
        "site:uol.com.br",
        "site:terra.com.br",
        "site:metropoles.com",
        "site:cnnbrasil.com.br",
        "site:band.uol.com.br",
        "site:recordtv.r7.com",
    ]

    queries_expandidas = []

    for query in QUERIES:

        queries_expandidas.append(query)

        for ano in anos:
            queries_expandidas.append(f"{query} {ano}")

        for uf in estados:
            queries_expandidas.append(f"{query} {uf}")

        for site in sites:
            queries_expandidas.append(f"{query} {site}")

        for ano in anos:
            for uf in estados:
                queries_expandidas.append(f"{query} {uf} {ano}")

    queries_expandidas = list(set(queries_expandidas))

    print(f"📌 Queries totais: {len(queries_expandidas)}")

    try:

        with DDGS() as ddgs:

            for indice, query in enumerate(queries_expandidas, start=1):

                print("------------------------------------------------")
                print(f"🔍 Query {indice}/{len(queries_expandidas)}")
                print(query)

                try:

                    resultados = ddgs.text(
                        query,
                        region="br-pt",
                        safesearch="off",
                        max_results=700
                    )

                    novos = 0

                    for resultado in resultados:

                        url = resultado.get("href")

                        if not url:
                            continue

                        url_lower = url.lower()

                        if any(
                            lixo in url_lower
                            for lixo in [
                                 ".pdf"
                            ]
                       ):
                        continue

                        if url not in urls_encontradas:
                            urls_encontradas[url] = query
                            novos += 1

                    print(f"✅ Novas URLs: {novos}")
                    print(f"📦 Total acumulado: {len(urls_encontradas)}")

                except Exception as e:

                    print("❌ Erro na query")
                    print(e)

                time.sleep(random.uniform(0.1, 0.4))

    except Exception as e:

        print("❌ Erro geral DDGS")
        print(e)

    print("================================================")
    print(f"✅ TOTAL FINAL: {len(urls_encontradas)} URLs")
    print("================================================")

    return urls_encontradas


# ============================================================
# RESUMO
# ============================================================

def exibir_resumo_banco():

    sql = """
    SELECT
        COUNT(*) AS total_registros,
        COUNT(DISTINCT url) AS total_urls,
        COUNT(DISTINCT municipio) AS total_municipios,
        COUNT(DISTINCT categoria) AS total_categorias
    FROM pop_rua;
    """

    with engine.begin() as conn:

        row = conn.execute(
            text(sql)
        ).mappings().first()

    print("======================================")
    print("📊 RESUMO BANCO")
    print("======================================")
    print(f"Registros: {row['total_registros']}")
    print(f"URLs: {row['total_urls']}")
    print(f"Municípios: {row['total_municipios']}")
    print(f"Categorias: {row['total_categorias']}")


# ============================================================
# MAIN
# ============================================================

def main():

    print("======================================")
    print("🚀 INICIANDO COLETOR TURBINADO")
    print(f"⏰ {datetime.now()}")
    print("======================================")

    criar_tabela()

    urls = buscar_urls()

    if not urls:
        print("⚠️ Nenhuma URL encontrada.")
        return

    total_processadas = 0
    total_inseridas = 0
    total_duplicadas = 0
    total_erros = 0

    itens = list(urls.items())

    print("======================================")
    print("⚡ PROCESSAMENTO MULTITHREAD")
    print("======================================")

    with ThreadPoolExecutor(max_workers=12) as executor:

        futures = {
            executor.submit(processar_noticia, item): item
            for item in itens
        }

        for indice, future in enumerate(as_completed(futures), start=1):

            try:

                registro = future.result()

                print("--------------------------------------")
                print(f"Processado: {indice}/{len(itens)}")

                if not registro:
                    total_erros += 1
                    continue

                total_processadas += 1

                inseriu = inserir_registro(registro)

                if inseriu:

                    total_inseridas += 1

                    print(
                        f"✅ Inserido: "
                        f"{registro['titulo'][:80]}"
                    )

                else:

                    total_duplicadas += 1

                    print(
                        f"🔁 Duplicado: "
                        f"{registro['titulo'][:80]}"
                    )

            except Exception as e:

                total_erros += 1

                print("❌ Erro future")
                print(e)

    print("======================================")
    print("📌 RESUMO FINAL")
    print("======================================")

    print(f"URLs encontradas: {len(urls)}")
    print(f"Processadas: {total_processadas}")
    print(f"Inseridas: {total_inseridas}")
    print(f"Duplicadas: {total_duplicadas}")
    print(f"Erros: {total_erros}")

    print(f"⏰ Finalizado: {datetime.now()}")

    exibir_resumo_banco()

    print("🚀 FINALIZADO")


if __name__ == "__main__":
    main()

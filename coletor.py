import os
import re
import time
import random
import unicodedata
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from bs4 import BeautifulSoup
from ddgs import DDGS
from newspaper import Article

from sqlalchemy import create_engine, text


# ============================================================
# CONFIG
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não encontrada")

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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64)"
    )
}

# ============================================================
# QUERIES
# ============================================================

QUERIES = [
    "morador de rua morto",
    "morador de rua assassinado",
    "morador de rua agredido",
    "morador de rua baleado",
    "morador de rua esfaqueado",
    "morador de rua queimado",
    "morador de rua atropelado",
    "morador de rua encontrado morto",
    "pessoa em situação de rua morta",
    "pessoa em situação de rua assassinada",
    "sem teto morto",
    "sem teto assassinado",
    "violência contra morador de rua",
    "crime contra morador de rua",
    "população em situação de rua",
    "sem-teto",
    "sem teto",
    "pessoas em situação de rua",
    "homem em situação de rua",
    "mulher em situação de rua",
    "criança em situação de rua",
    "adolescente em situação de rua",
    "jovem em situação de rua",
    "pedinte",
    "mendicância",
    "mendigos",
    "mendigo",
    "morador de rua",
    "moradora de rua",
    "pessoa em situação de rua",
    "cidadãos em situação de rua",
    "cidadão em situação de rua",
    "PSR",
    "família em situação de rua",
    "acolhimento população em situação de rua",
    "centro pop",
    "PAR",
]

# ============================================================
# UF
# ============================================================

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

    texto = str(valor or "").lower()

    texto = unicodedata.normalize("NFKD", texto)

    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()

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
    """

    with engine.begin() as conn:
        conn.execute(text(sql))

# ============================================================
# INSERT
# ============================================================

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

    print("📍 Carregando municípios")

    df = pd.read_csv(URL_IBGE)

    df["nome_norm"] = (
        df["nome"]
        .astype(str)
        .apply(normalizar_texto)
    )

    coords = {}

    for _, row in df.iterrows():

        try:

            codigo_uf = int(row["codigo_uf"])

            municipio_norm = row["nome_norm"]

            coords[municipio_norm] = {
                "nome_original": row["nome"],
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "uf": MAPA_UF.get(codigo_uf, "NI")
            }

        except:
            pass

    lista = sorted(
        coords.keys(),
        key=len,
        reverse=True
    )

    print(f"✅ {len(lista)} municípios")

    return coords, lista

COORDS, LISTA_MUNICIPIOS = carregar_municipios()

# ============================================================
# DETECTAR MUNICÍPIO
# ============================================================

def detectar_municipio(texto):

    texto_norm = normalizar_texto(texto)

    for municipio in LISTA_MUNICIPIOS:

        if len(municipio) < 3:
            continue

        if municipio in texto_norm:
            return municipio

    return None

# ============================================================
# CATEGORIA
# ============================================================

def classificar(texto):

    texto = normalizar_texto(texto)

    if any(x in texto for x in [
        "morto",
        "morreu",
        "assassinado",
        "homicidio",
        "homicídio"
    ]):
        return "Morte"

    if any(x in texto for x in [
        "agredido",
        "espancado",
        "violencia",
        "violência",
        "baleado",
        "esfaqueado"
    ]):
        return "Violência"

    if any(x in texto for x in [
        "atropelado",
        "acidente"
    ]):
        return "Acidente"

    return "Outros"

# ============================================================
# EXTRAIR TEXTO FALLBACK
# ============================================================

def extrair_texto_requests(url):

    try:

        response = requests.get(
            url,
            timeout=15,
            headers=HEADERS
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        titulo = ""

        if soup.title:
            titulo = soup.title.text

        paragrafos = soup.find_all("p")

        texto = " ".join(
            p.get_text(" ", strip=True)
            for p in paragrafos
        )

        return titulo, texto

    except:
        return "", ""

# ============================================================
# PROCESSAR
# ============================================================

def processar_noticia(item):

    url, query = item

    try:

        titulo = ""
        texto = ""

        try:

            artigo = Article(
                url,
                language="pt"
            )

            artigo.download()
            artigo.parse()

            titulo = artigo.title or ""
            texto = artigo.text or ""

        except:
            pass

        # FALLBACK
        if len(texto) < 50:

            titulo2, texto2 = extrair_texto_requests(url)

            if len(texto2) > len(texto):
                titulo = titulo2
                texto = texto2

        if len(texto) < 30:
            return None

        base = f"{titulo} {texto} {url}"

        municipio_norm = detectar_municipio(base)

        if municipio_norm:

            info = COORDS.get(municipio_norm)

            municipio = info["nome_original"]
            uf = info["uf"]
            latitude = info["latitude"]
            longitude = info["longitude"]

        else:

            municipio = "Não identificado"
            uf = "NI"
            latitude = None
            longitude = None

        categoria = classificar(base)

        return {
            "titulo": titulo[:1000],
            "url": url,
            "municipio": municipio,
            "uf": uf,
            "categoria": categoria,
            "latitude": latitude,
            "longitude": longitude,
            "data_coleta": datetime.now(),
            "data_publicacao": None,
            "query_origem": query,
        }

    except:
        return None

# ============================================================
# BUSCAR URLS
# ============================================================

def buscar_urls():

    urls = {}

    anos = [
        "2018",
        "2019",
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
        "2026"
    ]

    estados = list(MAPA_UF.values())

    queries = []

    for q in QUERIES:

        queries.append(q)

        for ano in anos:
            queries.append(f"{q} {ano}")

        for uf in estados:
            queries.append(f"{q} {uf}")

        for uf in estados:
            for ano in anos:
                queries.append(f"{q} {uf} {ano}")

    queries = list(set(queries))

    print(f"🔎 {len(queries)} queries")

    with DDGS() as ddgs:

        for i, query in enumerate(queries):

            try:

                print(f"🔍 {i+1}/{len(queries)}")

                resultados = ddgs.text(
                    query,
                    region="br-pt",
                    safesearch="off",
                    max_results=300
                )

                novos = 0

                for r in resultados:

                    url = r.get("href")

                    if not url:
                        continue

                    if any(x in url.lower() for x in [
                        "youtube",
                        "facebook",
                        "instagram",
                        ".pdf"
                    ]):
                        continue

                    if url not in urls:
                        urls[url] = query
                        novos += 1

                print(f"✅ +{novos}")

            except Exception as e:
                print(e)

            time.sleep(0.1)

    print(f"📦 TOTAL URLs: {len(urls)}")

    return urls

# ============================================================
# MAIN
# ============================================================

def main():

    criar_tabela()

    urls = buscar_urls()

    itens = list(urls.items())

    total = 0

    with ThreadPoolExecutor(max_workers=40) as executor:

        futures = [
            executor.submit(
                processar_noticia,
                item
            )
            for item in itens
        ]

        for future in as_completed(futures):

            registro = future.result()

            if not registro:
                continue

            try:

                inseriu = inserir_registro(registro)

                if inseriu:
                    total += 1
                    print(f"✅ {total}")

            except Exception as e:
                print(e)

    print("================================")
    print(f"TOTAL INSERIDO: {total}")
    print("================================")

if __name__ == "__main__":
    main()

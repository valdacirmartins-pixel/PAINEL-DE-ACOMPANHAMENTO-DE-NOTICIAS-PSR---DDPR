import os
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from ddgs import DDGS
from newspaper import Article, Config
from sqlalchemy import create_engine, text

# ============================================================
# CONFIGURAÇÃO DE VARREDURA EXAUSTIVA
# ============================================================

APP_TIMEZONE = "America/Sao_Paulo"
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# 1. LIGAÇÃO DIRETA: TERMOS DE BUSCA POR CATEGORIA
# O robô usará cada um desses termos para cada UF
DICIONARIO_BUSCA = {
    "Morte": [
        "morador de rua morto", "corpo de morador de rua encontrado", 
        "homicídio pessoa em situação de rua", "óbito morador de rua hoje"
    ],
    "Violência": [
        "morador de rua espancado", "ataque a morador de rua", 
        "pessoa em situação de rua esfaqueada", "violência contra morador de rua"
    ],
    "Impacto Positivo": [
        "doação para moradores de rua", "projeto social situação de rua", 
        "abrigo inaugurado morador de rua", "morador de rua consegue emprego",
        "ação de solidariedade população de rua"
    ],
    "Ação Política/Jurídica": [
        "prefeitura morador de rua", "projeto de lei situação de rua", 
        "decisão judicial morador de rua", "censo população de rua",
        "política pública moradores de rua"
    ],
    "Saúde/Acidente": [
        "morador de rua atropelado", "atendimento médico morador de rua", 
        "consultório na rua", "morador de rua hipotermia frio"
    ]
}

UFS_BRASIL = [
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA',
    'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN',
    'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
]

COORD_ESTADOS = {
    'AC': (-9.02, -70.81), 'AL': (-9.57, -36.78), 'AP': (0.03, -51.07), 'AM': (-3.41, -64.03),
    'BA': (-12.51, -41.70), 'CE': (-5.20, -39.53), 'DF': (-15.80, -47.86), 'ES': (-19.18, -40.30),
    'GO': (-15.82, -49.83), 'MA': (-4.96, -45.27), 'MT': (-12.68, -55.42), 'MS': (-20.77, -54.78),
    'MG': (-18.51, -44.51), 'PA': (-1.99, -52.14), 'PB': (-7.23, -36.78), 'PR': (-24.89, -51.55),
    'PE': (-8.81, -36.95), 'PI': (-7.71, -42.72), 'RJ': (-22.84, -43.15), 'RN': (-5.22, -36.52),
    'RS': (-30.03, -51.21), 'RO': (-11.50, -63.58), 'RR': (2.73, -62.07), 'SC': (-27.24, -50.21),
    'SP': (-23.55, -46.63), 'SE': (-10.57, -37.45), 'TO': (-10.17, -48.33)
}

config = Config()
config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0'
config.request_timeout = 15

# ============================================================
# PROCESSAMENTO
# ============================================================

def salvar_no_banco(dados):
    sql = """
    INSERT INTO pop_rua (titulo, url, municipio, uf, categoria, latitude, longitude, data_coleta, data_publicacao)
    VALUES (:titulo, :url, :municipio, :uf, :categoria, :latitude, :longitude, :data_coleta, :data_publicacao)
    ON CONFLICT (url) DO NOTHING;
    """
    with engine.begin() as conn:
        return conn.execute(text(sql), dados).rowcount

# ============================================================
# LOOP DE VARREDURA CATEGORIZADA
# ============================================================

def main():
    print("🛰️ INICIANDO VARREDURA POR LIGAÇÃO DIRETA (CATEGORIA x TERMO x UF)")
    total_sucesso = 0
    urls_vistas = set()

    with DDGS() as ddgs:
        for uf in UFS_BRASIL:
            lat, lon = COORD_ESTADOS[uf]
            
            # Percorre cada categoria e cada termo ligado a ela
            for categoria, termos in DICIONARIO_BUSCA.items():
                for termo_base in termos:
                    query = f"{termo_base} {uf}"
                    print(f"🔍 Buscando [{categoria}]: {query}")
                    
                    try:
                        # Pegamos os top 15 de cada termo específico
                        resultados = ddgs.text(query, region="br-pt", max_results=15)
                        if not resultados: continue

                        for r in resultados:
                            link = r.get("href")
                            if not link or link in urls_vistas: continue
                            urls_vistas.add(link)

                            try:
                                art = Article(link, language="pt", config=config)
                                art.download()
                                art.parse()

                                if len(art.text) < 150: continue

                                registro = {
                                    "titulo": art.title[:250],
                                    "url": link,
                                    "municipio": f"Busca em {uf}",
                                    "uf": uf,
                                    "categoria": categoria, # Categoria ligada diretamente ao termo
                                    "latitude": lat,
                                    "longitude": lon,
                                    "data_coleta": datetime.now(ZoneInfo(APP_TIMEZONE)),
                                    "data_publicacao": art.publish_date
                                }

                                if salvar_no_banco(registro):
                                    total_sucesso += 1
                                    print(f"   ✅ Novo registro: {art.title[:40]}")
                            
                            except: continue
                        
                        # Pequena pausa para evitar bloqueio por IP
                        time.sleep(random.uniform(2, 4))

                    except Exception as e:
                        print(f"⚠️ Alerta na busca: {e}")
                        time.sleep(10)

    print(f"🏁 Varredura completa. {total_sucesso} registros mapeados.")

if __name__ == "__main__":
    main()

import os
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from ddgs import DDGS
from newspaper import Article, Config
from sqlalchemy import create_engine, text

# ============================================================
# CONFIGURAÇÃO DE VARREDURA ABSOLUTA - 27 UNIDADES DA FEDERAÇÃO
# ============================================================

APP_TIMEZONE = "America/Sao_Paulo"
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# LISTA COMPLETA E INALTERADA - TODOS OS CANTOS DO BRASIL
UFS_NOMES = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas', 'BA': 'Bahia', 
    'CE': 'Ceará', 'DF': 'Distrito Federal', 'ES': 'Espírito Santo', 'GO': 'Goiás', 
    'MA': 'Maranhão', 'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais', 
    'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná', 'PE': 'Pernambuco', 'PI': 'Piauí', 
    'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte', 'RS': 'Rio Grande do Sul', 
    'RO': 'Rondônia', 'RR': 'Roraima', 'SC': 'Santa Catarina', 'SP': 'São Paulo', 
    'SE': 'Sergipe', 'TO': 'Tocantins'
}

COORD_ESTADOS = {
    'AC': (-9.02, -70.81), 'AL': (-9.57, -36.78), 'AP': (0.03, -51.07), 'AM': (-3.41, -64.03),
    'BA': (-12.51, -41.70), 'CE': (-5.20, -39.53), 'DF': (-15.80, -47.86), 'ES': (-19.18, -40.30),
    'GO': (-15.82, -49.83), 'MA': (-4.96, -45.27), 'MT': (-12.68, -55.42), 'MS': (-20.77, -54.78),
    'MG': (-18.51, -44.51), 'PA': (-1.99, -52.14), 'PB': (-7.23, -36.78), 'PR': (-24.89, -51.55),
    'PE': (-8.81, -36.95), 'PI': (-7.71, -42.72), 'RJ': (-22.84, -43.15), 'RN': (-5.22, -36.52),
    'RS': (-30.03, -51.21), 'RO': (-11.50, -63.58), 'RR': (2.73, -62.07), 'SC': (-27.24, -50.21),
    'SP': (-23.55, -46.63), 'SE': (-10.57, -37.45), 'TO': (-10.17, -48.33)
}

# CATEGORIAS AMPLIADAS PARA COBERTURA TÉCNICA E SOCIAL
DICIONARIO_BUSCA = {
    "Morte/Hipotermia": [
        "morador de rua morto", "corpo encontrado situação de rua", 
        "homicídio morador de rua", "pessoa sem teto falecida", "hipotermia população de rua"
    ],
    "Violência/Agressão": [
        "morador de rua espancado", "ataque a morador de rua", 
        "violência contra população de rua", "agressão pessoa em situação de rua"
    ],
    "Saúde/Social": [
        "Consultório na Rua", "saúde mental população de rua", 
        "segurança alimentar população de rua", "projeto social população de rua",
        "doação moradores de rua", "acolhimento institucional rua"
    ],
    "Políticas Públicas/Governo": [
        "Diretoria de Políticas para a População em Situação de Rua",
        "Ministério dos Direitos Humanos população de rua",
        "Censo população de rua 2026", "Plano Ruas Visíveis",
        "prefeitura moradores de rua", "decisão judicial morador de rua"
    ]
}

config = Config()
config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
config.request_timeout = 25

def salvar_no_banco(dados):
    sql = """
    INSERT INTO pop_rua (titulo, url, municipio, uf, categoria, latitude, longitude, data_coleta, data_publicacao)
    VALUES (:titulo, :url, :municipio, :uf, :categoria, :latitude, :longitude, :data_coleta, :data_publicacao)
    ON CONFLICT (url) DO UPDATE SET categoria = EXCLUDED.categoria;
    """
    with engine.begin() as conn:
        return conn.execute(text(sql), dados).rowcount

def main():
    print(f"🛰️ INICIANDO VARREDURA TOTAL BRASIL - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    total_sucesso = 0
    urls_vistas = set()

    with DDGS() as ddgs:
        # Loop garantido em todas as 27 UFs
        for uf, nome_extenso in UFS_NOMES.items():
            lat_fixa, lon_fixa = COORD_ESTADOS.get(uf)
            
            for categoria, termos in DICIONARIO_BUSCA.items():
                for termo_base in termos:
                    # Busca combinada para não perder variação regional
                    query = f'"{termo_base}" {nome_extenso}'
                    print(f"🔍 [UF: {uf}] [CAT: {categoria}] -> {query}")
                    
                    try:
                        # max_results=20 e timelimit='m' (mês) para garantir profundidade
                        resultados = ddgs.text(query, region="br-pt", max_results=20, timelimit='m')
                        
                        if not resultados: continue

                        for r in resultados:
                            link = r.get("href")
                            if not link or link in urls_vistas: continue
                            urls_vistas.add(link)

                            try:
                                art = Article(link, language="pt", config=config)
                                art.download()
                                art.parse()

                                # Filtro de qualidade do conteúdo
                                if len(art.text) < 250: continue

                                registro = {
                                    "titulo": art.title[:250],
                                    "url": link,
                                    "municipio": f"Estado de {nome_extenso}",
                                    "uf": uf,
                                    "categoria": categoria,
                                    "latitude": lat_fixa,
                                    "longitude": lon_fixa,
                                    "data_coleta": datetime.now(ZoneInfo(APP_TIMEZONE)),
                                    "data_publicacao": art.publish_date
                                }

                                if salvar_no_banco(registro):
                                    total_sucesso += 1
                                    print(f"    ✅ Sucesso: {art.title[:50]}...")
                            
                            except Exception:
                                continue
                        
                        # Delay seguro para evitar bloqueio por excesso de requisições
                        time.sleep(random.uniform(4, 8))

                    except Exception as e:
                        print(f"⚠️ Alerta na busca (UF: {uf}): {e}")
                        time.sleep(20)

    print(f"🏁 Varredura completa em todo o território nacional. Total: {total_sucesso} novos registros.")

if __name__ == "__main__":
    while True:
        try:
            main()
            print("💤 Aguardando ciclo de 4 horas...")
            time.sleep(14400)
        except Exception as e:
            print(f"❌ Erro fatal no loop: {e}")
            time.sleep(600)

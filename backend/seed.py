"""Dados de demonstração: encostas simuladas na RMR com 12 horas de leituras simuladas.

As coordenadas são aproximadas e os valores de risco são FICTÍCIOS (só para demonstrar o painel).
"""
import random
from datetime import datetime, timedelta

from . import database, nucleo

# (nome, bairro, município, lat, lon, cenário)
ENCOSTAS = [
    ("Encosta 01", "Dois Unidos", "Recife", -8.0003, -34.8967, "critico"),
    ("Encosta 02", "Passarinho", "Olinda", -8.0089, -34.8990, "limiar"),
    ("Encosta 03", "Alto José do Pinho", "Recife", -8.0192, -34.9083, "atencao"),
    ("Encosta 04", "Morro da Conceição", "Recife", -8.0071, -34.9034, "alto"),
    ("Encosta 05", "Nova Descoberta", "Recife", -8.0107, -34.9246, "calmo"),
    ("Encosta 06", "Brejo da Guabiraba", "Recife", -7.9894, -34.9433, "calmo"),
    ("Encosta 07", "Vasco da Gama", "Recife", -8.0231, -34.9156, "atencao"),
]

# cenário: (valores iniciais, valores finais) ao longo de 12 horas
CENARIOS = {
    "calmo":   ({"chuva_24h": 8,  "chuva_72h": 25,  "umidade_solo": 35, "inclinacao": 0.6, "fluxo_optico": 0.4, "aceleracao": 0.0, "tem_lona": 0},
                {"chuva_24h": 12, "chuva_72h": 30,  "umidade_solo": 38, "inclinacao": 0.7, "fluxo_optico": 0.5, "aceleracao": 0.0, "tem_lona": 0}),
    "atencao": ({"chuva_24h": 30, "chuva_72h": 80,  "umidade_solo": 55, "inclinacao": 1.5, "fluxo_optico": 1.5, "aceleracao": 0.1, "tem_lona": 0},
                {"chuva_24h": 45, "chuva_72h": 110, "umidade_solo": 62, "inclinacao": 2.0, "fluxo_optico": 2.4, "aceleracao": 0.2, "tem_lona": 1}),
    "alto":    ({"chuva_24h": 25, "chuva_72h": 70,  "umidade_solo": 50, "inclinacao": 1.2, "fluxo_optico": 1.0, "aceleracao": 0.0, "tem_lona": 0},
                {"chuva_24h": 55, "chuva_72h": 140, "umidade_solo": 68, "inclinacao": 2.6, "fluxo_optico": 3.4, "aceleracao": 0.3, "tem_lona": 1}),
    "limiar":  ({"chuva_24h": 25, "chuva_72h": 70,  "umidade_solo": 50, "inclinacao": 1.2, "fluxo_optico": 1.0, "aceleracao": 0.0, "tem_lona": 0},
                {"chuva_24h": 65, "chuva_72h": 150, "umidade_solo": 70, "inclinacao": 2.8, "fluxo_optico": 3.6, "aceleracao": 0.3, "tem_lona": 1}),
    "critico": ({"chuva_24h": 60, "chuva_72h": 150, "umidade_solo": 70, "inclinacao": 2.5, "fluxo_optico": 3.5, "aceleracao": 0.5, "tem_lona": 1},
                {"chuva_24h": 130, "chuva_72h": 260, "umidade_solo": 94, "inclinacao": 5.0, "fluxo_optico": 10.0, "aceleracao": 2.0, "tem_lona": 1}),
}


def popular():
    if database.tem_encostas():
        return
    rng = random.Random(7)
    agora = datetime.now().replace(minute=0, second=0, microsecond=0)
    for nome, bairro, municipio, lat, lon, cenario in ENCOSTAS:
        encosta_id = database.cadastrar_encosta(nome, bairro, municipio, lat, lon)
        ini, fim = CENARIOS[cenario]
        for h in range(12):
            t = h / 11
            leitura = {}
            for k in ini:
                if k == "tem_lona":                      # a lona aparece no meio do período
                    leitura[k] = int(fim[k] if t > 0.4 else ini[k])
                    continue
                v = (ini[k] + (fim[k] - ini[k]) * t) * rng.uniform(0.92, 1.08)
                v = max(0.0, v) if k != "aceleracao" else v
                leitura[k] = round(min(v, 100.0) if k == "umidade_solo" else v, 2)
            previsao = nucleo.prever(leitura)
            database.salvar_leitura(encosta_id, leitura, previsao,
                                    agora - timedelta(hours=11 - h))

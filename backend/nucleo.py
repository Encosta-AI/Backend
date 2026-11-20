"""Núcleo de Risco: carrega o modelo salvo e transforma uma leitura em nível de risco."""
import joblib
import pandas as pd
from pathlib import Path

NIVEIS = ["verde", "amarelo", "laranja", "vermelho"]
CAMINHO = Path(__file__).resolve().parent / "nucleo_de_risco.joblib"

_pacote = joblib.load(CAMINHO)  # {"modelo", "colunas", "limiar_critico"}


def prever(leitura: dict) -> dict:
    """Recebe as variáveis de uma leitura e devolve nível, confiança (%) e se o alerta veio do limiar."""
    x = pd.DataFrame([leitura])[_pacote["colunas"]]
    p = _pacote["modelo"].predict_proba(x)[0]
    nivel = int(p.argmax())
    por_limiar = False
    if p[3] > _pacote["limiar_critico"] and nivel != 3:
        nivel = 3          # limiar assimétrico: na dúvida, prefere alertar
        por_limiar = True
    return {
        "nivel": NIVEIS[nivel],
        "confianca": round(float(p[nivel]) * 100, 1),
        "prob_vermelho": round(float(p[3]) * 100, 1),
        "por_limiar": por_limiar,
    }

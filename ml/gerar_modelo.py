"""Gera o Núcleo de Risco (XGBoost calibrado) com dados simulados.

Salva backend/nucleo_de_risco.joblib no MESMO formato da célula 7 do notebook
"Núcleo de Risco": {"modelo", "colunas", "limiar_critico"}.
Se vocês já têm o .joblib do Colab, basta colocá-lo em backend/ no lugar deste.

Uso (na pasta do projeto):  python ml/gerar_modelo.py
"""
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import recall_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

rng = np.random.default_rng(42)
n = 3000

df = pd.DataFrame({
    "chuva_24h": rng.gamma(2, 25, n),
    "chuva_72h": rng.gamma(2, 50, n),
    "umidade_solo": rng.uniform(15, 100, n),
    "inclinacao": rng.gamma(1.5, 1.0, n),
    "fluxo_optico": np.clip(rng.gamma(1.2, 2.0, n), 0, 15),
    "aceleracao": rng.normal(0.2, 0.8, n),
    "tem_lona": rng.integers(0, 2, n),
})
score = (0.012 * df.chuva_24h + 0.006 * df.chuva_72h + 0.015 * df.umidade_solo
         + 0.35 * df.inclinacao + 0.25 * df.fluxo_optico
         + 0.30 * np.maximum(df.aceleracao, 0) + 0.5 * df.tem_lona
         + rng.normal(0, 0.25, n))
df["risco"] = pd.cut(
    score,
    [-np.inf, np.quantile(score, .55), np.quantile(score, .80), np.quantile(score, .94), np.inf],
    labels=[0, 1, 2, 3]).astype(int)

X, y = df.drop(columns="risco"), df["risco"]
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)

modelo = CalibratedClassifierCV(
    XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1, random_state=42),
    method="isotonic", cv=3)
modelo.fit(X_tr, y_tr)

proba = modelo.predict_proba(X_te)
pred = proba.argmax(axis=1)
pred[proba[:, 3] > 0.30] = 3
print("recall do vermelho com limiar de 30%:", round(recall_score(y_te == 3, pred == 3), 3))

destino = Path(__file__).resolve().parent.parent / "backend" / "nucleo_de_risco.joblib"
joblib.dump({"modelo": modelo, "colunas": list(X.columns), "limiar_critico": 0.30}, destino)
print("modelo salvo em", destino)

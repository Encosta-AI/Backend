"""Classificador de lona: olha a foto da câmera e diz se a barreira tem lona plástica.

Usa o modelo treinado no Colab (YOLOv8n-cls), salvo como backend/classificador_lona.pt
(ou no caminho da variável LONA_MODELO). Se o arquivo não existir, o sistema continua
funcionando e apenas avisa que a análise de foto está indisponível.
"""
import io
import os
from pathlib import Path

CAMINHO = Path(os.environ.get("LONA_MODELO", Path(__file__).resolve().parent / "classificador_lona.pt"))
TAMANHO = 224

_modelo = None
_tentou = False


def _carregar():
    """Carrega o modelo uma vez (a biblioteca é pesada, então só na primeira análise)."""
    global _modelo, _tentou
    if _tentou:
        return _modelo
    _tentou = True
    if not CAMINHO.exists():
        return None
    try:
        from ultralytics import YOLO
        _modelo = YOLO(str(CAMINHO))
    except Exception:
        _modelo = None
    return _modelo


def disponivel() -> bool:
    return CAMINHO.exists()


def _eh_sem_lona(nome: str) -> bool:
    return "sem" in nome.lower()          # as classes do treino: "Barreiras com lona" / "Barrairas sem lona"


def classificar(dados: bytes) -> dict | None:
    """Devolve {'tem_lona': 0/1, 'classe', 'confianca'} ou None se o modelo não está disponível."""
    modelo = _carregar()
    if modelo is None:
        return None
    from PIL import Image
    try:
        with Image.open(io.BytesIO(dados)) as im:
            r = modelo.predict(im.convert("RGB"), imgsz=TAMANHO, verbose=False)[0]
    except Exception:
        return None
    nome = r.names[int(r.probs.top1)]
    sem = _eh_sem_lona(nome)
    return {"tem_lona": 0 if sem else 1,
            "classe": "sem lona" if sem else "com lona",
            "confianca": round(float(r.probs.top1conf) * 100, 1)}

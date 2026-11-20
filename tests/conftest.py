"""Preparação do ambiente de testes: banco e pasta de fotos temporários, senha e chave de teste."""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# precisam existir ANTES de importar o backend (o módulo de login lê as variáveis ao ser importado)
os.environ["ADMIN_USUARIO"] = "admin"
os.environ["ADMIN_SENHA"] = "senha-de-teste-123"
os.environ["SEGREDO_SESSAO"] = "segredo-de-teste"
os.environ["DISPOSITIVO_CHAVE"] = "chave-do-dispositivo"

import pytest
from fastapi.testclient import TestClient

from backend import auth, database, fotos, main, vistorias

SENHA = os.environ["ADMIN_SENHA"]
CHAVE = os.environ["DISPOSITIVO_CHAVE"]

LEITURA_OK = {"chuva_24h": 40, "chuva_72h": 100, "umidade_solo": 50, "inclinacao": 1.5,
              "fluxo_optico": 2.0, "aceleracao": 0.0, "tem_lona": 0}

VISTORIA_OK = {"nome": "Maria da Silva", "telefone": "81999998888", "email": "maria@exemplo.com",
               "cidade": "Recife", "tipo": "Barreira", "endereco": "Rua das Flores, 120",
               "latitude": "-8.0476", "longitude": "-34.877", "descricao": "Rachaduras na barreira",
               "consentimento": "on"}


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """Cliente HTTP sem login, com banco novo (7 encostas simuladas) a cada teste."""
    monkeypatch.setattr(database, "DB", tmp_path / "teste.db")
    monkeypatch.setattr(fotos, "PASTA", tmp_path / "fotos")
    vistorias._envios.clear()
    auth._falhas.clear()
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def admin(cliente):
    """Cliente já logado como administrador."""
    r = cliente.post("/api/admin/login", json={"usuario": "admin", "senha": SENHA})
    assert r.status_code == 200
    return cliente

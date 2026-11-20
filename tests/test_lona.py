"""Testes da ligação do classificador de lona (CT-76 a CT-82). O modelo real é trocado por um falso
para o teste não depender do arquivo .pt nem da biblioteca pesada."""
import types

from backend import lona

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _falso(monkeypatch, tem_lona=1):
    monkeypatch.setattr(lona, "disponivel", lambda: True)
    monkeypatch.setattr(lona, "classificar", lambda d: {
        "tem_lona": tem_lona, "classe": "com lona" if tem_lona else "sem lona", "confianca": 97.0})


def test_ct76_sem_modelo_o_sistema_continua(admin, monkeypatch):
    """CT-76 | Funcional | Enviar foto sem o modelo de lona instalado | 201, lona = null, análise 'indisponível'"""
    monkeypatch.setattr(lona, "disponivel", lambda: False)
    monkeypatch.setattr(lona, "classificar", lambda d: None)
    r = admin.put("/api/encostas/1/foto", content=PNG)
    assert r.status_code == 201 and r.json()["lona"] is None
    assert admin.get("/api/encostas/1/lona").json() == {"disponivel": False, "analise": None}


def test_ct77_foto_analisada(admin, monkeypatch):
    """CT-77 | Funcional | Enviar foto com o modelo disponível | resposta e consulta trazem tem_lona, classe e confiança"""
    _falso(monkeypatch, 1)
    r = admin.put("/api/encostas/1/foto", content=PNG)
    assert r.json()["lona"]["tem_lona"] == 1
    a = admin.get("/api/encostas/1/lona").json()
    assert a["disponivel"] is True and a["analise"]["classe"] == "com lona"


def test_ct78_aplicar_muda_a_leitura(admin, monkeypatch):
    """CT-78 | Funcional | Aplicar o resultado da foto na leitura | tem_lona da encosta passa a valer o da foto e o risco é recalculado"""
    _falso(monkeypatch, 0)
    antes = next(e for e in admin.get("/api/encostas").json() if e["id"] == 1)
    admin.put("/api/encostas/1/foto", content=PNG)
    r = admin.post("/api/encostas/1/lona/aplicar")
    assert r.status_code == 200 and r.json()["tem_lona"] == 0
    depois = next(e for e in admin.get("/api/encostas").json() if e["id"] == 1)
    assert depois["tem_lona"] == 0 and depois["nivel"] == r.json()["nivel"]
    assert len(admin.get("/api/encostas/1/historico?limite=50").json()) >= 1
    assert antes["chuva_24h"] == depois["chuva_24h"]          # só o tem_lona mudou


def test_ct79_aplicar_sem_analise(admin, monkeypatch):
    """CT-79 | Funcional | Aplicar sem ter enviado foto | 409"""
    _falso(monkeypatch)
    assert admin.post("/api/encostas/2/lona/aplicar").status_code == 409


def test_ct80_foto_nova_apaga_analise_antiga(admin, monkeypatch):
    """CT-80 | Funcional | Nova foto sem modelo depois de uma analisada | a análise antiga não é reutilizada"""
    _falso(monkeypatch, 1)
    admin.put("/api/encostas/1/foto", content=PNG)
    monkeypatch.setattr(lona, "classificar", lambda d: None)
    admin.put("/api/encostas/1/foto", content=PNG)
    assert admin.get("/api/encostas/1/lona").json()["analise"] is None


def test_ct81_lona_so_para_admin(cliente):
    """CT-81 | Segurança | Consultar e aplicar lona sem login | 401 nas duas rotas"""
    assert cliente.get("/api/encostas/1/lona").status_code == 401
    assert cliente.post("/api/encostas/1/lona/aplicar").status_code == 401


def test_ct82_traducao_das_classes(monkeypatch):
    """CT-82 | Funcional | Nomes de classe do treino ('sem lona' / 'com lona') | tem_lona 0 e 1 corretos"""
    class Probs:
        def __init__(self, i): self.top1, self.top1conf = i, 0.9

    class Modelo:
        names = {0: "Barrairas sem lona", 1: "Barreiras com lona"}
        def __init__(self, i): self.i = i
        def predict(self, im, **k): return [types.SimpleNamespace(names=self.names, probs=Probs(self.i))]

    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (8, 8)).save(buf, "PNG")
    for i, esperado in ((0, 0), (1, 1)):
        monkeypatch.setattr(lona, "_carregar", lambda i=i: Modelo(i))
        assert lona.classificar(buf.getvalue())["tem_lona"] == esperado

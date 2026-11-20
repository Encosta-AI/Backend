"""Testes exploratórios: tentativas de quebrar o sistema. Os que falharam na 1ª execução viraram defeitos (BUG-xx)."""
import pytest

from backend import chuva
from tests.conftest import LEITURA_OK, SENHA, VISTORIA_OK


def test_ct65_cabecalho_forjado_nao_burla_bloqueio_de_login(cliente):
    """CT-65 | RNF-Seg | Segurança | Trocar o cabeçalho X-Forwarded-For a cada tentativa de login | o bloqueio por tentativas continua valendo (6ª tentativa = 429)"""
    codigos = [cliente.post("/api/admin/login", json={"usuario": "admin", "senha": "x"},
                            headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(8)]
    assert 429 in codigos, codigos


def test_ct66_cabecalho_forjado_nao_burla_limite_de_vistorias(cliente):
    """CT-66 | RNF-Seg | Segurança | Trocar o cabeçalho X-Forwarded-For a cada pedido de vistoria | o limite de 5 por hora continua valendo"""
    codigos = [cliente.post("/api/vistorias", json=VISTORIA_OK,
                            headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(8)]
    assert 429 in codigos, codigos


@pytest.mark.parametrize("arquivo", ["/index.html", "/script.js", "/login.html"])
def test_ct67_arquivos_do_painel_sem_login(cliente, arquivo):
    """CT-67 | RF02 | Segurança | A API não entrega mais os arquivos da tela | 404, o painel vive no site"""
    assert cliente.get(arquivo, follow_redirects=False).status_code == 404


@pytest.mark.parametrize("valor", ["nan", "inf", "-inf", "1e400"])
def test_ct68_numeros_especiais_nas_coordenadas(cliente, valor):
    """CT-68 | RF07 | Funcional | Coordenadas NaN, infinito ou gigantes | rejeitadas (422), nunca gravadas"""
    r = cliente.post("/api/vistorias", json={**VISTORIA_OK, "latitude": valor, "longitude": valor})
    assert r.status_code == 422


def test_ct69_nan_na_leitura(admin):
    """CT-69 | RF04 | Funcional | Leitura com NaN e Infinity no JSON | rejeitada (422), não chega ao modelo"""
    for bruto in ('{"encosta_id":1,"chuva_24h":NaN,"chuva_72h":1,"umidade_solo":1,"inclinacao":1,"fluxo_optico":1,"aceleracao":0,"tem_lona":0}',
                  '{"encosta_id":1,"chuva_24h":Infinity,"chuva_72h":1,"umidade_solo":1,"inclinacao":1,"fluxo_optico":1,"aceleracao":0,"tem_lona":0}'):
        r = admin.post("/api/leituras", content=bruto, headers={"Content-Type": "application/json"})
        assert r.status_code == 422


def test_ct70_nome_so_com_espacos(cliente):
    """CT-70 | RF07 | Funcional | Nome ou endereço só com espaços | rejeitado (422)"""
    assert cliente.post("/api/vistorias", json={**VISTORIA_OK, "nome": "     "}).status_code == 422
    assert cliente.post("/api/vistorias", json={**VISTORIA_OK, "endereco": "      "}).status_code == 422


def test_ct71_corpo_enorme(cliente):
    """CT-71 | RNF-Seg | Segurança | Pedido de vistoria com corpo de 5 MB | rejeitado sem derrubar o servidor"""
    r = cliente.post("/api/vistorias", json={**VISTORIA_OK, "descricao": "x" * (5 * 1024 * 1024)})
    assert r.status_code in (413, 422)
    assert cliente.post("/api/vistorias", json=VISTORIA_OK).status_code == 201


def test_ct72_reiniciar_demo_em_producao(admin, monkeypatch):
    """CT-72 | RF03 | Segurança | Em produção (MODO_DEMO=0) o botão 'Reiniciar dados' não pode apagar as encostas reais | 403 e dados preservados"""
    monkeypatch.setenv("MODO_DEMO", "0")
    admin.post("/api/encostas", json={"nome": "Real", "bairro": "Bairro", "municipio": "Recife", "lat": -8.0, "lon": -34.9})
    r = admin.post("/api/demo/reiniciar")
    assert r.status_code == 403
    assert len(admin.get("/api/encostas").json()) == 8


def test_ct73_falha_do_inmet_nao_fica_em_cache_por_30_min(admin, monkeypatch):
    """CT-73 | RF10 | Funcional | O INMET cai e volta logo depois | a falha não fica guardada por 30 min: a próxima consulta já usa os dados novos"""
    from datetime import datetime, timezone
    agora = datetime.now(timezone.utc)
    chuva._cache.update(quando=0.0, dados=None)
    estado = {"falhar": True}

    def baixar(*a):
        if estado["falhar"]:
            raise OSError("sem rede")
        return [{"DT_MEDICAO": agora.strftime("%Y-%m-%d"), "HR_MEDICAO": agora.strftime("%H%M"), "CHUVA": "2"}]
    monkeypatch.setattr(chuva, "_baixar", baixar)
    assert admin.get("/api/chuva").json()["ok"] is False
    chuva._cache["quando"] -= 120                      # passam 2 minutos
    estado["falhar"] = False
    assert admin.get("/api/chuva").json()["ok"] is True


def test_ct74_api_com_login_continua_acessivel(admin):
    """CT-74 | RF02 | Regressão | Administrador logado consulta a API | 200 (a sessão continua valendo sem a tela antiga)"""
    assert admin.get("/api/admin/eu").status_code == 200
    assert admin.get("/api/encostas").status_code == 200
    assert admin.get("/", follow_redirects=False).status_code == 404


def test_ct75_proxy_de_confianca(cliente, monkeypatch):
    """CT-75 | RNF-Seg | Regressão | Servidor hospedado atrás de proxy (CONFIAR_PROXY=1) | o IP real vem do cabeçalho e cada IP tem o seu próprio limite"""
    monkeypatch.setenv("CONFIAR_PROXY", "1")
    for _ in range(5):
        cliente.post("/api/admin/login", json={"usuario": "admin", "senha": "x"}, headers={"X-Forwarded-For": "200.1.1.1"})
    bloqueado = cliente.post("/api/admin/login", json={"usuario": "admin", "senha": SENHA}, headers={"X-Forwarded-For": "200.1.1.1"})
    livre = cliente.post("/api/admin/login", json={"usuario": "admin", "senha": SENHA}, headers={"X-Forwarded-For": "200.2.2.2"})
    assert bloqueado.status_code == 429 and livre.status_code == 200

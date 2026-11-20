"""Casos de teste automatizados do Encosta Ai.

Cada função tem um código CT-xx e aponta o requisito (RF/RNF) que verifica. O relatório
(gerar_relatorio.py) lê estas linhas do docstring: "CT-xx | requisito | tipo | descrição | esperado".
"""
import time
from datetime import datetime, timedelta, timezone

import pytest

from backend import chuva, nucleo, tempo
from tests.conftest import CHAVE, LEITURA_OK, SENHA, VISTORIA_OK

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


# ====================================================================== RF01 login do administrador
def test_ct01_login_valido(cliente):
    """CT-01 | RF01 | Funcional | Login com usuário e senha corretos | 200 e cookie de sessão HttpOnly/SameSite=strict"""
    r = cliente.post("/api/admin/login", json={"usuario": "admin", "senha": SENHA})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert cliente.get("/api/admin/eu").json()["logado"] is True


@pytest.mark.parametrize("usuario,senha", [("admin", "errada"), ("outro", SENHA), ("", ""), ("admin", "")])
def test_ct02_login_invalido(cliente, usuario, senha):
    """CT-02 | RF01 | Funcional | Login com senha errada, usuário errado ou campos vazios | 401 e sem sessão"""
    r = cliente.post("/api/admin/login", json={"usuario": usuario, "senha": senha})
    assert r.status_code == 401
    assert cliente.get("/api/admin/eu").json()["logado"] is False


def test_ct03_login_campo_ausente(cliente):
    """CT-03 | RF01 | Funcional | Login sem o campo senha | 422 (requisição inválida)"""
    assert cliente.post("/api/admin/login", json={"usuario": "admin"}).status_code == 422


def test_ct04_bloqueio_por_tentativas(cliente):
    """CT-04 | RNF-Seg | Segurança | 5 senhas erradas seguidas | a 6ª tentativa é bloqueada com 429"""
    for _ in range(5):
        assert cliente.post("/api/admin/login", json={"usuario": "admin", "senha": "x"}).status_code == 401
    assert cliente.post("/api/admin/login", json={"usuario": "admin", "senha": "x"}).status_code == 429


def test_ct05_logout(admin):
    """CT-05 | RF01 | Funcional | Sair do painel | sessão encerrada e rotas protegidas voltam a negar"""
    assert admin.post("/api/admin/logout").status_code == 200
    assert admin.get("/api/encostas").status_code == 401


def test_ct06_token_adulterado(cliente):
    """CT-06 | RNF-Seg | Segurança | Cookie de sessão forjado/adulterado | acesso negado (401)"""
    for falso in ["abc.def", "e30=.0000", "lixo"]:
        cliente.cookies.set("sessao", falso)
        assert cliente.get("/api/encostas").status_code == 401


# ====================================================================== RF02 proteção das rotas
ROTAS_PROTEGIDAS = [
    ("GET", "/api/encostas"), ("GET", "/api/encostas/1/historico"), ("POST", "/api/prever"),
    ("POST", "/api/encostas"), ("GET", "/api/vistorias"), ("PATCH", "/api/vistorias/1"),
    ("GET", "/api/chuva"), ("GET", "/api/encostas/1/foto"), ("PUT", "/api/encostas/1/foto"),
    ("POST", "/api/leituras"), ("POST", "/api/demo/reiniciar"), ("POST", "/api/demo/avancar/1"),
]


@pytest.mark.parametrize("metodo,rota", ROTAS_PROTEGIDAS)
def test_ct07_rotas_exigem_login(cliente, metodo, rota):
    """CT-07 | RF02 | Segurança | Acessar rota do administrador sem login | 401"""
    assert cliente.request(metodo, rota, json={}).status_code == 401


def test_ct08_api_nao_entrega_painel(cliente):
    """CT-08 | RF02 | Funcional | A API não entrega mais a tela: o painel fica no site, separado do backend"""
    assert cliente.get("/", follow_redirects=False).status_code == 404


# ====================================================================== RF03 cadastro de encosta
def test_ct09_cadastrar_encosta(admin):
    """CT-09 | RF03 | Funcional | Cadastrar encosta válida | 201 e aparece na listagem sem leitura"""
    r = admin.post("/api/encostas", json={"nome": "Encosta Teste", "bairro": "Casa Amarela",
                                          "municipio": "Recife", "lat": -8.02, "lon": -34.9})
    assert r.status_code == 201
    lista = admin.get("/api/encostas").json()
    nova = next(e for e in lista if e["id"] == r.json()["id"])
    assert nova["nivel"] is None


@pytest.mark.parametrize("campo,valor", [("nome", "A"), ("bairro", ""), ("municipio", "x" * 81),
                                          ("lat", 91), ("lat", -91), ("lon", 181), ("lon", -181)])
def test_ct10_encosta_invalida(admin, campo, valor):
    """CT-10 | RF03 | Funcional (valor-limite) | Cadastrar encosta com nome curto, vazio, longo ou coordenada fora da faixa | 422"""
    corpo = {"nome": "Encosta", "bairro": "Bairro", "municipio": "Recife", "lat": -8.0, "lon": -34.9}
    corpo[campo] = valor
    assert admin.post("/api/encostas", json=corpo).status_code == 422


# ====================================================================== RF04 leituras e risco
def test_ct11_leitura_valida(admin):
    """CT-11 | RF04 | Funcional | Enviar leitura válida | 201, nível de risco válido e gravação no histórico"""
    r = admin.post("/api/leituras", json={**LEITURA_OK, "encosta_id": 1})
    assert r.status_code == 201
    assert r.json()["nivel"] in nucleo.NIVEIS
    hist = admin.get("/api/encostas/1/historico?limite=1").json()
    assert hist[-1]["chuva_24h"] == LEITURA_OK["chuva_24h"]


def test_ct12_leitura_encosta_inexistente(admin):
    """CT-12 | RF04 | Funcional | Leitura para encosta que não existe | 404"""
    assert admin.post("/api/leituras", json={**LEITURA_OK, "encosta_id": 9999}).status_code == 404


LIMITES = [  # campo, válidos (limites), inválidos (logo fora do limite)
    ("chuva_24h", [0, 500], [-0.1, 500.1]), ("chuva_72h", [0, 1000], [-1, 1001]),
    ("umidade_solo", [0, 100], [-0.1, 100.1]), ("inclinacao", [0, 45], [-1, 46]),
    ("fluxo_optico", [0, 50], [-1, 51]), ("aceleracao", [-20, 20], [-21, 21]),
    ("tem_lona", [0, 1], [-1, 2]),
]


@pytest.mark.parametrize("campo,validos,invalidos", LIMITES)
def test_ct13_valor_limite_leitura(admin, campo, validos, invalidos):
    """CT-13 | RF04 | Funcional (valor-limite) | Cada variável da leitura nos limites e logo fora deles | limites aceitos (201), fora dos limites rejeitados (422)"""
    for v in validos:
        r = admin.post("/api/leituras", json={**LEITURA_OK, "encosta_id": 1, campo: v})
        assert r.status_code == 201, (campo, v)
    for v in invalidos:
        r = admin.post("/api/leituras", json={**LEITURA_OK, "encosta_id": 1, campo: v})
        assert r.status_code == 422, (campo, v)


@pytest.mark.parametrize("valor", ["abc", None, [], {}])
def test_ct14_tipo_invalido_leitura(admin, valor):
    """CT-14 | RF04 | Funcional (partição de equivalência) | Leitura com texto, nulo, lista ou objeto em campo numérico | 422"""
    assert admin.post("/api/leituras", json={**LEITURA_OK, "encosta_id": 1, "umidade_solo": valor}).status_code == 422


def test_ct15_leitura_campo_ausente(admin):
    """CT-15 | RF04 | Funcional | Leitura sem um dos campos obrigatórios | 422"""
    corpo = {**LEITURA_OK, "encosta_id": 1}
    corpo.pop("fluxo_optico")
    assert admin.post("/api/leituras", json=corpo).status_code == 422


def test_ct16_dispositivo_com_chave(cliente):
    """CT-16 | RF04 | Segurança | Dispositivo (câmera/ESP32) envia leitura com a chave correta | 201"""
    r = cliente.post("/api/leituras", json={**LEITURA_OK, "encosta_id": 1}, headers={"X-Chave-Dispositivo": CHAVE})
    assert r.status_code == 201


@pytest.mark.parametrize("chave", ["", "errada", CHAVE + "x", CHAVE[:-1]])
def test_ct17_dispositivo_chave_errada(cliente, chave):
    """CT-17 | RF04 | Segurança | Dispositivo com chave ausente, errada ou parecida | 401"""
    r = cliente.post("/api/leituras", json={**LEITURA_OK, "encosta_id": 1}, headers={"X-Chave-Dispositivo": chave})
    assert r.status_code == 401


def test_ct18_dispositivo_nao_le_dados(cliente):
    """CT-18 | RF02 | Segurança | A chave do dispositivo não dá acesso à leitura de dados do painel | 401"""
    assert cliente.get("/api/encostas", headers={"X-Chave-Dispositivo": CHAVE}).status_code == 401


# ====================================================================== RF05 núcleo de risco
def test_ct19_risco_calmo():
    """CT-19 | RF05 | Funcional | Leitura calma (pouca chuva, solo parado, sem aceleração) | nível verde"""
    r = nucleo.prever({"chuva_24h": 5, "chuva_72h": 20, "umidade_solo": 30, "inclinacao": 0.5,
                       "fluxo_optico": 0.3, "aceleracao": 0.0, "tem_lona": 0})
    assert r["nivel"] == "verde"


def test_ct20_risco_critico():
    """CT-20 | RF05 | Funcional | Leitura crítica (chuva forte, solo saturado, aceleração alta) | nível vermelho"""
    r = nucleo.prever({"chuva_24h": 130, "chuva_72h": 260, "umidade_solo": 94, "inclinacao": 5.0,
                       "fluxo_optico": 10.0, "aceleracao": 2.0, "tem_lona": 1})
    assert r["nivel"] == "vermelho"


def test_ct21_risco_coerente_com_a_chuva():
    """CT-21 | RF05 | Funcional | Piora gradual das condições | o risco nunca diminui quando tudo piora"""
    ordem = {n: i for i, n in enumerate(nucleo.NIVEIS)}
    anterior = -1
    for f in range(0, 11):
        t = f / 10
        r = nucleo.prever({"chuva_24h": 5 + 125 * t, "chuva_72h": 20 + 240 * t, "umidade_solo": 30 + 64 * t,
                           "inclinacao": 0.5 + 4.5 * t, "fluxo_optico": 0.3 + 9.7 * t,
                           "aceleracao": 2.0 * t, "tem_lona": 0})
        assert ordem[r["nivel"]] >= anterior, (f, r)
        anterior = ordem[r["nivel"]]


def test_ct22_formato_da_resposta():
    """CT-22 | RF05 | Funcional | Estrutura da resposta do modelo | nível, confiança (0–100), prob. vermelho (0–100) e flag do limiar"""
    r = nucleo.prever(LEITURA_OK)
    assert set(r) == {"nivel", "confianca", "prob_vermelho", "por_limiar"}
    assert 0 <= r["confianca"] <= 100 and 0 <= r["prob_vermelho"] <= 100 and isinstance(r["por_limiar"], bool)


def test_ct23_simulador_nao_grava(admin):
    """CT-23 | RF05 | Funcional | Simulador (/api/prever) | devolve o risco sem gravar nada no histórico"""
    antes = len(admin.get("/api/encostas/1/historico?limite=200").json())
    assert admin.post("/api/prever", json=LEITURA_OK).status_code == 200
    assert len(admin.get("/api/encostas/1/historico?limite=200").json()) == antes


# ====================================================================== RF06 tempo até a ruptura
def _hist(velocidades, inicio=None, passo_min=60):
    inicio = inicio or datetime(2026, 11, 1, 6, 0)
    return [{"criado_em": (inicio + timedelta(minutes=passo_min * i)).isoformat(), "fluxo_optico": v}
            for i, v in enumerate(velocidades)]


def test_ct24_ruptura_com_aceleracao():
    """CT-24 | RF06 | Funcional | Solo acelerando (1/v decrescente e linear) | estimativa válida, no futuro, com qualidade alta"""
    h = _hist([1 / (1.0 - 0.1 * i) for i in range(6)])   # 1/v cai 0,1 por hora -> ruptura 5 h depois da 1ª leitura
    r = tempo.estimar(h)
    assert r["ok"] and r["qualidade"] >= 0.99
    assert datetime.fromisoformat(r["ruptura_em"]) >= datetime.fromisoformat(h[-1]["criado_em"])


def test_ct25_ruptura_valor_exato():
    """CT-25 | RF06 | Funcional | Resultado numérico conhecido | 1/v = 1,0 − 0,1·t chega a zero em t = 10 h; da 6ª leitura (t = 5 h) faltam 5 h"""
    h = _hist([1 / (1.0 - 0.1 * i) for i in range(6)])
    assert tempo.estimar(h)["horas"] == pytest.approx(5.0, abs=0.05)


def test_ct26_sem_aceleracao():
    """CT-26 | RF06 | Funcional | Velocidade constante | sem estimativa (não há tendência de ruptura)"""
    assert tempo.estimar(_hist([2.0] * 6))["ok"] is False


def test_ct27_solo_desacelerando():
    """CT-27 | RF06 | Funcional | Solo desacelerando (velocidade caindo) | sem estimativa"""
    assert tempo.estimar(_hist([4.0, 3.5, 3.0, 2.5, 2.0, 1.5]))["ok"] is False


@pytest.mark.parametrize("n,esperado", [(0, False), (3, False), (4, True), (5, True)])
def test_ct28_minimo_de_pontos(n, esperado):
    """CT-28 | RF06 | Funcional (valor-limite) | 0, 3, 4 e 5 leituras com movimento | só estima com 4 ou mais"""
    h = _hist([1 / (1.0 - 0.1 * i) for i in range(n)])
    assert tempo.estimar(h)["ok"] is esperado


def test_ct29_velocidade_minima():
    """CT-29 | RF06 | Funcional (valor-limite) | Velocidade abaixo de 0,3 px/h é ignorada | leituras paradas não entram no cálculo"""
    assert tempo.estimar(_hist([0.29, 0.29, 0.29, 0.29, 0.29]))["ok"] is False


def test_ct30_limite_72_horas():
    """CT-30 | RF06 | Funcional (valor-limite) | Ruptura estimada muito distante (> 72 h) | sem estimativa"""
    h = _hist([1 / (2.0 - 0.001 * i) for i in range(6)])
    r = tempo.estimar(h)
    assert r["ok"] is False


def test_ct31_leituras_com_mesmo_horario():
    """CT-31 | RF06 | Funcional | Leituras duplicadas no mesmo instante | não quebra e informa que não dá para estimar"""
    h = _hist([1, 2, 3, 4, 5], passo_min=0)
    assert tempo.estimar(h)["ok"] is False


def test_ct32_leituras_irregulares():
    """CT-32 | RF06 | Funcional | Velocidades bagunçadas (ajuste ruim) | sem estimativa por baixa qualidade"""
    assert tempo.estimar(_hist([1.0, 5.0, 0.4, 6.0, 0.5, 7.0]))["ok"] is False


def test_ct33_antecipacao_da_ruptura():
    """CT-33 | RF06 | Funcional | Solo acelera de repente | o painel recebe o aviso 'antecipada_min' (≥ 15 min)"""
    base = [1 / (1.0 - 0.05 * i) for i in range(6)]
    h = _hist(base + [base[-1] * 3])
    r = tempo.com_comparacao(h)
    assert r["ok"] and r.get("antecipada_min", 0) >= 15


def test_ct34_demo_tempestade_coerente():
    """CT-34 | RF06 | Funcional | Passos da demonstração de tempestade | a velocidade só aumenta e respeita os limites do modelo"""
    ult = {"chuva_24h": 60, "chuva_72h": 150, "umidade_solo": 70, "inclinacao": 2.5,
           "fluxo_optico": 3.5, "aceleracao": 0.5, "tem_lona": 1}
    anterior = ult["fluxo_optico"]
    for _ in range(30):
        ult = tempo.passo_tempestade(ult)
        assert ult["fluxo_optico"] >= anterior and ult["fluxo_optico"] <= 50
        assert ult["umidade_solo"] <= 100 and ult["chuva_24h"] <= 300
        anterior = ult["fluxo_optico"]


def test_ct35_ruptura_na_listagem(admin):
    """CT-35 | RF06 | Integração | Encosta em alerta na listagem | traz o campo 'ruptura' (e as sem alerta trazem None)"""
    lista = admin.get("/api/encostas").json()
    for e in lista:
        if e["nivel"] in ("laranja", "vermelho"):
            assert e["ruptura"] is not None
        else:
            assert e["ruptura"] is None


# ====================================================================== RF07 pedido de vistoria (civil)
def test_ct36_vistoria_valida(cliente):
    """CT-36 | RF07 | Funcional | Civil envia pedido completo | 201 com apenas ok e protocolo (sem risco nem dados internos)"""
    r = cliente.post("/api/vistorias", json=VISTORIA_OK)
    assert r.status_code == 201
    assert set(r.json()) == {"ok", "protocolo"}


def test_ct37_vistoria_minima(cliente):
    """CT-37 | RF07 | Funcional | Pedido só com os campos obrigatórios (sem e-mail, coordenadas e descrição) | 201"""
    corpo = {k: VISTORIA_OK[k] for k in ("nome", "telefone", "cidade", "endereco", "consentimento")}
    assert cliente.post("/api/vistorias", json=corpo).status_code == 201


@pytest.mark.parametrize("campo,valor,esperado", [
    ("nome", "Ab", 422), ("nome", "Abc", 201), ("nome", "A" * 100, 201), ("nome", "A" * 101, 422),
    ("telefone", "1234567", 422), ("telefone", "12345678", 201), ("telefone", "1" * 25, 201), ("telefone", "1" * 26, 422),
    ("endereco", "ab", 422), ("endereco", "abc", 201), ("endereco", "a" * 201, 422),
    ("descricao", "d" * 1000, 201), ("descricao", "d" * 1001, 422),
    ("cidade", "R", 422), ("cidade", "Re", 201),
])
def test_ct38_limites_dos_campos(cliente, campo, valor, esperado):
    """CT-38 | RF07 | Funcional (valor-limite) | Tamanho mínimo e máximo de nome, telefone, endereço, descrição e cidade | dentro do limite 201, fora 422"""
    assert cliente.post("/api/vistorias", json={**VISTORIA_OK, campo: valor}).status_code == esperado


@pytest.mark.parametrize("email,esperado", [("a@b.co", 201), ("sem-arroba", 422), ("a@b", 422), ("a b@c.com", 422), ("", 201)])
def test_ct39_email(cliente, email, esperado):
    """CT-39 | RF07 | Funcional (partição de equivalência) | E-mail válido, sem arroba, sem domínio, com espaço e em branco | só os válidos/vazio passam"""
    assert cliente.post("/api/vistorias", json={**VISTORIA_OK, "email": email}).status_code == esperado


@pytest.mark.parametrize("tipo,esperado", [("Encosta", 201), ("Barreira", 201), ("Muro de contenção", 201),
                                           ("Não sei informar", 201), ("Prédio", 422), ("", 422)])
def test_ct40_tipo_de_local(cliente, tipo, esperado):
    """CT-40 | RF07 | Funcional | Tipo do local: as 4 opções do formulário e valores fora da lista | só as opções válidas passam"""
    assert cliente.post("/api/vistorias", json={**VISTORIA_OK, "tipo": tipo}).status_code == esperado


@pytest.mark.parametrize("lat,lon,esperado", [
    ("-8,0476", "-34,877", 201), ("-8.0476", "-34.877", 201), ("", "", 201),
    ("-8.0476", "", 422), ("", "-34.877", 422),
    ("90", "180", 201), ("-90", "-180", 201), ("90.1", "0", 422), ("0", "180.1", 422), ("abc", "1", 422)])
def test_ct41_coordenadas(cliente, lat, lon, esperado):
    """CT-41 | RF07 | Funcional (valor-limite) | Coordenadas com vírgula, em branco, só uma, nos limites, fora deles e com texto | regras de par e faixa respeitadas"""
    r = cliente.post("/api/vistorias", json={**VISTORIA_OK, "latitude": lat, "longitude": lon})
    assert r.status_code == esperado


@pytest.mark.parametrize("consent,esperado", [("on", 201), (True, 201), ("sim", 201), (False, 422), ("", 422), ("off", 422)])
def test_ct42_consentimento_lgpd(cliente, consent, esperado):
    """CT-42 | RF07 | Funcional | Consentimento LGPD marcado, desmarcado e valores estranhos | sem consentimento não envia (422)"""
    assert cliente.post("/api/vistorias", json={**VISTORIA_OK, "consentimento": consent}).status_code == esperado


def test_ct43_honeypot(admin):
    """CT-43 | RNF-Seg | Segurança | Robô preenche o campo-isca 'site' | responde ok mas NÃO grava a solicitação"""
    r = admin.post("/api/vistorias", json={**VISTORIA_OK, "site": "http://spam.com"})
    assert r.status_code == 201 and "protocolo" not in r.json()
    assert admin.get("/api/vistorias").json() == []


def test_ct44_limite_por_ip(cliente):
    """CT-44 | RNF-Seg | Segurança | 6 pedidos seguidos do mesmo IP | os 5 primeiros passam, o 6º recebe 429"""
    codigos = [cliente.post("/api/vistorias", json=VISTORIA_OK).status_code for _ in range(6)]
    assert codigos == [201] * 5 + [429]


def test_ct45_sql_injection(admin):
    """CT-45 | RNF-Seg | Segurança | Tentativa de SQL injection nos campos de texto | texto guardado literalmente e as tabelas continuam intactas"""
    ataque = "x'); DROP TABLE vistorias;--"
    assert admin.post("/api/vistorias", json={**VISTORIA_OK, "nome": ataque, "descricao": ataque}).status_code == 201
    lista = admin.get("/api/vistorias").json()
    assert lista[0]["nome"] == ataque
    assert len(admin.get("/api/encostas").json()) == 7


def test_ct46_painel_nao_usa_innerhtml():
    """CT-46 | RNF-Seg | Segurança | Texto digitado pelo civil não pode virar HTML no painel | a tela monta o conteúdo sem innerHTML"""
    from pathlib import Path
    painel = Path(__file__).resolve().parent.parent.parent / "encostaAiFront" / "src" / "components" / "PainelAdmin.tsx"
    texto = painel.read_text(encoding="utf-8")
    assert "innerHTML" not in texto and "insertAdjacentHTML" not in texto and "document.write" not in texto and "dangerouslySetInnerHTML" not in texto


def test_ct47_dados_pessoais_so_admin(cliente):
    """CT-47 | RF08 | Segurança | Listar solicitações (nome, telefone, endereço) sem ser administrador | 401"""
    cliente.post("/api/vistorias", json=VISTORIA_OK)
    assert cliente.get("/api/vistorias").status_code == 401


# ====================================================================== RF08 gestão das solicitações
def test_ct48_listar_e_filtrar(admin):
    """CT-48 | RF08 | Funcional | Administrador lista solicitações (mais recentes primeiro) e filtra por status | ordem e filtro corretos"""
    ids = [admin.post("/api/vistorias", json={**VISTORIA_OK, "nome": f"Pessoa {i}"}).json()["protocolo"] for i in range(3)]
    lista = admin.get("/api/vistorias").json()
    assert [v["id"] for v in lista] == sorted(ids, reverse=True)
    admin.patch(f"/api/vistorias/{ids[0]}", json={"status": "concluida"})
    assert [v["id"] for v in admin.get("/api/vistorias?status=concluida").json()] == [ids[0]]
    assert len(admin.get("/api/vistorias?status=nova").json()) == 2


@pytest.mark.parametrize("status,esperado", [("nova", 200), ("em_analise", 200), ("concluida", 200), ("apagada", 422), ("", 422)])
def test_ct49_mudar_status(admin, status, esperado):
    """CT-49 | RF08 | Funcional (partição de equivalência) | Mudar a situação para valores válidos e inválidos | só nova, em_analise e concluida"""
    p = admin.post("/api/vistorias", json=VISTORIA_OK).json()["protocolo"]
    assert admin.patch(f"/api/vistorias/{p}", json={"status": status}).status_code == esperado


def test_ct50_status_de_solicitacao_inexistente(admin):
    """CT-50 | RF08 | Funcional | Mudar situação de solicitação que não existe | 404"""
    assert admin.patch("/api/vistorias/99999", json={"status": "concluida"}).status_code == 404


def test_ct51_limite_de_listagem(admin):
    """CT-51 | RF08 | Funcional (valor-limite) | Parâmetro limite=0, -5 e 100000 | nunca quebra: o servidor ajusta para o intervalo 1–500"""
    admin.post("/api/vistorias", json=VISTORIA_OK)
    for lim in (0, -5, 100000):
        assert admin.get(f"/api/vistorias?limite={lim}").status_code == 200


# ====================================================================== RF09 foto da câmera
def test_ct52_foto_png_e_jpg(admin):
    """CT-52 | RF09 | Funcional | Enviar foto PNG e depois JPEG | 201, a foto é exibida e a antiga é substituída (só uma por encosta)"""
    assert admin.put("/api/encostas/1/foto", content=PNG).status_code == 201
    r = admin.get("/api/encostas/1/foto")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert admin.put("/api/encostas/1/foto", content=JPG).status_code == 201
    assert admin.get("/api/encostas/1/foto").headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("conteudo", [b"<html>nao sou imagem</html>", b"GIF89a....", b"", b"%PDF-1.4"])
def test_ct53_arquivo_que_nao_e_imagem(admin, conteudo):
    """CT-53 | RF09 | Segurança | Enviar HTML, GIF, PDF ou arquivo vazio como foto | 415 (o conteúdo real é conferido, não o nome)"""
    assert admin.put("/api/encostas/1/foto", content=conteudo).status_code == 415


def test_ct54_foto_grande(admin):
    """CT-54 | RF09 | Funcional (valor-limite) | Foto de exatamente 3 MB e de 3 MB + 1 byte | a primeira é aceita, a segunda recebe 413"""
    limite = 3 * 1024 * 1024
    assert admin.put("/api/encostas/1/foto", content=PNG + b"0" * (limite - len(PNG))).status_code == 201
    assert admin.put("/api/encostas/1/foto", content=PNG + b"0" * (limite - len(PNG) + 1)).status_code == 413


def test_ct55_foto_encosta_inexistente_ou_sem_foto(admin):
    """CT-55 | RF09 | Funcional | Foto de encosta que não existe e encosta sem foto | enviar: 404; ver sem foto: 404"""
    assert admin.put("/api/encostas/9999/foto", content=PNG).status_code == 404
    assert admin.get("/api/encostas/2/foto").status_code == 404


def test_ct56_cabecalhos_da_foto(admin):
    """CT-56 | RF09 | Segurança | Cabeçalhos ao exibir a foto | no-store (sem cache) e nosniff"""
    admin.put("/api/encostas/1/foto", content=PNG)
    h = admin.get("/api/encostas/1/foto").headers
    assert h["cache-control"] == "no-store" and h["x-content-type-options"] == "nosniff"


# ====================================================================== RF10 chuva do INMET
def _registros(agora, horas=80, mm="1,0"):
    saida = []
    for h in range(horas):
        t = agora - timedelta(hours=h)
        saida.append({"DT_MEDICAO": t.strftime("%Y-%m-%d"), "HR_MEDICAO": t.strftime("%H%M"), "CHUVA": mm})
    return saida


def test_ct57_soma_de_chuva():
    """CT-57 | RF10 | Funcional | Somar chuva de 24 h e 72 h (vírgula decimal) | 24 h = 24 mm, 72 h = 72 mm com 1 mm por hora"""
    agora = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)
    r = chuva.somar(_registros(agora), agora)
    assert r["chuva_24h"] == 24.0 and r["chuva_72h"] == 72.0


def test_ct58_medicoes_invalidas():
    """CT-58 | RF10 | Funcional | Medições sem valor, com texto, hora inválida ou futuras | são ignoradas sem quebrar"""
    agora = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)
    lixo = [{"DT_MEDICAO": "2026-11-06", "HR_MEDICAO": "1300", "CHUVA": None},
            {"DT_MEDICAO": "2026-11-06", "HR_MEDICAO": "1300", "CHUVA": "abc"},
            {"DT_MEDICAO": "2026-99-99", "HR_MEDICAO": "1300", "CHUVA": "5"},
            {"DT_MEDICAO": "2026-11-07", "HR_MEDICAO": "1300", "CHUVA": "50"}]
    r = chuva.somar(lixo + _registros(agora, 3), agora)
    assert r["chuva_72h"] == 3.0


def test_ct59_sem_dados():
    """CT-59 | RF10 | Funcional | Nenhuma medição nas últimas 72 h | erro tratado (ValueError), sem número inventado"""
    agora = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        chuva.somar([], agora)


def test_ct60_inmet_fora_do_ar(admin, monkeypatch):
    """CT-60 | RF10 | Funcional | API do INMET indisponível | o painel recebe ok=false com o motivo, sem erro 500"""
    chuva._cache.update(quando=0.0, dados=None)
    monkeypatch.setattr(chuva, "_baixar", lambda *a: (_ for _ in ()).throw(OSError("sem rede")))
    r = admin.get("/api/chuva?atualizar=true")
    assert r.status_code == 200 and r.json()["ok"] is False and "motivo" in r.json()


def test_ct61_cache_da_chuva(admin, monkeypatch):
    """CT-61 | RF10 | Funcional | Duas consultas seguidas | a 2ª usa o cache (a API externa é chamada uma vez só)"""
    chuva._cache.update(quando=0.0, dados=None)
    chamadas = []
    agora = datetime.now(timezone.utc)
    monkeypatch.setattr(chuva, "_baixar", lambda *a: chamadas.append(1) or _registros(agora, 10))
    admin.get("/api/chuva")
    admin.get("/api/chuva")
    assert len(chamadas) == 1


# ====================================================================== não funcionais
def test_ct62_cors(cliente):
    """CT-62 | RNF-Seg | Segurança | Pedido vindo do site oficial e de um site desconhecido | só o site oficial recebe permissão de CORS"""
    base = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    ok = cliente.options("/api/vistorias", headers={**base, "Origin": "https://encostaai.vercel.app"})
    mau = cliente.options("/api/vistorias", headers={**base, "Origin": "https://site-malicioso.com"})
    assert ok.headers.get("access-control-allow-origin") == "https://encostaai.vercel.app"
    assert "access-control-allow-origin" not in mau.headers


def test_ct63_desempenho_do_calculo_de_risco(admin):
    """CT-63 | RNF-Desempenho | Não funcional | 200 chamadas seguidas ao cálculo de risco | tempo médio < 100 ms e máximo < 500 ms por chamada"""
    tempos = []
    for _ in range(200):
        t0 = time.perf_counter()
        assert admin.post("/api/prever", json=LEITURA_OK).status_code == 200
        tempos.append((time.perf_counter() - t0) * 1000)
    media = sum(tempos) / len(tempos)
    print(f"\nDESEMPENHO média={media:.1f} ms máx={max(tempos):.1f} ms p95={sorted(tempos)[189]:.1f} ms")
    assert media < 100 and max(tempos) < 500


def test_ct64_regressao_da_demonstracao(admin):
    """CT-64 | RF06 | Regressão | Avançar 5 h de tempestade na encosta crítica e reiniciar os dados | a ruptura é recalculada e o reinício restaura as 7 encostas"""
    for _ in range(5):
        assert admin.post("/api/demo/avancar/1").status_code == 200
    e1 = next(e for e in admin.get("/api/encostas").json() if e["id"] == 1)
    assert e1["nivel"] == "vermelho" and e1["ruptura"] is not None
    assert admin.post("/api/demo/reiniciar").status_code == 200
    assert len(admin.get("/api/encostas").json()) == 7

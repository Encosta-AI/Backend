"""API do EncostaAI (FastAPI). O painel e o site público ficam em outro projeto e só consomem esta API."""
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from fastapi.middleware.cors import CORSMiddleware

from . import auth, chuva, database, fotos, nucleo, seed, tempo, vistorias

app = FastAPI(title="EncostaAI", description="Alerta antecipado de deslizamentos - RMR")

# Sites que podem chamar a API pelo navegador. Ajuste pela variável
# ORIGENS_PERMITIDAS (separadas por vírgula) ao hospedar o backend.
ORIGENS = os.environ.get(
    "ORIGENS_PERMITIDAS",
    "https://encostaai.vercel.app,http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ORIGENS if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(vistorias.router)
app.include_router(auth.router)
app.include_router(fotos.router)

ADMIN = [Depends(auth.exigir_admin)]      # rotas do painel: só administrador logado


@app.exception_handler(RequestValidationError)
async def erro_de_validacao(req: Request, exc: RequestValidationError):
    """422 enxuto: não devolve o valor enviado (NaN/Infinity quebravam a serialização e davam erro 500)."""
    erros = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": erros})


def _exigir_demo():
    """As rotas de demonstração apagam/alteram dados: em produção defina MODO_DEMO=0."""
    if os.environ.get("MODO_DEMO", "1") == "0":
        raise HTTPException(403, "Desativado: o modo de demonstração está desligado neste servidor.")


@app.get("/api/chuva", dependencies=ADMIN)
def chuva_real(atualizar: bool = False):
    """Chuva acumulada (24 h e 72 h) da estação do INMET; 'ok': false se a API não respondeu."""
    return chuva.obter(forcar=atualizar)


class Leitura(BaseModel):
    """Variáveis de entrada do Núcleo de Risco (com limites para barrar valores absurdos)."""
    chuva_24h: float = Field(ge=0, le=500)
    chuva_72h: float = Field(ge=0, le=1000)
    umidade_solo: float = Field(ge=0, le=100)
    inclinacao: float = Field(ge=0, le=45)
    fluxo_optico: float = Field(ge=0, le=50)
    aceleracao: float = Field(ge=-20, le=20)
    tem_lona: int = Field(ge=0, le=1)


class LeituraEncosta(Leitura):
    encosta_id: int


class NovaEncosta(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    bairro: str = Field(min_length=2, max_length=80)
    municipio: str = Field(min_length=2, max_length=80)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


@app.on_event("startup")
def iniciar():
    auth.configurar()
    database.criar_tabelas()
    vistorias.criar_tabela()
    seed.popular()          # só preenche se o banco estiver vazio


def _com_ruptura(e: dict) -> dict:
    """Em alerta (laranja/vermelho), anexa a estimativa de tempo até a ruptura."""
    if e.get("nivel") in ("laranja", "vermelho"):
        e["ruptura"] = tempo.com_comparacao(database.historico(e["id"], 8))
    else:
        e["ruptura"] = None
    return e


@app.get("/api/encostas", dependencies=ADMIN)
def listar_encostas():
    return [_com_ruptura(e) for e in database.listar_encostas()]


@app.post("/api/demo/avancar/{encosta_id}", dependencies=ADMIN)
def demo_avancar(encosta_id: int):
    """Demonstração: avança 1 h com chuva forte na encosta e grava a nova leitura."""
    _exigir_demo()
    if not database.encosta_existe(encosta_id):
        raise HTTPException(404, "Encosta não encontrada")
    atual = next(e for e in database.listar_encostas() if e["id"] == encosta_id)
    if atual["nivel"] is None:
        raise HTTPException(400, "Esta encosta ainda não tem leituras")
    nova = tempo.passo_tempestade(atual)
    database.avancar_tempo(encosta_id, 1)
    database.salvar_leitura(encosta_id, nova, nucleo.prever(nova))
    return {"ok": True}


@app.post("/api/demo/reiniciar", dependencies=ADMIN)
def demo_reiniciar():
    """Demonstração: apaga tudo e recria os dados simulados."""
    _exigir_demo()
    database.apagar_tudo()
    seed.popular()
    return {"ok": True}


@app.post("/api/encostas", status_code=201, dependencies=ADMIN)
def cadastrar_encosta(e: NovaEncosta):
    return {"id": database.cadastrar_encosta(e.nome, e.bairro, e.municipio, e.lat, e.lon)}


@app.get("/api/encostas/{encosta_id}/historico", dependencies=ADMIN)
def historico(encosta_id: int, limite: int = 24):
    if not database.encosta_existe(encosta_id):
        raise HTTPException(404, "Encosta não encontrada")
    return database.historico(encosta_id, min(max(limite, 1), 200))


@app.post("/api/prever", dependencies=ADMIN)
def prever(leitura: Leitura):
    """Simulador: calcula o risco sem gravar nada no banco."""
    return nucleo.prever(leitura.model_dump())


@app.post("/api/leituras", status_code=201, dependencies=[Depends(auth.exigir_admin_ou_dispositivo)])
def registrar_leitura(l: LeituraEncosta):
    """Recebe uma leitura de uma encosta, calcula o risco e grava no histórico."""
    if not database.encosta_existe(l.encosta_id):
        raise HTTPException(404, "Encosta não encontrada")
    dados = l.model_dump(exclude={"encosta_id"})
    previsao = nucleo.prever(dados)
    database.salvar_leitura(l.encosta_id, dados, previsao)
    return previsao



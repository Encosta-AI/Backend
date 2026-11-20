"""Login do administrador (painel) e chave opcional para dispositivos (câmera, sensores).

- O administrador entra com usuário e senha; o servidor devolve um cookie assinado (HttpOnly).
- Defina ADMIN_USUARIO e ADMIN_SENHA como variáveis de ambiente ao hospedar.
  Se ADMIN_SENHA não estiver definida, é criada uma senha aleatória, guardada em backend/.admin_senha
  e mostrada no terminal na primeira vez (útil só para rodar localmente).
- Dispositivos (câmera/ESP32) podem enviar leituras com o cabeçalho X-Chave-Dispositivo igual à
  variável DISPOSITIVO_CHAVE. Se ela não estiver definida, só o administrador envia leituras.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

ARQUIVO_SENHA = Path(__file__).resolve().parent / ".admin_senha"
DURACAO = 8 * 3600                 # a sessão vale 8 horas
COOKIE = "sessao"
MAX_FALHAS = 5                     # tentativas erradas por IP em 15 minutos
_falhas: dict[str, list[float]] = {}

USUARIO = os.environ.get("ADMIN_USUARIO", "admin")
_senha = os.environ.get("ADMIN_SENHA", "")
_segredo = b""


def configurar():
    """Chamada na inicialização: define a senha (se faltar) e a chave de assinatura."""
    global _senha, _segredo
    if not _senha:
        if ARQUIVO_SENHA.exists():
            _senha = ARQUIVO_SENHA.read_text(encoding="utf-8").strip()
        else:
            _senha = secrets.token_urlsafe(9)
            ARQUIVO_SENHA.write_text(_senha, encoding="utf-8")
            print("\n" + "=" * 60)
            print(f"  Painel do administrador  ->  usuário: {USUARIO}   senha: {_senha}")
            print("  (senha criada para uso local; para hospedar, defina ADMIN_SENHA)")
            print("=" * 60 + "\n")
    chave = os.environ.get("SEGREDO_SESSAO") or "sessao:" + _senha
    _segredo = hashlib.sha256(chave.encode()).digest()


def _assinar(dados: bytes) -> str:
    return hmac.new(_segredo, dados, hashlib.sha256).hexdigest()


def _criar_token() -> str:
    corpo = base64.urlsafe_b64encode(json.dumps({"u": USUARIO, "exp": int(time.time()) + DURACAO}).encode())
    return corpo.decode() + "." + _assinar(corpo)


def _token_valido(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    corpo, assinatura = token.rsplit(".", 1)
    if not hmac.compare_digest(assinatura, _assinar(corpo.encode())):
        return False
    try:
        dados = json.loads(base64.urlsafe_b64decode(corpo.encode()))
    except ValueError:
        return False
    return dados.get("exp", 0) > time.time() and dados.get("u") == USUARIO


def eh_admin(req: Request) -> bool:
    return _token_valido(req.cookies.get(COOKIE))


def exigir_admin(req: Request):
    """Dependência do FastAPI: só deixa passar quem está logado como administrador."""
    if not eh_admin(req):
        raise HTTPException(401, "É preciso entrar como administrador.")


def exigir_admin_ou_dispositivo(req: Request):
    """Leituras: administrador logado OU dispositivo com a chave correta."""
    chave_ok = os.environ.get("DISPOSITIVO_CHAVE", "")
    enviada = req.headers.get("x-chave-dispositivo", "")
    if chave_ok and hmac.compare_digest(enviada, chave_ok):
        return
    exigir_admin(req)


def ip_cliente(req: Request) -> str:
    """IP de quem fez o pedido. O cabeçalho X-Forwarded-For só é aceito se o servidor estiver atrás de
    um proxy de confiança (CONFIAR_PROXY=1, ex.: Render/Railway). Sem isso, qualquer pessoa poderia
    forjar o cabeçalho e fugir do bloqueio de login e do limite de pedidos."""
    if os.environ.get("CONFIAR_PROXY") == "1":
        enc = req.headers.get("x-forwarded-for")
        if enc:
            return enc.split(",")[0].strip()
    return req.client.host if req.client else "?"


_ip = ip_cliente


router = APIRouter(prefix="/api/admin", tags=["admin"])


class Login(BaseModel):
    usuario: str = Field(max_length=80)
    senha: str = Field(max_length=200)


@router.post("/login")
def login(dados: Login, req: Request, resp: Response):
    ip, agora = _ip(req), time.time()
    recentes = [t for t in _falhas.get(ip, []) if agora - t < 900]
    if len(recentes) >= MAX_FALHAS:
        raise HTTPException(429, "Muitas tentativas. Aguarde alguns minutos.")
    ok = hmac.compare_digest(dados.usuario.encode(), USUARIO.encode()) and \
        hmac.compare_digest(dados.senha.encode(), _senha.encode())
    if not ok:
        recentes.append(agora)
        _falhas[ip] = recentes
        raise HTTPException(401, "Usuário ou senha incorretos.")
    _falhas.pop(ip, None)
    seguro, mesmo_site = _cookie(req)
    resp.set_cookie(COOKIE, _criar_token(), max_age=DURACAO, httponly=True, samesite=mesmo_site, secure=seguro)
    return {"ok": True}


def _cookie(req: Request) -> tuple[bool, str]:
    """Em HTTPS (site e API em domínios diferentes) o cookie precisa de SameSite=None.
    No desenvolvimento, Strict basta: localhost:5173 e localhost:8000 são o mesmo site."""
    modo = os.environ.get("COOKIE_SAMESITE", "").strip().lower()
    seguro = req.url.scheme == "https" or req.headers.get("x-forwarded-proto") == "https"
    if modo not in ("lax", "strict", "none"):
        modo = "none" if seguro else "strict"
    if modo == "none":
        seguro = True
    return seguro, modo


@router.post("/logout")
def logout(req: Request, resp: Response):
    seguro, mesmo_site = _cookie(req)
    resp.delete_cookie(COOKIE, samesite=mesmo_site, secure=seguro)
    return {"ok": True}


@router.get("/eu")
def eu(req: Request):
    return {"logado": eh_admin(req), "usuario": USUARIO if eh_admin(req) else None}

"""Solicitações de vistoria enviadas pelo civil (site público).

Os campos têm os mesmos nomes do formulário do site (InspectionModal.tsx), então o front envia
o que já tem. O civil NÃO recebe nível de risco nem previsão: o alerta oficial é só da Defesa Civil.
"""
import re
import time
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from . import auth, database

router = APIRouter(prefix="/api/vistorias", tags=["vistorias"])

# limite simples contra spam: no máximo N envios por hora para cada IP (memória do servidor)
MAX_POR_HORA = 5
_envios: dict[str, list[float]] = {}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class NovaVistoria(BaseModel):
    nome: str = Field(min_length=3, max_length=100)
    telefone: str = Field(min_length=8, max_length=25)
    email: str | None = Field(default=None, max_length=120)
    cidade: str = Field(min_length=2, max_length=80)
    tipo: Literal["Encosta", "Barreira", "Muro de contenção", "Não sei informar"] = "Não sei informar"
    endereco: str = Field(min_length=3, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    descricao: str | None = Field(default=None, max_length=1000)
    consentimento: bool = False        # LGPD: o civil precisa concordar com o uso dos dados
    site: str = ""                     # campo-isca: pessoas deixam vazio, robôs preenchem

    @field_validator("nome", "telefone", "email", "cidade", "endereco", "descricao", mode="before")
    @classmethod
    def limpar(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None           # texto vazio vira "não informado"
        return v

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def coordenada(cls, v):
        # o formulário envia texto: "" (não informado) ou "-8,0123" (vírgula) também são aceitos
        if isinstance(v, str):
            v = v.strip().replace(",", ".")
            return float(v) if v else None
        return v

    @field_validator("consentimento", mode="before")
    @classmethod
    def consentimento_do_form(cls, v):
        # checkbox de formulário HTML envia "on" quando marcado
        if isinstance(v, str):
            return v.strip().lower() in ("on", "true", "1", "sim")
        return v

    @field_validator("email")
    @classmethod
    def email_valido(cls, v):
        if v and not _EMAIL.match(v):
            raise ValueError("E-mail inválido.")
        return v

    @model_validator(mode="after")
    def exigir_consentimento_e_par(self):
        if not self.consentimento:
            raise ValueError("É preciso concordar com o uso dos dados para enviar a solicitação.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Informe latitude e longitude juntas, ou deixe as duas em branco.")
        return self


def criar_tabela():
    with database.conectar() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS vistorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            criado_em TEXT NOT NULL,
            nome TEXT NOT NULL,
            telefone TEXT NOT NULL,
            email TEXT,
            cidade TEXT NOT NULL,
            tipo TEXT NOT NULL,
            endereco TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            descricao TEXT,
            status TEXT NOT NULL DEFAULT 'nova'
        )""")


def _ip(req: Request) -> str:
    return auth.ip_cliente(req)


def _limitar(ip: str):
    agora = time.time()
    recentes = [t for t in _envios.get(ip, []) if agora - t < 3600]
    if len(recentes) >= MAX_POR_HORA:
        raise HTTPException(429, "Muitos envios em pouco tempo. Tente novamente mais tarde.")
    recentes.append(agora)
    _envios[ip] = recentes


@router.post("", status_code=201)
def enviar_vistoria(v: NovaVistoria, req: Request):
    if v.site:                                   # robô: finge que deu certo e não grava nada
        return {"ok": True}
    _limitar(_ip(req))
    with database.conectar() as con:
        cur = con.execute(
            """INSERT INTO vistorias (criado_em, nome, telefone, email, cidade, tipo, endereco,
                                      latitude, longitude, descricao)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(timespec="seconds"), v.nome, v.telefone, v.email, v.cidade,
             v.tipo, v.endereco, v.latitude, v.longitude, v.descricao))
        protocolo = cur.lastrowid
    # resposta mínima: o civil só recebe o número de protocolo
    return {"ok": True, "protocolo": protocolo}


# ---------- área do administrador ----------
STATUS = ("nova", "em_analise", "concluida")


class MudancaStatus(BaseModel):
    status: Literal["nova", "em_analise", "concluida"]


@router.get("", dependencies=[Depends(auth.exigir_admin)])
def listar_vistorias(status: str | None = None, limite: int = 100):
    """Lista as solicitações (mais recentes primeiro). Contém dados pessoais: só administrador."""
    limite = min(max(limite, 1), 500)
    with database.conectar() as con:
        if status in STATUS:
            linhas = con.execute("SELECT * FROM vistorias WHERE status=? ORDER BY id DESC LIMIT ?",
                                 (status, limite)).fetchall()
        else:
            linhas = con.execute("SELECT * FROM vistorias ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    return [dict(r) for r in linhas]


@router.patch("/{vistoria_id}", dependencies=[Depends(auth.exigir_admin)])
def mudar_status(vistoria_id: int, m: MudancaStatus):
    with database.conectar() as con:
        cur = con.execute("UPDATE vistorias SET status=? WHERE id=?", (m.status, vistoria_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Solicitação não encontrada")
    return {"ok": True}

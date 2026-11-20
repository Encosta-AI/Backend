"""Última foto da câmera de cada encosta (só a mais recente fica guardada).

A câmera de borda (ou o administrador, no teste) envia o arquivo como corpo bruto da requisição
(Content-Type image/jpeg ou image/png). Só o administrador logado vê a imagem.
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from . import auth, database, lona, nucleo

router = APIRouter(prefix="/api/encostas", tags=["fotos"])

PASTA = Path(__file__).resolve().parent / "fotos"
MAX_BYTES = int(os.environ.get("FOTO_MAX_BYTES", 3 * 1024 * 1024))     # 3 MB


def _tipo(dados: bytes) -> str | None:
    """Confere o conteúdo real do arquivo (não confia no nome nem no cabeçalho enviado)."""
    if dados[:3] == b"\xff\xd8\xff":
        return "jpg"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def _arquivo(encosta_id: int) -> Path | None:
    for ext in ("jpg", "png"):
        p = PASTA / f"{encosta_id}.{ext}"
        if p.exists():
            return p
    return None


@router.put("/{encosta_id}/foto", status_code=201, dependencies=[Depends(auth.exigir_admin_ou_dispositivo)])
async def enviar_foto(encosta_id: int, req: Request):
    if not database.encosta_existe(encosta_id):
        raise HTTPException(404, "Encosta não encontrada")
    tamanho = req.headers.get("content-length")
    if tamanho and tamanho.isdigit() and int(tamanho) > MAX_BYTES:
        raise HTTPException(413, "Imagem grande demais (máximo 3 MB).")
    dados = b""
    async for pedaco in req.stream():                  # lê aos poucos e para se passar do limite
        dados += pedaco
        if len(dados) > MAX_BYTES:
            raise HTTPException(413, "Imagem grande demais (máximo 3 MB).")
    ext = _tipo(dados)
    if not ext:
        raise HTTPException(415, "Envie uma imagem JPEG ou PNG.")
    PASTA.mkdir(exist_ok=True)
    antiga = _arquivo(encosta_id)
    destino = PASTA / f"{encosta_id}.{ext}"
    destino.write_bytes(dados)
    if antiga and antiga != destino:
        antiga.unlink(missing_ok=True)
    analise = lona.classificar(dados)                  # None se o modelo de lona não está instalado
    _json(encosta_id).unlink(missing_ok=True)          # análise da foto anterior não vale mais
    if analise:
        _json(encosta_id).write_text(json.dumps(analise))
    return {"ok": True, "bytes": len(dados), "lona": analise}


def _json(encosta_id: int) -> Path:
    return PASTA / f"{encosta_id}.lona.json"


@router.get("/{encosta_id}/lona", dependencies=[Depends(auth.exigir_admin)])
def ver_lona(encosta_id: int):
    """Resultado da análise da última foto: tem_lona, classe e confiança (ou disponivel=false)."""
    if not database.encosta_existe(encosta_id):
        raise HTTPException(404, "Encosta não encontrada")
    if not lona.disponivel():
        return {"disponivel": False, "analise": None}
    arq = _json(encosta_id)
    return {"disponivel": True, "analise": json.loads(arq.read_text()) if arq.exists() else None}


@router.post("/{encosta_id}/lona/aplicar", dependencies=[Depends(auth.exigir_admin)])
def aplicar_lona(encosta_id: int):
    """Usa o resultado da foto como 'tem_lona' da leitura atual e recalcula o risco."""
    if not database.encosta_existe(encosta_id):
        raise HTTPException(404, "Encosta não encontrada")
    arq = _json(encosta_id)
    if not arq.exists():
        raise HTTPException(409, "Não há análise de lona para a foto atual.")
    analise = json.loads(arq.read_text())
    atual = next(e for e in database.listar_encostas() if e["id"] == encosta_id)
    if atual["nivel"] is None:
        raise HTTPException(409, "Esta encosta ainda não tem leituras.")
    leitura = {v: atual[v] for v in ("chuva_24h", "chuva_72h", "umidade_solo", "inclinacao",
                                     "fluxo_optico", "aceleracao")}
    leitura["tem_lona"] = analise["tem_lona"]
    previsao = nucleo.prever(leitura)
    database.atualizar_ultima_leitura(encosta_id, analise["tem_lona"], previsao)
    return {"ok": True, "tem_lona": analise["tem_lona"], **previsao}


@router.get("/{encosta_id}/foto", dependencies=[Depends(auth.exigir_admin)])
def ver_foto(encosta_id: int):
    arq = _arquivo(encosta_id)
    if not arq:
        raise HTTPException(404, "Esta encosta ainda não tem foto.")
    tipo = "image/jpeg" if arq.suffix == ".jpg" else "image/png"
    return Response(arq.read_bytes(), media_type=tipo, headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

"""Chuva real da estação automática do INMET (Recife), para alimentar chuva_24h e chuva_72h.

ATENÇÃO: o formato abaixo (campos DT_MEDICAO, HR_MEDICAO e CHUVA do endpoint
/estacao/{inicio}/{fim}/{codigo}) vem da documentação pública e de uso conhecido da API, mas NÃO
foi testado ao vivo no ambiente de desenvolvimento (a rede bloqueia o INMET). Rode
`python -m backend.chuva` na sua máquina para conferir antes de depender disso.

Se a API falhar, o painel continua funcionando: o endpoint avisa que está sem dados reais.
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://apitempo.inmet.gov.br/estacao"
ESTACAO = os.environ.get("INMET_ESTACAO", "A301")      # Recife (confira o código no portal do INMET)
CACHE_SEG = 30 * 60                                     # o INMET atualiza de hora em hora
TIMEOUT = 10

CACHE_FALHA_SEG = 60                                    # falha não deve ficar guardada por 30 min

_cache: dict = {"quando": 0.0, "dados": None, "ttl": CACHE_SEG}


def _baixar(inicio: str, fim: str) -> list[dict]:
    req = urllib.request.Request(f"{BASE}/{inicio}/{fim}/{ESTACAO}", headers={"User-Agent": "EncostaAI/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        dados = json.loads(r.read().decode("utf-8"))
    if not isinstance(dados, list):
        raise ValueError("Resposta inesperada do INMET")
    return dados


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def somar(registros: list[dict], agora: datetime) -> dict:
    """Soma a chuva (mm) das últimas 24 h e 72 h. HR_MEDICAO vem em UTC (formato '1300')."""
    chuva_24 = chuva_72 = 0.0
    validos = 0
    ultima = None
    for r in registros:
        mm = _num(r.get("CHUVA"))
        data, hora = r.get("DT_MEDICAO"), str(r.get("HR_MEDICAO", "")).zfill(4)
        if mm is None or not data or len(hora) != 4:
            continue
        try:
            quando = datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        idade = agora - quando
        if idade < timedelta(0) or idade >= timedelta(hours=72):
            continue
        validos += 1
        chuva_72 += mm
        if idade < timedelta(hours=24):
            chuva_24 += mm
        if ultima is None or quando > ultima:
            ultima = quando
    if not validos:
        raise ValueError("Sem medições de chuva nas últimas 72 h")
    return {"chuva_24h": round(chuva_24, 1), "chuva_72h": round(chuva_72, 1),
            "medicoes": validos, "ultima_medicao": ultima.isoformat()}


def obter(forcar: bool = False) -> dict:
    """Devolve a chuva acumulada, com cache. Nunca levanta erro: informa 'ok': False."""
    agora_s = time.time()
    if not forcar and _cache["dados"] and agora_s - _cache["quando"] < _cache.get("ttl", CACHE_SEG):
        return _cache["dados"]
    agora = datetime.now(timezone.utc)
    try:
        dias = [(agora - timedelta(days=d)).strftime("%Y-%m-%d") for d in (3, 0)]
        resumo = somar(_baixar(dias[0], dias[1]), agora)
        dados = {"ok": True, "fonte": "INMET", "estacao": ESTACAO, **resumo,
                 "consultado_em": agora.isoformat(timespec="seconds")}
    except Exception as erro:                      # rede, formato ou estação diferentes do esperado
        if _cache["dados"] and _cache["dados"].get("ok"):
            return {**_cache["dados"], "desatualizado": True}
        dados = {"ok": False, "fonte": "INMET", "estacao": ESTACAO, "motivo": f"{type(erro).__name__}: {erro}"}
    _cache.update(quando=agora_s, dados=dados, ttl=CACHE_SEG if dados["ok"] else CACHE_FALHA_SEG)
    return dados


if __name__ == "__main__":      # teste rápido na sua máquina: python -m backend.chuva
    print(json.dumps(obter(forcar=True), indent=2, ensure_ascii=False))

"""Estimativa do tempo até a ruptura pelo método do inverso da velocidade (Fukuzono, 1985).

Em encostas que aceleram antes de romper, o gráfico de 1/velocidade x tempo tende a uma reta.
O ponto em que a reta cruza o zero é o instante estimado da ruptura. É uma ESTIMATIVA DE TENDÊNCIA,
não uma previsão exata: a cada leitura nova o cálculo é refeito.
"""
from datetime import datetime, timedelta

JANELA = 6            # quantas leituras mais recentes entram no ajuste
MIN_PONTOS = 4
VEL_MIN = 0.3         # px/h: abaixo disso o solo está praticamente parado
R2_MIN = 0.7          # qualidade mínima do ajuste linear
LIMITE_HORAS = 72     # acima disso a tendência é lenta demais para ser útil


def _ajuste_linear(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    sst = sum((y - my) ** 2 for y in ys)
    sse = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 if sst == 0 else 1 - sse / sst
    return a, b, r2


def estimar(historico: list[dict]) -> dict:
    """historico: leituras do mais antigo para o mais novo (com criado_em e fluxo_optico)."""
    pts = [h for h in historico if (h["fluxo_optico"] or 0) >= VEL_MIN][-JANELA:]
    if len(pts) < MIN_PONTOS:
        return {"ok": False, "motivo": "Poucas leituras com movimento para estimar a tendência."}

    ref = datetime.fromisoformat(pts[-1]["criado_em"])
    xs = [(datetime.fromisoformat(p["criado_em"]) - ref).total_seconds() / 3600 for p in pts]
    ys = [1 / p["fluxo_optico"] for p in pts]
    ajuste = _ajuste_linear(xs, ys)
    if ajuste is None:
        return {"ok": False, "motivo": "Leituras com o mesmo horário."}
    a, b, r2 = ajuste

    if b >= -1e-4:
        return {"ok": False, "motivo": "Sem aceleração do solo: não há tendência de ruptura."}
    if r2 < R2_MIN:
        return {"ok": False, "motivo": "Leituras irregulares: tendência ainda pouco confiável."}

    horas = max(-a / b, 0.0)            # tempo, a partir da última leitura, até 1/v chegar a zero
    if horas > LIMITE_HORAS:
        return {"ok": False, "motivo": "Tendência lenta: ruptura estimada a mais de 72 h."}

    return {
        "ok": True,
        "ruptura_em": (ref + timedelta(hours=horas)).isoformat(timespec="seconds"),
        "horas": round(horas, 2),
        "qualidade": round(r2, 2),
        "pontos": len(pts),
    }


def passo_tempestade(ultima: dict) -> dict:
    """Demonstração: próxima leitura (1 h depois) com chuva forte e o solo acelerando.

    A velocidade segue a lei do método (1/v diminui a cada hora), então a contagem regressiva
    do painel fica coerente. Valores FICTÍCIOS, só para demonstrar o recálculo.
    """
    v = max(ultima["fluxo_optico"], 0.3)
    inv = 1 / v
    inv_novo = max(inv - max(0.025, inv * 0.12), 0.02)
    v_novo = min(1 / inv_novo, 50.0)
    return {
        "chuva_24h": round(min(ultima["chuva_24h"] * 1.12 + 4, 300), 2),
        "chuva_72h": round(min(ultima["chuva_72h"] * 1.05 + 6, 600), 2),
        "umidade_solo": round(min(ultima["umidade_solo"] + 3, 100), 2),
        "inclinacao": round(min(ultima["inclinacao"] + 0.15, 45), 2),
        "fluxo_optico": round(v_novo, 2),
        "aceleracao": round(min(v_novo - ultima["fluxo_optico"], 20), 2),
        "tem_lona": 1,
    }


def com_comparacao(historico: list[dict]) -> dict:
    """Estimativa atual + aviso se a leitura mais recente ANTECIPOU a ruptura (15 min ou mais)."""
    atual = estimar(historico)
    if atual["ok"] and len(historico) > 1:
        anterior = estimar(historico[:-1])
        if anterior["ok"]:
            antes = datetime.fromisoformat(anterior["ruptura_em"])
            agora = datetime.fromisoformat(atual["ruptura_em"])
            minutos = round((antes - agora).total_seconds() / 60)
            if minutos >= 15:
                atual["antecipada_min"] = minutos
    return atual

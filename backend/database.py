"""Banco SQLite: encostas monitoradas e histórico de leituras com a previsão de cada uma."""
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(__file__).resolve().parent / "encostaai.db"

VARIAVEIS = ["chuva_24h", "chuva_72h", "umidade_solo", "inclinacao",
             "fluxo_optico", "aceleracao", "tem_lona"]


def conectar():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def criar_tabelas():
    with conectar() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS encostas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            bairro TEXT NOT NULL,
            municipio TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS leituras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            encosta_id INTEGER NOT NULL REFERENCES encostas(id),
            criado_em TEXT NOT NULL,
            chuva_24h REAL, chuva_72h REAL, umidade_solo REAL, inclinacao REAL,
            fluxo_optico REAL, aceleracao REAL, tem_lona INTEGER,
            nivel TEXT NOT NULL,
            confianca REAL NOT NULL,
            prob_vermelho REAL NOT NULL,
            por_limiar INTEGER NOT NULL
        );
        """)


def cadastrar_encosta(nome, bairro, municipio, lat, lon) -> int:
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO encostas (nome, bairro, municipio, lat, lon) VALUES (?,?,?,?,?)",
            (nome, bairro, municipio, lat, lon))
        return cur.lastrowid


def salvar_leitura(encosta_id: int, leitura: dict, previsao: dict, criado_em: datetime | None = None):
    criado_em = (criado_em or datetime.now()).isoformat(timespec="seconds")
    with conectar() as con:
        con.execute(
            f"""INSERT INTO leituras (encosta_id, criado_em, {", ".join(VARIAVEIS)},
                nivel, confianca, prob_vermelho, por_limiar)
                VALUES (?,?,{",".join("?" * len(VARIAVEIS))},?,?,?,?)""",
            (encosta_id, criado_em, *[leitura[v] for v in VARIAVEIS],
             previsao["nivel"], previsao["confianca"], previsao["prob_vermelho"],
             int(previsao["por_limiar"])))


def encosta_existe(encosta_id: int) -> bool:
    with conectar() as con:
        return con.execute("SELECT 1 FROM encostas WHERE id=?", (encosta_id,)).fetchone() is not None


def atualizar_ultima_leitura(encosta_id: int, tem_lona: int, previsao: dict) -> bool:
    """Troca o tem_lona da leitura mais recente e regrava o risco recalculado (False se não há leitura)."""
    with conectar() as con:
        linha = con.execute(
            "SELECT id FROM leituras WHERE encosta_id=? ORDER BY criado_em DESC, id DESC LIMIT 1",
            (encosta_id,)).fetchone()
        if not linha:
            return False
        con.execute(
            "UPDATE leituras SET tem_lona=?, nivel=?, confianca=?, prob_vermelho=?, por_limiar=? WHERE id=?",
            (tem_lona, previsao["nivel"], previsao["confianca"], previsao["prob_vermelho"],
             int(previsao["por_limiar"]), linha["id"]))
    return True


def listar_encostas():
    """Cada encosta com a leitura mais recente (se houver)."""
    with conectar() as con:
        linhas = con.execute("""
            SELECT e.*, l.criado_em, l.nivel, l.confianca, l.prob_vermelho, l.por_limiar,
                   l.chuva_24h, l.chuva_72h, l.umidade_solo, l.inclinacao,
                   l.fluxo_optico, l.aceleracao, l.tem_lona
            FROM encostas e
            LEFT JOIN leituras l ON l.id = (
                SELECT id FROM leituras WHERE encosta_id = e.id ORDER BY criado_em DESC, id DESC LIMIT 1)
            ORDER BY e.id""").fetchall()
    return [dict(r) for r in linhas]


def historico(encosta_id: int, limite: int = 24):
    with conectar() as con:
        linhas = con.execute(
            "SELECT * FROM leituras WHERE encosta_id=? ORDER BY criado_em DESC, id DESC LIMIT ?",
            (encosta_id, limite)).fetchall()
    return [dict(r) for r in reversed(linhas)]   # do mais antigo para o mais novo


def avancar_tempo(encosta_id: int, horas: float = 1.0):
    """Demonstração: recua em 'horas' o horário das leituras da encosta, abrindo espaço para uma nova leitura 'agora'."""
    with conectar() as con:
        con.execute(
            "UPDATE leituras SET criado_em = strftime('%Y-%m-%dT%H:%M:%S', criado_em, ?) WHERE encosta_id=?",
            (f"-{int(horas * 3600)} seconds", encosta_id))


def apagar_tudo():
    with conectar() as con:
        con.executescript("DELETE FROM leituras; DELETE FROM encostas; DELETE FROM sqlite_sequence;")


def tem_encostas() -> bool:
    with conectar() as con:
        return con.execute("SELECT COUNT(*) FROM encostas").fetchone()[0] > 0

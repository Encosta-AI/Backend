"""Lê os docstrings dos testes + o resultado do pytest (junit xml) e imprime a tabela de casos de teste.
Uso: python -m pytest tests --junitxml=resultado.xml ; python tests/gerar_relatorio.py resultado.xml"""
import ast
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

pasta = Path(__file__).resolve().parent
casos = {}
for arq in sorted(pasta.glob("test_*.py")):
    for no in ast.walk(ast.parse(arq.read_text(encoding="utf-8"))):
        if isinstance(no, ast.FunctionDef) and no.name.startswith("test_ct"):
            doc = ast.get_docstring(no) or ""
            partes = [p.strip() for p in doc.split("|")]
            if len(partes) == 5:
                casos[no.name] = partes

resultado = defaultdict(lambda: [0, 0])      # função -> [execuções, falhas]
for tc in ET.parse(sys.argv[1]).getroot().iter("testcase"):
    nome = re.sub(r"\[.*\]$", "", tc.get("name"))
    resultado[nome][0] += 1
    if tc.find("failure") is not None or tc.find("error") is not None:
        resultado[nome][1] += 1

print("| ID | Requisito | Tipo | Cenário | Resultado esperado | Execuções | Situação |")
print("|---|---|---|---|---|---|---|")
for nome, (ct, req, tipo, desc, esp) in sorted(casos.items(), key=lambda x: x[1][0]):
    ex, falhas = resultado.get(nome, [0, 0])
    print(f"| {ct} | {req} | {tipo} | {desc} | {esp} | {ex} | {'Aprovado' if ex and not falhas else 'REPROVADO'} |")

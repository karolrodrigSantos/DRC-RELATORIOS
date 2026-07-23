"""
classify.py — Classificação heurística de itens dos bancos de preços em
disciplinas de engenharia: **Civil, Elétrica, Hidromecânica** (regra de
negócio v2), mais "Mão de Obra" (usada nos relatórios de custo de mão de
obra) e "Outros" (fallback).

A classificação é por palavras-chave na descrição/código/unidade. É
deliberadamente simples (heurística, não substitui julgamento técnico) e
pode sempre ser sobrescrita manualmente pela tela "Mapeamento de Itens" —
a sobrescrita manual tem prioridade sobre esta função (ver db.upsert_precos).
"""

import unicodedata

# Disciplinas oficiais do sistema (regra de negócio v2)
DISCIPLINAS = ["Civil", "Elétrica", "Hidromecânica", "Mão de Obra", "Outros"]

_MAO_DE_OBRA_KW = [
    "ajudante", "pedreiro", "servente", "encanador", "eletricista", "soldador",
    "carpinteiro", "armador", "pintor", "mestre de obras", "engenheiro", "encarregado",
    "operador", "motorista", "vigia", "almoxarife", "topografo", "topógrafo",
    "azulejista", "gesseiro", "impermeabilizador", "montador", "bombeiro hidraulico",
]

_ELETRICA_KW = [
    "eletric", "cabo", "disjuntor", "transformador", "painel", "quadro de distrib",
    "energia", "gerador", "no-break", "nobreak", "iluminacao", "iluminação",
    "fio ", "condutor", "capacitor", "inversor", "chave seccionadora", "para-raio",
    "aterramento", "tomada", "luminaria", "luminária", "retificador", "bateria",
    "fotovoltaic", "solar", "subestacao", "subestação", "voltag", "amperag",
    "clp", "telemetria", "automacao", "automação", "instrumentacao", "instrumentação",
]

# Hidromecânica = bombas, motores, válvulas, tubulações e demais equipamentos
# eletromecânicos/hidráulicos de estações e redes (une o que antes era
# "Mecânica" + "Equipamentos" em uma única disciplina, por regra de negócio v2)
_HIDROMECANICA_KW = [
    "bomba", "motor", "redutor", "valvula", "válvula", "rolamento", "mancal",
    "compressor", "ventilador", "soprador", "misturador", "agitador", "polia",
    "engrenagem", "acoplamento", "tubulacao", "tubulação", "flange", "registro",
    "filtro", "peneira", "grade mecaniz", "raspador", "guincho", "talha",
    "ponte rolante", "elevador", "escada rolante", "compactador", "adutora",
    "decantador", "floculador", "clorador", "dosador", "aerador", "reservatorio",
    "reservatório", "hidrometro", "hidrômetro", "macromedidor", "conjunto motobomba",
]

_CIVIL_KW = [
    "concreto", "alvenaria", "tijolo", "cimento", "argamassa", "reboco",
    "escavacao", "escavação", "aterro", "pavimento", "asfalto", "brita",
    "terraplenagem", "fundacao", "fundação", "laje", "viga", "pilar",
    "impermeabiliza", "azulejo", "piso", "revestimento", "estrutura metalica",
    "estrutura metálica", "telhado", "cobertura", "esquadria", "grade metalica",
    "canal", "galeria", "tunel", "túnel", "muro", "drenagem", "edificio",
    "edifício", "predio", "prédio", "urbanizacao", "urbanização",
]


def _norm(txt):
    if txt is None:
        return ""
    txt = str(txt).lower()
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode("ascii")
    return txt


def classify_disciplina(descricao, unidade=None, codigo=None):
    """Retorna uma das DISCIPLINAS a partir de heurísticas de palavra-chave."""
    desc = _norm(descricao)
    cod = _norm(codigo)
    und = _norm(unidade)

    if cod.startswith("mo0") or cod.startswith("mo-") or (und == "h" and any(k in desc for k in _MAO_DE_OBRA_KW)):
        return "Mão de Obra"
    if any(k in desc for k in _MAO_DE_OBRA_KW):
        return "Mão de Obra"
    if any(k in desc for k in _ELETRICA_KW):
        return "Elétrica"
    if any(k in desc for k in _HIDROMECANICA_KW):
        return "Hidromecânica"
    if any(k in desc for k in _CIVIL_KW):
        return "Civil"
    return "Outros"


def classify_series(series_desc, series_unidade=None, series_codigo=None):
    """Aplica classify_disciplina em uma pd.Series de descrições (vetorizado simples)."""
    import pandas as pd
    n = len(series_desc)
    und = series_unidade if series_unidade is not None else pd.Series([None] * n)
    cod = series_codigo if series_codigo is not None else pd.Series([None] * n)
    return [
        classify_disciplina(d, u, c)
        for d, u, c in zip(series_desc, und, cod)
    ]

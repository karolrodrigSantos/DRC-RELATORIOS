"""
matching.py — Identificação automática de UP a partir de um texto livre
(descrição de ativo/serviço de um fornecedor) e busca de itens similares
nos bancos de preços (Sabesp, SINAPI, TCPO) por similaridade textual.

A pontuação é ponderada por "recall" dos termos da consulta (o quanto das
palavras-chave digitadas pelo usuário aparece na descrição do catálogo),
o que funciona melhor do que um Jaccard/token-set puro quando os catálogos
têm descrições técnicas muito mais longas e detalhadas que o texto de
entrada (ex.: "Bomba centrífuga 50cv" vs. "BOMBA CENTRIFUGA MOTOR ELETRICO
TRIFASICO 9,86 DIAMETRO DE SUCCAO X ELEVACAO 1" X 1", 4 ESTAGIOS..."). Usa
apenas a stdlib (difflib + re), para manter o deploy leve no Streamlit Cloud.
"""

import re
import unicodedata
import difflib
import pandas as pd

_STOPWORDS = {
    "de", "da", "do", "das", "dos", "em", "ate", "até", "para", "com", "a",
    "e", "o", "os", "as", "um", "uma", "no", "na", "nos", "nas", "por", "x",
}


def _norm(txt):
    if txt is None:
        return ""
    txt = str(txt).lower().strip()
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode("ascii")
    return txt


def _tokenize(txt):
    """Extrai apenas tokens alfabéticos (>=3 letras), removendo stopwords e
    números — números de catálogo (potência, diâmetro, medidas) tendem a
    coincidir por acaso entre itens totalmente diferentes e adicionam ruído
    à comparação, por isso ficam de fora da pontuação por token."""
    txt = _norm(txt)
    tokens = re.findall(r"[a-z]+", txt)
    return set(t for t in tokens if len(t) > 2 and t not in _STOPWORDS)


def _score(consulta, candidato):
    """
    Similaridade ponderada por recall dos termos da consulta:
      - recall (peso 0.55): fração das palavras-chave da CONSULTA que aparecem no candidato
                             (é o componente mais importante — garante que descrições de
                             catálogo mais longas/detalhadas não percam pontos só por terem
                             mais especificações técnicas do que o texto digitado)
      - f1     (peso 0.20): equilíbrio entre recall e precisão (Jaccard-like)
      - precisão (peso 0.10): fração do candidato coberta pela consulta
      - seq    (peso 0.15): razão de sequência de caracteres (difflib), como reforço/desempate
    Retorna um score de 0 a 1.
    """
    a_n, b_n = _norm(consulta), _norm(candidato)
    if not a_n or not b_n:
        return 0.0

    ta, tb = _tokenize(consulta), _tokenize(candidato)
    seq = difflib.SequenceMatcher(None, a_n, b_n).ratio()
    if not ta or not tb:
        return 0.3 * seq

    inter = ta & tb
    recall = len(inter) / len(ta)
    precisao = len(inter) / len(tb)
    f1 = (2 * recall * precisao / (recall + precisao)) if (recall + precisao) > 0 else 0.0

    return 0.55 * recall + 0.20 * f1 + 0.10 * precisao + 0.15 * seq


def identificar_up(texto, up_df: pd.DataFrame, uar_df: pd.DataFrame, top_n=3):
    """
    Identifica a(s) UP(s) mais prováveis para um texto livre de ativo/serviço,
    comparando contra a nomenclatura das UARs (mais granular).

    Retorna uma lista de dicts: [{'up_codigo', 'up_nome', 'uar_codigo',
    'uar_nome', 'score'}], ordenada por score decrescente (0 a 1).
    """
    candidatos = []
    if uar_df is not None and not uar_df.empty:
        for r in uar_df.itertuples():
            s = _score(texto, r.uar_nome)
            if s > 0:
                candidatos.append({
                    "up_codigo": r.up_codigo, "uar_codigo": r.uar_codigo,
                    "uar_nome": r.uar_nome, "score": s,
                })
    candidatos.sort(key=lambda x: x["score"], reverse=True)
    top = candidatos[:top_n]

    up_nomes = dict(zip(up_df["up_codigo"], up_df["up_nome"])) if up_df is not None else {}
    for c in top:
        c["up_nome"] = up_nomes.get(c["up_codigo"], "")
    return top


def buscar_similares(texto, banco_preco_df: pd.DataFrame, top_n=5):
    """
    Busca, dentro de um DataFrame já filtrado (ex.: um banco + um i0), os
    itens com descrição mais similar ao texto informado.

    Retorna o DataFrame de entrada com uma coluna extra 'similaridade'
    (0 a 1), ordenado decrescente, limitado a top_n linhas.
    """
    if banco_preco_df is None or banco_preco_df.empty:
        return banco_preco_df
    df = banco_preco_df.copy()
    df["similaridade"] = df["descricao"].apply(lambda d: _score(texto, d))
    df = df.sort_values("similaridade", ascending=False)
    return df.head(top_n)

"""
import_utils.py — Normalização de arquivos de banco de preços (SABESP, SINAPI,
TCPO) para o schema comum usado pelo banco de dados (ver db.upsert_precos).

Cada parser recebe um DataFrame "cru" (como veio do Excel/CSV) e devolve um
DataFrame com as colunas:
    banco, i0, codigo, descricao, unidade, preco, mao_obra, disciplina
"""

import re
import pandas as pd
import numpy as np
from datetime import date
from .classify import classify_series

MESES_PT = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def parse_i0_from_text(texto):
    """Extrai um i0 (primeiro dia do mês) a partir de textos como
    'Maio 26', 'MAI/26', '2026/04', '04/2026', 'Banco de Insumos - Maio 26'..."""
    if texto is None:
        return None
    t = str(texto).strip().lower()

    m = re.search(r"(\d{4})[/-](\d{1,2})\b", t)
    if m:
        ano, mes = int(m.group(1)), int(m.group(2))
        return date(ano, mes, 1).isoformat()

    m = re.search(r"(\d{1,2})[/-](\d{4})\b", t)
    if m:
        mes, ano = int(m.group(1)), int(m.group(2))
        return date(ano, mes, 1).isoformat()

    for abbr, mes in MESES_PT.items():
        m = re.search(rf"{abbr}\w*[\s/-]?\s*(\d{{2,4}})", t)
        if m:
            ano = int(m.group(1))
            ano = 2000 + ano if ano < 100 else ano
            return date(ano, mes, 1).isoformat()
    return None


def _to_float(v):
    if v is None or v == "" or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    s = s.replace(".", "").replace(",", ".") if re.match(r"^\d{1,3}(\.\d{3})*,\d+$", s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_sabesp(raw_df: pd.DataFrame, i0: str) -> pd.DataFrame:
    """
    Layout esperado (planilha 'BANCO SABESP'):
    col0=Código FINAL, col1=Descrição, col2=Unid, col3=Preço Unit., col4=Mão de Obra
    Linhas de título de seção têm col0 vazio — são descartadas.
    """
    df = raw_df.copy()
    df.columns = list(range(df.shape[1]))
    df = df.iloc[:, :5]
    df.columns = ["codigo", "descricao", "unidade", "preco", "mao_obra"]
    df = df[df["codigo"].notna()]
    df = df[df["codigo"].astype(str).str.strip() != "."]
    df["preco"] = df["preco"].apply(_to_float)
    df["mao_obra"] = df["mao_obra"].apply(_to_float)
    df = df[df["preco"].notna()]
    df["banco"] = "SABESP"
    df["i0"] = i0
    df["disciplina"] = classify_series(df["descricao"], df["unidade"], df["codigo"])
    return df[["banco", "i0", "codigo", "descricao", "unidade", "preco", "mao_obra", "disciplina"]]


def parse_sinapi(raw_df: pd.DataFrame, i0: str) -> pd.DataFrame:
    """
    Layout esperado (planilha 'BANCO SINAPI'):
    col0=Código FINAL, col1=Descrição, col2=Unid, col3=Preço Unit.
    """
    df = raw_df.copy()
    df.columns = list(range(df.shape[1]))
    df = df.iloc[:, :4]
    df.columns = ["codigo", "descricao", "unidade", "preco"]
    df = df[df["codigo"].notna()]
    df["preco"] = df["preco"].apply(_to_float)
    df = df[df["preco"].notna()]
    df["mao_obra"] = None
    df["banco"] = "SINAPI"
    df["i0"] = i0
    df["disciplina"] = classify_series(df["descricao"], df["unidade"], df["codigo"])
    return df[["banco", "i0", "codigo", "descricao", "unidade", "preco", "mao_obra", "disciplina"]]


def parse_tcpo(raw_df: pd.DataFrame, i0: str = None) -> pd.DataFrame:
    """
    Layout esperado (planilha 'BANCO TCPO'):
    Base, Item, Descrição, Un., Tipo, Data Preço, Preço
    O i0 pode ser lido diretamente da coluna 'Data Preço' (formato 'YYYY/MM'),
    linha a linha — mais preciso que um único valor fixo. Se 'i0' for passado,
    ele é usado como fallback para linhas sem data reconhecível.
    """
    df = raw_df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if cl.startswith("item"):
            col_map[c] = "codigo"
        elif cl.startswith("descri"):
            col_map[c] = "descricao"
        elif cl.startswith("un"):
            col_map[c] = "unidade"
        elif cl.startswith("data"):
            col_map[c] = "data_preco"
        elif cl.startswith("pre"):
            col_map[c] = "preco"
    df = df.rename(columns=col_map)
    keep = [c for c in ["codigo", "descricao", "unidade", "preco", "data_preco"] if c in df.columns]
    df = df[keep]
    df = df[df["codigo"].notna()]
    df["preco"] = df["preco"].apply(_to_float)
    df = df[df["preco"].notna()]
    if "data_preco" in df.columns:
        df["i0_calc"] = df["data_preco"].apply(parse_i0_from_text)
        df["i0"] = df["i0_calc"].fillna(i0)
    else:
        df["i0"] = i0
    df = df[df["i0"].notna()]
    df["mao_obra"] = None
    df["banco"] = "TCPO"
    df["disciplina"] = classify_series(df["descricao"], df.get("unidade"), df["codigo"])
    return df[["banco", "i0", "codigo", "descricao", "unidade", "preco", "mao_obra", "disciplina"]]


def parse_generic(raw_df: pd.DataFrame, banco: str, i0: str,
                   col_codigo, col_descricao, col_unidade, col_preco, col_mao_obra=None) -> pd.DataFrame:
    """Fallback para upload de arquivo CSV/XLSX com colunas escolhidas manualmente pelo usuário."""
    df = raw_df.copy()
    out = pd.DataFrame()
    out["codigo"] = df[col_codigo].astype(str)
    out["descricao"] = df[col_descricao]
    out["unidade"] = df[col_unidade] if col_unidade else None
    out["preco"] = df[col_preco].apply(_to_float)
    out["mao_obra"] = df[col_mao_obra].apply(_to_float) if col_mao_obra else None
    out = out[out["preco"].notna()]
    out["banco"] = banco
    out["i0"] = i0
    out["disciplina"] = classify_series(out["descricao"], out["unidade"], out["codigo"])
    return out[["banco", "i0", "codigo", "descricao", "unidade", "preco", "mao_obra", "disciplina"]]


def read_any(file) -> dict:
    """Lê um arquivo (xlsx ou csv) e devolve {nome_planilha: DataFrame} (csv vira {'CSV': df})."""
    name = getattr(file, "name", "")
    if str(name).lower().endswith((".xlsx", ".xls")):
        xls = pd.ExcelFile(file)
        return {sheet: xls.parse(sheet, header=None) for sheet in xls.sheet_names}
    else:
        return {"CSV": pd.read_csv(file)}

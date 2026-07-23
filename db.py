"""
db.py — Camada de acesso a dados (SQLite) do Sistema de Inteligência de Ativos
e Relatórios de Engenharia (Metodologia DRC / i0).

Todas as funções desta camada usam SQLite puro (stdlib), sem dependências
externas de banco de dados — facilita hospedagem gratuita (Streamlit Cloud).
"""

import sqlite3
import json
import os
import pandas as pd
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "drc_sistema.db")
SEED_UP_UAR_PATH = os.path.join(os.path.dirname(__file__), "seed_up_uar.json")


# ----------------------------------------------------------------------
# Conexão
# ----------------------------------------------------------------------
@contextmanager
def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS up (
    up_codigo           TEXT PRIMARY KEY,
    up_nome             TEXT NOT NULL,
    up_tipo             TEXT,      -- Individual / Massa
    etiqueta_obrigatoria TEXT,     -- Sim / Não
    unidade_medida      TEXT
);

CREATE TABLE IF NOT EXISTS uar (
    uar_codigo   TEXT PRIMARY KEY,
    uar_nome     TEXT NOT NULL,
    up_codigo    TEXT REFERENCES up(up_codigo)
);

CREATE TABLE IF NOT EXISTS atributo_tecnico (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tabela      TEXT NOT NULL,     -- ex: ACIONAMENTO
    codigo_item INTEGER NOT NULL,
    descricao   TEXT NOT NULL,
    UNIQUE(tabela, codigo_item)
);

-- Grupos DRC/VOC conforme Seção 3 da Nota Técnica (mapa UP -> categoria -> método)
CREATE TABLE IF NOT EXISTS grupo_metodo (
    up_codigo TEXT PRIMARY KEY REFERENCES up(up_codigo),
    categoria TEXT,        -- ex: "6 - Máquinas e Equipamentos"
    metodo    TEXT         -- DRC / VOC
);

-- Histórico de preços por item / banco / mês de referência (i0)
CREATE TABLE IF NOT EXISTS banco_preco (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    banco       TEXT NOT NULL,     -- SABESP / SINAPI / TCPO
    i0          TEXT NOT NULL,     -- 'YYYY-MM-01'
    codigo      TEXT NOT NULL,
    descricao   TEXT,
    unidade     TEXT,
    preco       REAL,
    mao_obra    REAL,
    disciplina  TEXT,              -- Mecânica / Civil / Elétrica / Equipamentos / Mão de Obra / Outros
    up_codigo   TEXT REFERENCES up(up_codigo),
    uar_codigo  TEXT REFERENCES uar(uar_codigo),
    criado_em   TEXT DEFAULT (datetime('now')),
    UNIQUE(banco, i0, codigo)
);
CREATE INDEX IF NOT EXISTS idx_banco_preco_i0 ON banco_preco(i0);
CREATE INDEX IF NOT EXISTS idx_banco_preco_codigo ON banco_preco(banco, codigo);
CREATE INDEX IF NOT EXISTS idx_banco_preco_disciplina ON banco_preco(disciplina);

-- Mapeamento manual persistente: código de item de um banco -> UP/UAR/disciplina
-- (sobrescreve a classificação automática em futuras importações)
CREATE TABLE IF NOT EXISTS mapeamento_item (
    banco       TEXT NOT NULL,
    codigo      TEXT NOT NULL,
    up_codigo   TEXT REFERENCES up(up_codigo),
    uar_codigo  TEXT REFERENCES uar(uar_codigo),
    disciplina  TEXT,
    PRIMARY KEY (banco, codigo)
);

-- Propostas de fornecedores para o módulo comparativo DRC (histórico de comparativos gerados)
CREATE TABLE IF NOT EXISTS drc_proposta (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    i0                 TEXT NOT NULL,
    codigo             TEXT,
    descricao          TEXT,
    fornecedor         TEXT,
    preco_fornecedor   REAL,
    preco_contratado   REAL,
    banco_referencia   TEXT,      -- banco usado como referência (ou 'MEDIA')
    preco_referencial  REAL,
    variacao_pct        REAL,      -- variação do fornecedor vs. referencial
    up_codigo           TEXT,
    status              TEXT,      -- 'Verde' / 'Amarelo' / 'Vermelho'
    criado_em          TEXT DEFAULT (datetime('now'))
);

-- Cadastro de preços de FORNECEDORES e preços CONTRATADOS (CRUD - requisito 6)
CREATE TABLE IF NOT EXISTS fornecedor_preco (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_ativo_servico     TEXT NOT NULL,   -- descrição livre do ativo/serviço do fornecedor
    fornecedor             TEXT,
    preco_fornecedor       REAL,
    preco_contratado       REAL,
    up_codigo              TEXT REFERENCES up(up_codigo),   -- identificado automaticamente
    uar_codigo             TEXT REFERENCES uar(uar_codigo),
    disciplina             TEXT,
    confianca_identificacao REAL,   -- score (0-1) da identificação automática de UP
    criado_em              TEXT DEFAULT (datetime('now')),
    atualizado_em           TEXT DEFAULT (datetime('now'))
);

-- Índices de IPCA por mês de referência (i0), cadastrados/carregados pelo usuário (requisito 5)
CREATE TABLE IF NOT EXISTS ipca_indice (
    i0            TEXT PRIMARY KEY,   -- 'YYYY-MM-01'
    indice        REAL,               -- número índice IPCA (opcional, se disponível)
    variacao_pct  REAL,               -- variação % do IPCA no mês (acumulada ou mensal, à escolha do usuário)
    observacao    TEXT
);

-- Parâmetros da regra DRC (requisito 7) — parametrizável pela interface
CREATE TABLE IF NOT EXISTS config_drc (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);

-- Log de importações (auditoria)
CREATE TABLE IF NOT EXISTS importacao_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    banco       TEXT,
    i0          TEXT,
    arquivo     TEXT,
    n_linhas    INTEGER,
    criado_em   TEXT DEFAULT (datetime('now'))
);
"""


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def seed_up_uar():
    """Carrega a Tabela III (UP/UAR) do manual Sabesp, se ainda não carregada."""
    with get_conn() as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM up")
        if cur.fetchone()["n"] > 0:
            return  # já carregado
        data = json.load(open(SEED_UP_UAR_PATH, encoding="utf-8"))
        conn.executemany(
            "INSERT OR IGNORE INTO up (up_codigo, up_nome, up_tipo, etiqueta_obrigatoria, unidade_medida) "
            "VALUES (:up_codigo, :up_nome, :up_tipo, :etiqueta_obrigatoria, :unidade_medida)",
            data["ups"],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO uar (uar_codigo, uar_nome, up_codigo) "
            "VALUES (:uar_codigo, :uar_nome, :up_codigo)",
            data["uars"],
        )


def seed_atributos_tecnicos():
    """Tabela IV.A do manual — Acionamento."""
    acionamento = [
        (1, "Bateria"), (2, "Combustão"), (3, "Elétrico"), (4, "Hidráulico"),
        (5, "Hidropneumático"), (6, "Linear"), (7, "Manual"), (8, "Motorizado"),
        (9, "Pneumático"), (10, "Rotativo"), (11, "Auto Operada"),
        (12, "Automático"), (13, "Não se Aplica"), (14, "Sem Acionamento"),
    ]
    with get_conn() as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM atributo_tecnico WHERE tabela='ACIONAMENTO'")
        if cur.fetchone()["n"] > 0:
            return
        conn.executemany(
            "INSERT OR IGNORE INTO atributo_tecnico (tabela, codigo_item, descricao) VALUES ('ACIONAMENTO', ?, ?)",
            acionamento,
        )


def seed_grupo_metodo():
    """Mapa UP -> categoria -> método (DRC/VOC), conforme Seção 3 da NT (slide 'DRC 5-8')."""
    linhas = [
        ("91", "1 - Intangíveis", "VOC"),
        ("01", "2 - Terrenos", "VOC"),
        ("08", "3 - Redes e Ligações", "DRC"),
        ("11", "3 - Redes e Ligações", "DRC"),
        ("04", "4 - Canais, Galerias e Túneis", "DRC"),
        ("02", "5 - Edificações", "DRC"),
        ("07", "5 - Edificações", "DRC"),
        ("28", "5 - Edificações", "DRC"),
        ("03", "6 - Máquinas e Equipamentos", "DRC"),
        ("05", "6 - Máquinas e Equipamentos", "DRC"),
        ("06", "6 - Máquinas e Equipamentos", "DRC"),
        ("09", "6 - Máquinas e Equipamentos", "DRC"),
        ("10", "6 - Máquinas e Equipamentos", "DRC"),
        ("19", "6 - Máquinas e Equipamentos", "DRC"),
        ("26", "6 - Máquinas e Equipamentos", "DRC"),
        ("27", "6 - Máquinas e Equipamentos", "DRC"),
        ("29", "6 - Máquinas e Equipamentos", "DRC"),
        ("30", "6 - Máquinas e Equipamentos", "DRC"),
        ("34", "6 - Máquinas e Equipamentos", "DRC"),
        ("35", "6 - Máquinas e Equipamentos", "DRC"),
        ("12", "7 - Bens de Uso Geral", "VOC"),
        ("13", "7 - Bens de Uso Geral", "VOC"),
        ("14", "7 - Bens de Uso Geral", "VOC"),
        ("18", "7 - Bens de Uso Geral", "VOC"),
        ("20", "7 - Bens de Uso Geral", "VOC"),
        ("21", "7 - Bens de Uso Geral", "VOC"),
        ("22", "7 - Bens de Uso Geral", "VOC"),
        ("23", "7 - Bens de Uso Geral", "VOC"),
        ("24", "7 - Bens de Uso Geral", "VOC"),
        ("25", "7 - Bens de Uso Geral", "VOC"),
    ]
    with get_conn() as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM grupo_metodo")
        if cur.fetchone()["n"] > 0:
            return
        conn.executemany(
            "INSERT OR IGNORE INTO grupo_metodo (up_codigo, categoria, metodo) VALUES (?, ?, ?)",
            linhas,
        )


def seed_config_drc():
    """Parâmetros default da regra DRC (requisito 7): faixa verde ±5%, amarela ±10%."""
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO config_drc (chave, valor) VALUES ('limite_verde_pct', '5')")
        conn.execute("INSERT OR IGNORE INTO config_drc (chave, valor) VALUES ('limite_amarelo_pct', '10')")


def bootstrap():
    init_db()
    seed_up_uar()
    seed_atributos_tecnicos()
    seed_grupo_metodo()
    seed_config_drc()


# ----------------------------------------------------------------------
# Consultas utilitárias (retornam DataFrame)
# ----------------------------------------------------------------------
def df_query(sql, params=None):
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params or {})


def list_ups():
    return df_query("SELECT * FROM up ORDER BY up_codigo")


def list_uars(up_codigo=None):
    if up_codigo:
        return df_query("SELECT * FROM uar WHERE up_codigo = :up ORDER BY uar_codigo", {"up": up_codigo})
    return df_query("SELECT * FROM uar ORDER BY uar_codigo")


def list_i0(banco=None):
    if banco:
        return df_query("SELECT DISTINCT i0 FROM banco_preco WHERE banco = :b ORDER BY i0", {"b": banco})
    return df_query("SELECT DISTINCT i0 FROM banco_preco ORDER BY i0")


def list_bancos():
    return df_query("SELECT DISTINCT banco FROM banco_preco ORDER BY banco")


def get_precos(banco=None, i0=None, disciplina=None, up_codigo=None, uar_codigo=None, texto=None):
    sql = "SELECT * FROM banco_preco WHERE 1=1"
    params = {}
    if banco:
        sql += " AND banco = :banco"
        params["banco"] = banco
    if i0:
        sql += " AND i0 = :i0"
        params["i0"] = i0
    if disciplina:
        sql += " AND disciplina = :disciplina"
        params["disciplina"] = disciplina
    if up_codigo:
        sql += " AND up_codigo = :up_codigo"
        params["up_codigo"] = up_codigo
    if uar_codigo:
        sql += " AND uar_codigo = :uar_codigo"
        params["uar_codigo"] = uar_codigo
    if texto:
        sql += " AND descricao LIKE :texto"
        params["texto"] = f"%{texto}%"
    sql += " ORDER BY i0, banco, codigo"
    return df_query(sql, params)


def upsert_precos(df: pd.DataFrame, log_arquivo="upload manual"):
    """
    Insere/atualiza registros de banco_preco a partir de um DataFrame já normalizado
    com colunas: banco, i0, codigo, descricao, unidade, preco, mao_obra, disciplina.
    Aplica mapeamento manual salvo (mapeamento_item), quando existir, sobre UP/UAR/disciplina.
    """
    if df.empty:
        return 0
    with get_conn() as conn:
        mapeamentos = {
            (r["banco"], r["codigo"]): (r["up_codigo"], r["uar_codigo"], r["disciplina"])
            for r in conn.execute("SELECT * FROM mapeamento_item")
        }
        n = 0
        for _, row in df.iterrows():
            key = (row["banco"], str(row["codigo"]))
            up_codigo, uar_codigo, disciplina = (None, None, row.get("disciplina"))
            if key in mapeamentos:
                up_codigo, uar_codigo, disciplina_map = mapeamentos[key]
                disciplina = disciplina_map or disciplina
            conn.execute(
                """
                INSERT INTO banco_preco (banco, i0, codigo, descricao, unidade, preco, mao_obra, disciplina, up_codigo, uar_codigo)
                VALUES (:banco, :i0, :codigo, :descricao, :unidade, :preco, :mao_obra, :disciplina, :up_codigo, :uar_codigo)
                ON CONFLICT(banco, i0, codigo) DO UPDATE SET
                    descricao=excluded.descricao,
                    unidade=excluded.unidade,
                    preco=excluded.preco,
                    mao_obra=excluded.mao_obra,
                    disciplina=excluded.disciplina,
                    up_codigo=COALESCE(excluded.up_codigo, banco_preco.up_codigo),
                    uar_codigo=COALESCE(excluded.uar_codigo, banco_preco.uar_codigo)
                """,
                {
                    "banco": row["banco"],
                    "i0": row["i0"],
                    "codigo": str(row["codigo"]),
                    "descricao": row.get("descricao"),
                    "unidade": row.get("unidade"),
                    "preco": row.get("preco"),
                    "mao_obra": row.get("mao_obra"),
                    "disciplina": disciplina,
                    "up_codigo": up_codigo,
                    "uar_codigo": uar_codigo,
                },
            )
            n += 1
        conn.execute(
            "INSERT INTO importacao_log (banco, i0, arquivo, n_linhas) VALUES (:banco, :i0, :arquivo, :n)",
            {"banco": df["banco"].iloc[0], "i0": df["i0"].iloc[0], "arquivo": log_arquivo, "n": n},
        )
    return n


def salvar_mapeamento(banco, codigo, up_codigo=None, uar_codigo=None, disciplina=None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO mapeamento_item (banco, codigo, up_codigo, uar_codigo, disciplina)
            VALUES (:banco, :codigo, :up_codigo, :uar_codigo, :disciplina)
            ON CONFLICT(banco, codigo) DO UPDATE SET
                up_codigo=excluded.up_codigo,
                uar_codigo=excluded.uar_codigo,
                disciplina=excluded.disciplina
            """,
            {"banco": banco, "codigo": str(codigo), "up_codigo": up_codigo, "uar_codigo": uar_codigo, "disciplina": disciplina},
        )
        # aplica retroativamente aos registros já importados desse código
        conn.execute(
            """
            UPDATE banco_preco
            SET up_codigo = COALESCE(:up_codigo, up_codigo),
                uar_codigo = COALESCE(:uar_codigo, uar_codigo),
                disciplina = COALESCE(:disciplina, disciplina)
            WHERE banco = :banco AND codigo = :codigo
            """,
            {"banco": banco, "codigo": str(codigo), "up_codigo": up_codigo, "uar_codigo": uar_codigo, "disciplina": disciplina},
        )


def salvar_propostas_drc(df: pd.DataFrame):
    if df.empty:
        return 0
    with get_conn() as conn:
        n = 0
        for _, row in df.iterrows():
            conn.execute(
                """
                INSERT INTO drc_proposta (i0, codigo, descricao, fornecedor, preco_fornecedor, banco_referencia,
                                           preco_referencial, variacao_pct, status)
                VALUES (:i0, :codigo, :descricao, :fornecedor, :preco_fornecedor, :banco_referencia,
                        :preco_referencial, :variacao_pct, :status)
                """,
                row.to_dict(),
            )
            n += 1
    return n


def list_propostas_drc(i0=None):
    if i0:
        return df_query("SELECT * FROM drc_proposta WHERE i0 = :i0 ORDER BY criado_em DESC", {"i0": i0})
    return df_query("SELECT * FROM drc_proposta ORDER BY criado_em DESC")


# ========================================================================
# REQUISITO 1 — CRUD de UPs (cadastro, edição e exclusão)
# ========================================================================
def create_up(up_codigo, up_nome, up_tipo, etiqueta_obrigatoria, unidade_medida):
    with get_conn() as conn:
        existe = conn.execute("SELECT 1 FROM up WHERE up_codigo = ?", (up_codigo,)).fetchone()
        if existe:
            raise ValueError(f"Já existe uma UP com o código {up_codigo}.")
        conn.execute(
            "INSERT INTO up (up_codigo, up_nome, up_tipo, etiqueta_obrigatoria, unidade_medida) VALUES (?,?,?,?,?)",
            (up_codigo, up_nome, up_tipo, etiqueta_obrigatoria, unidade_medida),
        )


def update_up(up_codigo, up_nome, up_tipo, etiqueta_obrigatoria, unidade_medida):
    with get_conn() as conn:
        conn.execute(
            "UPDATE up SET up_nome=?, up_tipo=?, etiqueta_obrigatoria=?, unidade_medida=? WHERE up_codigo=?",
            (up_nome, up_tipo, etiqueta_obrigatoria, unidade_medida, up_codigo),
        )


def dependencias_up(up_codigo):
    """Conta quantos registros dependem desta UP, para alertar antes de excluir."""
    with get_conn() as conn:
        n_uar = conn.execute("SELECT COUNT(*) n FROM uar WHERE up_codigo=?", (up_codigo,)).fetchone()["n"]
        n_preco = conn.execute("SELECT COUNT(*) n FROM banco_preco WHERE up_codigo=?", (up_codigo,)).fetchone()["n"]
        n_map = conn.execute("SELECT COUNT(*) n FROM mapeamento_item WHERE up_codigo=?", (up_codigo,)).fetchone()["n"]
        n_forn = conn.execute("SELECT COUNT(*) n FROM fornecedor_preco WHERE up_codigo=?", (up_codigo,)).fetchone()["n"]
    return {"uar": n_uar, "banco_preco": n_preco, "mapeamento": n_map, "fornecedor_preco": n_forn}


def delete_up(up_codigo, force=False):
    """
    Exclui uma UP. Se houver UARs, preços ou mapeamentos vinculados e force=False,
    levanta ValueError informando as dependências. Com force=True, remove/desvincula
    tudo em cascata (UARs da UP são excluídas; vínculos em banco_preco/mapeamento_item/
    fornecedor_preco são apenas desvinculados, os registros de preço não são apagados).
    """
    deps = dependencias_up(up_codigo)
    total = sum(deps.values())
    if total > 0 and not force:
        raise ValueError(
            f"UP possui vínculos ({deps['uar']} UARs, {deps['banco_preco']} preços, "
            f"{deps['mapeamento']} mapeamentos, {deps['fornecedor_preco']} preços de fornecedor). "
            "Use a exclusão forçada para remover/desvincular tudo."
        )
    with get_conn() as conn:
        if force:
            conn.execute("DELETE FROM uar WHERE up_codigo=?", (up_codigo,))
            conn.execute("UPDATE banco_preco SET up_codigo=NULL WHERE up_codigo=?", (up_codigo,))
            conn.execute("UPDATE mapeamento_item SET up_codigo=NULL WHERE up_codigo=?", (up_codigo,))
            conn.execute("UPDATE fornecedor_preco SET up_codigo=NULL WHERE up_codigo=?", (up_codigo,))
            conn.execute("DELETE FROM grupo_metodo WHERE up_codigo=?", (up_codigo,))
        conn.execute("DELETE FROM up WHERE up_codigo=?", (up_codigo,))


def create_uar(uar_codigo, uar_nome, up_codigo):
    with get_conn() as conn:
        existe = conn.execute("SELECT 1 FROM uar WHERE uar_codigo=?", (uar_codigo,)).fetchone()
        if existe:
            raise ValueError(f"Já existe uma UAR com o código {uar_codigo}.")
        conn.execute("INSERT INTO uar (uar_codigo, uar_nome, up_codigo) VALUES (?,?,?)", (uar_codigo, uar_nome, up_codigo))


def update_uar(uar_codigo, uar_nome, up_codigo):
    with get_conn() as conn:
        conn.execute("UPDATE uar SET uar_nome=?, up_codigo=? WHERE uar_codigo=?", (uar_nome, up_codigo, uar_codigo))


def delete_uar(uar_codigo):
    with get_conn() as conn:
        conn.execute("UPDATE banco_preco SET uar_codigo=NULL WHERE uar_codigo=?", (uar_codigo,))
        conn.execute("UPDATE mapeamento_item SET uar_codigo=NULL WHERE uar_codigo=?", (uar_codigo,))
        conn.execute("UPDATE fornecedor_preco SET uar_codigo=NULL WHERE uar_codigo=?", (uar_codigo,))
        conn.execute("DELETE FROM uar WHERE uar_codigo=?", (uar_codigo,))


# ========================================================================
# REQUISITO 5 — Cadastro de índices de IPCA por i0
# ========================================================================
def upsert_ipca(i0, indice=None, variacao_pct=None, observacao=None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO ipca_indice (i0, indice, variacao_pct, observacao) VALUES (:i0, :indice, :variacao_pct, :obs)
            ON CONFLICT(i0) DO UPDATE SET indice=excluded.indice, variacao_pct=excluded.variacao_pct, observacao=excluded.observacao
            """,
            {"i0": i0, "indice": indice, "variacao_pct": variacao_pct, "obs": observacao},
        )


def list_ipca():
    return df_query("SELECT * FROM ipca_indice ORDER BY i0")


def delete_ipca(i0):
    with get_conn() as conn:
        conn.execute("DELETE FROM ipca_indice WHERE i0=?", (i0,))


# ========================================================================
# REQUISITO 7 — Parâmetros da regra DRC (parametrizável)
# ========================================================================
def get_config(chave, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT valor FROM config_drc WHERE chave=?", (chave,)).fetchone()
        return row["valor"] if row else default


def set_config(chave, valor):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO config_drc (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
            (chave, str(valor)),
        )


def get_limites_drc():
    """Retorna (limite_verde_pct, limite_amarelo_pct) — ambos em % (valor absoluto)."""
    verde = float(get_config("limite_verde_pct", 5))
    amarelo = float(get_config("limite_amarelo_pct", 10))
    return verde, amarelo


def classificar_status(variacao_pct):
    """
    REQUISITO 7 e 8 — classifica a variação percentual do preço do fornecedor
    frente ao referencial nas 3 faixas de alerta:
      Verde    -> dentro do limite "conforme" (default ±5%)
      Amarelo  -> entre o limite conforme e o limite de atenção (default ±10%)
      Vermelho -> acima do limite de atenção (não conforme)
    """
    if variacao_pct is None or pd.isna(variacao_pct):
        return "Sem dados"
    verde, amarelo = get_limites_drc()
    v = abs(variacao_pct)
    if v <= verde:
        return "Verde"
    if v <= amarelo:
        return "Amarelo"
    return "Vermelho"


# ========================================================================
# REQUISITO 6 — CRUD de preços de fornecedores e preços contratados
# ========================================================================
def create_fornecedor_preco(tipo_ativo_servico, fornecedor, preco_fornecedor, preco_contratado,
                             up_codigo=None, uar_codigo=None, disciplina=None, confianca=None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO fornecedor_preco
                (tipo_ativo_servico, fornecedor, preco_fornecedor, preco_contratado,
                 up_codigo, uar_codigo, disciplina, confianca_identificacao)
            VALUES (:t, :f, :pf, :pc, :up, :uar, :d, :conf)
            """,
            {"t": tipo_ativo_servico, "f": fornecedor, "pf": preco_fornecedor, "pc": preco_contratado,
             "up": up_codigo, "uar": uar_codigo, "d": disciplina, "conf": confianca},
        )


def update_fornecedor_preco(id_, tipo_ativo_servico, fornecedor, preco_fornecedor, preco_contratado,
                             up_codigo=None, uar_codigo=None, disciplina=None):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE fornecedor_preco
            SET tipo_ativo_servico=:t, fornecedor=:f, preco_fornecedor=:pf, preco_contratado=:pc,
                up_codigo=:up, uar_codigo=:uar, disciplina=:d, atualizado_em=datetime('now')
            WHERE id=:id
            """,
            {"t": tipo_ativo_servico, "f": fornecedor, "pf": preco_fornecedor, "pc": preco_contratado,
             "up": up_codigo, "uar": uar_codigo, "d": disciplina, "id": id_},
        )


def delete_fornecedor_preco(id_):
    with get_conn() as conn:
        conn.execute("DELETE FROM fornecedor_preco WHERE id=?", (id_,))


def list_fornecedor_precos():
    return df_query(
        "SELECT f.*, u.up_nome FROM fornecedor_preco f LEFT JOIN up u ON u.up_codigo = f.up_codigo "
        "ORDER BY f.criado_em DESC"
    )

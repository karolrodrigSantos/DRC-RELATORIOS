"""
app.py — Sistema de Inteligência de Ativos e Relatórios de Engenharia
(Metodologia DRC e Índices i0) — v2

Executar localmente:
    streamlit run app.py
"""
import io
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import db
from utils.import_utils import (
    parse_sabesp, parse_sinapi, parse_tcpo, parse_generic,
    parse_i0_from_text, read_any,
)
from utils.matching import identificar_up, buscar_similares
from utils.classify import classify_disciplina, DISCIPLINAS
from utils import export_utils

st.set_page_config(
    page_title="Inteligência de Ativos — DRC / i0",
    page_icon="📊",
    layout="wide",
)

db.bootstrap()

STATUS_CORES = {"Verde": "#2e7d32", "Amarelo": "#f9a825", "Vermelho": "#c62828", "Sem dados": "#9e9e9e"}
STATUS_BG = {"Verde": "#e8f5e9", "Amarelo": "#fff8e1", "Vermelho": "#ffebee", "Sem dados": "#f5f5f5"}

# ----------------------------------------------------------------------
# Sidebar / navegação
# ----------------------------------------------------------------------
st.sidebar.title("📊 Inteligência de Ativos")
st.sidebar.caption("Metodologia DRC — Bancos Sabesp / SINAPI / TCPO")

PAGINAS = [
    "🏠 Visão Geral",
    "📤 Upload de Preços",
    "🔍 Consulta e Filtros",
    "🗂️ UPs e UARs (Cadastro)",
    "📈 Índices para Atualização",
    "📊 Variação Entre Bancos",
    "🌡️ Inflação por Disciplina",
    "💹 Inflação por IPCA",
    "⚖️ Módulo DRC — Comparativo",
    "📉 Dashboards",
    "🔗 Mapeamento de Itens",
]
pagina = st.sidebar.radio("Navegação", PAGINAS, label_visibility="collapsed")

st.sidebar.divider()
st.sidebar.caption(
    "UP = Unidade de Patrimônio · UAR = Unidade de Acréscimo e Recuperação · "
    "i0 = mês de referência de preços"
)


# ----------------------------------------------------------------------
# Helpers gerais
# ----------------------------------------------------------------------
def fmt_i0(i0_str):
    if not i0_str:
        return "-"
    return pd.to_datetime(i0_str).strftime("%b/%Y")


def i0_options(banco=None):
    df = db.list_i0(banco)
    return sorted(df["i0"].tolist())


def badge_status(status):
    cor = STATUS_CORES.get(status, "#9e9e9e")
    bg = STATUS_BG.get(status, "#f5f5f5")
    return f'<span style="background-color:{bg};color:{cor};padding:3px 10px;border-radius:12px;font-weight:600;border:1px solid {cor}55;">{status}</span>'


def highlight_status(row):
    styles = [""] * len(row)
    if "status" in row.index:
        bg = STATUS_BG.get(row["status"], "")
        if bg:
            styles = [f"background-color: {bg}"] * len(row)
    return styles


def bloco_exportacao(titulo, dfs: dict, fig=None, key_prefix=""):
    """Bloco reutilizável de exportação (Excel / PDF / PowerPoint) para qualquer relatório."""
    st.markdown("###### ⬇️ Exportar este relatório")
    c1, c2, c3 = st.columns(3)

    with c1:
        try:
            xls_bytes = export_utils.to_excel_bytes(dfs)
            st.download_button("📗 Excel (.xlsx)", xls_bytes, f"{key_prefix}.xlsx",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"xls_{key_prefix}")
        except Exception as e:
            st.caption(f"Excel indisponível: {e}")

    with c2:
        if st.button("📕 Gerar PDF", key=f"pdf_btn_{key_prefix}"):
            try:
                img = export_utils.fig_to_png_bytes(fig) if fig is not None else None
                secoes = [(nome, df, img if i == 0 else None, None) for i, (nome, df) in enumerate(dfs.items())]
                pdf_bytes = export_utils.to_pdf_bytes(titulo, secoes)
                st.session_state[f"pdf_{key_prefix}"] = pdf_bytes
            except Exception as e:
                st.error(f"Não foi possível gerar o PDF: {e}")
        if st.session_state.get(f"pdf_{key_prefix}"):
            st.download_button("Baixar PDF gerado", st.session_state[f"pdf_{key_prefix}"],
                                f"{key_prefix}.pdf", "application/pdf", key=f"pdf_dl_{key_prefix}")

    with c3:
        if st.button("📙 Gerar PowerPoint", key=f"ppt_btn_{key_prefix}"):
            try:
                img = export_utils.fig_to_png_bytes(fig) if fig is not None else None
                secoes = [(nome, df, img if i == 0 else None, None) for i, (nome, df) in enumerate(dfs.items())]
                ppt_bytes = export_utils.to_pptx_bytes(titulo, secoes)
                st.session_state[f"ppt_{key_prefix}"] = ppt_bytes
            except Exception as e:
                st.error(f"Não foi possível gerar o PowerPoint: {e}")
        if st.session_state.get(f"ppt_{key_prefix}"):
            st.download_button("Baixar PPTX gerado", st.session_state[f"ppt_{key_prefix}"],
                                f"{key_prefix}.pptx",
                                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                key=f"ppt_dl_{key_prefix}")


# ========================================================================
# PÁGINA: Visão Geral
# ========================================================================
if pagina == "🏠 Visão Geral":
    st.title("Visão Geral do Sistema")
    st.write(
        "Base de inteligência de preços e ativos para suporte à metodologia "
        "**DRC (Custo de Reposição Depreciado)** — comparação entre os bancos "
        "**Sabesp, SINAPI e TCPO** ao longo de múltiplos meses de referência (i0)."
    )

    col1, col2, col3, col4 = st.columns(4)
    total_itens = db.df_query("SELECT COUNT(*) n FROM banco_preco")["n"].iloc[0]
    total_bancos = db.df_query("SELECT COUNT(DISTINCT banco) n FROM banco_preco")["n"].iloc[0]
    total_i0 = db.df_query("SELECT COUNT(DISTINCT i0) n FROM banco_preco")["n"].iloc[0]
    total_up = db.df_query("SELECT COUNT(*) n FROM up")["n"].iloc[0]

    col1.metric("Itens de preço carregados", f"{total_itens:,}".replace(",", "."))
    col2.metric("Bancos de preços", total_bancos)
    col3.metric("Meses de referência (i0)", total_i0)
    col4.metric("UPs cadastradas", total_up)

    st.subheader("Itens por banco e mês de referência")
    resumo = db.df_query(
        "SELECT banco, i0, COUNT(*) n_itens, ROUND(AVG(preco),2) preco_medio "
        "FROM banco_preco GROUP BY banco, i0 ORDER BY i0, banco"
    )
    if not resumo.empty:
        resumo_view = resumo.copy()
        resumo_view["i0"] = resumo_view["i0"].apply(fmt_i0)
        st.dataframe(resumo_view, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum preço carregado ainda. Use a página **Upload de Preços**.")

    st.subheader("Últimas importações")
    log = db.df_query("SELECT * FROM importacao_log ORDER BY criado_em DESC LIMIT 15")
    if not log.empty:
        st.dataframe(log, use_container_width=True, hide_index=True)

    with st.expander("Como os UPs/UARs se relacionam ao método de valoração (DRC x VOC)"):
        gm = db.df_query(
            "SELECT g.up_codigo, u.up_nome, g.categoria, g.metodo "
            "FROM grupo_metodo g JOIN up u ON u.up_codigo = g.up_codigo ORDER BY g.categoria, g.up_codigo"
        )
        st.dataframe(gm, use_container_width=True, hide_index=True)
        st.caption(
            "Mapa extraído da Seção 3 da Nota Técnica DRC (ARSESP) — Redes, Canais e "
            "Máquinas/Equipamentos são valorados por DRC; Terrenos, Intangíveis e Bens de "
            "Uso Geral por VOC."
        )


# ========================================================================
# PÁGINA: Upload de Preços
# ========================================================================
elif pagina == "📤 Upload de Preços":
    st.title("Upload de Novos Preços")
    st.write(
        "Carregue **um ou mais meses de referência (i0)** para Sabesp, SINAPI e TCPO. "
        "Cada upload é independente — carregue quantos meses forem necessários (ex.: "
        "jan/26, mar/26, abr/26, jun/26) para os relatórios de inflação por disciplina e por IPCA."
    )

    modo = st.radio(
        "Formato do arquivo",
        ["Sabesp (padrão)", "SINAPI (padrão)", "TCPO (padrão)", "Genérico (escolher colunas)"],
        horizontal=True,
    )

    arquivo = st.file_uploader("Arquivo (.xlsx ou .csv)", type=["xlsx", "xls", "csv"])

    if arquivo is not None:
        try:
            planilhas = read_any(arquivo)
        except Exception as e:
            st.error(f"Não foi possível ler o arquivo: {e}")
            planilhas = {}

        if planilhas:
            nome_planilha = st.selectbox("Planilha / aba", list(planilhas.keys()))
            raw = planilhas[nome_planilha]
            st.caption("Pré-visualização das primeiras linhas:")
            st.dataframe(raw.head(8), use_container_width=True)

            df_normalizado = None

            if modo == "Sabesp (padrão)":
                titulo_sugerido = None
                try:
                    titulo_sugerido = parse_i0_from_text(raw.iloc[0, 1])
                except Exception:
                    pass
                i0_sel = st.text_input(
                    "Mês de referência (i0) — formato AAAA-MM-01",
                    value=titulo_sugerido or "",
                )
                if st.button("Processar e importar (Sabesp)"):
                    if not i0_sel:
                        st.error("Informe o i0.")
                    else:
                        df_normalizado = parse_sabesp(raw, i0_sel)

            elif modo == "SINAPI (padrão)":
                titulo_sugerido = None
                try:
                    titulo_sugerido = parse_i0_from_text(raw.iloc[0, 1])
                except Exception:
                    pass
                i0_sel = st.text_input(
                    "Mês de referência (i0) — formato AAAA-MM-01",
                    value=titulo_sugerido or "",
                )
                if st.button("Processar e importar (SINAPI)"):
                    if not i0_sel:
                        st.error("Informe o i0.")
                    else:
                        df_normalizado = parse_sinapi(raw, i0_sel)

            elif modo == "TCPO (padrão)":
                st.caption(
                    "O TCPO informa a data do preço por linha (coluna 'Data Preço'); "
                    "o i0 abaixo é usado apenas como valor de reserva (fallback)."
                )
                i0_fallback = st.text_input("i0 de reserva (AAAA-MM-01)", value="")
                if st.button("Processar e importar (TCPO)"):
                    raw_header = planilhas[nome_planilha]
                    df_normalizado = parse_tcpo(raw_header, i0=i0_fallback or None)

            else:  # Genérico
                cols = list(raw.columns)
                banco_nome = st.text_input("Nome do banco (ex.: SABESP, SINAPI, TCPO, OUTRO)")
                i0_sel = st.text_input("Mês de referência (i0) — formato AAAA-MM-01")
                c1, c2, c3 = st.columns(3)
                col_codigo = c1.selectbox("Coluna Código", cols)
                col_descricao = c2.selectbox("Coluna Descrição", cols)
                col_unidade = c3.selectbox("Coluna Unidade", ["(nenhuma)"] + cols)
                c4, c5 = st.columns(2)
                col_preco = c4.selectbox("Coluna Preço", cols)
                col_mao_obra = c5.selectbox("Coluna Mão de Obra", ["(nenhuma)"] + cols)
                if st.button("Processar e importar (Genérico)"):
                    if not banco_nome or not i0_sel:
                        st.error("Informe o nome do banco e o i0.")
                    else:
                        df_normalizado = parse_generic(
                            raw, banco_nome.upper(), i0_sel,
                            col_codigo, col_descricao,
                            None if col_unidade == "(nenhuma)" else col_unidade,
                            col_preco,
                            None if col_mao_obra == "(nenhuma)" else col_mao_obra,
                        )

            if df_normalizado is not None:
                if df_normalizado.empty:
                    st.warning("Nenhuma linha válida encontrada após o processamento.")
                else:
                    st.success(f"{len(df_normalizado)} linhas processadas.")
                    st.dataframe(df_normalizado.head(20), use_container_width=True)
                    n = db.upsert_precos(df_normalizado, log_arquivo=arquivo.name)
                    st.success(f"✅ {n} itens gravados no banco de dados (i0 = {df_normalizado['i0'].iloc[0]}).")
                    st.cache_data.clear()

    st.divider()
    st.subheader("Meses (i0) já carregados por banco")
    resumo_i0 = db.df_query(
        "SELECT banco, i0, COUNT(*) n_itens FROM banco_preco GROUP BY banco, i0 ORDER BY banco, i0"
    )
    if not resumo_i0.empty:
        resumo_i0_view = resumo_i0.copy()
        resumo_i0_view["i0"] = resumo_i0_view["i0"].apply(fmt_i0)
        st.dataframe(resumo_i0_view, use_container_width=True, hide_index=True)


# ========================================================================
# PÁGINA: Consulta e Filtros
# ========================================================================
elif pagina == "🔍 Consulta e Filtros":
    st.title("Consulta e Filtros")

    c1, c2, c3 = st.columns(3)
    bancos = ["(todos)"] + db.list_bancos()["banco"].tolist()
    banco_f = c1.selectbox("Banco", bancos)
    banco_f = None if banco_f == "(todos)" else banco_f

    i0s = ["(todos)"] + i0_options(banco_f)
    i0_f = c2.selectbox("i0 (mês de referência)", i0s, format_func=lambda x: x if x == "(todos)" else fmt_i0(x))
    i0_f = None if i0_f == "(todos)" else i0_f

    disciplinas = ["(todas)"] + DISCIPLINAS
    disc_f = c3.selectbox("Disciplina", disciplinas)
    disc_f = None if disc_f == "(todas)" else disc_f

    c4, c5, c6 = st.columns(3)
    ups = db.list_ups()
    up_opts = ["(todas)"] + [f"{r.up_codigo} - {r.up_nome}" for r in ups.itertuples()]
    up_f = c4.selectbox("UP", up_opts)
    up_f = None if up_f == "(todas)" else up_f.split(" - ")[0]

    uars = db.list_uars(up_f) if up_f else db.list_uars()
    uar_opts = ["(todas)"] + [f"{r.uar_codigo} - {r.uar_nome}" for r in uars.itertuples()]
    uar_f = c5.selectbox("UAR", uar_opts)
    uar_f = None if uar_f == "(todas)" else uar_f.split(" - ")[0]

    texto_f = c6.text_input("Buscar na descrição")

    resultado = db.get_precos(
        banco=banco_f, i0=i0_f, disciplina=disc_f,
        up_codigo=up_f, uar_codigo=uar_f, texto=texto_f or None,
    )
    st.write(f"**{len(resultado)}** itens encontrados.")
    resultado_view = resultado.copy()
    if not resultado_view.empty:
        resultado_view["i0"] = resultado_view["i0"].apply(fmt_i0)
    st.dataframe(
        resultado_view[["banco", "i0", "codigo", "descricao", "unidade", "preco", "mao_obra", "disciplina", "up_codigo", "uar_codigo"]]
        if not resultado_view.empty else resultado_view,
        use_container_width=True, hide_index=True,
    )

    if not resultado.empty:
        bloco_exportacao("Consulta de Preços", {"Consulta": resultado_view}, key_prefix="consulta_precos")

    st.subheader("Evolução de preço de um item específico")
    if not resultado.empty:
        codigo_sel = st.selectbox("Selecione um código para ver a série histórica (i0 x preço)",
                                   sorted(resultado["codigo"].unique().tolist()))
        banco_sel = resultado[resultado["codigo"] == codigo_sel]["banco"].iloc[0]
        serie = db.df_query(
            "SELECT i0, preco FROM banco_preco WHERE banco = :b AND codigo = :c ORDER BY i0",
            {"b": banco_sel, "c": codigo_sel},
        )
        if len(serie) > 0:
            serie["i0"] = pd.to_datetime(serie["i0"])
            fig = px.line(serie, x="i0", y="preco", markers=True,
                           title=f"Histórico de preço — {banco_sel} / {codigo_sel}")
            st.plotly_chart(fig, use_container_width=True)
            if len(serie) == 1:
                st.info("Este item possui apenas um mês de referência carregado até o momento.")


# ========================================================================
# PÁGINA: UPs e UARs (Cadastro) — REQUISITO 1
# ========================================================================
elif pagina == "🗂️ UPs e UARs (Cadastro)":
    st.title("Cadastro de UP e UAR")
    st.write(
        "Tabelas de referência conforme o Manual de Contabilidade de Ativos da Sabesp "
        "(Tabela III — Codificações por UP e UAR). Nesta página é possível **cadastrar, "
        "editar e excluir** UPs e UARs."
    )

    tab_up, tab_uar, tab_atr = st.tabs(["🏗️ Unidades de Patrimônio (UP)", "🔩 UARs", "⚙️ Atributos Técnicos"])

    # ------------------------------------------------------------------
    with tab_up:
        st.subheader("UPs cadastradas")
        st.dataframe(db.list_ups(), use_container_width=True, hide_index=True)

        st.divider()
        acao = st.radio("Ação", ["➕ Cadastrar nova UP", "✏️ Editar UP existente", "🗑️ Excluir UP"], horizontal=True)

        if acao == "➕ Cadastrar nova UP":
            with st.form("form_nova_up"):
                c1, c2 = st.columns(2)
                novo_codigo = c1.text_input("Código da UP (ex.: 36)")
                novo_nome = c2.text_input("Nome da UP")
                c3, c4, c5 = st.columns(3)
                novo_tipo = c3.selectbox("Tipo", ["Individual", "Massa"])
                nova_etiqueta = c4.selectbox("Etiqueta patrimonial obrigatória", ["Sim", "Não"])
                nova_unidade = c5.text_input("Unidade de medida", value="un")
                enviado = st.form_submit_button("Cadastrar UP")
                if enviado:
                    if not novo_codigo or not novo_nome:
                        st.error("Preencha código e nome.")
                    else:
                        try:
                            db.create_up(novo_codigo.strip().zfill(2) if novo_codigo.isdigit() else novo_codigo.strip(),
                                         novo_nome.strip(), novo_tipo, nova_etiqueta, nova_unidade.strip())
                            st.success(f"UP {novo_codigo} cadastrada com sucesso.")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))

        elif acao == "✏️ Editar UP existente":
            ups = db.list_ups()
            if ups.empty:
                st.info("Nenhuma UP cadastrada.")
            else:
                opcoes = [f"{r.up_codigo} - {r.up_nome}" for r in ups.itertuples()]
                escolha = st.selectbox("Selecione a UP para editar", opcoes)
                cod = escolha.split(" - ")[0]
                linha = ups[ups["up_codigo"] == cod].iloc[0]
                with st.form("form_editar_up"):
                    novo_nome = st.text_input("Nome da UP", value=linha["up_nome"])
                    c3, c4, c5 = st.columns(3)
                    novo_tipo = c3.selectbox("Tipo", ["Individual", "Massa"],
                                              index=0 if linha["up_tipo"] == "Individual" else 1)
                    nova_etiqueta = c4.selectbox("Etiqueta obrigatória", ["Sim", "Não"],
                                                  index=0 if linha["etiqueta_obrigatoria"] == "Sim" else 1)
                    nova_unidade = c5.text_input("Unidade de medida", value=linha["unidade_medida"] or "un")
                    enviado = st.form_submit_button("Salvar alterações")
                    if enviado:
                        db.update_up(cod, novo_nome.strip(), novo_tipo, nova_etiqueta, nova_unidade.strip())
                        st.success("UP atualizada com sucesso.")
                        st.rerun()

        else:  # Excluir
            ups = db.list_ups()
            if ups.empty:
                st.info("Nenhuma UP cadastrada.")
            else:
                opcoes = [f"{r.up_codigo} - {r.up_nome}" for r in ups.itertuples()]
                escolha = st.selectbox("Selecione a UP para excluir", opcoes, key="up_excluir")
                cod = escolha.split(" - ")[0]
                deps = db.dependencias_up(cod)
                total_deps = sum(deps.values())
                if total_deps > 0:
                    st.warning(
                        f"Esta UP possui vínculos: **{deps['uar']}** UARs, **{deps['banco_preco']}** itens de preço, "
                        f"**{deps['mapeamento']}** mapeamentos e **{deps['fornecedor_preco']}** preços de fornecedor."
                    )
                    forcar = st.checkbox("Excluir mesmo assim (UARs vinculadas serão apagadas; preços/mapeamentos ficam sem UP)")
                else:
                    forcar = False
                if st.button("🗑️ Confirmar exclusão", type="primary"):
                    try:
                        db.delete_up(cod, force=forcar)
                        st.success(f"UP {cod} excluída.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    # ------------------------------------------------------------------
    with tab_uar:
        st.subheader("UARs cadastradas")
        ups = db.list_ups()
        up_opts = ["(todas)"] + [f"{r.up_codigo} - {r.up_nome}" for r in ups.itertuples()]
        up_f = st.selectbox("Filtrar por UP", up_opts, key="uar_filtro_up")
        up_f_cod = None if up_f == "(todas)" else up_f.split(" - ")[0]
        st.dataframe(db.list_uars(up_f_cod), use_container_width=True, hide_index=True)

        st.divider()
        acao_uar = st.radio("Ação", ["➕ Cadastrar nova UAR", "✏️ Editar UAR", "🗑️ Excluir UAR"], horizontal=True, key="acao_uar")

        if acao_uar == "➕ Cadastrar nova UAR":
            with st.form("form_nova_uar"):
                novo_codigo = st.text_input("Código da UAR (ex.: 0599999)")
                novo_nome = st.text_input("Nome da UAR")
                up_escolhida = st.selectbox("UP à qual pertence", [f"{r.up_codigo} - {r.up_nome}" for r in ups.itertuples()])
                enviado = st.form_submit_button("Cadastrar UAR")
                if enviado:
                    if not novo_codigo or not novo_nome:
                        st.error("Preencha código e nome.")
                    else:
                        try:
                            db.create_uar(novo_codigo.strip(), novo_nome.strip(), up_escolhida.split(" - ")[0])
                            st.success("UAR cadastrada com sucesso.")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))

        elif acao_uar == "✏️ Editar UAR":
            uars_all = db.list_uars()
            if uars_all.empty:
                st.info("Nenhuma UAR cadastrada.")
            else:
                opcoes = [f"{r.uar_codigo} - {r.uar_nome}" for r in uars_all.itertuples()]
                escolha = st.selectbox("Selecione a UAR", opcoes)
                cod = escolha.split(" - ")[0]
                linha = uars_all[uars_all["uar_codigo"] == cod].iloc[0]
                with st.form("form_editar_uar"):
                    novo_nome = st.text_input("Nome", value=linha["uar_nome"])
                    up_atual_idx = 0
                    up_lista = [f"{r.up_codigo} - {r.up_nome}" for r in ups.itertuples()]
                    for i, o in enumerate(up_lista):
                        if o.startswith(str(linha["up_codigo"]) + " -"):
                            up_atual_idx = i
                    up_escolhida = st.selectbox("UP", up_lista, index=up_atual_idx)
                    enviado = st.form_submit_button("Salvar alterações")
                    if enviado:
                        db.update_uar(cod, novo_nome.strip(), up_escolhida.split(" - ")[0])
                        st.success("UAR atualizada.")
                        st.rerun()

        else:
            uars_all = db.list_uars()
            if uars_all.empty:
                st.info("Nenhuma UAR cadastrada.")
            else:
                opcoes = [f"{r.uar_codigo} - {r.uar_nome}" for r in uars_all.itertuples()]
                escolha = st.selectbox("Selecione a UAR para excluir", opcoes, key="uar_excluir")
                cod = escolha.split(" - ")[0]
                if st.button("🗑️ Confirmar exclusão da UAR", type="primary"):
                    db.delete_uar(cod)
                    st.success("UAR excluída.")
                    st.rerun()

    # ------------------------------------------------------------------
    with tab_atr:
        st.write("**Tabela IV.A — Acionamento**")
        atr = db.df_query("SELECT * FROM atributo_tecnico WHERE tabela = 'ACIONAMENTO' ORDER BY codigo_item")
        st.dataframe(atr, use_container_width=True, hide_index=True)


# ========================================================================
# PÁGINA: Índices para Atualização
# ========================================================================
elif pagina == "📈 Índices para Atualização":
    st.title("Relatório de Índices para Atualização")
    st.write(
        "Calcula o índice de variação de preços (base 100) para atualização de "
        "valores históricos de ativos, agregado por **UP** (quando os itens "
        "estiverem mapeados — ver página *Mapeamento de Itens*) ou por "
        "**disciplina** (funciona imediatamente, sem mapeamento manual)."
    )

    agregacao = st.radio("Agregar por", ["Disciplina", "UP (Unidade de Patrimônio)"], horizontal=True)
    banco_sel = st.selectbox("Banco de preços", db.list_bancos()["banco"].tolist())

    todos_i0 = i0_options(banco_sel)
    if len(todos_i0) < 1:
        st.warning("Nenhum i0 carregado para este banco.")
    else:
        base_i0 = st.selectbox("Mês-base (índice 100)", todos_i0, format_func=fmt_i0)

        if agregacao == "Disciplina":
            dados = db.df_query(
                "SELECT i0, disciplina, AVG(preco) preco_medio "
                "FROM banco_preco WHERE banco = :b GROUP BY i0, disciplina",
                {"b": banco_sel},
            )
            chave = "disciplina"
        else:
            dados = db.df_query(
                "SELECT i0, up_codigo, AVG(preco) preco_medio "
                "FROM banco_preco WHERE banco = :b AND up_codigo IS NOT NULL GROUP BY i0, up_codigo",
                {"b": banco_sel},
            )
            chave = "up_codigo"
            if dados.empty:
                st.info(
                    "Nenhum item deste banco está mapeado para uma UP ainda. "
                    "Use a página **Mapeamento de Itens** para associar códigos a UPs, "
                    "ou selecione agregação por Disciplina."
                )

        if not dados.empty:
            base = dados[dados["i0"] == base_i0][[chave, "preco_medio"]].rename(columns={"preco_medio": "preco_base"})
            merged = dados.merge(base, on=chave, how="left")
            merged["indice"] = (merged["preco_medio"] / merged["preco_base"] * 100).round(2)
            merged_view = merged.copy()
            merged_view["i0"] = merged_view["i0"].apply(fmt_i0)

            pivot = merged_view.pivot_table(index=chave, columns="i0", values="indice")
            st.subheader("Tabela de índices (base 100 no mês selecionado)")
            st.dataframe(pivot.style.format("{:.2f}"), use_container_width=True)

            fig = px.line(merged.assign(i0=pd.to_datetime(merged["i0"])), x="i0", y="indice", color=chave,
                           markers=True, title=f"Evolução do índice de preços — {banco_sel}")
            fig.add_hline(y=100, line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)

            bloco_exportacao("Índices para Atualização", {"Indices": pivot.reset_index()}, fig=fig, key_prefix="indices_atualizacao")


# ========================================================================
# PÁGINA: Variação Entre Bancos (por Segmento)
# ========================================================================
elif pagina == "📊 Variação Entre Bancos":
    st.title("Relatório de Variação de Preço Entre Bancos")
    st.write(
        "Compara a variação percentual de preços entre dois meses de referência (i0), "
        "nos três bancos, segmentada por disciplina de engenharia "
        "(**Civil, Elétrica, Hidromecânica**)."
    )

    todos_i0 = i0_options()
    if len(todos_i0) < 2:
        st.warning("É necessário ter ao menos 2 meses de referência (i0) carregados (em qualquer banco) para comparar.")
    else:
        c1, c2 = st.columns(2)
        i0_ini = c1.selectbox("i0 inicial", todos_i0, index=0, format_func=fmt_i0)
        i0_fim = c2.selectbox("i0 final", todos_i0, index=len(todos_i0) - 1, format_func=fmt_i0)

        disc_opts = ["Civil", "Elétrica", "Hidromecânica", "Mão de Obra"]
        disc_sel = st.multiselect("Disciplinas", disc_opts, default=["Civil", "Elétrica", "Hidromecânica"])

        dados = db.df_query(
            "SELECT banco, i0, disciplina, AVG(preco) preco_medio, COUNT(*) n_itens "
            "FROM banco_preco WHERE i0 IN (:a, :b) AND disciplina IN ({}) "
            "GROUP BY banco, i0, disciplina".format(",".join(f"'{d}'" for d in disc_sel)),
            {"a": i0_ini, "b": i0_fim},
        ) if disc_sel else pd.DataFrame()

        if dados.empty:
            st.info("Sem dados para os filtros selecionados.")
        else:
            pivot = dados.pivot_table(index=["banco", "disciplina"], columns="i0", values="preco_medio")
            if i0_ini in pivot.columns and i0_fim in pivot.columns:
                pivot["variacao_%"] = ((pivot[i0_fim] / pivot[i0_ini]) - 1) * 100
                pivot = pivot.round(2)
                st.subheader(f"Variação de {fmt_i0(i0_ini)} para {fmt_i0(i0_fim)}")
                st.dataframe(pivot, use_container_width=True)

                plot_df = pivot.reset_index()
                fig = px.bar(
                    plot_df, x="disciplina", y="variacao_%", color="banco", barmode="group",
                    title="Variação percentual de preços por segmento e banco",
                )
                fig.add_hline(y=0, line_color="gray")
                st.plotly_chart(fig, use_container_width=True)

                bloco_exportacao("Variação Entre Bancos", {"Variacao": plot_df}, fig=fig, key_prefix="variacao_bancos")
            else:
                st.warning("Um dos meses selecionados não possui dados suficientes para algum segmento.")


# ========================================================================
# PÁGINA: Inflação por Disciplina — REQUISITO 4
# ========================================================================
elif pagina == "🌡️ Inflação por Disciplina":
    st.title("Inflação de Preços de Serviços e Equipamentos por Disciplina")
    st.write(
        "Calcula a inflação de preços **dentro do mesmo banco**, comparando dois meses "
        "de referência (i0) diferentes, segmentada nas disciplinas **Civil, Elétrica e "
        "Hidromecânica**. Carregue quantos i0 forem necessários na página "
        "**Upload de Preços** — cada banco pode ter seus próprios meses carregados."
    )

    banco_sel = st.selectbox("Banco de preços", db.list_bancos()["banco"].tolist(), key="infl_disc_banco")
    todos_i0 = i0_options(banco_sel)

    if len(todos_i0) < 2:
        st.warning(f"É necessário carregar ao menos 2 meses (i0) para o banco {banco_sel} nesta análise.")
    else:
        c1, c2 = st.columns(2)
        i0_ini = c1.selectbox("i0 inicial", todos_i0, index=0, format_func=fmt_i0, key="infl_disc_ini")
        i0_fim = c2.selectbox("i0 final", todos_i0, index=len(todos_i0) - 1, format_func=fmt_i0, key="infl_disc_fim")

        disc_opts = ["Civil", "Elétrica", "Hidromecânica"]
        disc_sel = st.multiselect("Disciplinas", disc_opts, default=disc_opts, key="infl_disc_sel")

        if not disc_sel:
            st.info("Selecione ao menos uma disciplina.")
        else:
            dados = db.df_query(
                "SELECT i0, disciplina, AVG(preco) preco_medio, COUNT(*) n_itens "
                "FROM banco_preco WHERE banco = :b AND i0 IN (:a, :c) AND disciplina IN ({}) "
                "GROUP BY i0, disciplina".format(",".join(f"'{d}'" for d in disc_sel)),
                {"b": banco_sel, "a": i0_ini, "c": i0_fim},
            )
            if dados.empty:
                st.info("Sem dados suficientes para os filtros selecionados.")
            else:
                pivot = dados.pivot_table(index="disciplina", columns="i0", values="preco_medio")
                if i0_ini in pivot.columns and i0_fim in pivot.columns:
                    pivot["inflacao_%"] = ((pivot[i0_fim] / pivot[i0_ini]) - 1) * 100
                    pivot = pivot.round(2)

                    st.subheader(f"Inflação {banco_sel}: {fmt_i0(i0_ini)} → {fmt_i0(i0_fim)}")
                    st.dataframe(pivot, use_container_width=True)

                    cols = st.columns(len(pivot))
                    for i, (disc, row) in enumerate(pivot.iterrows()):
                        cols[i].metric(disc, f"{row['inflacao_%']:.2f}%")

                    fig = px.bar(pivot.reset_index(), x="disciplina", y="inflacao_%", color="disciplina",
                                 title=f"Inflação por disciplina — {banco_sel} ({fmt_i0(i0_ini)} → {fmt_i0(i0_fim)})")
                    fig.add_hline(y=0, line_color="gray")
                    st.plotly_chart(fig, use_container_width=True)

                    # série completa (todos os i0 do banco), não só início/fim
                    st.subheader("Série completa por disciplina (todos os i0 carregados)")
                    serie_completa = db.df_query(
                        "SELECT i0, disciplina, AVG(preco) preco_medio FROM banco_preco "
                        "WHERE banco = :b AND disciplina IN ({}) GROUP BY i0, disciplina".format(
                            ",".join(f"'{d}'" for d in disc_sel)),
                        {"b": banco_sel},
                    )
                    serie_completa["i0_dt"] = pd.to_datetime(serie_completa["i0"])
                    fig2 = px.line(serie_completa.sort_values("i0_dt"), x="i0_dt", y="preco_medio",
                                   color="disciplina", markers=True,
                                   title=f"Evolução do preço médio por disciplina — {banco_sel}")
                    st.plotly_chart(fig2, use_container_width=True)

                    bloco_exportacao(
                        f"Inflação por Disciplina — {banco_sel}",
                        {"Inflacao_Disciplina": pivot.reset_index(), "Serie_Completa": serie_completa},
                        fig=fig, key_prefix="inflacao_disciplina",
                    )
                else:
                    st.warning("Um dos meses selecionados não possui dados suficientes.")


# ========================================================================
# PÁGINA: Inflação por IPCA — REQUISITO 5
# ========================================================================
elif pagina == "💹 Inflação por IPCA":
    st.title("Inflação por IPCA — Comparação com os Bancos de Preços")
    st.write(
        "Cadastre os valores de **IPCA** para cada mês de referência (i0) — ex.: janeiro, "
        "março, abril e junho de 2026 — e compare com a variação de preço de um item/"
        "equipamento/material específico, disponível na base, nos bancos **Sabesp, SINAPI "
        "e TCPO**."
    )

    tab_cad, tab_comp = st.tabs(["📋 Cadastro de IPCA por i0", "📊 Comparativo Item x IPCA"])

    with tab_cad:
        st.subheader("IPCA cadastrado")
        ipca_df = db.list_ipca()
        if not ipca_df.empty:
            ipca_view = ipca_df.copy()
            ipca_view["i0"] = ipca_view["i0"].apply(fmt_i0)
            st.dataframe(ipca_view, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum IPCA cadastrado ainda.")

        st.markdown("**Cadastrar / atualizar IPCA de um i0**")
        with st.form("form_ipca"):
            c1, c2, c3 = st.columns(3)
            i0_ipca = c1.text_input("i0 (AAAA-MM-01)", placeholder="2026-01-01")
            variacao_ipca = c2.number_input("Variação % no mês (ou acumulada, à sua escolha)", value=0.0, step=0.01, format="%.2f")
            indice_ipca = c3.number_input("Número índice (opcional)", value=0.0, step=0.01, format="%.2f")
            obs_ipca = st.text_input("Observação (opcional)")
            enviado = st.form_submit_button("Salvar IPCA")
            if enviado:
                if not i0_ipca:
                    st.error("Informe o i0.")
                else:
                    db.upsert_ipca(i0_ipca.strip(), indice=indice_ipca or None, variacao_pct=variacao_ipca, observacao=obs_ipca or None)
                    st.success("IPCA salvo.")
                    st.rerun()

        st.markdown("**Também é possível carregar um arquivo (csv/xlsx) com colunas `i0` e `variacao_pct`**")
        arq_ipca = st.file_uploader("Arquivo de IPCA", type=["csv", "xlsx"], key="upload_ipca")
        if arq_ipca is not None:
            planilhas = read_any(arq_ipca)
            raw = list(planilhas.values())[0]
            st.dataframe(raw.head(10), use_container_width=True)
            cols = list(raw.columns)
            c1, c2 = st.columns(2)
            col_i0 = c1.selectbox("Coluna i0", cols)
            col_var = c2.selectbox("Coluna variação %", cols)
            if st.button("Importar IPCA do arquivo"):
                n = 0
                for _, r in raw.iterrows():
                    i0_val = parse_i0_from_text(r[col_i0]) or str(r[col_i0])
                    try:
                        db.upsert_ipca(i0_val, variacao_pct=float(str(r[col_var]).replace(",", ".")))
                        n += 1
                    except Exception:
                        continue
                st.success(f"{n} registros de IPCA importados.")
                st.rerun()

        if not ipca_df.empty:
            del_i0 = st.selectbox("Excluir IPCA de um i0", ["(nenhum)"] + ipca_df["i0"].tolist(),
                                   format_func=lambda x: x if x == "(nenhum)" else fmt_i0(x))
            if del_i0 != "(nenhum)" and st.button("🗑️ Excluir IPCA selecionado"):
                db.delete_ipca(del_i0)
                st.success("IPCA excluído.")
                st.rerun()

    with tab_comp:
        ipca_df = db.list_ipca()
        if ipca_df.empty:
            st.info("Cadastre ao menos 2 meses de IPCA na aba anterior para habilitar a comparação.")
        else:
            banco_sel = st.selectbox("Banco", db.list_bancos()["banco"].tolist(), key="ipca_banco")
            i0_disponiveis = sorted(set(i0_options(banco_sel)) & set(ipca_df["i0"].tolist()))
            if len(i0_disponiveis) < 2:
                st.warning(
                    "Não há pelo menos 2 meses (i0) em comum entre o banco selecionado e o IPCA cadastrado. "
                    "Carregue mais meses do banco ou cadastre o IPCA dos meses já carregados."
                )
            else:
                texto_busca = st.text_input("Buscar equipamento/material/serviço (texto livre)", key="ipca_busca")
                base_i0 = db.get_precos(banco=banco_sel, texto=texto_busca or None)
                if base_i0.empty:
                    st.info("Digite um termo de busca para localizar o item na base.")
                else:
                    codigo_sel = st.selectbox("Item", sorted(base_i0["codigo"].unique().tolist()),
                                               format_func=lambda c: f"{c} — {base_i0[base_i0['codigo']==c]['descricao'].iloc[0]}")
                    descricao_item = base_i0[base_i0["codigo"] == codigo_sel]["descricao"].iloc[0]

                    serie_item = db.df_query(
                        "SELECT i0, preco FROM banco_preco WHERE banco=:b AND codigo=:c AND i0 IN ({})".format(
                            ",".join(f"'{i}'" for i in i0_disponiveis)),
                        {"b": banco_sel, "c": codigo_sel},
                    ).sort_values("i0")

                    if len(serie_item) < 2:
                        st.info("Este item não possui preço em pelo menos 2 dos i0 comuns com o IPCA cadastrado.")
                    else:
                        base_preco = serie_item["preco"].iloc[0]
                        serie_item["indice_item"] = (serie_item["preco"] / base_preco * 100).round(2)

                        ipca_ord = ipca_df[ipca_df["i0"].isin(serie_item["i0"])].sort_values("i0").copy()
                        ipca_ord["indice_ipca"] = (100 + ipca_ord["variacao_pct"].fillna(0).cumsum()).round(2)
                        # normaliza para começar em 100 no primeiro i0 comum também para o IPCA
                        ipca_ord["indice_ipca"] = (ipca_ord["indice_ipca"] / ipca_ord["indice_ipca"].iloc[0] * 100).round(2)

                        comp = serie_item.merge(ipca_ord[["i0", "indice_ipca", "variacao_pct"]], on="i0", how="left")
                        comp["diferenca_vs_ipca_pp"] = (comp["indice_item"] - comp["indice_ipca"]).round(2)
                        comp_view = comp.copy()
                        comp_view["i0"] = comp_view["i0"].apply(fmt_i0)

                        st.subheader(f"{banco_sel} — {descricao_item}")
                        st.dataframe(comp_view, use_container_width=True, hide_index=True)

                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=comp["i0"], y=comp["indice_item"], mode="lines+markers", name="Item (banco)"))
                        fig.add_trace(go.Scatter(x=comp["i0"], y=comp["indice_ipca"], mode="lines+markers", name="IPCA", line=dict(dash="dash")))
                        fig.update_layout(title=f"Item x IPCA (base 100) — {banco_sel}", xaxis_title="i0", yaxis_title="Índice (base 100)")
                        st.plotly_chart(fig, use_container_width=True)

                        bloco_exportacao(
                            f"Inflação por IPCA — {banco_sel} — {descricao_item}",
                            {"Item_x_IPCA": comp_view}, fig=fig, key_prefix="inflacao_ipca",
                        )


# ========================================================================
# PÁGINA: Módulo DRC — Comparativo — REQUISITOS 6, 7 e 8
# ========================================================================
elif pagina == "⚖️ Módulo DRC — Comparativo":
    st.title("Módulo DRC — Comparativo de Propostas")
    st.write(
        "Cadastre o preço de um **fornecedor** (e, opcionalmente, o **preço contratado**), "
        "o sistema identifica automaticamente a **UP** correspondente e busca os itens mais "
        "similares nos bancos **Sabesp, SINAPI e TCPO**. O comparativo classifica o resultado "
        "em **Verde / Amarelo / Vermelho**, conforme a faixa de tolerância parametrizável."
    )

    tab_cad, tab_comp, tab_param = st.tabs([
        "📋 Cadastro de Preços (Fornecedor / Contratado)",
        "🔍 Comparativo e Análise",
        "⚙️ Parâmetros da Regra DRC",
    ])

    up_df_all = db.list_ups()
    uar_df_all = db.list_uars()

    # ------------------------------------------------------------------
    # Cadastro (CRUD) — requisito 6
    # ------------------------------------------------------------------
    with tab_cad:
        st.subheader("Preços cadastrados")
        fornecedores_df = db.list_fornecedor_precos()
        if not fornecedores_df.empty:
            st.dataframe(
                fornecedores_df[["id", "tipo_ativo_servico", "fornecedor", "preco_fornecedor",
                                  "preco_contratado", "up_codigo", "up_nome", "disciplina", "confianca_identificacao"]],
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("Nenhum preço de fornecedor cadastrado ainda.")

        st.divider()
        acao = st.radio("Ação", ["➕ Cadastrar novo", "✏️ Editar existente", "🗑️ Excluir"], horizontal=True, key="acao_forn")

        if acao == "➕ Cadastrar novo":
            with st.form("form_novo_fornecedor"):
                tipo_ativo = st.text_input("Tipo de serviço ou ativo do fornecedor", placeholder="Ex.: Bomba centrífuga horizontal 50cv")
                c1, c2, c3 = st.columns(3)
                fornecedor_nome = c1.text_input("Fornecedor")
                preco_fornecedor = c2.number_input("Preço do fornecedor (R$)", min_value=0.0, step=100.0, format="%.2f")
                preco_contratado = c3.number_input("Preço contratado (R$) — opcional", min_value=0.0, step=100.0, format="%.2f")
                enviado = st.form_submit_button("Cadastrar e identificar UP automaticamente")
                if enviado:
                    if not tipo_ativo:
                        st.error("Descreva o tipo de serviço/ativo.")
                    else:
                        candidatos = identificar_up(tipo_ativo, up_df_all, uar_df_all, top_n=1)
                        up_ident = candidatos[0]["up_codigo"] if candidatos else None
                        uar_ident = candidatos[0]["uar_codigo"] if candidatos else None
                        score = candidatos[0]["score"] if candidatos else 0.0
                        disc = classify_disciplina(tipo_ativo)
                        db.create_fornecedor_preco(
                            tipo_ativo, fornecedor_nome, preco_fornecedor,
                            preco_contratado or None, up_ident, uar_ident, disc, score,
                        )
                        if candidatos:
                            st.success(
                                f"Cadastrado. UP identificada automaticamente: **{up_ident} — "
                                f"{candidatos[0]['up_nome']}** (confiança {score:.0%}, via UAR "
                                f"'{candidatos[0]['uar_nome']}')."
                            )
                        else:
                            st.warning("Cadastrado, mas não foi possível identificar a UP automaticamente. Edite manualmente se necessário.")
                        st.rerun()

        elif acao == "✏️ Editar existente":
            if fornecedores_df.empty:
                st.info("Nada para editar.")
            else:
                escolha = st.selectbox(
                    "Selecione o registro",
                    fornecedores_df["id"].tolist(),
                    format_func=lambda i: f"#{i} — {fornecedores_df[fornecedores_df['id']==i]['tipo_ativo_servico'].iloc[0]}",
                )
                linha = fornecedores_df[fornecedores_df["id"] == escolha].iloc[0]
                with st.form("form_editar_fornecedor"):
                    tipo_ativo = st.text_input("Tipo de serviço/ativo", value=linha["tipo_ativo_servico"])
                    c1, c2, c3 = st.columns(3)
                    fornecedor_nome = c1.text_input("Fornecedor", value=linha["fornecedor"] or "")
                    preco_fornecedor = c2.number_input("Preço do fornecedor (R$)", value=float(linha["preco_fornecedor"] or 0), step=100.0, format="%.2f")
                    preco_contratado = c3.number_input("Preço contratado (R$)", value=float(linha["preco_contratado"] or 0), step=100.0, format="%.2f")
                    up_opts = [f"{r.up_codigo} - {r.up_nome}" for r in up_df_all.itertuples()]
                    idx_up = 0
                    for i, o in enumerate(up_opts):
                        if o.startswith(str(linha["up_codigo"]) + " -"):
                            idx_up = i
                    up_escolhida = st.selectbox("UP (ajuste manual, se necessário)", up_opts, index=idx_up)
                    enviado = st.form_submit_button("Salvar alterações")
                    if enviado:
                        disc = classify_disciplina(tipo_ativo)
                        db.update_fornecedor_preco(
                            int(escolha), tipo_ativo, fornecedor_nome, preco_fornecedor,
                            preco_contratado or None, up_escolhida.split(" - ")[0], linha["uar_codigo"], disc,
                        )
                        st.success("Registro atualizado.")
                        st.rerun()

        else:  # Excluir
            if fornecedores_df.empty:
                st.info("Nada para excluir.")
            else:
                escolha = st.selectbox(
                    "Selecione o registro para excluir",
                    fornecedores_df["id"].tolist(),
                    format_func=lambda i: f"#{i} — {fornecedores_df[fornecedores_df['id']==i]['tipo_ativo_servico'].iloc[0]}",
                    key="excluir_forn",
                )
                if st.button("🗑️ Confirmar exclusão", type="primary"):
                    db.delete_fornecedor_preco(int(escolha))
                    st.success("Registro excluído.")
                    st.rerun()

    # ------------------------------------------------------------------
    # Comparativo — requisitos 6, 7, 8
    # ------------------------------------------------------------------
    with tab_comp:
        fornecedores_df = db.list_fornecedor_precos()
        origem = st.radio("Origem do item a comparar", ["Usar cadastro existente", "Lançamento avulso (não salva no cadastro)"], horizontal=True)

        if origem == "Usar cadastro existente":
            if fornecedores_df.empty:
                st.info("Cadastre um preço de fornecedor na aba anterior primeiro.")
                st.stop()
            escolha = st.selectbox(
                "Registro do fornecedor",
                fornecedores_df["id"].tolist(),
                format_func=lambda i: f"#{i} — {fornecedores_df[fornecedores_df['id']==i]['tipo_ativo_servico'].iloc[0]}",
            )
            linha = fornecedores_df[fornecedores_df["id"] == escolha].iloc[0]
            tipo_ativo = linha["tipo_ativo_servico"]
            preco_fornecedor = linha["preco_fornecedor"]
            preco_contratado = linha["preco_contratado"]
            up_ident = linha["up_codigo"]
        else:
            tipo_ativo = st.text_input("Tipo de serviço/ativo")
            c1, c2 = st.columns(2)
            preco_fornecedor = c1.number_input("Preço do fornecedor (R$)", min_value=0.0, step=100.0, format="%.2f")
            preco_contratado = c2.number_input("Preço contratado (R$) — opcional", min_value=0.0, step=100.0, format="%.2f")
            up_ident = None
            if tipo_ativo:
                cand = identificar_up(tipo_ativo, up_df_all, uar_df_all, top_n=1)
                up_ident = cand[0]["up_codigo"] if cand else None

        if not tipo_ativo:
            st.info("Informe a descrição do item para localizar similares nos bancos.")
        else:
            candidatos_up = identificar_up(tipo_ativo, up_df_all, uar_df_all, top_n=3)
            if candidatos_up:
                st.markdown("**UP identificada automaticamente:**")
                for c in candidatos_up:
                    st.write(f"- {c['up_codigo']} — {c['up_nome']}  _(via UAR '{c['uar_nome']}', confiança {c['score']:.0%})_")

            bancos_disp = db.list_bancos()["banco"].tolist()
            c1, c2 = st.columns(2)
            bancos_incluir = c1.multiselect("Bancos para referência", bancos_disp, default=bancos_disp)
            i0_por_banco = {}
            with c2:
                for b in bancos_incluir:
                    opts = i0_options(b)
                    if opts:
                        i0_por_banco[b] = st.selectbox(f"i0 — {b}", opts, format_func=fmt_i0, key=f"i0_{b}")

            linhas_similares = []
            for b, i0v in i0_por_banco.items():
                base = db.get_precos(banco=b, i0=i0v)
                sim = buscar_similares(tipo_ativo, base, top_n=3)
                if sim is not None and not sim.empty:
                    sim = sim.copy()
                    sim["banco"] = b
                    linhas_similares.append(sim)

            if not linhas_similares:
                st.warning("Nenhum item similar encontrado nos bancos selecionados.")
            else:
                todos_sim = pd.concat(linhas_similares, ignore_index=True)
                todos_sim["i0"] = todos_sim["i0"].apply(fmt_i0)
                st.subheader("Itens similares encontrados nos bancos")
                st.dataframe(
                    todos_sim[["banco", "i0", "codigo", "descricao", "preco", "similaridade"]].sort_values(
                        ["banco", "similaridade"], ascending=[True, False]),
                    use_container_width=True, hide_index=True,
                )

                melhor_por_banco = todos_sim.sort_values("similaridade", ascending=False).groupby("banco").first().reset_index()
                referencial = melhor_por_banco["preco"].mean()

                st.subheader("Análise comparativa")
                variacao_fornecedor = ((preco_fornecedor / referencial) - 1) * 100 if referencial else None
                status_fornecedor = db.classificar_status(variacao_fornecedor)

                variacao_contratado = None
                status_contratado = None
                if preco_contratado:
                    variacao_contratado = ((preco_contratado / referencial) - 1) * 100 if referencial else None
                    status_contratado = db.classificar_status(variacao_contratado)

                resumo = pd.DataFrame([
                    {"Item": "Preço Referencial (média dos bancos)", "Valor (R$)": round(referencial, 2), "Variação vs. Referencial": "-", "Status": "-"},
                    {"Item": "Preço do Fornecedor", "Valor (R$)": round(preco_fornecedor, 2),
                     "Variação vs. Referencial": f"{variacao_fornecedor:.2f}%" if variacao_fornecedor is not None else "-",
                     "Status": status_fornecedor},
                ])
                if preco_contratado:
                    resumo = pd.concat([resumo, pd.DataFrame([{
                        "Item": "Preço Contratado", "Valor (R$)": round(preco_contratado, 2),
                        "Variação vs. Referencial": f"{variacao_contratado:.2f}%" if variacao_contratado is not None else "-",
                        "Status": status_contratado,
                    }])], ignore_index=True)

                st.dataframe(resumo.style.apply(highlight_status, axis=1), use_container_width=True, hide_index=True)

                cA, cB, cC = st.columns(3)
                cA.metric("Preço Referencial", f"R$ {referencial:,.2f}")
                cB.markdown(f"**Fornecedor:** {badge_status(status_fornecedor)}", unsafe_allow_html=True)
                if status_contratado:
                    cC.markdown(f"**Contratado:** {badge_status(status_contratado)}", unsafe_allow_html=True)

                verde, amarelo = db.get_limites_drc()
                st.caption(
                    f"Regra vigente: **Verde** ≤ ±{verde:.0f}% · **Amarelo** entre ±{verde:.0f}% e ±{amarelo:.0f}% · "
                    f"**Vermelho** acima de ±{amarelo:.0f}% (ajustável na aba *Parâmetros da Regra DRC*)."
                )

                fig_comp = px.bar(
                    melhor_por_banco.assign(**{"Fornecedor": preco_fornecedor}),
                    x="banco", y="preco", title="Preço do fornecedor vs. bancos de referência",
                )
                fig_comp.add_hline(y=preco_fornecedor, line_color="red", line_dash="dash", annotation_text="Preço Fornecedor")
                if preco_contratado:
                    fig_comp.add_hline(y=preco_contratado, line_color="blue", line_dash="dot", annotation_text="Preço Contratado")
                st.plotly_chart(fig_comp, use_container_width=True)

                if st.button("💾 Salvar este comparativo no histórico"):
                    registro = pd.DataFrame([{
                        "i0": list(i0_por_banco.values())[0] if i0_por_banco else None,
                        "codigo": None, "descricao": tipo_ativo, "fornecedor": "N/D",
                        "preco_fornecedor": preco_fornecedor, "preco_contratado": preco_contratado or None,
                        "banco_referencia": "MEDIA_" + "_".join(bancos_incluir),
                        "preco_referencial": referencial, "variacao_pct": variacao_fornecedor,
                        "up_codigo": up_ident, "status": status_fornecedor,
                    }])
                    n = db.salvar_propostas_drc(registro)
                    st.success(f"{n} comparativo salvo no histórico.")

                bloco_exportacao(
                    f"Comparativo DRC — {tipo_ativo}",
                    {"Resumo": resumo, "Itens_Similares": todos_sim[["banco", "i0", "codigo", "descricao", "preco", "similaridade"]]},
                    fig=fig_comp, key_prefix="drc_comparativo",
                )

        st.divider()
        st.subheader("Histórico de comparativos salvos")
        hist = db.list_propostas_drc()
        if not hist.empty:
            st.dataframe(hist.style.apply(highlight_status, axis=1), use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhum comparativo salvo ainda.")

    # ------------------------------------------------------------------
    # Parâmetros — requisito 7
    # ------------------------------------------------------------------
    with tab_param:
        st.subheader("Parâmetros da Regra DRC (requisito 7)")
        st.write(
            "Define as faixas de tolerância usadas para classificar o comparativo em "
            "**Verde / Amarelo / Vermelho** (requisito 8). Por padrão: até **±5%** do "
            "referencial é considerado conforme (regra padrão do DRC); entre a faixa "
            "conforme e o limite de atenção, o item fica em alerta amarelo; acima disso, "
            "vermelho (não conforme)."
        )
        verde_atual, amarelo_atual = db.get_limites_drc()
        with st.form("form_config_drc"):
            novo_verde = st.number_input("Limite 'Verde' (conforme) — % de variação absoluta", min_value=0.0, value=verde_atual, step=0.5, format="%.1f")
            novo_amarelo = st.number_input("Limite 'Amarelo' (atenção) — % de variação absoluta", min_value=0.0, value=amarelo_atual, step=0.5, format="%.1f")
            enviado = st.form_submit_button("Salvar parâmetros")
            if enviado:
                if novo_amarelo < novo_verde:
                    st.error("O limite amarelo deve ser maior ou igual ao limite verde.")
                else:
                    db.set_config("limite_verde_pct", novo_verde)
                    db.set_config("limite_amarelo_pct", novo_amarelo)
                    st.success("Parâmetros atualizados com sucesso.")
                    st.rerun()

        st.info(
            f"Regra atual: Verde ≤ ±{verde_atual:.1f}% · Amarelo até ±{amarelo_atual:.1f}% · "
            f"Vermelho acima de ±{amarelo_atual:.1f}%."
        )


# ========================================================================
# PÁGINA: Dashboards — REQUISITO 9
# ========================================================================
elif pagina == "📉 Dashboards":
    st.title("Dashboards e Gráficos")
    st.write("Painéis visuais: **Linha, Barras, Heatmap** e **BAR Incremental** (evolução incremental do índice de preços).")

    tipo_grafico = st.selectbox("Tipo de gráfico", ["📈 Linha", "📊 Barras", "🔥 Heatmap", "🧱 BAR Incremental"])

    banco_sel = st.selectbox("Banco", db.list_bancos()["banco"].tolist(), key="dash_banco")
    disc_opts = ["Civil", "Elétrica", "Hidromecânica", "Mão de Obra", "Outros"]

    # ------------------------------------------------------------------
    if tipo_grafico == "📈 Linha":
        disc_sel = st.multiselect("Disciplinas", disc_opts, default=["Civil", "Elétrica", "Hidromecânica"], key="dash_linha_disc")
        dados = db.df_query(
            "SELECT i0, disciplina, AVG(preco) preco_medio FROM banco_preco "
            "WHERE banco=:b AND disciplina IN ({}) GROUP BY i0, disciplina".format(",".join(f"'{d}'" for d in disc_sel)),
            {"b": banco_sel},
        )
        if dados.empty:
            st.info("Sem dados para os filtros selecionados.")
        else:
            dados["i0"] = pd.to_datetime(dados["i0"])
            fig = px.line(dados.sort_values("i0"), x="i0", y="preco_medio", color="disciplina", markers=True,
                          title=f"Evolução do preço médio — {banco_sel}")
            st.plotly_chart(fig, use_container_width=True)
            bloco_exportacao("Dashboard — Linha", {"Dados": dados}, fig=fig, key_prefix="dash_linha")

    # ------------------------------------------------------------------
    elif tipo_grafico == "📊 Barras":
        todos_i0 = i0_options(banco_sel)
        if len(todos_i0) < 2:
            st.warning("É necessário ao menos 2 meses (i0) carregados para este banco.")
        else:
            c1, c2 = st.columns(2)
            i0_ini = c1.selectbox("i0 inicial", todos_i0, format_func=fmt_i0, key="dash_bar_ini")
            i0_fim = c2.selectbox("i0 final", todos_i0, index=len(todos_i0) - 1, format_func=fmt_i0, key="dash_bar_fim")
            dados = db.df_query(
                "SELECT i0, disciplina, AVG(preco) preco_medio FROM banco_preco "
                "WHERE banco=:b AND i0 IN (:a,:c) GROUP BY i0, disciplina",
                {"b": banco_sel, "a": i0_ini, "c": i0_fim},
            )
            if dados.empty:
                st.info("Sem dados suficientes.")
            else:
                pivot = dados.pivot_table(index="disciplina", columns="i0", values="preco_medio")
                if i0_ini in pivot.columns and i0_fim in pivot.columns:
                    pivot["variacao_%"] = ((pivot[i0_fim] / pivot[i0_ini]) - 1) * 100
                    fig = px.bar(pivot.reset_index(), x="disciplina", y="variacao_%", color="disciplina",
                                 title=f"Variação % por disciplina — {banco_sel} ({fmt_i0(i0_ini)} → {fmt_i0(i0_fim)})")
                    fig.add_hline(y=0, line_color="gray")
                    st.plotly_chart(fig, use_container_width=True)
                    bloco_exportacao("Dashboard — Barras", {"Dados": pivot.reset_index()}, fig=fig, key_prefix="dash_barras")

    # ------------------------------------------------------------------
    elif tipo_grafico == "🔥 Heatmap":
        todos_i0 = i0_options()
        if len(todos_i0) < 2:
            st.warning("É necessário ao menos 2 meses (i0) carregados (em qualquer banco).")
        else:
            c1, c2 = st.columns(2)
            i0_ini = c1.selectbox("i0 inicial", todos_i0, format_func=fmt_i0, key="dash_heat_ini")
            i0_fim = c2.selectbox("i0 final", todos_i0, index=len(todos_i0) - 1, format_func=fmt_i0, key="dash_heat_fim")
            dados = db.df_query(
                "SELECT banco, i0, disciplina, AVG(preco) preco_medio FROM banco_preco WHERE i0 IN (:a,:c) GROUP BY banco, i0, disciplina",
                {"a": i0_ini, "c": i0_fim},
            )
            if dados.empty:
                st.info("Sem dados suficientes.")
            else:
                pivot = dados.pivot_table(index=["banco", "disciplina"], columns="i0", values="preco_medio")
                if i0_ini in pivot.columns and i0_fim in pivot.columns:
                    pivot["variacao_%"] = ((pivot[i0_fim] / pivot[i0_ini]) - 1) * 100
                    heat_df = pivot.reset_index().pivot(index="disciplina", columns="banco", values="variacao_%")
                    fig = px.imshow(
                        heat_df, text_auto=".1f", color_continuous_scale="RdYlGn_r", origin="lower",
                        title=f"Heatmap de variação % — {fmt_i0(i0_ini)} → {fmt_i0(i0_fim)}",
                        labels=dict(color="Variação %"),
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    bloco_exportacao("Dashboard — Heatmap", {"Dados": heat_df.reset_index()}, fig=fig, key_prefix="dash_heatmap")

    # ------------------------------------------------------------------
    else:  # BAR Incremental
        st.caption(
            "Visualização em cascata (waterfall) da evolução **incremental** do índice de preços "
            "médio do banco/disciplina selecionados ao longo dos meses (i0) carregados — usada como "
            "proxy visual para acompanhar a evolução da Base de Ativos Regulatórios (BAR) período a período."
        )
        disc_sel = st.selectbox("Disciplina", disc_opts, key="dash_bar_incr_disc")
        dados = db.df_query(
            "SELECT i0, AVG(preco) preco_medio FROM banco_preco WHERE banco=:b AND disciplina=:d GROUP BY i0 ORDER BY i0",
            {"b": banco_sel, "d": disc_sel},
        )
        if len(dados) < 2:
            st.warning("É necessário ao menos 2 meses (i0) carregados para este banco/disciplina.")
        else:
            dados["indice"] = (dados["preco_medio"] / dados["preco_medio"].iloc[0] * 100)
            dados["delta"] = dados["indice"].diff()
            medidas = ["absolute"] + ["relative"] * (len(dados) - 1)
            valores = [dados["indice"].iloc[0]] + dados["delta"].iloc[1:].round(2).tolist()
            rotulos = [fmt_i0(i) for i in dados["i0"]]

            fig = go.Figure(go.Waterfall(
                orientation="v", measure=medidas, x=rotulos, y=valores,
                connector={"line": {"color": "rgb(120,120,120)"}},
                increasing={"marker": {"color": "#2e7d32"}},
                decreasing={"marker": {"color": "#c62828"}},
                totals={"marker": {"color": "#6a1b9a"}},
            ))
            fig.update_layout(title=f"BAR Incremental (proxy) — índice base 100 — {banco_sel} / {disc_sel}")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(dados.assign(i0=dados["i0"].apply(fmt_i0)).round(2), use_container_width=True, hide_index=True)
            bloco_exportacao("Dashboard — BAR Incremental", {"Dados": dados}, fig=fig, key_prefix="dash_bar_incremental")


# ========================================================================
# PÁGINA: Mapeamento de Itens
# ========================================================================
elif pagina == "🔗 Mapeamento de Itens":
    st.title("Mapeamento de Itens dos Bancos → UP / UAR / Disciplina")
    st.info(
        "Os códigos usados pelos bancos de preços (Sabesp, SINAPI, TCPO) não seguem "
        "a mesma codificação das UPs/UARs do manual de ativos. Use esta tela para "
        "associar manualmente um código de item a uma UP/UAR e/ou corrigir a "
        "disciplina sugerida automaticamente. O vínculo é lembrado e aplicado a "
        "todos os meses (i0) futuros e já carregados desse código."
    )

    c1, c2 = st.columns(2)
    banco_sel = c1.selectbox("Banco", db.list_bancos()["banco"].tolist())
    texto = c2.text_input("Buscar item por descrição ou código")

    itens = db.get_precos(banco=banco_sel, texto=texto or None)
    itens_unicos = itens.drop_duplicates(subset=["codigo"])[["codigo", "descricao", "disciplina", "up_codigo", "uar_codigo"]]
    st.dataframe(itens_unicos.head(200), use_container_width=True, hide_index=True)

    if not itens_unicos.empty:
        codigo_sel = st.selectbox("Código do item a mapear", itens_unicos["codigo"].tolist())
        linha_atual = itens_unicos[itens_unicos["codigo"] == codigo_sel].iloc[0]
        st.write(f"**Descrição:** {linha_atual['descricao']}")

        if st.button("🤖 Sugerir UP/UAR automaticamente (via similaridade)"):
            sugestoes = identificar_up(linha_atual["descricao"], db.list_ups(), db.list_uars(), top_n=3)
            for s in sugestoes:
                st.write(f"- {s['up_codigo']} — {s['up_nome']} (UAR: {s['uar_nome']}, confiança {s['score']:.0%})")

        ups = db.list_ups()
        up_opts = ["(nenhuma)"] + [f"{r.up_codigo} - {r.up_nome}" for r in ups.itertuples()]
        idx_up = 0
        if pd.notna(linha_atual["up_codigo"]):
            for i, o in enumerate(up_opts):
                if o.startswith(str(linha_atual["up_codigo"]) + " -"):
                    idx_up = i
        up_escolhida = st.selectbox("UP", up_opts, index=idx_up)
        up_codigo_final = None if up_escolhida == "(nenhuma)" else up_escolhida.split(" - ")[0]

        uars = db.list_uars(up_codigo_final) if up_codigo_final else db.list_uars()
        uar_opts = ["(nenhuma)"] + [f"{r.uar_codigo} - {r.uar_nome}" for r in uars.itertuples()]
        uar_escolhida = st.selectbox("UAR", uar_opts)
        uar_codigo_final = None if uar_escolhida == "(nenhuma)" else uar_escolhida.split(" - ")[0]

        disc_idx = DISCIPLINAS.index(linha_atual["disciplina"]) if linha_atual["disciplina"] in DISCIPLINAS else 0
        disc_escolhida = st.selectbox("Disciplina", DISCIPLINAS, index=disc_idx)

        if st.button("💾 Salvar mapeamento"):
            db.salvar_mapeamento(banco_sel, codigo_sel, up_codigo_final, uar_codigo_final, disc_escolhida)
            st.success("Mapeamento salvo e aplicado retroativamente a todos os meses (i0) já carregados.")
            st.cache_data.clear()

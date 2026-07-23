# Sistema de Inteligência de Ativos e Relatórios de Engenharia
### Metodologia DRC (Custo de Reposição Depreciado) e Índices i0 — v2

Sistema em **Python + Streamlit** para gestão de ativos de saneamento, processamento
dos bancos de preços **Sabesp, SINAPI e TCPO** e emissão de relatórios baseados em
séries temporais de meses de referência (**i0**).

---

## 1. O que o sistema faz

- Mantém um **histórico de preços por item, banco e mês de referência (i0)**, permitindo
  carregar novos meses via upload (xlsx/csv) sem perder o histórico anterior, com
  **múltiplos i0 por banco** carregados de forma independente.
- **CRUD completo de UPs e UARs** (cadastrar, editar, excluir), a partir da Tabela III
  do manual Sabesp já pré-carregada (30 UPs / 919 UARs).
- Classifica automaticamente cada item em uma disciplina — **Civil, Elétrica,
  Hidromecânica** (+ Mão de Obra / Outros) — por heurística de palavras-chave, com
  sobrescrita manual disponível.
- **Identificação automática de UP** a partir de texto livre (ex.: descrição de um
  ativo/serviço de fornecedor), por similaridade textual contra a nomenclatura das
  919 UARs — sem depender de nenhuma chave de código em comum.
- **Busca de itens similares** nos 3 bancos de preços para qualquer descrição livre.
- Gera os relatórios:
  1. **Índices para Atualização** — índice de preço (base 100) por UP ou por disciplina.
  2. **Variação Entre Bancos** — comparação entre os 3 bancos, por disciplina, entre dois i0.
  3. **Inflação por Disciplina** (Civil / Elétrica / Hidromecânica) — comparação **dentro
     do mesmo banco**, entre i0 diferentes.
  4. **Inflação por IPCA** — compara a variação de preço de um item específico, em
     qualquer um dos 3 bancos, com o IPCA cadastrado para os mesmos meses de referência.
  5. **Módulo DRC — Comparativo** — cadastro de preços de fornecedor e preço contratado,
     identificação automática de UP, busca de itens similares nos 3 bancos e cálculo de
     variação percentual, com classificação **Verde / Amarelo / Vermelho** conforme
     regra parametrizável (padrão: ±5% conforme, ±10% atenção, acima disso não conforme).
  6. **Dashboards** — gráficos de Linha, Barras, Heatmap e "BAR Incremental" (waterfall).
- **Exportação de qualquer relatório** em **Excel, PDF e PowerPoint**, com um clique.

O banco de dados já vem **pré-carregado** com os três bancos de preços fornecidos
(Sabesp e SINAPI em `i0 = 2026-05`, TCPO com `i0` detectado linha a linha a partir da
coluna "Data Preço", predominantemente `2026-04`).

---

## 2. Estrutura de pastas

```
drc_sistema/
├── app.py                     # Aplicação Streamlit (11 páginas)
├── db.py                      # Schema SQLite + funções de acesso a dados / CRUD
├── seed_initial_bancos.py     # Script de carga inicial dos 3 bancos de preços
├── seed_up_uar.json           # Dados da Tabela III (UP/UAR) já extraídos do manual
├── requirements.txt
├── utils/
│   ├── classify.py            # Heurística de classificação por disciplina
│   ├── import_utils.py        # Parsers Sabesp / SINAPI / TCPO / genérico
│   ├── matching.py            # Identificação automática de UP + busca por similaridade
│   └── export_utils.py        # Exportação Excel / PDF / PowerPoint
└── data/
    ├── drc_sistema.db         # Banco SQLite (já populado)
    └── BANCOS_SABESP__SINAPI_E_TCPO.xlsx   # Arquivo-fonte da carga inicial
```

## 3. Modelo de dados (SQL)

| Tabela | Descrição |
|---|---|
| `up` | Unidades de Patrimônio (código, nome, tipo Individual/Massa, unidade) — CRUD completo |
| `uar` | Unidades de Acréscimo e Recuperação, vinculadas a uma `up` — CRUD completo |
| `atributo_tecnico` | Tabela IV do manual (ex.: Acionamento) |
| `grupo_metodo` | Mapa UP → categoria → método (DRC ou VOC), conforme Seção 3 da NT ARSESP |
| `banco_preco` | Histórico de preços: banco, **i0**, código, descrição, unidade, preço, mão de obra, disciplina, UP/UAR vinculados |
| `mapeamento_item` | Vínculo manual persistente código→UP/UAR/disciplina (sobrepõe a classificação automática) |
| `fornecedor_preco` | **CRUD de preços de fornecedores e preços contratados**, com UP/UAR/disciplina identificados automaticamente |
| `ipca_indice` | Índices/variações de IPCA cadastrados por i0 |
| `config_drc` | Parâmetros da regra DRC (faixas Verde/Amarelo/Vermelho) — parametrizável pela interface |
| `drc_proposta` | Histórico de comparativos do Módulo DRC (fornecedor x referencial x contratado) |
| `importacao_log` | Auditoria de cada upload realizado |

---

## 4. Rodando localmente (VS Code)

```bash
cd drc_sistema
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

# (Opcional) recarregar/atualizar a base inicial de preços
python seed_initial_bancos.py data/BANCOS_SABESP__SINAPI_E_TCPO.xlsx

streamlit run app.py
```

O app abre em `http://localhost:8501`. O banco SQLite já é criado/populado
automaticamente na primeira execução (`db.bootstrap()`).

---

## 5. Publicando gratuitamente no GitHub + Streamlit Cloud

1. **Criar o repositório no GitHub** — [github.com/new](https://github.com/new).
2. **Subir o código**
   ```bash
   cd drc_sistema
   git init
   git add .
   git commit -m "Sistema DRC v2 - CRUD UP, inflação por disciplina/IPCA, comparativo DRC, dashboards, exportação"
   git branch -M main
   git remote add origin https://github.com/SEU-USUARIO/drc-sistema-ativos.git
   git push -u origin main
   ```
3. **Criar o app no Streamlit Community Cloud** — [share.streamlit.io](https://share.streamlit.io)
   → login GitHub → **New app** → selecione o repositório, branch `main`, arquivo `app.py` → **Deploy**.
4. O Streamlit Cloud instala automaticamente tudo do `requirements.txt` (inclui
   `reportlab`, `python-pptx` e `kaleido`, usados na exportação de relatórios).
5. **Persistência dos dados:** o filesystem do Streamlit Cloud é **efêmero**. Cadastros
   feitos em produção (novos i0, UPs, fornecedores, IPCA, mapeamentos) são perdidos ao
   reiniciar o app. Para uso contínuo real, migre `db.py` de SQLite para um Postgres
   gratuito (ex.: [Supabase](https://supabase.com) ou [Neon](https://neon.tech)) —
   a estrutura de tabelas (`SCHEMA`) permanece praticamente a mesma.

---

## 6. Fluxo de uso recomendado

1. **Upload de Preços** → carregar quantos meses (i0) forem necessários, por banco.
2. **UPs e UARs (Cadastro)** → ajustar/criar UPs conforme a realidade da concessionária.
3. **Mapeamento de Itens** (opcional) → vincular itens dos bancos às UPs, para habilitar
   o relatório de Índices por UP.
4. **Inflação por Disciplina** / **Inflação por IPCA** → acompanhar a evolução de preços.
5. **Módulo DRC:**
   - Aba *Cadastro*: registrar preço do fornecedor (+ preço contratado, opcional) — a UP é
     identificada automaticamente.
   - Aba *Comparativo*: escolher os bancos/i0 de referência; o sistema busca os itens mais
     similares e calcula a variação %, com selo Verde/Amarelo/Vermelho.
   - Aba *Parâmetros*: ajustar as faixas de tolerância (padrão ±5% / ±10%).
6. **Dashboards** → visões de Linha, Barras, Heatmap e BAR Incremental.
7. Em qualquer relatório, use o bloco **"⬇️ Exportar este relatório"** para baixar em
   Excel, PDF ou PowerPoint.

---

## 7. Observações técnicas e limitações conhecidas

- A classificação por disciplina é **heurística** (palavras-chave) — pode ser corrigida
  manualmente via **Mapeamento de Itens**.
- A **identificação automática de UP** e a **busca por similaridade** usam um algoritmo de
  similaridade textual (recall ponderado sobre tokens, sem dependências externas) — ela
  prioriza a presença dos termos-chave da consulta (ex.: "bomba", "centrífuga") na
  descrição do catálogo, mas **não interpreta valores numéricos de especificação** (ex.:
  "50cv" não é comparado numericamente com "16 CV até 50 CV"). Por isso, **sempre revise
  a tabela de itens similares** exibida antes de validar o comparativo — em catálogos
  com muitas variações de potência/diâmetro do mesmo equipamento, o item plotado como
  "melhor match" pode não ser exatamente a faixa de potência desejada.
- Os códigos de item dos bancos de preços (Sabesp/SINAPI/TCPO) **não** seguem a mesma
  codificação das UPs/UARs do manual de ativos — por isso o vínculo item→UP é via
  identificação automática (matching textual) ou mapeamento manual, nunca por chave direta.
- O parser do TCPO lê a data do preço **linha a linha** (coluna "Data Preço"), permitindo
  múltiplos i0 dentro de um único arquivo/aba.
- A exportação de gráficos para PDF/PPTX depende da biblioteca `kaleido`; se ela não
  estiver disponível no ambiente, o sistema ainda exporta as tabelas normalmente (sem a
  imagem do gráfico), sem quebrar a exportação.
- O gráfico "BAR Incremental" é uma **visualização proxy** (waterfall do índice de preço
  médio período a período) — os bancos de preços não contêm o valor de ativos da Base
  Regulatória (BAR) em si, apenas preços de insumos/serviços.

# Prompt Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Melhorar o prompt enviado à IA para inferir melhor o significado de cada coluna através do nome e da amostra de dados — adicionando transposição da amostra por coluna, detecção local de padrões (hints) e novas instruções no system prompt.

**Architecture:** A função `build_enrichment_prompt` em `src/ai/prompt_builder.py` passa a transpor a amostra de dados de linhas para valores-por-coluna e injeta hints determinísticos gerados por `_detect_hints()`. O `SYSTEM_PROMPT` recebe 3 novos blocos de instrução. Nenhum outro arquivo é modificado.

**Tech Stack:** Python 3.11+, `re`, `json` (stdlib), `pytest` para testes.

---

## File Map

| Ação | Arquivo |
|---|---|
| Modify | `src/ai/prompt_builder.py` |
| Create | `tests/test_prompt_builder.py` |

---

### Task 1: Função auxiliar `_transpose_sample`

Transpõe `list[dict]` (linhas) em `dict[str, list]` (valores por coluna).

**Files:**
- Modify: `src/ai/prompt_builder.py`
- Create: `tests/test_prompt_builder.py`

- [ ] **Step 1: Criar o arquivo de testes com o primeiro teste falhando**

Criar `tests/test_prompt_builder.py` com o conteúdo:

```python
import pytest
from src.ai.prompt_builder import _transpose_sample


def test_transpose_sample_basic():
    sample = [
        {"nome": "Alice", "idade": 30},
        {"nome": "Bob",   "idade": 25},
    ]
    result = _transpose_sample(sample)
    assert result == {"nome": ["Alice", "Bob"], "idade": [30, 25]}


def test_transpose_sample_empty():
    assert _transpose_sample([]) == {}


def test_transpose_sample_missing_keys():
    sample = [{"a": 1, "b": 2}, {"a": 3}]
    result = _transpose_sample(sample)
    assert result["a"] == [1, 3]
    assert result["b"] == [2]
```

- [ ] **Step 2: Rodar o teste para confirmar falha**

```
pytest tests/test_prompt_builder.py -v
```

Saída esperada: `ImportError` ou `AttributeError` — `_transpose_sample` não existe.

- [ ] **Step 3: Implementar `_transpose_sample` em `src/ai/prompt_builder.py`**

Adicionar logo após os imports existentes (antes de `UTILS_FUNCTIONS_CATALOG`):

```python
def _transpose_sample(sample_data: list[dict]) -> dict[str, list]:
    """Transpõe [{col: val, ...}, ...] em {col: [val1, val2, ...], ...}."""
    result: dict[str, list] = {}
    for row in sample_data:
        for key, value in row.items():
            result.setdefault(key, []).append(value)
    return result
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

```
pytest tests/test_prompt_builder.py -v
```

Saída esperada: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/ai/prompt_builder.py tests/test_prompt_builder.py
git commit -m "feat: add _transpose_sample helper for per-column sample data"
```

---

### Task 2: Função `_detect_hints`

Analisa nome e amostra de uma coluna e retorna uma string de hint determinístico.

**Files:**
- Modify: `src/ai/prompt_builder.py`
- Modify: `tests/test_prompt_builder.py`

- [ ] **Step 1: Adicionar testes para `_detect_hints`**

Adicionar ao final de `tests/test_prompt_builder.py`:

```python
from src.ai.prompt_builder import _detect_hints


# CPF
def test_detect_hints_cpf():
    samples = ["123.456.789-00", "987.654.321-01"]
    assert "CPF" in _detect_hints("numero_cpf", samples)
    assert "PII=true" in _detect_hints("numero_cpf", samples)
    assert "removeSpecialChars" in _detect_hints("numero_cpf", samples)


def test_detect_hints_cpf_sem_formatacao():
    samples = ["12345678900"]
    # CPF sem pontuação: 11 dígitos — o regex aceita sem pontos/traço
    hint = _detect_hints("cpf_cliente", samples)
    assert "CPF" in hint


# CNPJ
def test_detect_hints_cnpj():
    samples = ["12.345.678/0001-99", "98.765.432/0001-00"]
    hint = _detect_hints("cnpj_empresa", samples)
    assert "CNPJ" in hint
    assert "PII=true" in hint


# Email
def test_detect_hints_email():
    samples = ["alice@example.com", "bob@corp.com.br"]
    hint = _detect_hints("email_contato", samples)
    assert "e-mail" in hint
    assert "cleanEmail" in hint


# JSON estruturado
def test_detect_hints_json():
    samples = ['{"tipo": "PF", "renda": 5000}', '{"tipo": "PJ"}']
    hint = _detect_hints("dados_complementares", samples)
    assert "JSON estruturado" in hint
    assert "none" in hint


# Booleano
def test_detect_hints_booleano_sim_nao():
    samples = ["Sim", "Não", "Sim", "Não"]
    hint = _detect_hints("ativo", samples)
    assert "castBoolean" in hint


def test_detect_hints_booleano_true_false():
    samples = ["true", "false", "true"]
    hint = _detect_hints("flag_ativo", samples)
    assert "castBoolean" in hint


# Monetário BRL
def test_detect_hints_monetario():
    samples = ["R$ 1.500,00", "R$ 200,50"]
    hint = _detect_hints("honorarios", samples)
    assert "castMoneyBRL" in hint


def test_detect_hints_monetario_sem_rs():
    samples = ["1.500,00", "200,50"]
    hint = _detect_hints("valor_total", samples)
    assert "castMoneyBRL" in hint


# Data em texto
def test_detect_hints_data_ddmmaaaa():
    samples = ["15/03/1985", "22/07/1990"]
    hint = _detect_hints("data_nascimento", samples)
    assert "safeCastDate" in hint


def test_detect_hints_data_iso():
    samples = ["1985-03-15", "1990-07-22"]
    hint = _detect_hints("dt_nascimento", samples)
    assert "safeCastDate" in hint


# Sem hint
def test_detect_hints_sem_padrao():
    samples = ["Escritório Central", "Filial Norte", "Matriz"]
    hint = _detect_hints("descricao_unidade", samples)
    assert hint == ""


# Amostra vazia / apenas nulls
def test_detect_hints_somente_nulls():
    assert _detect_hints("qualquer_coluna", [None, None]) == ""


def test_detect_hints_lista_vazia():
    assert _detect_hints("qualquer_coluna", []) == ""


# Prioridade: CPF antes de data (CPF tem dígitos que poderiam parecer data)
def test_detect_hints_cpf_priority_over_date():
    samples = ["123.456.789-00"]
    hint = _detect_hints("documento", samples)
    assert "CPF" in hint
    assert "safeCastDate" not in hint
```

- [ ] **Step 2: Rodar os testes para confirmar falha**

```
pytest tests/test_prompt_builder.py -v -k "detect_hints"
```

Saída esperada: `ImportError` — `_detect_hints` não existe.

- [ ] **Step 3: Implementar `_detect_hints` em `src/ai/prompt_builder.py`**

Adicionar logo após `_transpose_sample`:

```python
import re as _re
import json as _json_module

_CPF_RE  = _re.compile(r'^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$')
_CNPJ_RE = _re.compile(r'^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$')
_EMAIL_RE = _re.compile(r'\S+@\S+\.\S+')
_MONEY_RE = _re.compile(r'R\$|\d{1,3}(\.\d{3})*,\d{2}')
_DATE_RE  = _re.compile(r'\b(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4})\b')
_BOOL_VALUES = {"sim", "não", "nao", "s", "n", "true", "false", "ativo", "inativo", "0", "1"}


def _detect_hints(col_name: str, sample_values: list) -> str:
    """Detecta padrões na amostra e retorna um hint para o prompt da IA."""
    non_null = [str(v) for v in sample_values if v is not None]
    if not non_null:
        return ""

    # CPF — prioridade 1
    if any(_CPF_RE.match(v.strip()) for v in non_null):
        return "[HINT: padrão CPF → PII=true, suggested_function: removeSpecialChars]"

    # CNPJ — prioridade 2
    if any(_CNPJ_RE.match(v.strip()) for v in non_null):
        return "[HINT: padrão CNPJ → PII=true, suggested_function: removeSpecialChars]"

    # Email
    if any(_EMAIL_RE.search(v) for v in non_null):
        return "[HINT: e-mail detectado → PII=true, suggested_function: cleanEmail]"

    # JSON estruturado
    for v in non_null:
        try:
            parsed = _json_module.loads(v)
            if isinstance(parsed, (dict, list)):
                return "[HINT: STRING contém JSON estruturado → descrever campos internos se possível, suggested_function: none]"
        except (ValueError, TypeError):
            pass

    # Booleano texto — todos os não-nulos devem ser valores booleanos
    if all(v.strip().lower() in _BOOL_VALUES for v in non_null):
        return "[HINT: booleano → suggested_function: castBoolean]"

    # Monetário BRL
    if any(_MONEY_RE.search(v) for v in non_null):
        return "[HINT: valor monetário BRL → suggested_function: castMoneyBRL]"

    # Data em texto
    if any(_DATE_RE.search(v) for v in non_null):
        return "[HINT: data em texto → suggested_function: safeCastDate]"

    return ""
```

- [ ] **Step 4: Rodar todos os testes**

```
pytest tests/test_prompt_builder.py -v
```

Saída esperada: todos os testes passando.

- [ ] **Step 5: Commit**

```bash
git add src/ai/prompt_builder.py tests/test_prompt_builder.py
git commit -m "feat: add _detect_hints for deterministic pattern detection in column samples"
```

---

### Task 3: Refatorar `build_enrichment_prompt` com transposição + hints

Substituir a listagem de colunas + bloco separado de amostra pelo novo formato com valores por coluna e hints injetados.

**Files:**
- Modify: `src/ai/prompt_builder.py`
- Modify: `tests/test_prompt_builder.py`

- [ ] **Step 1: Adicionar testes de integração para o novo formato do prompt**

Adicionar ao final de `tests/test_prompt_builder.py`:

```python
from src.ai.prompt_builder import build_enrichment_prompt
from src.extractor.schema_extractor import TableSchema, ColumnSchema


def _make_schema(columns, sample_data):
    return TableSchema(
        table_name="test_table",
        source_file="test.parquet",
        db="raw",
        row_count=100,
        sample_data=sample_data,
        columns=[ColumnSchema(name=n, type=t, nullable=True) for n, t in columns],
    )


def test_prompt_contains_column_samples():
    schema = _make_schema(
        columns=[("HONORARIOS", "STRING"), ("STATUS", "STRING")],
        sample_data=[
            {"HONORARIOS": "1.500,00", "STATUS": "Ativo"},
            {"HONORARIOS": "2.000,00", "STATUS": "Inativo"},
        ],
    )
    messages = build_enrichment_prompt(schema)
    user_msg = messages[1]["content"]
    assert "HONORARIOS" in user_msg
    assert "1.500,00" in user_msg
    assert "STATUS" in user_msg
    assert "Ativo" in user_msg


def test_prompt_injects_monetary_hint():
    schema = _make_schema(
        columns=[("VALOR_HONORARIOS", "STRING")],
        sample_data=[
            {"VALOR_HONORARIOS": "R$ 1.500,00"},
            {"VALOR_HONORARIOS": "R$ 200,00"},
        ],
    )
    messages = build_enrichment_prompt(schema)
    user_msg = messages[1]["content"]
    assert "castMoneyBRL" in user_msg


def test_prompt_injects_cpf_hint():
    schema = _make_schema(
        columns=[("NUMERO_CPF", "STRING")],
        sample_data=[
            {"NUMERO_CPF": "123.456.789-00"},
            {"NUMERO_CPF": "987.654.321-01"},
        ],
    )
    messages = build_enrichment_prompt(schema)
    user_msg = messages[1]["content"]
    assert "CPF" in user_msg
    assert "PII=true" in user_msg


def test_prompt_injects_json_hint():
    schema = _make_schema(
        columns=[("DADOS_EXTRAS", "STRING")],
        sample_data=[
            {"DADOS_EXTRAS": '{"tipo": "PF", "renda": 5000}'},
        ],
    )
    messages = build_enrichment_prompt(schema)
    user_msg = messages[1]["content"]
    assert "JSON estruturado" in user_msg


def test_prompt_no_separate_sample_block():
    schema = _make_schema(
        columns=[("NOME", "STRING")],
        sample_data=[{"NOME": "Alice"}],
    )
    messages = build_enrichment_prompt(schema)
    user_msg = messages[1]["content"]
    # O bloco separado de amostra foi removido
    assert "primeiras" not in user_msg
    assert "```json" not in user_msg


def test_prompt_no_hint_for_plain_text():
    schema = _make_schema(
        columns=[("DESCRICAO", "STRING")],
        sample_data=[
            {"DESCRICAO": "Escritório Central"},
            {"DESCRICAO": "Filial Norte"},
        ],
    )
    messages = build_enrichment_prompt(schema)
    user_msg = messages[1]["content"]
    assert "[HINT:" not in user_msg


def test_prompt_glossary_hint_included():
    schema = _make_schema(
        columns=[("CD_EMPRESA", "STRING")],
        sample_data=[{"CD_EMPRESA": "001"}],
    )
    messages = build_enrichment_prompt(schema, glossary={"CD_EMPRESA": "Código interno da empresa"})
    user_msg = messages[1]["content"]
    assert "Código interno da empresa" in user_msg
```

- [ ] **Step 2: Rodar os testes para confirmar falha nos novos testes**

```
pytest tests/test_prompt_builder.py -v -k "prompt"
```

Saída esperada: `test_prompt_no_separate_sample_block` passa (pois o bloco ainda existe), os outros falham ou passam parcialmente — confirme que `test_prompt_no_separate_sample_block` **falha** (ainda tem `primeiras` no prompt atual).

- [ ] **Step 3: Substituir o corpo de `build_enrichment_prompt` em `src/ai/prompt_builder.py`**

Substituir a função completa:

```python
def build_enrichment_prompt(
    schema: TableSchema,
    glossary: dict[str, str] | None = None,
) -> list[dict]:
    """
    Constrói a lista de mensagens para a API OpenRouter.

    Args:
        schema: Schema da tabela extraído do Parquet/CSV/JSON.
        glossary: Glossário de descrições de colunas conhecidas.

    Returns:
        Lista de dicts no formato OpenAI messages.
    """
    glossary = glossary or {}
    transposed = _transpose_sample(schema.sample_data)

    col_lines: list[str] = []
    for col in schema.columns:
        known_desc = glossary.get(col.name.upper(), "")
        desc_hint = f"  // Descrição conhecida: {known_desc}" if known_desc else ""

        samples = transposed.get(col.name, [])
        sample_repr = json.dumps(samples, ensure_ascii=False) if samples else "N/A"
        pattern_hint = _detect_hints(col.name, samples)

        line = (
            f"  - {col.name} ({col.type}, {'nullable' if col.nullable else 'required'}){desc_hint}\n"
            f"    Amostras: {sample_repr}"
        )
        if pattern_hint:
            line += f"\n    {pattern_hint}"

        col_lines.append(line)

    cols_str = "\n".join(col_lines)

    user_content = f"""Analise a seguinte tabela e retorne a metadata enriquecida conforme o formato solicitado.
Para cada coluna, os valores de amostra estão listados diretamente abaixo do nome da coluna.
Use-os para validar tipos, identificar padrões e inferir o significado de campos obscuros.
Siga os HINTs de pré-análise como forte evidência.

IMPORTANTE: Para cada coluna, sugira:
1. O prefixo de taxonomia mais adequado no campo "suggested_prefix"
2. A função utils.js mais adequada no campo "suggested_function"

Tabela: {schema.table_name}
Banco/Origem: {schema.db or 'desconhecido'}
Total de linhas: {schema.row_count:,}

Colunas:
{cols_str}

Retorne APENAS o JSON de metadata, sem nenhum texto adicional."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
```

- [ ] **Step 4: Rodar todos os testes**

```
pytest tests/test_prompt_builder.py -v
```

Saída esperada: todos os testes passando.

- [ ] **Step 5: Commit**

```bash
git add src/ai/prompt_builder.py tests/test_prompt_builder.py
git commit -m "feat: refactor build_enrichment_prompt to transpose sample per column and inject hints"
```

---

### Task 4: Atualizar `SYSTEM_PROMPT` com os 3 novos blocos

Adicionar instruções sobre hints, JSON estruturado e inferência por nome sem prefixo.

**Files:**
- Modify: `src/ai/prompt_builder.py`

Não há lógica nova aqui — apenas texto. Não há testes de unidade para strings de prompt, mas o teste `test_prompt_contains_column_samples` e os demais de Task 3 continuam a passar como regressão.

- [ ] **Step 1: Localizar a seção `## DADOS DE AMOSTRA` no `SYSTEM_PROMPT` e adicionar o bloco de hints logo após**

No `SYSTEM_PROMPT`, substituir:

```python
## DADOS DE AMOSTRA
Você receberá uma pequena amostra dos dados (JSON) para ajudar na identificação:
- Do tipo real dos dados (ex: se uma STRING contém JSON, DATA ou UUID)
- Do significado semântico (ex: se uma coluna 'TP' contém 'PESSOA' ou 'EMPRESA')
- De sensibilidade (ex: detectar CPFs, E-mails ou Telefones na amostra)

## PADRÃO DE PREFIXOS
```

Por:

```python
## DADOS DE AMOSTRA
Você receberá os valores de amostra de cada coluna listados diretamente abaixo do nome da coluna.
Use-os para:
- Identificar o tipo real dos dados (ex: STRING que contém JSON, DATA ou UUID)
- Inferir o significado semântico (ex: coluna 'TP' com valores 'PESSOA'/'EMPRESA' → TP prefix)
- Detectar sensibilidade e PII (CPFs, e-mails, telefones nos valores)

## HINTS DE PRÉ-ANÁLISE
Algumas colunas virão com [HINT: ...] baseados em análise automática de padrões.
Trate cada HINT como forte evidência — siga-o a menos que os valores da amostra
contradigam claramente. Nunca ignore um HINT sem justificativa nos dados.

## PADRÃO DE PREFIXOS
```

- [ ] **Step 2: Adicionar o bloco de JSON estruturado após a tabela de prefixos**

Ainda no `SYSTEM_PROMPT`, localizar o trecho que começa com `**REGRAS IMPORTANTES para suggested_prefix:**` e adicionar logo após o último ponto desta seção (antes de `{UTILS_FUNCTIONS_CATALOG}`):

```python
## COLUNAS COM JSON ESTRUTURADO
Se uma coluna STRING contiver JSON na amostra (indicado por HINT ou visível nos valores):
- Descreva o propósito do campo e mencione que armazena um objeto estruturado
- Liste os campos internos mais relevantes identificados na amostra
- Use suggested_function: "none" (JSON não passa por limpeza simples)
- Avalie sensibilidade e PII com base no conteúdo interno do JSON, não só no nome da coluna
```

- [ ] **Step 3: Adicionar inferência por nome extenso sem prefixo à seção de prefixos**

Na tabela de prefixos, após `**REGRAS IMPORTANTES para suggested_prefix:**`, adicionar:

```
- Para colunas SEM prefixo padrão: use o nome completo como âncora semântica principal.
  Exemplos: "data_nascimento" → DT + safeCastDate; "numero_documento_fiscal" → CD + removeSpecialChars
- Palavras-chave em português que indicam prefixo:
  data/dt → DT | valor/vl → VL | nome/no → NO | quantidade/qt → QT
  percentual/pc → PC | tipo/tp → TP | indicador/is/flag → IS | codigo/cd → CD
- Palavras-chave em inglês:
  date → DT | value/amount → VL | name → NO | count → QT
  percent → PC | type/status → TP | flag/is_/has_ → IS | id/code → CD
```

- [ ] **Step 4: Rodar todos os testes para confirmar que não há regressão**

```
pytest tests/ -v
```

Saída esperada: todos os testes existentes passando.

- [ ] **Step 5: Commit**

```bash
git add src/ai/prompt_builder.py
git commit -m "feat: update SYSTEM_PROMPT with hints block, JSON structured rules and prefix inference keywords"
```

---

## Checklist de auto-review

- [x] **Cobertura do spec:** transposição da amostra ✓ | `_detect_hints` com todos os 7 padrões ✓ | hint de JSON ✓ | 3 blocos no SYSTEM_PROMPT ✓ | inferência por nome sem prefixo ✓
- [x] **Placeholders:** nenhum TBD ou TODO no plano
- [x] **Consistência de tipos:** `_transpose_sample` retorna `dict[str, list]`, consumido por `_detect_hints(col.name, samples)` e `json.dumps(samples)` — todos coerentes
- [x] **Prioridade de hints:** CPF → CNPJ → Email → JSON → Bool → Monetário → Data — documentada e implementada no mesmo arquivo

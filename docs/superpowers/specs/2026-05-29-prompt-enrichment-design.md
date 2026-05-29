# Design: Melhoria do Prompt de Enriquecimento de Metadados

**Data:** 2026-05-29  
**Status:** Aprovado  
**Arquivo alvo:** `src/ai/prompt_builder.py`

## Contexto

O CLI gera arquivos SQLX para Dataform/BigQuery a partir de schemas extraídos de arquivos Parquet/CSV/JSON. Para a camada Silver, um LLM (via OpenRouter) enriquece os metadados de cada coluna com: descrição, prefixo de taxonomia, função de transformação sugerida, flag PII e nível de sensibilidade.

### Problemas identificados

O prompt atual apresenta quatro gaps relevantes:

1. A IA descreve mal colunas com nomes crípticos ou abreviados sem prefixo
2. A IA escolhe o `suggested_function` errado (ex: `cleanString` em campo de data em texto)
3. A IA não detecta PII corretamente (CPF/CNPJ/email não identificados)
4. A IA não infere o `suggested_prefix` correto para colunas sem padrão de nomenclatura

### Contexto dos dados

- Colunas chegam **sempre sem prefixo** (`CD_`, `DT_`, etc.)
- Nomes podem ser longos, em português e/ou inglês
- Tabelas de tamanho médio: 20–60 colunas
- Algumas colunas STRING podem conter **JSON estruturado** como valor

## Abordagem escolhida

**Abordagem B — Hints locais por regex + transposição da amostra por coluna.**

Combina duas melhorias independentes:
1. Transpor a amostra de "linhas" para "valores por coluna"
2. Detectar padrões óbvios com Python antes de enviar à IA e injetar hints determinísticos

## Design Detalhado

### 1. Transposição da amostra por coluna

**Comportamento atual:**  
A amostra é enviada como bloco separado de linhas completas (objetos JSON), exigindo que a IA "pivote" mentalmente para associar cada valor à sua coluna.

**Novo comportamento:**  
`build_enrichment_prompt` transpõe `schema.sample_data` (lista de dicts) em um dict `{coluna → [valores]}` e injeta os valores diretamente na listagem de cada coluna. O bloco separado de amostra JSON é removido.

**Formato resultante no user message:**

```
- HONORARIOS_ADVOCATICOS (STRING, nullable)
  Amostras: ["1.500,00", "R$ 2.000,00", "850,50", null, "3.200,00"]

- DATA_NASCIMENTO (STRING, nullable)
  Amostras: ["15/03/1985", "1990-07-22", "28/11/1972"]

- DADOS_ADICIONAIS (STRING, nullable)
  Amostras: ['{"tipo": "PF", "renda": 5000}', '{"tipo": "PJ", "cnpj": "12.345.678/0001-99"}']
  [HINT: STRING contém JSON estruturado → descrever campos internos se possível, suggested_function: none]
```

### 2. Função `_detect_hints(col_name, sample_values) -> str`

Nova função privada em `prompt_builder.py`. Analisa nome e valores da amostra e retorna uma string de hint (ou string vazia).

| Padrão | Critério | Hint gerado |
|---|---|---|
| CPF | regex `\d{3}\.?\d{3}\.?\d{3}-?\d{2}` em ≥1 valor | `[HINT: padrão CPF → PII=true, suggested_function: removeSpecialChars]` |
| CNPJ | regex `\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}` em ≥1 valor | `[HINT: padrão CNPJ → PII=true, suggested_function: removeSpecialChars]` |
| Email | regex `\S+@\S+\.\S+` em ≥1 valor | `[HINT: e-mail detectado → PII=true, suggested_function: cleanEmail]` |
| Data em texto | regex de `dd/mm/aaaa`, `aaaa-mm-dd`, `dd-mm-aaaa` em ≥1 valor | `[HINT: data em texto → suggested_function: safeCastDate]` |
| Booleano texto | todos os valores não-nulos ∈ `{sim, não, s, n, true, false, ativo, inativo, 0, 1}` | `[HINT: booleano → suggested_function: castBoolean]` |
| Monetário BRL | regex `R\$` ou padrão `\d{1,3}(\.\d{3})*,\d{2}` em ≥1 valor | `[HINT: valor monetário BRL → suggested_function: castMoneyBRL]` |
| JSON estruturado | `json.loads()` com sucesso em ≥1 valor não-nulo | `[HINT: STRING contém JSON estruturado → descrever campos internos se possível, suggested_function: none]` |

**Regra de prioridade:** CPF/CNPJ têm prioridade sobre outros padrões (um CNPJ pode parecer número mas é PII). Apenas o hint mais específico é retornado por coluna.

### 3. Novos blocos no `SYSTEM_PROMPT`

**Bloco A — Instruções sobre hints** (inserir após `## DADOS DE AMOSTRA`):

```
## HINTS DE PRÉ-ANÁLISE
Algumas colunas virão com [HINT: ...] baseados em análise automática de padrões.
Trate cada HINT como forte evidência — siga-o a menos que os valores da amostra
contradigam claramente. Nunca ignore um HINT sem justificativa nos dados.
```

**Bloco B — Colunas com JSON estruturado** (nova seção):

```
## COLUNAS COM JSON ESTRUTURADO
Se uma coluna STRING contiver JSON na amostra (indicado por HINT ou visível nos valores):
- Descreva o propósito do campo e mencione que é um objeto estruturado
- Liste os campos internos mais relevantes que conseguir identificar na amostra
- Use suggested_function: "none" (JSON não passa por transformação de limpeza simples)
- Avalie sensibilidade e PII com base no conteúdo interno do JSON, não só no nome da coluna
```

**Bloco C — Inferência por nome extenso sem prefixo** (adicionar à seção de prefixos):

```
- Para colunas SEM prefixo padrão: use o nome completo como âncora semântica principal.
  Ex: "data_nascimento" → DT + safeCastDate; "numero_documento_fiscal" → CD + removeSpecialChars
- Palavras-chave em português: data/dt→DT, valor/vl→VL, nome/no→NO,
  quantidade/qt→QT, percentual/pc→PC, tipo/tp→TP, indicador/is/flag→IS, codigo/cd→CD
- Palavras-chave em inglês: date→DT, value/amount→VL, name→NO, count→QT,
  percent→PC, type/status→TP, flag/is_/has_→IS, id/code→CD
```

## Escopo de mudanças

| Arquivo | Mudanças |
|---|---|
| `src/ai/prompt_builder.py` | Adicionar `_detect_hints()`, refatorar `build_enrichment_prompt()` para transpor amostra e injetar hints, atualizar `SYSTEM_PROMPT` com 3 novos blocos |

Nenhum outro arquivo é modificado.

## O que não muda

- Formato de saída JSON do LLM (nenhuma quebra de compatibilidade)
- `schema_extractor.py`, `openrouter_client.py`, `metadata_manager.py`, geradores
- Tamanho da amostra (continua `SAMPLE_SIZE = 5`)

## Critérios de sucesso

- Colunas com CPF/CNPJ/email na amostra → `pii=true` consistentemente
- Colunas com data em texto → `suggested_function: safeCastDate`
- Colunas com JSON estruturado → `suggested_function: none` + descrição menciona campos internos
- Colunas com nomes longos em PT/EN sem prefixo → `suggested_prefix` correto inferido do nome

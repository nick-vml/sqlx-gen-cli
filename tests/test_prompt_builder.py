from src.ai.prompt_builder import _transpose_sample, _detect_hints, build_enrichment_prompt
from src.extractor.schema_extractor import TableSchema, ColumnSchema


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


def test_transpose_sample_preserves_row_order():
    sample = [
        {"col": "primeiro"},
        {"col": "segundo"},
        {"col": "terceiro"},
    ]
    result = _transpose_sample(sample)
    assert result["col"] == ["primeiro", "segundo", "terceiro"]


# ---------------------------------------------------------------------------
# _detect_hints
# ---------------------------------------------------------------------------

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


def test_detect_hints_cnpj_sem_formatacao():
    samples = ["12345678000199"]  # 14 bare digits
    hint = _detect_hints("cnpj_cliente", samples)
    assert "CNPJ" in hint


def test_detect_hints_cpf_formato_parcial_nao_detecta():
    # garbled partial format — must NOT be detected as CPF
    samples = ["123.45678900"]  # one dot, no dash, not a valid CPF format
    hint = _detect_hints("documento", samples)
    assert "CPF" not in hint


def test_detect_hints_monetario_false_positive():
    # 4-digit number with comma — must NOT be detected as BRL monetary
    samples = ["1000,00"]
    hint = _detect_hints("algum_campo", samples)
    # 1000,00 should NOT match — it has 4 digits before comma, which breaks the pattern
    # The fix uses (?<!\d)\d{1,3} so "1000,00" should not be detected
    assert "castMoneyBRL" not in hint


# ---------------------------------------------------------------------------
# build_enrichment_prompt integration tests
# ---------------------------------------------------------------------------


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
    # The old separate sample block must be gone
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


def test_prompt_handles_datetime_sample():
    from datetime import datetime
    schema = _make_schema(
        columns=[("DT_NASCIMENTO", "TIMESTAMP")],
        sample_data=[
            {"DT_NASCIMENTO": datetime(1985, 3, 15, 10, 30)},
            {"DT_NASCIMENTO": datetime(1990, 7, 22, 0, 0)},
        ],
    )
    messages = build_enrichment_prompt(schema)
    user_msg = messages[1]["content"]
    assert "DT_NASCIMENTO" in user_msg
    assert "1985" in user_msg

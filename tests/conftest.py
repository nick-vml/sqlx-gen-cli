import pytest
from pathlib import Path


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    return tmp_path

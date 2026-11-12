import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLES = sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.py"))


@pytest.mark.parametrize("example_path", EXAMPLES, ids=[path.stem for path in EXAMPLES])
def test_example_imports_without_hardware(example_path: Path) -> None:
    module_name = f"example_{example_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, example_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

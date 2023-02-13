from pathlib import Path

from examples.golf.main import sorted_ints_app, demo
from tests.conftest import check_application_artifacts_output_stability


def test_demo() -> None:
    demo()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(
        sorted_ints_app, output_dir=Path(__file__).parent / "artifacts"
    )

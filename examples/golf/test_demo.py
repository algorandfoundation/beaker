from pathlib import Path

from tests.conftest import check_application_artifacts_output_stability

from examples.golf.main import demo, sorted_ints_app


def test_demo() -> None:
    demo()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(
        sorted_ints_app, output_dir=Path(__file__).parent / "artifacts"
    )

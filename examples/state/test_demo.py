from examples.state.main import demo
from examples.state.contract import app
from tests.conftest import check_application_artifacts_output_stability


def test_demo() -> None:
    demo()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(app, dir_per_test_file=False)

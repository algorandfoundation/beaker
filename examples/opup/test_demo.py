from tests.conftest import check_application_artifacts_output_stability

from examples.opup.contract import expensive_app
from examples.opup.main import demo


def test_demo() -> None:
    demo()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(expensive_app, dir_per_test_file=False)

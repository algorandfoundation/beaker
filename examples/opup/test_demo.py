from examples.opup.contract import expensive_app
from examples.opup.main import demo
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    check_application_artifacts_output_stability(expensive_app, dir_per_test_file=False)

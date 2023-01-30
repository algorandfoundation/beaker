from examples.golf.main import sorted_ints_app, demo
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    check_application_artifacts_output_stability(sorted_ints_app, dir_name="artifacts")

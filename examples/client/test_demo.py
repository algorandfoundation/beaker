from examples.client.main import demo, my_app
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    check_application_artifacts_output_stability(my_app, dir_per_test_file=False)

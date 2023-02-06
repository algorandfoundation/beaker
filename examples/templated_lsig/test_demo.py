from examples.templated_lsig.main import demo, app
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    check_application_artifacts_output_stability(app, dir_per_test_file=False)

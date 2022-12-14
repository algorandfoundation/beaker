from examples.templated_lsig.main import demo, App
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    app = App()
    check_application_artifacts_output_stability(app)

from examples.state.main import demo
from examples.state.contract import StateExample
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    app = StateExample()
    check_application_artifacts_output_stability(app)

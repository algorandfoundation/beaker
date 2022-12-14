from examples.state.main import demo
from examples.structure.main import Structer
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    app = Structer()
    check_application_artifacts_output_stability(app)

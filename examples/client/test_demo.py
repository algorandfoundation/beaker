from examples.client.main import demo, ClientExample
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    app = ClientExample()
    check_application_artifacts_output_stability(app)

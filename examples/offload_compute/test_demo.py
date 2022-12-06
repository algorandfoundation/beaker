from examples.offload_compute.main import demo, EthChecker
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    app = EthChecker()
    check_application_artifacts_output_stability(app)

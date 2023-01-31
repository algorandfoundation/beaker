from examples.offload_compute.main import demo, eth_checker
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    check_application_artifacts_output_stability(eth_checker)

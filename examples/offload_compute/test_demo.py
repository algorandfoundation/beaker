from tests.conftest import check_application_artifacts_output_stability

from examples.offload_compute import demo, eth_checker


def test_demo() -> None:
    demo.main()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(
        eth_checker.app, dir_per_test_file=False
    )

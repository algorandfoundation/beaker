from tests.conftest import check_application_artifacts_output_stability

from examples.opup import contract, demo


def test_demo() -> None:
    demo.main()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(contract.app, dir_per_test_file=False)

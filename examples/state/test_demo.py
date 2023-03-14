from tests.conftest import check_application_artifacts_output_stability

from examples.state import contract, main


def test_demo() -> None:
    main.demo()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(contract.app, dir_per_test_file=False)

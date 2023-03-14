from tests.conftest import check_application_artifacts_output_stability

from examples.golf import demo, sorted_integers


def test_demo() -> None:
    demo.main()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(
        sorted_integers.app, dir_per_test_file=False
    )

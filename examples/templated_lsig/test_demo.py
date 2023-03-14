from tests.conftest import check_application_artifacts_output_stability

from examples.templated_lsig import demo, sig_checker


def test_demo() -> None:
    demo.main()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(
        sig_checker.app, dir_per_test_file=False
    )

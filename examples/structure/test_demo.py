from tests.conftest import check_application_artifacts_output_stability

from examples.structure.main import demo, structer_app


def test_demo() -> None:
    demo()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(structer_app, dir_per_test_file=False)

from tests.conftest import check_application_artifacts_output_stability

from examples.structure import demo, structer


def test_demo() -> None:
    demo.main()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(structer.app, dir_per_test_file=False)

from tests.conftest import check_application_artifacts_output_stability

from examples.blueprint import app, demo


def test_demo() -> None:
    demo.main()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(
        app=app.extended_app, dir_per_test_file=False
    )

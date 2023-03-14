from tests.conftest import check_application_artifacts_output_stability

from examples.account_storage import demo, disk_hungry


def test_demo() -> None:
    demo.main()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(
        disk_hungry.app, dir_per_test_file=False
    )

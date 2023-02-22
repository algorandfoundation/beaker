from examples.account_storage.main import demo, disk_hungry
from tests.conftest import check_application_artifacts_output_stability


def test_demo() -> None:
    demo()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(disk_hungry, dir_per_test_file=False)

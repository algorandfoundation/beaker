from examples.boxen.application import app_member_app, membership_club_app
from examples.boxen.main import demo
from tests.conftest import check_application_artifacts_output_stability


def test_demo() -> None:
    demo()


def test_membership_club_output_stability() -> None:
    check_application_artifacts_output_stability(
        membership_club_app, dir_per_test_file=False
    )


def test_app_member_output_stability() -> None:
    check_application_artifacts_output_stability(
        app_member_app, dir_per_test_file=False
    )

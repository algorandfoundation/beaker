from tests.conftest import check_application_artifacts_output_stability
from examples.boxen.application import membership_club_app, app_member_app
from examples.boxen.main import demo


def test_demo():
    demo()


def test_membership_club_output_stability():
    check_application_artifacts_output_stability(
        membership_club_app, dir_per_test_file=False
    )


def test_app_member_output_stability():
    check_application_artifacts_output_stability(
        app_member_app, dir_per_test_file=False
    )

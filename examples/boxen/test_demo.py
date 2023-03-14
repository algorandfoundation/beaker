from tests.conftest import check_application_artifacts_output_stability

from examples.boxen import app_member, demo, membership_club


def test_demo() -> None:
    demo.main()


def test_membership_club_output_stability() -> None:
    check_application_artifacts_output_stability(
        membership_club.app, dir_per_test_file=False
    )


def test_app_member_output_stability() -> None:
    check_application_artifacts_output_stability(
        app_member.app, dir_per_test_file=False
    )

import pytest

from beaker import Application
from tests.conftest import check_application_artifacts_output_stability
from examples.boxen.application import MembershipClub, AppMember
from examples.boxen.main import demo


def test_demo():
    demo()


@pytest.mark.parametrize("app", [MembershipClub.construct(), AppMember.construct()])
def test_output_stability(app: Application):
    check_application_artifacts_output_stability(app, dir_per_test_file=False)

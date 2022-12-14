import pytest

from beaker import Application
from tests.conftest import check_application_artifacts_output_stability
from examples.boxen.application import MembershipClub, AppMember
from examples.boxen.main import demo


def test_demo():
    demo()


@pytest.mark.parametrize("app_class", [MembershipClub, AppMember])
def test_output_stability(app_class: type[Application]):
    app = app_class()
    check_application_artifacts_output_stability(app)

import pytest

from beaker.testing.legacy import LegacyApplication
from tests.conftest import check_application_artifacts_output_stability
from examples.boxen.application import MembershipClub, AppMember
from examples.boxen.main import demo


def test_demo():
    demo()


@pytest.mark.parametrize("app_class", [MembershipClub, AppMember])
def test_output_stability(app_class: type[LegacyApplication]):
    app = app_class()
    check_application_artifacts_output_stability(app, dir_per_test_file=False)

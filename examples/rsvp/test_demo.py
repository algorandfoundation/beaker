from tests.conftest import check_application_artifacts_output_stability

from examples.rsvp.contract import rsvp
from examples.rsvp.demo import demo


def test_demo() -> None:
    demo()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(app=rsvp, dir_per_test_file=False)

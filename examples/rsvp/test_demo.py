from examples.rsvp.demo import demo
from examples.rsvp.contract import rsvp
from tests.conftest import check_application_artifacts_output_stability


def test_demo():
    demo()


def test_output_stability():
    check_application_artifacts_output_stability(app=rsvp, dir_per_test_file=False)

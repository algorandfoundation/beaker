from .calculator import demo as calc_demo
from .counter import demo as count_demo
from .hello import demo as hello_demo


def test_calc():
    calc_demo()


def test_count():
    count_demo()


def test_hello():
    hello_demo()

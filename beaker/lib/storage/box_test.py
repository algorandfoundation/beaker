import pytest

import pyteal as pt
import beaker as bkr
from beaker.lib.storage import Box


def test_box():
    class BoxyApp(bkr.Application):
        bx = Box("mybox", 1024)

        @bkr.external
        def make_box(self):
            pass

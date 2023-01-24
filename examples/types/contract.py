import beaker as bkr
import pyteal as pt


class App(bkr.Application):
    @bkr.external
    def write_map(self):
        return pt.Seq()

    @bkr.external
    def read_map(self):
        return pt.Seq()

from .preparser import Preparser


def test_parse_exprs():
    def meth():
        x = 3
        y = 2**2
        x += 3
        x *= 3
        x /= 3

        x //= 3

        z = "ok"

        while y > 0:
            y -= 1

        for n in range(3):
            z += "no way"

        if x * y:
            return 1

        return 0

    pp = Preparser(meth)
    print(pp.as_expr())

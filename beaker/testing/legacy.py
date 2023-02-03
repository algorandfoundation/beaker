from pyteal import Global

from beaker import Application, unconditional_create_approval


class LegacyApplication(Application):

    address = Global.current_application_address()

    def __init__(self, implement_default_create: bool = True):
        super().__init__(
            name=self.__class__.__qualname__,
            descr=self.__doc__,
            state_class=self.__class__,
        )
        if implement_default_create:

            self.implement(unconditional_create_approval)
        self.post_init()

    def post_init(self) -> None:
        pass

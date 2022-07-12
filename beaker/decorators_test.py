import pytest
import pyteal as pt

from .decorators import handler, get_handler_config, Authorize

options = pt.CompileOptions(mode=pt.Mode.Application, version=pt.MAX_TEAL_VERSION)


def test_handler_config():
    @handler
    def handleable():
        pass

    hc = get_handler_config(handleable)

    assert hc.abi_method is not None, "Expected abi method to be created"
    meth = hc.abi_method.method_spec()
    assert len(meth.args) == 0, "Expected no args"
    assert meth.name == "handleable", "Expected name to match"

    config_dict = hc.__dict__
    del config_dict["abi_method"]

    for k, v in config_dict.items():
        assert v is None or v is False, f"Expected {k} to be unset"

    ###

    @handler(read_only=True)
    def handleable():
        pass

    hc = get_handler_config(handleable)

    config_dict = hc.__dict__

    assert hc.abi_method is not None, "Expected abi method to be created"
    del config_dict["abi_method"]
    assert hc.read_only == True, "Expected read_only to be true"
    del config_dict["read_only"]

    for k, v in config_dict.items():
        assert v is None or v is False, f"Expected {k} to be unset"

    ###

    @handler(authorize=Authorize.only(pt.Global.creator_address()))
    def handleable():
        pass

    hc = get_handler_config(handleable)

    config_dict = hc.__dict__

    assert hc.abi_method is not None, "Expected abi method to be created"
    del config_dict["abi_method"]
    for k, v in config_dict.items():
        assert v is None or v is False, f"Expected {k} to be unset"

    ###

    @handler(method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL))
    def handleable():
        pass

    hc = get_handler_config(handleable)

    config_dict = hc.__dict__

    assert hc.abi_method is not None, "Expected abi method to be created"
    del config_dict["abi_method"]
    assert hc.method_config is not None, "Expected method config to be set"
    assert (
        hc.method_config.opt_in == pt.CallConfig.CALL
    ), "Expected method config opt in to be set to call"
    del config_dict["method_config"]

    for k, v in config_dict.items():
        assert v is None or v is False, f"Expected {k} to be unset"


def test_authorize():
    auth_only = Authorize.only(pt.Global.creator_address())

    expr = pt.Txn.sender() == pt.Global.creator_address()
    expected = expr.__teal__(options)
    actual = auth_only.subroutine.implementation(pt.Txn.sender()).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    @handler(authorize=auth_only)
    def creator_only():
        return pt.Approve()

    expr = pt.Seq(pt.Assert(auth_only(pt.Txn.sender())), pt.Approve())

    expected = expr.__teal__(options)
    actual = creator_only().__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    with pytest.raises(pt.TealTypeError):
        Authorize.only(pt.Int(1))

    

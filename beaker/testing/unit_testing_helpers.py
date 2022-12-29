"""Module containing helper functions for testing PyTeal Utils."""
from typing import Any
from algosdk.atomic_transaction_composer import AtomicTransactionComposer

import pyteal as pt
from beaker import client, sandbox
from beaker import Application, external, delete, update, opt_in, close_out

algod_client = None
sandbox_accounts = None


def returned_int_as_bytes(i: int, bits: int = 64):
    return list(i.to_bytes(bits // 8, "big"))


class UnitTestingApp(Application):

    """Base unit testable application.

    There are 2 ways to use this class


    1) Initialize with a single Expr that returns bytes
        The bytes output from the Expr are returned from the abi method ``unit_test()[]byte``

    2) Subclass UnitTestingApp and override `unit_test`
        Any inputs or output may be specified but you're responsible for encoding the incoming
        arguments as a dict with keys matching the argument names of the custom `unit_test` method


    An instance of this class is passed to assert_output to check the return value against what you expect.
    """

    def __init__(self, expr_to_test: pt.Expr | None = None):
        self.expr = expr_to_test
        super().__init__()

    @delete
    def delete(self):
        return pt.Approve()

    @update
    def update(self):
        return pt.Approve()

    @opt_in
    def opt_in(self):
        return self.acct_state.initialize()

    @close_out
    def close_out(self):
        return pt.Approve()

    @external
    def opup(self):
        return pt.Approve()

    @external
    def unit_test(self, *, output: pt.abi.DynamicArray[pt.abi.Byte]):
        if self.expr is None:
            raise Exception(
                "Expression undefined. Either set the expr to test on init or override unit_test method"
            )
        return pt.Seq((s := pt.abi.String()).set(self.expr), output.decode(s.encode()))


def assert_output(
    app: UnitTestingApp,
    inputs: list[dict[str, Any]],
    outputs: list[Any],
    opups: int = 0,
):
    """
    Creates and calls the UnitTestingApp passed and compares the return value with the expected output

    :param app: An instance of a UnitTestingApp to make call against its `unit_test` method
    :param inputs: A list of dicts where each entry contains keys matching the input args for the `unit_test` method  and values corresponding to the type expected by the method
    :param outputs: A list of outputs to compare against the return value of the output of the `unit_test` method
    :param opups: A number of additional app call transactions to make to increase our budget

    """
    # TODO: make these avail in a pytest session context? pass them in directly?
    global algod_client, sandbox_accounts
    if algod_client is None:
        algod_client = sandbox.get_algod_client()

    if sandbox_accounts is None:
        sandbox_accounts = sandbox.get_accounts()

    app_client = client.ApplicationClient(
        algod_client, app, signer=sandbox_accounts[0].signer
    )
    app_client.create()

    has_state = app.acct_state.num_byte_slices + app.acct_state.num_uints > 0

    if has_state:
        app_client.opt_in()

    try:
        for idx, output in enumerate(outputs):
            input = {} if len(inputs) == 0 else inputs[idx]

            if opups > 0:
                atc = AtomicTransactionComposer()

                app_client.add_method_call(atc, app.unit_test, **input)
                for x in range(opups):
                    app_client.add_method_call(atc, app.opup, note=str(x).encode())

                try:
                    results = atc.execute(algod_client, 2)
                except Exception as e:
                    raise app_client.wrap_approval_exception(e)

                assert results.abi_results[0].return_value == output
            else:
                result = app_client.call(app.unit_test, **input)
                assert result.return_value == output
    except Exception as e:
        raise e
    finally:
        if has_state:
            app_client.close_out()
        app_client.delete()

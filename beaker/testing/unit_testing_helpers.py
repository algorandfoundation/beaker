"""Module containing helper functions for testing PyTeal Utils."""
from typing import Any, TypeVar
from algosdk.atomic_transaction_composer import AtomicTransactionComposer

import pyteal as pt
from beaker import client, sandbox
from beaker import Application
from beaker.application import State

algod_client = None
sandbox_accounts = None


def returned_int_as_bytes(i: int, bits: int = 64):
    return list(i.to_bytes(bits // 8, "big"))


TState = TypeVar("TState", bound=State)


class NoState(State):
    pass


def UnitTestingApp(
    state: State = NoState(), expr_to_test: pt.Expr | None = None
) -> Application:

    """Base unit testable application.

    There are 2 ways to use this class


    1) Initialize with a single Expr that returns bytes
        The bytes output from the Expr are returned from the abi method ``unit_test()[]byte``

    2) Subclass UnitTestingApp and override `unit_test`
        Any inputs or output may be specified but you're responsible for encoding the incoming
        arguments as a dict with keys matching the argument names of the custom `unit_test` method


    An instance of this class is passed to assert_output to check the return value against what you expect.
    """

    app = Application(state=state, unconditional_create_approval=False)

    @app.create
    def create() -> pt.Expr:
        return pt.Approve()

    @app.delete
    def delete() -> pt.Expr:
        return pt.Approve()

    @app.update
    def update() -> pt.Expr:
        return pt.Approve()

    @app.opt_in
    def opt_in() -> pt.Expr:
        return app.acct_state.initialize()

    @app.close_out
    def close_out() -> pt.Expr:
        return pt.Approve()

    @app.external
    def opup() -> pt.Expr:
        return pt.Approve()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        if expr_to_test is None:
            raise Exception(
                "Expression undefined. Either set the expr to test on init or override unit_test method"
            )
        return pt.Seq(
            (s := pt.abi.String()).set(expr_to_test), output.decode(s.encode())
        )

    return app


def assert_output(
    app: Application,
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

                app_client.add_method_call(atc, app.methods.unit_test, **input)
                for x in range(opups):
                    app_client.add_method_call(
                        atc, app.methods.opup, note=str(x).encode()
                    )

                results = app_client._execute_atc(atc, wait_rounds=2)

                assert results.abi_results[0].return_value == output
            else:
                result = app_client.call(app.methods.unit_test, **input)
                assert result.return_value == output
    except Exception as e:
        raise e
    finally:
        if has_state:
            app_client.close_out()
        app_client.delete()

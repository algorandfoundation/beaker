"""Module containing helper functions for testing PyTeal Utils."""
from typing import Any

import pyteal as pt
from algosdk.atomic_transaction_composer import AtomicTransactionComposer

from beaker import (
    Application,
    BuildOptions,
    client,
    sandbox,
    unconditional_create_approval,
    unconditional_opt_in_approval,
)

algod_client = None
sandbox_accounts = None


def returned_int_as_bytes(i: int, bits: int = 64) -> list[int]:
    return list(i.to_bytes(bits // 8, "big"))


def unit_test_app_blueprint(
    app: Application,
    /,
    expr_to_test: pt.Expr | None = None,
) -> Application:

    """Base unit testable application.

    There are 2 ways to use this class


    1) Initialize with a single Expr that returns bytes
        The bytes output from the Expr are returned from
        the abi method ``unit_test()[]byte``

    2) Subclass UnitTestingApp and override `unit_test`
        Any inputs or output may be specified but you're
        responsible for encoding the incoming arguments as a
        dict with keys matching the argument names of the custom `unit_test` method


    An instance of this class is passed to assert_output to check
    the return value against what you expect.
    """

    app = app.apply(unconditional_create_approval).apply(
        unconditional_opt_in_approval, initialize_local_state=True
    )

    @app.delete
    def delete() -> pt.Expr:
        return pt.Approve()

    @app.update
    def update() -> pt.Expr:
        return pt.Approve()

    @app.close_out
    def close_out() -> pt.Expr:
        return pt.Approve()

    @app.external
    def opup() -> pt.Expr:
        return pt.Approve()

    if expr_to_test is not None:
        test_expr = expr_to_test

        @app.external
        def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:

            return pt.Seq(
                (s := pt.abi.String()).set(test_expr), output.decode(s.encode())
            )

    return app


def UnitTestingApp(  # noqa: N802
    expr_to_test: pt.Expr | None = None,
    name: str = "UnitTestingApp",
    version: int = pt.MAX_PROGRAM_VERSION,
    state: Any | None = None,
) -> Application:
    return Application(
        name,
        build_options=BuildOptions(avm_version=version),
        state=state,
    ).apply(unit_test_app_blueprint, expr_to_test=expr_to_test)


def assert_output(
    app: Application,
    inputs: list[dict[str, Any]],
    outputs: list[Any],
    opups: int = 0,
) -> None:
    """
    Creates and calls the UnitTestingApp passed and compares the
    return value with the expected output

    :param app: An instance of a UnitTestingApp to make call
        against its `unit_test` method
    :param inputs: A list of dicts where each entry contains keys
        matching the input args for the `unit_test` method  and values
        corresponding to the type expected by the method
    :param outputs: A list of outputs to compare against the return
        value of the output of the `unit_test` method
    :param opups: A number of additional app call transactions to
        make to increase our budget

    """
    # TODO: make these avail in a pytest session context? pass them in directly?
    global algod_client, sandbox_accounts
    if algod_client is None:
        algod_client = sandbox.get_algod_client()

    if sandbox_accounts is None:
        sandbox_accounts = sandbox.get_accounts()

    spec = app.build(algod_client)

    try:
        spec.contract.get_method_by_name("unit_test")
    except KeyError as err:
        raise Exception(
            "Expression undefined. Either pass the expr to test or implement unit_test method"
        ) from err

    app_client = client.ApplicationClient(
        algod_client, app=spec, signer=sandbox_accounts[0].signer
    )
    app_client.create()

    has_state = (
        spec.local_state_schema.num_byte_slices or spec.local_state_schema.num_uints
    )

    if has_state:
        app_client.opt_in()

    try:
        for idx, output in enumerate(outputs):
            input = {} if len(inputs) == 0 else inputs[idx]

            if opups > 0:
                atc = AtomicTransactionComposer()

                app_client.add_method_call(atc, "unit_test", **input)
                for x in range(opups):
                    app_client.add_method_call(atc, "opup", note=str(x).encode())

                results = app_client.execute_atc(atc)

                assert results.abi_results[0].return_value == output
            else:
                result = app_client.call("unit_test", **input)
                assert result.return_value == output
    except Exception as e:
        raise e
    finally:
        if has_state:
            app_client.close_out()
        app_client.delete()

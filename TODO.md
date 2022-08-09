# TODOs

## house keeping

- [X] Install via pip

- [ ] (More) Documentation 

- [ ] (More) Unit/Integration Testing 

- [ ] Automated testing of examples

- [X] Better detection of app definition errors (cannot redeclare state keys, cannot declare over max schema)  

- [X] Use Dryrun for `read-only` methods

### Utils

- Add Blobs from pyteal-utils for Global/Local state  (https://github.com/algorand-devrel/beaker/pull/41)

- Efficient List/Map of ABI types or `Model` 

- A parameter level annotation for specifying expectations https://github.com/algorand-devrel/beaker/pull/29

    Maybe something like this where Matches returns the type but also adds some validation to the input and hints to the caller how its 
    expected to be called. Can also include a descr string

    ```py
    @external
    def pay_for_compute(
        self, 
        payment: Matches(
            abi.PaymentTransaction, 
            {**PaymentToMe , TxnField.amount: Int(const.Algos(10))}
        ),
        opup_app: Matches(
            abi.Application, 
            {Params.ApplicationId: MyApp.opup_app_id}
        ) 
    )
    ```

### Lsigs 

https://github.com/algorand-devrel/beaker/pull/33

- LSig Router based on `Args`

- LSig Template definition

- Verify hash of LSig logic (address) given input parameters and Template

### Contracts

- Trampoline - Adds method to deploy itself (w/ hook for other subroutine to call)

- Membership Token creation/validation

- Make OpUp on Public nets and hardcode it 

## features

- Add `Debug` mode using Dryrun 

- Add Box state interface (take into account that callers need to know what box names they'll need access to)

- Migration, what if the app needs to change schema at some point? Create new app with updated schema but how do users migrate to new application?

- Automated Test Harness generation? no idea how to do this, graviton + dryruns?




---------- coverage: platform linux, python 3.10.4-final-0 -----------
Name                                  Stmts   Miss  Cover   Missing
-------------------------------------------------------------------
beaker/application.py                    91      3    97%   123, 189, 196
beaker/application_test.py              215      4    98%   110, 227, 379, 388
beaker/client/application_client.py     302     57    81%   123-129, 183-187, 221-225, 259-263, 298-302, 336-340, 394-401, 403-410, 449, 452, 471, 476-486, 492, 498, 502-503, 556-563, 609, 619, 626, 653, 657, 667, 676-677, 705
beaker/client/logic_error.py             29      9    69%   11, 21-25, 44-46
beaker/contracts/op_up.py                24      2    92%   75, 87
beaker/decorators.py                    281     32    89%   77, 94, 102, 105-115, 190, 197-204, 297, 531, 535, 552, 556, 573, 577, 594, 598, 615, 619
beaker/decorators_test.py               182     15    92%   24, 43, 62, 77, 192, 196, 206, 212, 219, 226, 233, 240, 247, 254, 286
beaker/errors.py                          5      1    80%   6
beaker/lib/inline/inline_asm.py          24      1    96%   48
beaker/lib/math/math.py                  58      2    97%   81, 135
beaker/lib/math/signed_int.py            27      2    93%   13-14
beaker/lib/strings/string.py             40      2    95%   79, 120
beaker/sandbox/clients.py                10      1    90%   22
beaker/sandbox/kmd.py                    44     15    66%   41, 71-90
beaker/state.py                         230     39    83%   56, 70, 78-84, 89, 97, 102-103, 160, 176, 182, 188, 194, 202, 210, 257, 260, 263, 273, 276, 282, 285, 291, 293, 301, 303, 313, 315, 353-358, 414, 457, 468
beaker/struct.py                         53      4    92%   49-52
-------------------------------------------------------------------
TOTAL                                  2870    442    85%

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
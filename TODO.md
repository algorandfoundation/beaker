## TODOs

### house keeping

- Make it easier to install and specify deps
- Documentation
- Testing
- Better detection of type errors

### features

- Class mix-in type functionality (i.e. `class MyApp(Application, ARC18):` adds methods and global/local state requirements for ARC18)

- Provide `companion` application to be the receiver of op-up requests and trampoline-ing for funding during create

- Add box state interface (take into account that callers need to know what box names they'll need access to)

- Migration, what if the app needs to change schema at some point? Create new app with updated schema but how do users migrate to new application?

- Automated Test Harness generation? no idea how to do this, graviton + dryruns?


What else? File Issues!
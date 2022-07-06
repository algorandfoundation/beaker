## TODOs

- Make it easier to install and specify deps
- Other decorators to make method config stuff trivial, esp for bare method calls
- Documentation
- Testing
- Better detection of type errors
- Add box state interface (take into account that callers need to know what box names they'll need access to)

## Maybe TODOs

- Class mix-in type functionality (i.e. `class MyApp(Application, TokenGated):` adds token create to bootstrap && adds global schema val for the token id)
- Provide `helper` application to be the receiver of op-up requests and trampoline-ing for funding during create
- Datatypes: 
  - Map (arbitrary key=>value, how exactly?) 
  - Sorted array datatype (static types only, insertion sort)

What else?
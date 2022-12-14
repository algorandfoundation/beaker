# Contribution Guide

If you are interested in contributing to the project, we welcome and thank you. We want to make the best decentralized and effective blockchain platform available and we appreciate your willingness to help us.

## Filing Issues

Did you discover a bug? Do you have a feature request? Filing issues is an easy way anyone can contribute and helps us improve Beaker. We use GitHub Issues to track all known bugs and feature requests.

Before logging an issue be sure to check current issues, check the [open GitHub issues][issues_url] to see if your issue is described there.

If you’d like to contribute to any of the repositories, please file a [GitHub issue][issues_url] using the issues menu item. Make sure to specify whether you are describing a bug or a new enhancement using the **Bug report** or **Feature request** button.

See the GitHub help guide for more information on [filing an issue](https://help.github.com/en/articles/creating-an-issue).

## Contribution Model

Prior to contributing, an Issue should be filed to describe the bug or new feature. This helps align goals and design the solution before putting effort into the changes.  

For each of our repositories we use the same model for contributing code. Developers wanting to contribute must create pull requests. This process is described in the GitHub [Creating a pull request from a fork](https://help.github.com/en/articles/creating-a-pull-request-from-a-fork) documentation.  

With few exceptions, each pull request should be initiated against the master branch in the Beaker repository. After a pull request is submitted the core development team will review the submission and communicate with the developer using the comments sections of the PR. After the submission is reviewed and approved, it will be merged into the master branch of the source. These changes will be merged to our release branch on the next viable release date.

## Code Guidelines

We make a best-effort attempt to adhere to [PEP 8 - Style Guide for Python Code](https://www.python.org/dev/peps/pep-0008/)

A linter is run during CI to perform some basic checks.

After running `poetry install` to set up your Python virtual environment for this project, 
you will want to run (after activating the virtual environment with `poetry shell` if required) `pre-commit install`.

This will set up linting, formatting, and static analysis to run prior to any git commits you make to avoid potential issues.

### Module Guidelines

Every directory containing source code should be a Python module, meaning it should have an `__init__.py` file. This `__init__.py` file is responsible for exporting all public objects (i.e. classes, functions, and constants) for use outside of that module.

Modules may be created inside of other modules, in which case the deeper module is called a submodule or child module, and the module that contains it is called the parent module. For example, `beaker` is the parent module to `beaker.client`.

A sibling module is defined as a different child module of the parent module. For example, `beaker.client` and `beaker.testing` are sibling modules.

### Import Guidelines

#### In Runtime Code

When a runtime file in this codebase needs to import another module/file in this codebase, you should import the absolute path of the module/file, not the relative one, using the `from X import Y` method.

#### In Test Code

Test code is typically any file that ends with `_test.py` or is in the top-level `tests` folder. In
order to have a strong guarantee that we are testing in a similar environment to consumers of this
library, test code is encouraged to import _only_ the top-level Beaker module, either with
`from beaker import X, Y, Z` or `import beaker as bkr`.

This way we can be sure all objects that should be publicly exported are in fact accessible from the top-level module.

The only exception to this should be if the tests are for a non-exported object, in which case it is
necessary to import the object according to the runtime rules in the previous section.
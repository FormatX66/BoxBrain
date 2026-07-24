# Test strategy

Component tests live beside their component:

- `controller/tests/` verifies API contracts and the no-executor alpha state.
- `ui/test/` verifies the dashboard's critical operator-visible state.

Future integration tests should launch the controller with a temporary data
directory and a mock out-of-process plugin. Hardware and remote-target tests
must use a disposable, allowlisted lab target.


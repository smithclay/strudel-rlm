"""SingleInjectInterpreter — wraps PythonInterpreter to inject variables only once."""

from dspy.primitives.python_interpreter import PythonInterpreter


class SingleInjectInterpreter:
    """Thin wrapper around PythonInterpreter that injects variables only on the first execute() call.

    Pyodide state persists between calls, so re-injecting the ~14KB context string
    every iteration is wasteful and triggers loadPackagesFromImports() re-parsing.
    After the first call, we pass variables=None to skip re-injection.
    """

    def __init__(self, **kwargs):
        self._inner = PythonInterpreter(**kwargs)
        self._first_call = True

    def execute(self, code, variables=None):
        if self._first_call and variables is not None:
            self._first_call = False
            return self._inner.execute(code, variables=variables)
        return self._inner.execute(code, variables=None)

    # Proxy properties that RLM's _inject_execution_context needs
    @property
    def tools(self):
        return self._inner.tools

    @tools.setter
    def tools(self, value):
        self._inner.tools = value

    @property
    def output_fields(self):
        return self._inner.output_fields

    @output_fields.setter
    def output_fields(self, value):
        self._inner.output_fields = value

    @property
    def _tools_registered(self):
        return self._inner._tools_registered

    @_tools_registered.setter
    def _tools_registered(self, value):
        self._inner._tools_registered = value

    def start(self):
        return self._inner.start()

    def shutdown(self):
        return self._inner.shutdown()

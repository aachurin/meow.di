# meow.di
#
# Copyright (c) 2020-present Andrey Churin (aachurin@gmail.com)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import inspect
import types
import typing
from .component import Component, ReturnValue
from .exception import InjectorError


class _Callable(typing.Protocol):
    def __call__(self, **kwargs: object) -> object:  # pragma: nocover
        ...


_Step = typing.Tuple[
    _Callable, bool, typing.Dict[str, str], typing.Dict[str, object], str, bool
]


class Injector:
    allow_async = False

    def __init__(
        self,
        components: typing.Sequence[Component],
        initial: typing.Optional[typing.Mapping[str, typing.Type[object]]] = None,
        resolved: typing.Optional[typing.Mapping[object, object]] = None,
    ):
        self.components: typing.Sequence[Component] = list(components)
        self.initial: typing.Mapping[str, typing.Type[object]] = dict(initial or {})
        self.reverse_initial: typing.Mapping[typing.Type[object], str] = {
            val: key for key, val in self.initial.items()
        }
        self.resolved: typing.Dict[object, object] = dict(resolved or {})
        self.resolver_cache: typing.Dict[
            typing.Tuple[_Callable, ...], typing.List[_Step]
        ] = {}

    def resolve_function(
        self,
        func: _Callable,
        seen_state: typing.Set[str],
        output_name: typing.Optional[str] = None,
        parent_parameter: typing.Optional[inspect.Parameter] = None,
        set_return: bool = False,
    ) -> typing.List[_Step]:

        steps = []
        kwargs: typing.Dict[str, str] = {}
        consts: typing.Dict[str, object] = {}

        signature = inspect.signature(func)

        if output_name is None:
            if signature.return_annotation in self.reverse_initial:
                # some functions can override initial state
                output_name = self.reverse_initial[signature.return_annotation]
            else:
                output_name = "return_value"

        for parameter in signature.parameters.values():
            if parameter.annotation is ReturnValue:
                kwargs[parameter.name] = "return_value"
                continue

            # Check if the parameter class exists in 'initial'.
            if parameter.annotation in self.reverse_initial:
                initial_kwarg = self.reverse_initial[parameter.annotation]
                kwargs[parameter.name] = initial_kwarg
                continue

            # Check if the parameter class is already resolved.
            if parameter.annotation in self.resolved:
                consts[parameter.name] = self.resolved[parameter.annotation]
                continue

            # The 'Parameter' annotation can be used to get the parameter
            # itself. Used for example in 'Header' components that need the
            # parameter name in order to lookup a particular value.
            if parameter.annotation is inspect.Parameter:
                consts[parameter.name] = parent_parameter
                continue

            # Otherwise, find a component to resolve the parameter.
            for component in self.components:
                if component.can_handle_parameter(parameter):
                    if component.is_singleton:
                        try:
                            consts[parameter.name] = self.resolved[component]
                        except KeyError:
                            consts[parameter.name] = self.resolved[
                                component
                            ] = self.resolve_singleton(component.resolve)
                    else:
                        identity = component.identity(parameter)
                        kwargs[parameter.name] = identity
                        if identity not in seen_state:
                            seen_state.add(identity)
                            resolved_steps = self.resolve_function(
                                component.resolve,
                                seen_state,
                                output_name=identity,
                                parent_parameter=parameter,
                            )
                            steps += resolved_steps
                    break
            else:
                hint = self._get_hint(func, parameter)
                msg = f"In {hint}: no component able to handle parameter `{parameter.name}`."
                raise InjectorError(msg)

        is_async = inspect.iscoroutinefunction(func)
        if is_async and not self.allow_async:
            hint = self._get_hint(func)
            msg = f"Function {hint} may not be async."
            raise InjectorError(msg)

        steps.append((func, is_async, kwargs, consts, output_name, set_return))
        return steps

    def resolve_functions(
        self, funcs: typing.Tuple[_Callable, ...], state: typing.Mapping[str, object]
    ) -> typing.List[_Step]:
        steps = []
        seen_state = set(self.initial) | set(state)
        for func in funcs:
            func_steps = self.resolve_function(func, seen_state, set_return=True)
            steps.extend(func_steps)
        return steps

    def resolve_singleton(self, func: _Callable) -> object:
        consts = {}
        signature = inspect.signature(func)

        for parameter in signature.parameters.values():
            # Check if the parameter class is already resolved.
            if parameter.annotation in self.resolved:
                consts[parameter.name] = self.resolved[parameter.annotation]
                continue

            # Otherwise, find a component to resolve the parameter.
            for component in self.components:
                if component.is_singleton and component.can_handle_parameter(parameter):
                    try:
                        consts[parameter.name] = self.resolved[component]
                    except KeyError:
                        consts[parameter.name] = self.resolved[
                            component
                        ] = self.resolve_singleton(component.resolve)
                    break
            else:
                hint = self._get_hint(func, parameter)
                msg = f"In {hint}: no component able to handle parameter `{parameter.name}`."
                raise InjectorError(msg)

        is_async = inspect.iscoroutinefunction(func)
        if is_async and not self.allow_async:  # pragma: nocover
            hint = self._get_hint(func)
            msg = f"Function {hint} may not be async."
            raise InjectorError(msg)

        return func(**consts)

    @staticmethod
    def _get_hint(
        func: _Callable, parameter: typing.Optional[inspect.Parameter] = None
    ) -> str:  # pragma: nocover
        if isinstance(func, types.FunctionType):
            name = func.__name__
        elif isinstance(func, types.MethodType):
            name = f"{func.__self__.__class__.__name__}.{func.__func__.__name__}"
        else:
            name = str(func)
        if parameter:
            if parameter.annotation is not parameter.empty:
                if isinstance(parameter.annotation, type):
                    annotation = f": {parameter.annotation.__name__}"
                else:
                    annotation = ": {parameter.annotation!r}"
            else:
                annotation = ""
            args = f"... {parameter.name}{annotation} ..."
        else:
            args = ""
        return f"{name}({args})"

    def run(
        self, funcs: typing.Tuple[_Callable, ...], state: typing.Dict[str, object]
    ) -> object:
        if not funcs:  # pragma: nocover
            return None
        try:
            steps = self.resolver_cache[funcs]
        except KeyError:
            steps = self.resolve_functions(funcs, state)
            self.resolver_cache[funcs] = steps

        for func, is_async, kwargs, consts, output_name, set_return in steps:
            func_kwargs = {key: state[val] for key, val in kwargs.items()}
            if consts:
                func_kwargs.update(consts)
            state[output_name] = func(**func_kwargs)
            if set_return:
                state["return_value"] = state[output_name]

        # noinspection PyUnboundLocalVariable
        return state[output_name]


class AsyncInjector(Injector):  # pragma: nocover
    allow_async = True

    async def run_async(self, funcs, state):  # type: ignore
        if not funcs:
            return
        funcs = tuple(funcs)
        try:
            steps = self.resolver_cache[funcs]
        except KeyError:
            steps = self.resolve_functions(funcs, state)
            self.resolver_cache[funcs] = steps

        for func, is_async, kwargs, consts, output_name, set_return in steps:
            func_kwargs = {key: state[val] for key, val in kwargs.items()}
            func_kwargs.update(consts)
            if is_async:
                # noinspection PyUnresolvedReferences
                state[output_name] = await func(**func_kwargs)  # type: ignore
            else:
                state[output_name] = func(**func_kwargs)
            if set_return:
                state["return_value"] = state[output_name]

        # noinspection PyUnboundLocalVariable
        return state[output_name]

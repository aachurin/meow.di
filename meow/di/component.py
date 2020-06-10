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


import typing
import inspect
from .exception import InjectorError


class Component:
    is_singleton: bool = False

    def __init_subclass__(cls, singleton: typing.Optional[bool] = None):
        super().__init_subclass__()
        if singleton is not None:
            assert isinstance(singleton, bool)
            cls.is_singleton = singleton

    def identity(self, parameter: inspect.Parameter) -> str:
        """
        Each component needs a unique identifier string that we use for lookups
        from the `state` dictionary when we run the dependency injection.
        """
        parameter_name: str = parameter.name.lower()
        annotation_name: str = parameter.annotation.__name__.lower()

        # If `resolve_parameter` includes `Parameter` then we use an identifier
        # that is additionally parameterized by the parameter name.
        args = inspect.signature(self.resolve).parameters.values()
        if inspect.Parameter in [arg.annotation for arg in args]:
            return annotation_name + ":" + parameter_name

        # Standard case is to use the class name, lowercased.
        return annotation_name

    def can_handle_parameter(self, parameter: inspect.Parameter) -> bool:
        """
        Return `True` if this component can handle the given parameter.

        The default behavior is for components to handle whatever class
        is used as the return annotation by the `resolve` method.

        You can override this for more customized styles, for example if you
        wanted name-based parameter resolution, or if you want to provide
        a value for a range of different types.

        Eg. Include the `Request` instance for any parameter named `request`.
        """
        return_annotation = inspect.signature(self.resolve).return_annotation
        if return_annotation is inspect.Signature.empty:
            msg = (
                f"Component `{self.__class__.__name__}` must include a return annotation on the "
                f"`resolve()` method, or override `can_handle_parameter`."
            )
            raise InjectorError(msg)
        return parameter.annotation is return_annotation

    @typing.no_type_check
    def resolve(self):
        raise NotImplementedError()


ReturnValue = typing.NewType("ReturnValue", object)

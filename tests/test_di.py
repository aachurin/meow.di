import pytest  # type: ignore
import typing
import random
import inspect
from meow.di import Injector, Component, ReturnValue, InjectorError


RandomValue = typing.NewType("RandomValue", int)
State = typing.NewType("State", dict)
StateValue = typing.NewType("StateValue", str)


class App:
    def __init__(self, min_val: int, max_val: int):
        self.min_val = min_val
        self.max_val = max_val


class AnotherSingleton:
    pass


class AnotherSingletonComponent(Component, singleton=True):
    def resolve(self, app: App) -> AnotherSingleton:
        return AnotherSingleton()


class RandomGenerator:
    def __init__(self, min_val, max_val):
        self.min_val = min_val
        self.max_val = max_val
        self.step = 0

    def generate(self):
        ret = random.randint(self.min_val, self.max_val) + self.max_val * self.step
        self.step += 1
        return ret


class RandomGeneratorComponent(Component, singleton=True):
    def resolve(self, app: App, another: AnotherSingleton) -> RandomGenerator:
        return RandomGenerator(app.min_val, app.max_val)


class BadSingleton:
    pass


class BadSingletonComponent(Component, singleton=True):
    def resolve(self, key1: StateValue) -> BadSingleton:
        return BadSingleton()


class RandomValueComponent(Component):
    def resolve(self, generator: RandomGenerator) -> RandomValue:
        return generator.generate()


class StateValueComponent(Component):
    def resolve(self, state: State, param: inspect.Parameter) -> StateValue:
        return state[param.name]


@pytest.fixture(scope="module")
def injector():
    initial_state = {"state": State}
    resolved = {App: App(0, 100)}
    components = [
        RandomValueComponent(),
        AnotherSingletonComponent(),
        RandomGeneratorComponent(),
        StateValueComponent(),
        BadSingletonComponent(),
    ]
    return Injector(components, initial_state, resolved)


def get_state(state: State):
    return state


def another_state() -> State:
    return State({"key": "another value"})


def get_app(app: App):
    return app


def get_generator(generator: RandomGenerator):
    return generator


def get_random_value(value: RandomValue):
    return value


def update_return_value(value: RandomValue, ret: ReturnValue):
    return value - ret  # type: ignore


def get_key(key: StateValue):
    return key


def invalid_component(err: Exception):
    pass


async def async_func(key: StateValue):
    return key


def bad_singleton(obj: BadSingleton):
    pass


def new_state():
    return {"state": {"key": "value", "key2": "value2",}}


def test_error_no_component_annotation():
    initial_state = {}
    resolved = {}

    class BadComponent(Component):
        def resolve(self):
            return 42

    components = [BadComponent()]

    injector = Injector(components, initial_state, resolved)

    def some(x):
        pass

    with pytest.raises(InjectorError):
        injector.run((some,), {})


def test_component_not_resolved(injector):
    with pytest.raises(InjectorError):
        injector.run((invalid_component,), new_state())


def test_no_async(injector):
    with pytest.raises(InjectorError):
        injector.run((async_func,), new_state())


def test_bad_singleton(injector):
    with pytest.raises(InjectorError):
        injector.run((bad_singleton,), new_state())


def test_override_initial(injector):
    state = new_state()
    ret = injector.run((another_state, get_key,), state)
    assert ret == "another value"


def test_state(injector):
    state = new_state()
    assert injector.run((get_state,), state) == state["state"]


def test_initial_resolved(injector):
    state = new_state()
    assert isinstance(injector.run((get_app,), state), App)


def test_singleton(injector):
    state = new_state()
    gen1 = injector.run((get_generator,), state)
    state = new_state()
    gen2 = injector.run((get_generator,), state)
    assert gen1 is gen2


def test_injection(injector):
    state = new_state()
    ret1 = injector.run((get_random_value,), state)
    assert isinstance(ret1, int)
    state = new_state()
    ret2 = injector.run((get_random_value,), state)
    assert isinstance(ret2, int)
    assert ret1 != ret2


def test_return_value(injector):
    state = new_state()
    ret = injector.run((get_random_value, update_return_value), state)
    assert ret == 0


def test_inspect_param(injector):
    state = new_state()
    ret = injector.run((get_key,), state)
    assert ret == "value"

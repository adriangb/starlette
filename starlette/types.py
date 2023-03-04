import typing

Scope = typing.MutableMapping[str, typing.Any]
Message = typing.MutableMapping[str, typing.Any]

Receive = typing.Callable[[], typing.Awaitable[Message]]
Send = typing.Callable[[Message], typing.Awaitable[None]]

ASGIApp = typing.Callable[[Scope, Receive, Send], typing.Awaitable[None]]

StatelessLifespan = typing.Callable[[object], typing.AsyncContextManager]
StateLifespan = typing.Callable[
    [typing.Any, typing.Dict[str, typing.Any]], typing.AsyncContextManager
]
Lifespan = typing.Union[StatelessLifespan, StateLifespan]

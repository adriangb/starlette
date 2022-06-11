from contextlib import aclosing
from typing import AsyncGenerator, Protocol

from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DispatchResponse = AsyncGenerator[HTTPConnection, Response]


class SimpleDispatchFunction(Protocol):
    def __call__(self, __request: HTTPConnection) -> DispatchResponse:
        ...  # pragma: no cover


class _UnsendableResponse(Response):
    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:  # pragma: no cover
        raise NotImplementedError("You cannot evaluate this response")


class SimpleHTTPMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        dispatch: SimpleDispatchFunction,
    ) -> None:
        self._app = app
        self._dispatch = dispatch

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        conn = HTTPConnection(scope)
        async with aclosing(self._dispatch(conn)) as gen:
            scope = (await gen.__anext__()).scope

            async def wrapped_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = Headers(raw=message["headers"])
                    media_type = headers.get("Content-Type")
                    response = _UnsendableResponse(
                        status_code=message["status"],
                        headers=headers,
                        media_type=media_type,
                    )
                    try:
                        await gen.asend(response)
                    except StopAsyncIteration:
                        pass
                    else:
                        raise RuntimeError("Generator did not stop")  # pragma: no cover
                    message["status"] = response.status_code
                    if response.media_type and response.media_type != media_type:
                        response.init_headers(response.headers)
                    message["headers"] = response.headers.raw
                await send(message)

            await self._app(scope, receive, wrapped_send)

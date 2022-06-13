from contextlib import aclosing
from typing import AsyncGenerator, Optional, Protocol

from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SimpleDispatchFunction(Protocol):
    def __call__(
        self, request: HTTPConnection
    ) -> AsyncGenerator[Optional[Response], Response]:
        ...  # pragma: no cover


class _UnsendableResponse(Response):
    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:  # pragma: no cover
        raise NotImplementedError("You cannot evaluate this response")


class SimpleHTTPMiddleware:
    __slots__ = ("_app", "_dispatch")
    _dispatch: SimpleDispatchFunction

    def __init__(
        self,
        app: ASGIApp,
        dispatch: Optional[SimpleDispatchFunction] = None,
    ) -> None:
        self._app = app
        if dispatch is None:
            if self.__class__.dispatch is SimpleHTTPMiddleware.dispatch:
                raise ValueError("No dispatch function provided")
            self._dispatch = self.dispatch
        else:
            self._dispatch = dispatch

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        conn = HTTPConnection(scope)
        async with aclosing(self._dispatch(conn)) as gen:
            http_connection_or_response = await gen.__anext__()
            if http_connection_or_response is not None:  # a Response instance
                await http_connection_or_response(scope, receive, send)
                return

            async def wrapped_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = Headers(raw=message["headers"])
                    media_type = headers.get("Content-Type")
                    response: "Response" = _UnsendableResponse(
                        status_code=message["status"],
                        headers=headers,
                        media_type=media_type,
                    )
                    try:
                        await gen.asend(response)
                    except StopAsyncIteration:
                        pass
                    else:
                        raise RuntimeError("Generator did not stop")
                    message["status"] = response.status_code
                    if response.media_type and response.media_type != media_type:
                        response.init_headers(response.headers)
                    message["headers"] = response.headers.raw
                await send(message)

            await self._app(scope, receive, wrapped_send)

    def dispatch(
        self, request: HTTPConnection
    ) -> AsyncGenerator[Optional[Response], Response]:
        raise NotImplementedError(  # pragma: no cover
            "You must override this function to use it"
        )

from typing import Any, Callable

import pytest

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.simple import DispatchResponse, SimpleHTTPMiddleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket


def homepage(request: Request) -> Response:
    return PlainTextResponse("Homepage")


def exc(request: Request) -> Response:
    raise Exception("Exc")


def exc_stream(request: Request) -> Response:
    return StreamingResponse(_generate_faulty_stream())


def _generate_faulty_stream():
    yield b"Ok"
    raise Exception("Faulty Stream")


class NoResponse:
    def __init__(self, scope: Scope, receive: Receive, send: Send) -> None:
        pass

    def __await__(self) -> Any:
        return self.dispatch().__await__()

    async def dispatch(self) -> None:
        pass


async def websocket_endpoint(session: WebSocket):
    await session.accept()
    await session.send_text("Hello, world!")
    await session.close()


async def custom_middleware(request: HTTPConnection) -> DispatchResponse:
    response = yield request
    response.headers["Custom-Header"] = "Example"


app = Starlette(
    routes=[
        Route("/", endpoint=homepage),
        Route("/exc", endpoint=exc),
        Route("/exc-stream", endpoint=exc_stream),
        Route("/no-response", endpoint=NoResponse),
        WebSocketRoute("/ws", endpoint=websocket_endpoint),
    ],
    middleware=[Middleware(SimpleHTTPMiddleware, dispatch=custom_middleware)],
)


def test_custom_middleware(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    client = test_client_factory(app)
    response = client.get("/")
    assert response.headers["Custom-Header"] == "Example"

    with pytest.raises(Exception) as ctx:
        response = client.get("/exc")
    assert str(ctx.value) == "Exc"

    with pytest.raises(Exception) as ctx:
        response = client.get("/exc-stream")
    assert str(ctx.value) == "Faulty Stream"

    with pytest.raises(AssertionError):  # from TestClient
        response = client.get("/no-response")

    with client.websocket_connect("/ws") as session:
        text = session.receive_text()
        assert text == "Hello, world!"


def test_state_data_across_multiple_middlewares(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    expected_value1 = "foo"
    expected_value2 = "bar"

    async def middleware_a(request: HTTPConnection) -> DispatchResponse:
        request.state.foo = expected_value1
        yield request

    async def middleware_b(request: HTTPConnection) -> DispatchResponse:
        request.state.bar = expected_value2
        response = yield request
        response.headers["X-State-Foo"] = request.state.foo

    async def middleware_c(request: HTTPConnection) -> DispatchResponse:
        response = yield request
        response.headers["X-State-Bar"] = request.state.bar

    def homepage(request: Request) -> Response:
        return PlainTextResponse("OK")

    app = Starlette(
        routes=[Route("/", homepage)],
        middleware=[
            Middleware(SimpleHTTPMiddleware, dispatch=middleware_a),
            Middleware(SimpleHTTPMiddleware, dispatch=middleware_b),
            Middleware(SimpleHTTPMiddleware, dispatch=middleware_c),
        ],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "OK"
    assert response.headers["X-State-Foo"] == expected_value1
    assert response.headers["X-State-Bar"] == expected_value2


def test_modify_content_type(
    test_client_factory: Callable[[ASGIApp], TestClient]
) -> None:
    async def dispatch(request: HTTPConnection) -> DispatchResponse:
        resp = yield request
        resp.media_type = "text/plain"

    def homepage(request: Request) -> Response:
        return PlainTextResponse("OK")

    app = Starlette(
        routes=[Route("/", homepage)],
        middleware=[
            Middleware(SimpleHTTPMiddleware, dispatch=dispatch),
        ],
    )

    client = test_client_factory(app)
    response = client.get("/")
    assert response.text == "OK"
    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"

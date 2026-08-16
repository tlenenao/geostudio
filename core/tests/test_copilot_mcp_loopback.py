# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from app import db
from app.copilot.mcp_loopback import ALLOWED_MCP_TOOL_NAMES, McpLoopbackError, McpLoopbackSession
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    application = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    application.dependency_overrides[db.get_session] = override_session
    return application


@pytest.mark.anyio
async def test_list_tools_returns_full_catalog(app):
    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8200")
        session = McpLoopbackSession("anything", http_client=http_client)
        try:
            tools = await session.list_tools()
        finally:
            await session.aclose()
        names = {t["name"] for t in tools}
        assert ALLOWED_MCP_TOOL_NAMES <= names  # every allowlisted tool really exists server-side


@pytest.mark.anyio
async def test_call_tool_returns_text_result(app):
    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8200")
        session = McpLoopbackSession("anything", http_client=http_client)
        try:
            result = await session.call_tool("whoami", {})
        finally:
            await session.aclose()
        assert result.is_error is False
        assert "mockuser" in result.text


@pytest.mark.anyio
async def test_call_tool_surfaces_tool_execution_error_without_raising(app):
    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8200")
        session = McpLoopbackSession("anything", http_client=http_client)
        try:
            # get_item on a nonexistent id: the tool itself raises, MCP
            # reports it as a tool-level error (isError), not a protocol
            # failure — must not raise McpLoopbackError.
            result = await session.call_tool("get_item", {"itemId": "does-not-exist"})
        finally:
            await session.aclose()
        assert result.is_error is True


@pytest.mark.anyio
async def test_call_tool_surfaces_unknown_tool_name_as_tool_error(app):
    # Verified empirically against the real /mcp endpoint: an unknown tool
    # name is NOT a JSON-RPC protocol-level error in this MCP SDK version —
    # the server reports it exactly like a tool that raises (isError=true
    # inside a 200 "result", not a top-level "error" field). So call_tool
    # must not raise here either; it must surface it as ToolCallResult.
    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8200")
        session = McpLoopbackSession("anything", http_client=http_client)
        try:
            result = await session.call_tool("not_a_real_tool", {})
        finally:
            await session.aclose()
        assert result.is_error is True
        assert "not_a_real_tool" in result.text


@pytest.mark.anyio
async def test_call_tool_raises_on_genuine_protocol_level_failure(app):
    # A real protocol-level failure, distinct from the tool-level isError
    # results above: the server's DNS-rebinding Host-header guard (see
    # app/mcp/server.py — auto-enabled for localhost) rejects a request
    # bearing an unrecognized Host header with 421 before the handshake
    # even completes. This must surface as McpLoopbackError, proving
    # call_tool doesn't swallow every failure into ToolCallResult.
    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://unrecognized-host"
        )
        session = McpLoopbackSession("anything", http_client=http_client)
        try:
            with pytest.raises(McpLoopbackError):
                await session.call_tool("whoami", {})
        finally:
            await session.aclose()

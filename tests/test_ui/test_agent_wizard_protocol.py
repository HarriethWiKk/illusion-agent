""" agent 向导协议模型测试 """
from __future__ import annotations

from illusion.ui.protocol import BackendEvent, FrontendRequest


def test_agent_wizard_init_request():
    req = FrontendRequest(type="agent_wizard_init")
    assert req.type == "agent_wizard_init"


def test_agent_wizard_init_response():
    ev = BackendEvent(type="agent_wizard_init_response", tools=[{"name": "read"}], models=[{"value": "inherit"}])
    assert ev.type == "agent_wizard_init_response"
    assert ev.tools == [{"name": "read"}]
    assert ev.models == [{"value": "inherit"}]


def test_agent_generate_request():
    req = FrontendRequest(type="agent_generate_request", prompt="test runner", model="inherit", request_id="g1")
    assert req.prompt == "test runner"
    assert req.request_id == "g1"


def test_agent_generate_response():
    ev = BackendEvent(type="agent_generate_response", request_id="g1", agent={"identifier": "x", "when_to_use": "y", "system_prompt": "z"})
    assert ev.agent["identifier"] == "x"


def test_agent_wizard_submit():
    req = FrontendRequest(type="agent_wizard_submit", fields={"name": "foo"}, scope="user")
    assert req.fields == {"name": "foo"}
    assert req.scope == "user"


def test_agent_wizard_result():
    ev = BackendEvent(type="agent_wizard_result", success=True, path="/tmp/a.md")
    assert ev.success is True
    assert ev.path == "/tmp/a.md"

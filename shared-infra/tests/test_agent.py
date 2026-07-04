from spine.agent import Agent, Tool
from spine.models import FakeModelClient


def test_agent_run_returns_hello_end_to_end():
    model = FakeModelClient(reply="hello, world")
    agent = Agent(instructions="You are a friendly greeter.", model=model)

    result = agent.run("hi")

    assert result == "hello, world"
    assert model.calls, "model should have been called"
    assert "You are a friendly greeter." in model.calls[0]
    assert "User: hi" in model.calls[0]


def test_agent_prompt_lists_tools():
    def greet(name: str) -> str:
        return f"hi {name}"

    tool = Tool(name="greet", description="Greet someone by name.", fn=greet)
    model = FakeModelClient(reply="ok")
    agent = Agent(instructions="Assistant.", model=model, tools=[tool])

    agent.run("do it")

    prompt = model.calls[0]
    assert "greet: Greet someone by name." in prompt


def test_agent_can_invoke_registered_tool():
    def greet(name: str) -> str:
        return f"hi {name}"

    tool = Tool(name="greet", description="Greet.", fn=greet)
    agent = Agent(instructions="A.", model=FakeModelClient(), tools=[tool])

    assert agent.call_tool("greet", "spine") == "hi spine"
    assert agent.get_tool("greet") is tool

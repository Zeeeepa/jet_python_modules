from swarms import Agent
from swarms.structs.swarm_router import SwarmRouter

agents = [
    Agent(
        agent_name="Researcher",
        system_prompt="Answer questions briefly.",
        model_name="ollama/llama3.2",
    ),
    Agent(
        agent_name="Coder",
        system_prompt="Write small Python functions.",
        model_name="ollama/llama3.2",
    ),
]

router = SwarmRouter(
    name="multi-agent-router-demo",
    description="Routes tasks to the most suitable agent",
    agents=agents,
    swarm_type="MultiAgentRouter",
)

result = router.run("Write a function that adds two numbers")
print(result)

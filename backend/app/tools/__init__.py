"""
Tool registry: name -> Tool. The orchestrator lists these in the system prompt and looks them
up by the name the LLM writes in its JSON tool call. Adding a tool = one module + one line here.
"""
from app.tools import fitness_metrics, nutrition, user_profile, workout_schedule
from app.tools.base import Tool

TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (fitness_metrics.TOOL, nutrition.TOOL, workout_schedule.TOOL, user_profile.TOOL)
}

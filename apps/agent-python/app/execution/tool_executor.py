"""Tool execution facade."""

from app.execution.action_executor import ActionExecutor

ToolExecutor = ActionExecutor

__all__ = ["ActionExecutor", "ToolExecutor"]

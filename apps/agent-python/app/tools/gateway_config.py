import os


def use_java_tool_gateway() -> bool:
    return os.getenv("USE_JAVA_TOOL_GATEWAY", "false").lower() in {"1", "true", "yes"}

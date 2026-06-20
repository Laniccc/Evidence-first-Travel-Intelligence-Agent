from abc import ABC, abstractmethod

from app.schemas.evidence import Evidence


class BaseTravelTool(ABC):
    name: str

    @abstractmethod
    async def run(self, **kwargs) -> list[Evidence]:
        raise NotImplementedError


BaseTool = BaseTravelTool

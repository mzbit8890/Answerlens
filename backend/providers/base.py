from typing import Protocol, TypeVar

from pydantic import BaseModel

OutputModelT = TypeVar("OutputModelT", bound=BaseModel)


class StructuredOutputProvider(Protocol):
    async def generate_structured(
        self,
        prompt: str,
        response_model: type[OutputModelT],
    ) -> OutputModelT:
        """Generate and validate one application-owned Pydantic model."""
        ...

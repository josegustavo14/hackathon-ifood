from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=12, decimal_places=2),
    PlainSerializer(lambda value: format(value, ".2f"), return_type=str, when_used="json"),
]
Quantity = Annotated[Decimal, Field(gt=0), PlainSerializer(str, return_type=str, when_used="json")]

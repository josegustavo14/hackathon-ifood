from pydantic import HttpUrl, model_validator

from .common import Contract, Money, Quantity
from .ingredient import Unit


class ProductCandidate(Contract):
    id: str
    merchant_id: str
    name: str
    description: str | None = None
    price: Money
    currency: str = "BRL"
    package_quantity: Quantity | None = None
    package_unit: Unit | None = None
    available: bool
    image_url: HttpUrl | None = None
    source: str

    @model_validator(mode="after")
    def validate_package(self):
        if (self.package_quantity is None) != (self.package_unit is None):
            raise ValueError("package_quantity and package_unit must be provided together")
        if self.currency != "BRL":
            raise ValueError("currency must be BRL")
        return self

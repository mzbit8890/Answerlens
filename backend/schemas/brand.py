from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_AUDIENCES = 10
MAX_CAPABILITIES = 20
MAX_USE_CASES = 15
MAX_BRAND_CLAIMS = 30

MAX_BRAND_NAME_LENGTH = 200
MAX_CATEGORY_LENGTH = 200
MAX_AUDIENCE_LENGTH = 200
MAX_CAPABILITY_LENGTH = 300
MAX_USE_CASE_LENGTH = 300
MAX_POSITIONING_LENGTH = 2_000
MAX_CLAIM_LENGTH = 1_000

BrandName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_BRAND_NAME_LENGTH)
]
OptionalCategory = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CATEGORY_LENGTH)
]
Audience = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_AUDIENCE_LENGTH)
]
Capability = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CAPABILITY_LENGTH)
]
UseCase = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_USE_CASE_LENGTH)
]
Positioning = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_POSITIONING_LENGTH)
]
ClaimStatement = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CLAIM_LENGTH)
]


class BrandClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: ClaimStatement


class BrandProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand: BrandName
    category: OptionalCategory | None = None
    audiences: list[Audience] = Field(default_factory=list, max_length=MAX_AUDIENCES)
    capabilities: list[Capability] = Field(
        default_factory=list, max_length=MAX_CAPABILITIES
    )
    use_cases: list[UseCase] = Field(default_factory=list, max_length=MAX_USE_CASES)
    positioning: Positioning | None = None
    claims: list[BrandClaim] = Field(
        default_factory=list, max_length=MAX_BRAND_CLAIMS
    )

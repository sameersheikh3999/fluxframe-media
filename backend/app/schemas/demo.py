"""Transport contracts for the synthetic lead generator."""

from pydantic import BaseModel, ConfigDict, Field

from app.application.dto.demo import DemoQuality, DemoScenario
from app.domain.leads.enums import Industry

#: Hard ceiling enforced in the schema as well as in the service. Two layers,
#: because the schema gives a clean 422 with a readable message and the service
#: guarantees the rule holds no matter who calls it.
MAX_DEMO_BATCH = 10


class GenerateDemoLeadsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(default=5, ge=1, le=MAX_DEMO_BATCH)
    quality: DemoQuality = DemoQuality.RANDOM
    scenario: DemoScenario = DemoScenario.NORMAL_WEEK
    #: None means "draw from the realistic industry distribution".
    industry: Industry | None = None
    #: Set for a reproducible batch. Useful for demos and for debugging.
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class GeneratedLeadResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    lead_id: str
    full_name: str
    company_name: str
    email: str
    industry: str
    intended_temperature: str


class GenerateDemoLeadsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated: list[GeneratedLeadResponse]
    requested: int
    message: str

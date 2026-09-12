"""Test doubles satisfying the application's ports.

None of these inherit from anything. They are ordinary classes that happen to
have the right methods, which is all a `typing.Protocol` requires. That is the
practical payoff of choosing Protocol over ABC: a fake is a few lines, not an
inheritance ceremony — and no `unittest.mock` anywhere, so a signature change
breaks the test instead of silently passing.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.application.dto.system import DependencyState, DependencyStatus
from app.application.errors import CrmPermanentError, CrmTransientError
from app.application.ports.ai_run_recorder import AiRunRecord
from app.application.ports.crm_client import CrmContactRef, CrmContactUpsert
from app.application.ports.outbox_store import OutboxRecord
from app.application.ports.sales_brief_generator import SalesBrief, SalesBriefRequest
from app.domain.leads.activities import LeadActivity
from app.domain.leads.entities import Lead
from app.domain.shared.events import DomainEvent


class FrozenClock:
    """A clock that does not move. Satisfies ports.clock.Clock."""

    def __init__(self, instant: datetime | None = None) -> None:
        self._instant = instant or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._instant

    def advance(self, seconds: float) -> None:
        self._instant += timedelta(seconds=seconds)


class StubProbe:
    """A readiness probe with a predetermined answer."""

    def __init__(self, name: str, state: DependencyState, detail: str | None = None) -> None:
        self._status = DependencyStatus(name=name, state=state, detail=detail)

    async def check(self) -> DependencyStatus:
        return self._status


# --- in-memory repositories -------------------------------------------------


class InMemoryLeadRepository:
    def __init__(self, store: dict[UUID, Lead]) -> None:
        self._store = store
        self.staged: dict[UUID, Lead] = {}

    async def add(self, lead: Lead) -> None:
        self.staged[lead.id] = lead

    async def update(self, lead: Lead) -> None:
        self.staged[lead.id] = lead

    async def get(self, lead_id: UUID) -> Lead | None:
        return self.staged.get(lead_id) or self._store.get(lead_id)

    async def find_by_idempotency_key(self, key: str) -> Lead | None:
        for lead in list(self._store.values()) + list(self.staged.values()):
            if lead.idempotency_key == key:
                return lead
        return None

    async def count_recent_by_email(self, email: str, since_hours: int) -> int:
        return sum(1 for lead in self._store.values() if lead.contact.email == email)


class InMemoryActivityRepository:
    def __init__(self, store: list[LeadActivity]) -> None:
        self._store = store
        self.staged: list[LeadActivity] = []

    async def add(self, activity: LeadActivity) -> None:
        self.staged.append(activity)

    async def list_for_lead(self, lead_id: UUID) -> list[LeadActivity]:
        return [a for a in self._store if a.lead_id == lead_id]


class InMemoryOutboxRepository:
    def __init__(self, store: list[tuple[DomainEvent, str | None]]) -> None:
        self._store = store
        self.staged: list[tuple[DomainEvent, str | None]] = []

    async def add(self, event: DomainEvent, correlation_id: str | None = None) -> None:
        self.staged.append((event, correlation_id))


class FakeUnitOfWork:
    """An in-memory Unit of Work that really behaves like a transaction.

    This is the part that makes the outbox invariant testable without a
    database: writes go to per-transaction *staging* areas and are only merged
    into the shared stores on `commit()`. So a test can assert that a failure
    partway through leaves NOTHING behind — not a lead, not an activity, not an
    outbox event — which is precisely the guarantee the real UnitOfWork exists
    to provide.
    """

    def __init__(self) -> None:
        self.leads_store: dict[UUID, Lead] = {}
        self.activities_store: list[LeadActivity] = []
        self.outbox_store: list[tuple[DomainEvent, str | None]] = []
        self.commits = 0
        self.rollbacks = 0
        self._entered = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        self.leads = InMemoryLeadRepository(self.leads_store)
        self.activities = InMemoryActivityRepository(self.activities_store)
        self.outbox = InMemoryOutboxRepository(self.outbox_store)
        self._entered = True
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._entered:
            # Anything not committed is discarded, exactly like a rollback.
            self.rollbacks += 1
        self._entered = False

    async def commit(self) -> None:
        self.leads_store.update(self.leads.staged)
        self.activities_store.extend(self.activities.staged)
        self.outbox_store.extend(self.outbox.staged)
        self.leads.staged = {}
        self.activities.staged = []
        self.outbox.staged = []
        self.commits += 1

    async def rollback(self) -> None:
        self.leads.staged = {}
        self.activities.staged = []
        self.outbox.staged = []

    # --- assertions used by tests -----------------------------------------

    @property
    def events(self) -> list[DomainEvent]:
        return [event for event, _ in self.outbox_store]

    def event_types(self) -> list[str]:
        return [type(event).event_type for event in self.events]


# --- external service fakes -------------------------------------------------


class FakeCrmClient:
    """A CRM that records calls and can be told to fail."""

    def __init__(
        self,
        *,
        configured: bool = True,
        fail_with: Exception | None = None,
    ) -> None:
        self._configured = configured
        self._fail_with = fail_with
        self.calls: list[CrmContactUpsert] = []

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def upsert_contact(self, contact: CrmContactUpsert) -> CrmContactRef:
        self.calls.append(contact)
        if self._fail_with is not None:
            raise self._fail_with
        return CrmContactRef(contact_id=f"hs-{len(self.calls)}")


class FakeAiRunRecorder:
    def __init__(self) -> None:
        self.records: list[AiRunRecord] = []

    async def record(self, run: AiRunRecord) -> None:
        self.records.append(run)


class FakeSalesBriefGenerator:
    def __init__(self, *, configured: bool = True, fail_with: Exception | None = None) -> None:
        self._configured = configured
        self._fail_with = fail_with
        self.calls: list[SalesBriefRequest] = []

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def generate(self, request: SalesBriefRequest) -> SalesBrief:
        self.calls.append(request)
        if self._fail_with is not None:
            raise self._fail_with
        return SalesBrief(
            summary="They are opening a new clinic and have no content plan.",
            pain_points=("No content plan", "New location in six weeks"),
            urgency="high",
            suggested_service="short_form_video",
            opening_line="I hear the new clinic opens in six weeks.",
            confidence="high",
            model="fake-model",
            prompt_version="test_v1",
            latency_ms=42,
            input_tokens=100,
            output_tokens=50,
        )


class RecordingHandler:
    """An outbox handler that records deliveries and can fail on demand."""

    def __init__(self, fail_with: Exception | None = None) -> None:
        self.fail_with = fail_with
        self.handled: list[OutboxRecord] = []

    async def handle(self, record: OutboxRecord) -> None:
        self.handled.append(record)
        if self.fail_with is not None:
            raise self.fail_with


class InMemoryOutboxStore:
    """An outbox queue in a dict, for testing the dispatcher's policy."""

    def __init__(self, records: list[OutboxRecord] | None = None) -> None:
        self.pending: list[OutboxRecord] = list(records or [])
        self.processed: list[UUID] = []
        self.failed: list[tuple[UUID, str, datetime]] = []
        self.dead: list[tuple[UUID, str]] = []
        self.reclaimed = 0
        self.replayed: list[UUID] = []

    async def claim_batch(self, limit: int, now: datetime) -> list[OutboxRecord]:
        claimed, self.pending = self.pending[:limit], self.pending[limit:]
        return claimed

    async def mark_processed(self, event_id: UUID, now: datetime) -> None:
        self.processed.append(event_id)

    async def mark_failed(
        self, event_id: UUID, error: str, next_attempt_at: datetime, now: datetime
    ) -> None:
        self.failed.append((event_id, error, next_attempt_at))

    async def mark_dead(self, event_id: UUID, error: str, now: datetime) -> None:
        self.dead.append((event_id, error))

    async def reclaim_stalled(self, older_than: datetime, now: datetime) -> int:
        self.reclaimed += 1
        return 0

    async def replay(self, event_id: UUID, now: datetime) -> bool:
        self.replayed.append(event_id)
        return True


TRANSIENT = CrmTransientError("HubSpot is having a moment")
PERMANENT = CrmPermanentError("Unknown property fluxframe_industry")

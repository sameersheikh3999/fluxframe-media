# Testing strategy

227 tests. They run in about 75 seconds, on a laptop, with **no database server,
no Docker, no credentials and no network**.

That constraint is the strategy, not an accident: a test suite you can only run
with infrastructure attached is a test suite that stops being run.

## One style per layer

The layering pays off most visibly here. Each layer gets a different *kind* of
test, because each layer has different dependencies.

| Layer | Style | Needs | Where |
|---|---|---|---|
| `domain/` | pure unit | nothing at all | `tests/unit/domain/` |
| `application/` | unit + fakes | `FakeUnitOfWork`, `FrozenClock` | `tests/unit/application/` |
| `infrastructure/` HTTP | unit + `respx` | mocked httpx | `tests/unit/infrastructure/` |
| `infrastructure/` DB | integration | real SQLAlchemy, SQLite | `tests/integration/` |
| `api/` | contract | ASGI transport, no server | `tests/api/` |

### Domain — the cheapest and the most valuable

Scoring is a pure function, so testing it is just calling it:

```python
def test_classification_boundaries(score, expected):
    assert classify(score) is expected     # 49/50 and 79/80
```

No fixtures, no mocks, no setup. `test_score_is_always_clamped_into_range`
exhaustively checks every combination of all five enums — 4 × 5 × 4 × 5 × 10 =
4000 cases — and finishes in milliseconds. That is only possible because the
domain performs no I/O.

### Application — fakes, not mocks

`FakeUnitOfWork` genuinely stages and commits: writes go to per-transaction
staging areas and are merged into the shared stores only on `commit()`. So a
test can assert the *transaction semantics*, not just the happy path:

```python
async def test_nothing_is_written_when_the_transaction_never_commits(uow):
    with pytest.raises(InvalidLeadDataError):
        await service.capture_lead(make_command(first_name="   "))
    assert uow.leads_store == {}
    assert uow.outbox_store == []
```

There is no `unittest.mock` anywhere in the suite. Every double is a small real
class, so a signature change breaks the test instead of silently passing.

### Infrastructure — every failure mode, no network

`respx` intercepts httpx at the transport layer, which means the *entire*
HubSpot retry policy is verified without an account:

```python
@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
async def test_client_errors_are_permanent(status_code): ...

@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
async def test_server_and_throttle_errors_are_transient(status_code): ...
```

Same for the AI adapter, where the interesting cases are the bad ones: prose
instead of a tool call, an invented enum value, an empty pain-point list. Each
must raise rather than propagate a half-built brief — because a salesperson
would act on it.

## Why SQLite for the integration tests

Production is PostgreSQL. The integration tests run on SQLite, deliberately and
narrowly:

- The suite runs anywhere, immediately, with nothing installed.
- The ORM uses portable types with PostgreSQL variants —
  `JSON().with_variant(JSONB, "postgresql")`, `sa.Uuid()` — so the same models
  drive both.
- No SQLite-specific SQL exists anywhere in the application.

Tables are created with `Base.metadata.create_all`, not by running migrations,
because the migration targets PostgreSQL types.

### What this does NOT cover — stated, not hidden

| Not covered | Why | Covered instead by |
|---|---|---|
| `FOR UPDATE SKIP LOCKED` | SQLite ignores row locking | Rendering the migration SQL; genuinely exercised only on a real deploy |
| The partial index | SQLite syntax differs | `alembic upgrade head --sql` in CI |
| JSONB operators | Not used in queries yet | — |
| A live HubSpot round trip | Needs your token | Every response shape and failure mode, mocked |
| A live LLM call | Needs your key, costs money | Same, including malformed output |
| The form in a real browser | No E2E runner configured | The API contract; one Playwright smoke test is the obvious addition |

Knowing the boundary of your test suite is worth more than pretending it has
none.

## The architecture test

`tests/unit/test_architecture.py` imports the whole domain **in a subprocess**
and asserts no framework came with it:

```python
leaked = sorted(n for n in sys.modules if n.split(".")[0] in FORBIDDEN)
assert leaked == ""
```

Static analysis (`lint-imports`) misses an import hidden inside a function body.
A runtime check misses a branch that never executes. Both are cheap, so both run.

## Running them

```bash
cd backend
uv run pytest                  # everything
uv run pytest -m unit          # no I/O at all — the fast loop
uv run pytest -m integration   # database and ASGI
uv run pytest --lf             # re-run last failures
uv run pytest -q tests/unit/domain/test_scoring.py
```

## What a good new test looks like here

Name the behaviour, not the method. `test_a_replay_writes_no_second_outbox_event`
says what breaks if it fails; `test_capture_lead_2` does not. Several tests carry
a docstring explaining *why the behaviour matters*, which is the part that is
expensive to rediscover a year later.

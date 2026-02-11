## Golden Rules (Read This First)
- Routers never touch the DB.
- Services never return error flags.
- All permissions: router RBAC + service domain check.
- No ORM models in API responses.
- Exceptions are raised, never swallowed.
- SQLAlchemy is used in sync mode.
- Routers may be async; services remain sync-compatible.
- Do not use async ORM calls unless explicitly migrated.
- Do not cache permission-sensitive list endpoints unless user_id is in the cache key.
- Do not log request bodies, secrets, tokens, or PII.
- Conflict resolution: Golden Rules > Router Rules > Service Rules.
- Default behavior: when unsure, prefer correctness, explicit permissions, and clarity over brevity.

## Project Guidance
- Stack: FastAPI, SQLAlchemy (sync), Pydantic.
- Architecture: Router -> Service -> ORM.
- Naming: verb-first router functions; descriptive dependency names.
- DTOs: request/response schemas in `app/schema`; separate Create/Update/Response.
- Errors: raise `app/exceptions`; map in `app/api/errors.py`.
- Permissions: RBAC deps in routers + domain permission classes in services.
- Caching: use cache decorators for read paths with deterministic keys; include inputs (IDs, pagination, filters); invalidate on mutations.
- Logging: log success events only; never log request bodies, secrets, tokens, or PII.
- Responses: always return Pydantic schemas (no ORM models in API responses).
- Status codes: use FastAPI `status` constants for responses and error mappings.

## File Structure (condensed)
```
app/api/routes/v1/     # Routers
app/auth/              # Auth + RBAC dependencies
app/core/              # Config, logging, cache, permissions
app/exceptions/        # Custom exceptions
app/models/            # ORM models
app/schema/            # Pydantic schemas
app/service/           # Business logic
app/utils/enums.py     # Enums
tests/service/         # Service unit tests
```

## Router Rules
- Always wire `get_current_user` on authenticated endpoints.
- RBAC deps: `can_create/read/update/delete`, `check_permission`.
- Use Pydantic request/response models.
- Log success with `logger.info`.
- No business logic in routers.
- Use FastAPI `status` constants for response codes.
- Keep docstrings consistent: Summary, Args, Returns, Raises.
- Keep routers thin: only validation, dependencies, and calling services.
- Do not access the database directly beyond dependency wiring.

## Service Rules
- Inject `Session` in constructor.
- Use cache decorators for read paths; invalidate on mutations.
- Call domain permission classes (e.g., `ContestPermission`).
- Return Pydantic models, not ORM objects.
- Raise domain exceptions for error cases (no error flags).
- Keep services sync-compatible (no async ORM calls).
- Service methods may be async but must not use async ORM or async DB drivers.
- Perform all domain checks here (ownership, role checks, invariants).
- Keep services free of HTTP concerns (no request/response shaping).

## Docstring Format (Routers)
```text
"""
Action summary.

Short constraints or access notes (optional).

Args:
    param: description

Returns:
    description

Raises:
    ErrorType: when condition
"""
```

## Minimal Examples

### Router
```python
@router.post("/", response_model=MessageResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[can_create("contests")])
async def create_contest(
    contest: ContestCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ContestService = Depends(get_contest_service),
):
    """Create a new contest."""
    user_id = (await UserService.get_user_by_keycloak_id(db, current_user["sub"])).id
    await service.create_contest(contest, user_id)
    return MessageResponse(message="Contest created successfully")
```

### Service
```python
class ContestService:
    def __init__(self, db: Session):
        self.db = db

    @cache_get(key_builder=lambda self, contest_id: f"contest:{contest_id}", ttl=300)
    async def get_contest_by_id(self, contest_id: UUID, user_id: UUID) -> ContestResponse:
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))
        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)
        return ContestResponse.model_validate(contest)
```

## Enums
- `UserRole`, `QuestionDifficulty`, `BankPermission` in `app/utils/enums.py`.
- Inherit from `(str, enum.Enum)`; UPPERCASE for difficulty, lowercase for roles/permissions.
- Update the enums section when adding or modifying enum values.
- Use enums in models, schemas, and services for type safety.

## Testing Checklist
- One behavior per test.
- Mock DB with `MagicMock`.
- Assert outputs, not internals.
- Test success and failure paths.
- Place tests in `tests/service/test_<module>.py`.
- Use pytest fixtures for shared setup.
- Patch cache decorators in service tests to avoid Redis dependency.

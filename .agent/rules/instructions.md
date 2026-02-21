---
trigger: always_on
---

## Golden Rules (Updated)
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
- Architecture: Router -> Service -> Guard -> Validator -> Repository -> ORM.
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
tests/                 # Test suite
├── conftest.py        # Global fixtures
├── service/           # Service layer tests
│   ├── contest/       # Contest service tests
│   │   ├── conftest.py
│   │   ├── test_create_contest.py
│   │   ├── test_update_contest.py
│   │   ├── test_get_contest.py
│   │   ├── test_delete_contest.py
│   │   ├── test_publish_contest.py
│   │   └── test_manage_instructors.py
│   ├── teams/         # Team service tests
│   │   ├── conftest.py
│   │   ├── test_create_team.py
│   │   ├── test_get_team.py
│   │   ├── test_update_team.py
│   │   ├── test_add_team_members.py
│   │   └── test_remove_team_members.py
│   └── test_bank_service.py
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
from uuid import UUID
from sqlalchemy.orm import Session

from app.core.cache.decorators import cache_get
from app.core.guards.contest import ContestOperationGuard
from app.repositories.contest import ContestRepository
from app.schema.contest import ContestResponse
from app.validators.contest import ContestValidator

class ContestService:
    def __init__(
        self,
        repository: ContestRepository,
        guard: ContestOperationGuard,
        validator: ContestValidator,
    ):
        self.repository = repository
        self.guard = guard
        self.validator = validator

    @cache_get(key_builder=lambda self, contest_id: f"contest:{contest_id}", ttl=300)
    async def get_contest_by_id(self, contest_id: UUID, user_id: UUID) -> ContestResponse:
        """
        Retrieve a contest by its ID.

        Args:
            contest_id: UUID of the contest to retrieve.
            user_id: UUID of the user requesting the contest.

        Returns:
            ContestResponse: Contest details.

        Raises:
            ContestNotFoundError: If the contest does not exist.
            PermissionDeniedError: If the user lacks permission to access the contest.
        """
        contest = self.repository.get_contest_or_raise(contest_id)
        self.guard.check_read_contest(user_id=user_id, contest=contest)
        return ContestResponse.model_validate(contest)
```

## Enums
- `UserRole`, `QuestionDifficulty`, `BankPermission` in `app/utils/enums.py`.
- Inherit from `(str, enum.Enum)`; UPPERCASE for difficulty, lowercase for roles/permissions.
- Update the enums section when adding or modifying enum values.
- Use enums in models, schemas, and services for type safety.

## Repository Layer
- Encapsulate all database operations in repository classes.
- Use DTOs (Data Transfer Objects) for data transfer between layers.
- Raise domain-specific exceptions (e.g., `TeamNotFoundError`) instead of exposing raw database errors.
- Ensure repository methods are type-safe and return domain objects or DTOs.
- Avoid direct SQLAlchemy queries in services or routers.

## Guards
- Implement guards to centralize permission checks for operations.
- Validate user permissions before any state-changing operations.
- Use `TeamOperationGuard` for team-related permission checks.
- Guards should raise `PermissionDeniedError` immediately on failure.
- Ensure guards are stateless and reusable across services.

## Validators
- Centralize business rule validation in validator classes.
- Use `TeamValidator` to enforce team-specific constraints (e.g., team size, leader assignment).
- Validators should be stateless and raise domain-specific exceptions on violations.
- Perform validation before any state changes to ensure data integrity.

## Team Implementation Guidelines
- **Routes**: Keep routes thin; delegate all business logic to services.
  - Use `get_team_service` dependency to inject `TeamService`.
  - Enforce RBAC using `can_create`, `can_update`, `can_read` dependencies.
  - Use Pydantic schemas (`TeamCreate`, `TeamUpdate`, etc.) for request/response validation.
- **Services**: Orchestrate business logic by coordinating between repository, guard, and validator layers.
  - Use `TeamService` for all team-related operations.
  - Apply caching for read operations (e.g., `get_team_by_id`) with appropriate TTLs.
  - Invalidate cache on mutations (e.g., `create_team`, `update_team`).
- **Repository**: Encapsulate all database queries in `TeamRepository`.
  - Use eager loading for related entities (e.g., `ContestTeam`, `TeamUser`).
  - Provide paginated results for list endpoints.
- **Validators**: Use `TeamValidator` to enforce business rules.
  - Validate team name uniqueness, size constraints, and leader assignment.
  - Ensure validation methods are reusable and stateless.
- **Guards**: Use `TeamOperationGuard` to enforce permission checks.
  - Validate contest management permissions for team creation and updates.
  - Ensure guards are invoked before any repository or service calls.

## Testing
- Write unit tests for service layer
- Mock database interactions in service tests.
- Use fixtures to set up test data and dependencies.
- Test both success and failure paths for all operations.
- Ensure tests are isolated and do not rely on external systems.

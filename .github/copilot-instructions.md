## Golden Rules (Updated)
- Routers never touch the DB.
- Services never return error flags.
- All permissions: router RBAC + service domain check.
- No ORM models in API responses.
- Exceptions are raised, never swallowed.
- SQLAlchemy is used in sync mode.
- Routers may be async, services remain sync-compatible.
- Do not use async ORM calls unless explicitly migrated.
- Do not cache permission-sensitive list endpoints unless user_id is part of the cache key.
- Do not log request bodies, secrets, tokens, or PII.
- New or modified code must satisfy mypy type checking.

## Repository Layer
- Encapsulate all database operations in repository classes.
- Use DTOs (Data Transfer Objects) for data transfer between layers.
- Raise domain-specific exceptions (e.g., `TeamNotFoundError`) instead of exposing raw database errors.
- Ensure repository methods are type-safe and return domain objects or DTOs.
- Avoid direct SQLAlchemy queries in services or routers.
- Repositories must be persistence-only: no schema-to-ORM or DTO-to-ORM mapping logic in repository methods.

## Mapper Layer
- Centralize DTO/Schema/ORM mapping in `app/mappers` modules.
- Services should call mapper functions to:
    - build repository DTOs from request schemas,
    - build ORM entities from DTOs,
    - apply update DTO values onto ORM entities,
    - map ORM entities to response schemas.
- Keep mapper functions pure and deterministic (no DB access, no side effects).
- Prefer one mapper module per domain (e.g., `app/mappers/question.py`, `app/mappers/team.py`).

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
- Write unit tests for all layers (routes, services, repository, validators, guards).
- Mock database interactions in service tests.
- Use fixtures to set up test data and dependencies.
- Test both success and failure paths for all operations.
- Ensure tests are isolated and do not rely on external systems.

### Coding style and naming conventions
- Follow existing module naming and FastAPI patterns.
- Keep router function names verb-first (e.g., `create_contest`, `get_bank`).
- Keep dependency names descriptive (`get_db`, `get_current_user`).

### Type checking standards (mypy)
- Write explicit type annotations for new or modified public functions, methods, and class attributes.
- Avoid `Any` unless strictly required by third-party boundaries; prefer precise unions/protocols/generics.
- Keep repository, service, and schema interfaces fully typed so cross-layer DTO contracts are statically verifiable.
- Ensure Optional/nullable values are narrowed before attribute access or method calls.
- Use typed collections (`list[T]`, `dict[K, V]`, `set[T]`) and typed SQLAlchemy/Pydantic return values.
- Validate changes with mypy for affected modules, and resolve introduced type errors before considering work complete.

### Technology stack declarations and preferred libraries
- FastAPI for HTTP endpoints.
- SQLAlchemy ORM for persistence.
- Pydantic schemas in `app/schema` for request/response models.
- MinIO for storing code payloads through `CodeStorageService`.

### Architectural patterns to follow or avoid
- Keep API layer thin: routing, auth/dependency wiring, and request/response shaping.
- Move business logic to services in `app/service`.
- Avoid database access directly in routers beyond dependency wiring.
- Store large code/text payloads in object storage and persist only object keys in DB.

## CodeStorageService usage (required)

- Use `app/core/storage/code_storage.py` (`CodeStorageService`) for code payload storage.
- Do not store raw source code, template code, stdout/stderr blobs directly in DB text columns when key columns exist.
- Build deterministic object keys with `CodeStorageService.build_code_object_key(...)` in service layer.
- Upload with `CodeStorageService.upload_code(...)` before persisting key fields.
- Retrieve with `CodeStorageService.get_code(...)`/`get_code_bytes(...)` only where necessary.
- Delete with `CodeStorageService.delete_code(...)` when data is hard-deleted.
- Never log code contents or secrets; logging object keys and IDs is allowed.

### Security requirements and error handling approaches
- Enforce auth in routers using dependencies (e.g., `get_current_user`).
- Enforce fine-grained permissions at the router level using permission dependencies
	(e.g., `can_read("contests")`, `can_create("banks")`, `can_update("teams")`, `check_permission("banks", "share")`).
- Supported resources: `contests`, `banks`, `teams` with CRUD actions; `banks:share` for non-CRUD actions.
- See `app/core/keycloak_rbac_setup.md` for complete permission mappings.
- Use domain-level permission classes (e.g., `ContestPermission`) in `app/core/permissions.py`
  for resource-specific access checks (creator, admin, instructor roles). Call these in services
  to enforce business logic constraints.
- Use existing exception classes from `app/exceptions` and allow FastAPI handlers to
	surface them; do not swallow exceptions in routers.
- Raise exceptions from services; add new exception classes in `app/exceptions`
	when needed and wire them in `app/api/errors.py`.
- Choose appropriate HTTP status codes for router responses and error mappings
  (use FastAPI `status` constants).
- Do not log request bodies, secrets, tokens, or PII.

### Documentation standards
- Add docstrings for every router function describing inputs, outputs, and errors.
- Keep docstrings concise and consistent with current style in routes.

## Project structure and code examples

### File structure
```
app/
├── api/
│   ├── errors.py             # FastAPI error handlers
│   ├── route.py              # Router aggregation
│   └── routes/v1/            # API v1 endpoints (bank.py, contest.py, team.py, etc.)
├── auth/
│   └── dependencies.py       # Auth/permission dependencies
├── core/
│   ├── config.py             # Configuration
│   ├── logger.py             # Logging
│   ├── permissions.py        # Domain permission classes
│   ├── clients/              # Database and Redis clients
│   └── cache/                # Cache decorators and utilities
├── exceptions/               # Domain exceptions (auth.py, bank.py, contest.py, etc.)
├── models/                   # SQLAlchemy ORM models
├── schema/                   # Pydantic request/response models
├── service/                  # Business logic layer
└── utils/
    └── enums.py              # Application enums
tests/
└── service/                  # Service layer unit tests
```

### Router example (app/api/routes/v1/contest.py)
```python
from typing import Any, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import can_create, get_current_user
from app.core.clients.database import get_db
from app.core.logger import logger
from app.schema.contest import ContestCreate, MessageResponse
from app.service.contest_service import ContestService
from app.service.user_service import UserService

router = APIRouter()

def get_contest_service(db: Session = Depends(get_db)) -> ContestService:
    return ContestService(db)

@router.post(
    "/",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new contest",
    dependencies=[can_create("contests")],
)
async def create_contest(
    contest: ContestCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ContestService = Depends(get_contest_service),
):
    """
    Create a new contest.

    Only users with admin role can create contests.

    Args:
        contest: Contest creation data
        db: Database session
        current_user: Current authenticated user
        service: Contest service instance

    Returns:
        Success message

    Raises:
        PermissionDeniedError: If user is not admin
        UserNotFoundError: If user not found in database
    """
    keycloak_user_id = current_user["sub"]
    db_user = await UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    created_contest = await service.create_contest(contest, db_user.id)
    logger.info(f"Contest '{created_contest.name}' created by user {db_user.id}")
    return MessageResponse(message="Contest created successfully")
```

### Service example (app/service/contest_service.py)
```python
from uuid import UUID
from sqlalchemy.orm import Session

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.core.permissions import ContestPermission
from app.exceptions.contest import ContestNotFoundError
from app.models.contest import Contest
from app.schema.contest import ContestCreate, ContestResponse

class ContestService:
    """Service for contest database operations."""

    def __init__(self, db: Session):
        self.db = db

    @cache_delete(key_builder=lambda self, contest, created_by: f"contests:user:{created_by}:*")
    @cache_set(key_builder=lambda result: f"contest:{result.id}", ttl=300, from_result=True)
    async def create_contest(self, contest: ContestCreate, created_by: UUID) -> ContestResponse:
        """
        Create a new contest.

        Args:
            contest: Contest creation data
            created_by: User ID creating the contest

        Returns:
            Created contest object
        """
        db_contest = Contest(
            name=contest.name,
            description=contest.description,
            created_by=created_by,
        )
        self.db.add(db_contest)
        self.db.flush()
        self.db.refresh(db_contest)
        return ContestResponse.model_validate(db_contest)

    @cache_get(key_builder=lambda self, contest_id: f"contest:{contest_id}", ttl=300)
    async def get_contest_by_id(self, contest_id: UUID, user_id: UUID) -> ContestResponse:
        """
        Get a contest by its ID.

        Args:
            contest_id: Contest ID
            user_id: User ID requesting the contest (for permission check)

        Returns:
            Contest object

        Raises:
            ContestNotFoundError: If contest not found
        """
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))
        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)
        return ContestResponse.model_validate(contest)
```

### Schema example (app/schema/contest.py)
```python
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class ContestCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    is_public: bool = True

class ContestResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_public: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

### Model example (app/models/contest.py)
```python
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, Column, DateTime, String, Text, UUID, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import Base

class Contest(Base):
    __tablename__ = "contests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=True, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
```

### Exception example (app/exceptions/contest.py)
```python
from app.exceptions.base import BaseHTTPException

class ContestNotFoundError(BaseHTTPException):
    def __init__(self, contest_id: str):
        super().__init__(
            status_code=404,
            detail=f"Contest with ID {contest_id} not found",
            error_code="CONTEST_NOT_FOUND"
        )
```

### Permission class example (app/core/permissions.py)
```python
from uuid import UUID
from sqlalchemy.orm import Session

from app.exceptions.auth import PermissionDeniedError
from app.models.contest import Contest, ContestInstructor
from app.models.user import User
from app.utils.enums import UserRole

class ContestPermission:
    @staticmethod
    def can_manage_contest(db: Session, *, user_id: UUID, contest: Contest) -> None:
        """
        Raises PermissionDeniedError if user cannot manage contest.
        Allows creator, admin, or assigned instructors.
        """
        if contest.created_by == user_id:
            return

        is_admin = db.query(User.id).filter(
            User.id == user_id, User.role == UserRole.admin
        ).first() is not None

        if is_admin:
            return

        is_instructor = db.query(ContestInstructor).filter(
            ContestInstructor.contest_id == contest.id,
            ContestInstructor.instructor_id == user_id
        ).first() is not None

        if is_instructor:
            return

        raise PermissionDeniedError("You do not have permission to manage this contest")
```

## Router-specific instructions (current focus)
- Always include `get_current_user` as a dependency for authenticated endpoints.
- Wire fine-grained role/permission dependencies at the router level using `app.auth.dependencies`:
  - CRUD: `can_create(resource)`, `can_read(resource)`, `can_update(resource)`, `can_delete(resource)`
  - Non-CRUD: `check_permission(resource, action)` (e.g., `banks:share`)
  - Supported resources: `contests`, `banks`, `teams`
- Use `AccessControl`, `has_role`, or group wrappers (`admin_procedure`, `instructor_procedure`, `student_procedure`) for role/group checks.
- Use Pydantic request/response models from `app/schema` for all endpoints.
- Log key actions with `logger.info` after successful service calls.
- Do not perform business logic in routers; call services in `app/service`.

## Service-layer instructions (current focus)
- Place business logic in `app/service`; keep routers thin.
- Access the database via SQLAlchemy `Session` injected into service constructors.
- Use Pydantic response models from `app/schema` for service outputs.
- Apply caching via decorators in `app/core/cache/decorators.py` for read paths
  (e.g., get-by-id, get lists) and set appropriate TTLs.
- Cache keys should be deterministic and include key inputs (IDs, pagination, filters).
- Invalidate or bypass cache when data mutates (create/update/delete).
- Raise existing domain exceptions from `app/exceptions` for error cases.
- Create new exception classes in `app/exceptions` when needed and register them
	in `app/api/errors.py`.
- Log notable state changes with `logger.info` after successful operations.

## Domain Permission Classes (app/core/permissions.py)

Domain permission classes handle resource-specific access control at the service level.
These complement router-level RBAC dependencies and enforce business logic constraints.

- **ContestPermission**: Manages who can access and manage contests.
  - `can_manage_contest(db, user_id, contest)`: Allows creator, admin, or assigned instructors.
  - Call this in service methods before modifying contest state (update, delete, assign instructors).
  - Raises `PermissionDeniedError` if access is denied.
- Create new permission classes for other resources as needed (e.g., `BankPermission`, `TeamPermission`).
- Keep permission logic isolated; avoid mixing with business logic.

## DTO/Schema-layer instructions (current focus)
- Define request and response schemas in `app/schema` for each resource.
- Create separate request (e.g., `BankCreate`, `BankUpdate`) and response models (e.g., `BankResponse`).
- Reuse schemas only when semantically identical; prefer separate models for clarity.
- Never expose SQLAlchemy models directly in routers; always return Pydantic response models.
- Use `model_validate()` to convert ORM models to Pydantic schemas.
- Include all necessary fields in response models; exclude secrets and internal IDs from public schemas.
- Use `ConfigDict(from_attributes=True)` to enable ORM mode for seamless conversion.

## Enums (app/utils/enums.py)

### Current enums
- `UserRole`: student, instructor, admin, manager
- `QuestionDifficulty`: EASY, MEDIUM, HARD
- `BankPermission`: read, edit, owner

### Enum guidelines
- Store all application enums in `app/utils/enums.py`.
- Inherit from `(str, enum.Enum)` for string-based enums (seamless JSON serialization).
- Use UPPERCASE values for difficulty levels; use lowercase for roles and permissions.
- Use enums in model fields, schemas, and service logic for type safety.
- Add new enums when introducing new domain concepts (e.g., new permission types, status fields).
- Update this section when adding or modifying enums.

## Testing instructions

### Test checklist
- [ ] One behavior per test
- [ ] Mock DB (no real DB)
- [ ] Assert outputs, not internals
- [ ] Test both success and failure paths

### Test organization
- Place all tests in `tests/` directory with subdirectories matching app structure (e.g., `tests/service/`).
- Test files follow naming convention: `test_<module>.py` (e.g., `test_contest_service.py`).
- Test functions are prefixed with `test_` and describe what is being tested.
- Use `@pytest.mark.asyncio` for async test functions.

### Test fixtures and setup
- Use pytest fixtures for common setup (mock DB, services, sample data).
- Mock external dependencies using `unittest.mock.MagicMock` with `spec=Session` for DB sessions.
- Create mock model classes (e.g., `MockContest`, `MockBank`) to simulate ORM objects.
- Patch cache decorators (`cache_get`, `cache_set`, `cache_delete`) in service fixtures to avoid Redis connection issues.
- Import service classes inside fixtures using `TYPE_CHECKING` guard for type hints without circular imports.

### Test characteristics
- Test one thing per test function; keep tests focused and readable.
- Test both success cases (happy path) and error cases (exceptions, edge cases).
- Use descriptive docstrings for test functions explaining what is being tested.
- Mock database interactions; do not use real databases in unit tests.
- Assert on return values, exception types, and method call counts/arguments using `mock.assert_called_with()`.
- Test exception handling by catching expected exceptions from `app/exceptions`.

### Mocking best practices
- Use `side_effect` to simulate complex behaviors (e.g., DB refresh updating instance state).
- Mock `.filter()`, `.first()`, `.all()` chains for query builders.
- Keep mocks minimal; only mock what is necessary to isolate the unit under test.
- Do not verify internal implementation details; focus on inputs and outputs.

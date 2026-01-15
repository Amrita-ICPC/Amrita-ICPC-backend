# Authentication & RBAC Documentation

This module handles authentication using Keycloak (OIDC) and implements Role-Based Access Control (RBAC).

## Keycloak Configuration

To make this authentication module work, you need to configure Keycloak correctly.

### 1. Realm Setup
-   Create a new Realm (e.g., `amrita-icpc`) or use `master`.
-   Update `KEYCLOAK_REALM` in `.env`.

### 2. Client Setup
1.  **Create Client**:
    -   **Client ID**: `amrita-icpc-backend` (Update `KEYCLOAK_CLIENT_ID` in `.env`).
    -   **Client Protocol**: `openid-connect`.

2.  **Capability config**:
    -   **Client authentication**: `On` (if using confidential access type) or `Off` (if public). *Recommended: On* (confidential) for backend services.
    -   **Authorization**: `Off` (unless you want detailed Keycloak-managed authorization policies).
    -   **Authentication Flow**:
        -   `Standard Flow` (Authorization Code Flow): **ON** (For normal user login via browser).
        -   `Direct Access Grants` (Resource Owner Password Credentials): **OFF** (Recommended for security, unless testing via simple scripts).
        -   `Implicit Flow`: **OFF**.
        -   `Service Accounts Roles`: **ON** (If you have backend-to-backend communication needs).
        -   `OAuth 2.0 Device Authorization Grant`: **OFF** (Unless targeting devices with no input).

3.  **Access Settings**:
    -   **Root URL**: `http://localhost:8000` (or your frontend URL).
    -   **Valid Redirect URIs**: `http://localhost:8000/*` (Where Keycloak returns the code).
    -   **Web Origins**: `+` (or specific frontend origins to allow CORS).
    -   **Admin URL**: `http://localhost:8000`.

4.  **Credentials (If Client Auth is On)**:
    -   Go to **Credentials** tab.
    -   Copy the **Client Secret** and put it in `.env` as `KEYCLOAK_CLIENT_SECRET`.

### 3. Roles Configuration
-   Go to **Realm Roles** (or Client Roles) and define your roles:
    -   `admin`
    -   `student`
    -   `contestant`
-   Assign these roles to your users.

### 4. Token Mappers (Crucial for RBAC)
The `RoleChecker` dependency expects roles to be present in the JWT token.
By default, Keycloak puts realm roles in `realm_access.roles`.

-   Ensure your client has mappers to include Realm Roles in the ID Token and Access Token.
-   If you use Client Roles, ensure they are mapped to `resource_access.{client_id}.roles`.
-   **Verification**: Decode a test token at [jwt.io](https://jwt.io) and ensure you see a structure like:
    ```json
    {
      "realm_access": {
        "roles": ["admin", "student", ...]
      },
      ...
    }
    ```

## Usage

### Dependencies

We provide two main dependencies in `app.auth.dependencies`:

1.  `get_current_user`: Validates the Bearer token and returns the decoded payload.
2.  `RoleChecker`: Validates that the user has specific roles.

### Protected vs Unprotected Routes

#### Unprotected Route
Routes that do not require valid credentials (e.g., Health check, Login, Docs).

```python
@router.get("/public")
def public_endpoint():
    return {"message": "Anyone can see this"}
```

#### Protected Route (Authentication Only)
Routes that require a valid User but no specific role.

```python
from fastapi import Depends
from app.auth.dependencies import get_current_user

@router.get("/profile")
def user_profile(user: dict = Depends(get_current_user)):
    return {"user": user["preferred_username"], "email": user["email"]}
```

### Advanced RBAC Usage

We provide convenient wrappers in `app.auth.dependencies` that correspond to your system's roles and permissions.

#### 1. Procedure-based Access
Use these for endpoints specific to a user group.

```python
from app.auth.dependencies import admin_procedure, instructor_procedure

@router.get("/admin-dashboard", dependencies=[admin_procedure])
def admin_dashboard():
    return {"data": "Admin secrets"}

@router.post("/course", dependencies=[instructor_procedure])
def create_course():
    ...
```

#### 2. Permission-based Access
Use these for resource-specific actions. The system checks for roles like `resource:action`, `resource:*`, or `admin`.

```python
from app.auth.dependencies import can_create, can_read

@router.post("/teams", dependencies=[can_create("teams")])
def create_team():
    ...

@router.get("/teams/{id}", dependencies=[can_read("teams")])
def get_team(id: str):
    ...
```

#### 3. Router-Level Security
You can secure an entire set of routes by applying dependencies at the Router level.

```python
from fastapi import APIRouter
from app.auth.dependencies import admin_procedure

# All routes in this router require admin access
admin_router = APIRouter(dependencies=[admin_procedure])

@admin_router.get("/users")
def list_users(): ...

@admin_router.delete("/users/{id}")
def delete_user(): ...

# Or when including the router
# app.include_router(admin_router, prefix="/admin", dependencies=[admin_procedure])
```

### Keycloak Configuration for Groups
To use `admin_procedure` (which checks for "admin" group), ensure your Keycloak token includes group membership.

1.  In Keycloak, go to **Client Scopes**.
2.  Create a new scope or generic **Mappers**.
3.  Add **Group Membership** mapper.
4.  Token Claim Name: `groups`.
5.  Add to ID Token and Access Token.

## Error Handling

-   **401 Unauthorized**: Token is missing, invalid, or expired.
-   **403 Forbidden**: User is authenticated but lacks the required role.

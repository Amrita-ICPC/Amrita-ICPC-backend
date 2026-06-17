# Keycloak RBAC & Fine-Grained Access Configuration

This document outlines the fine-grained client roles and Role-Based Access Control (RBAC) setup defined in Keycloak for the `amrita-icpc-backend` client scope.

---

## 1. User Groups

The realm defines four primary groups corresponding to system roles:

*   **`/admin`**: System administrators. Holds all fine-grained client roles.
*   **`/instructor`**: Teachers and coordinators. Holds management permissions for contests, questions, and teams.
*   **`/student`**: Contest participants. Holds basic permissions to read contests/questions and manage teams.
*   **`/manager`**: High-level organizational managers.

---

## 2. Fine-Grained Client Roles

The client ID `icpc-backend` maps the following client roles to protected API endpoints and services:

### Contests
*   `contests:create` — Allows creating draft contests.
*   `contests:read` — Allows viewing contest details.
*   `contests:update` — Allows updating contest settings and metadata.
*   `contests:delete` — Allows deleting/soft-deleting contests.
*   `contests:publish` — Allows publishing a contest to make it live.
*   `contests:cancel` — Allows cancelling a contest.
*   `contests:manage_instructors` — Allows adding/removing instructors on a contest.
*   `contests:instructors:read` — Allows viewing assigned instructors list.

### Contest Questions
*   `contests:questions:create` — Allows adding/linking questions to a contest.
*   `contests:questions:read` — Allows reading questions assigned to a contest.
*   `contests:questions:update` — Allows updating question details/templates/testcases within a contest.
*   `contests:questions:delete` — Allows unlinking/removing questions from a contest.

### Teams
*   `teams:create` — Allows creating a new contest team.
*   `teams:read` — Allows viewing teams and team standings.
*   `teams:update` — Allows updating team name, members, and approval status.
*   `teams:delete` — Allows deleting/withdrawing a team.

### Question Banks
*   `banks:create` — Allows creating new question banks.
*   `banks:read` — Allows viewing available question banks.
*   `banks:update` — Allows updating question bank configurations.
*   `banks:delete` — Allows deleting question banks.
*   `banks:share` — Allows sharing question banks with other users.

### Bank Questions
*   `banks:questions:create` — Allows creating questions inside a question bank.
*   `banks:questions:read` — Allows reading questions in a question bank.
*   `banks:questions:update` — Allows updating questions in a question bank.
*   `banks:questions:delete` — Allows deleting questions from a question bank.

### Audiences
*   `audiences:create` — Allows creating audience targets (e.g. batch, class).
*   `audiences:read` — Allows reading audience details.
*   `audiences:update` — Allows updating audience mappings.
*   `audiences:delete` — Allows deleting audience scopes.

### Global Questions
*   `questions:create` — Allows creating global questions.
*   `questions:read` — Allows viewing global questions.
*   `questions:update` — Allows updating global questions.
*   `questions:delete` — Allows deleting global questions.

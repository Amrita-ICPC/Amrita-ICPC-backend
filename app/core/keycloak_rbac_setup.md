# Keycloak RBAC Setup

This document outlines the Role-Based Access Control (RBAC) setup for the application using Keycloak.

## Groups

The following groups are defined in the realm:

1.  **admin**
2.  **student**
3.  **instructor**
4.  **manager**

## Client Roles

The client roles defined for managing contests are:

*   `contests:read` - Allows viewing contests.
*   `contests:update` - Allows updating contest details.
*   `contests:delete` - Allows deleting contests.
*   `contests:create` - Allows creating new contests.

The client roles defined for managing banks are:

*   `banks:read` - Allows reading banks.
*   `banks:update` - Allows updating banks.
*   `banks:delete` - Allows deleting banks.
*   `banks:create` - Allows creating banks.
*   `banks:share` - Allows sharing banks.

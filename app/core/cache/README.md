# Caching Module Documentation

This directory contains the caching implementation for the application, leveraging Redis for storage. It provides a set of decorators to easily cache function results, invalidate cache entries, and explicitly update cache keys.

## Components

- **`decorators.py`**: Contains the core decorators (`@cache_get`, `@cache_delete`, `@cache_set`) and helper functions for type handling.
- **`serialize.py`**: Provides basic JSON serialization and deserialization utilities (`serialize`, `deserialize`).

---

## 1. `@cache_get`

**Purpose**: Caches the result of an asynchronous function. If the key exists in Redis, the cached value is returned. Otherwise, the function is executed, and its result is stored in Redis.

### Key Features
- **Automatic Serialization**: 
  - If the decorated function has a return type annotation (e.g., `-> UserResponse`), it uses Pydantic's `TypeAdapter` to validate and serialize/deserialize the data.
  - If no return type is present (or `None`), it falls back to the default `serialize`/`deserialize` functions (using standard JSON).
- **TTL (Time To Live)**: Configurable expiration time for cache keys.
- **Graceful Failures**: If Redis is unavailable or fails, it logs the error and executes the function normally (returning the fresh result).

### Usage

```python
from app.core.cache.decorators import cache_get

@cache_get(key_builder=lambda user_id: f"user:{user_id}", ttl=600)
async def get_user(user_id: str) -> UserResponse:
    # ... expensive database call ...
    return user
```

### Parameters
- `key_builder` (`Callable[..., str]`): Function that generates a unique cache key based on the arguments of the decorated function.
- `ttl` (`int`, default=300): Time in seconds for the cache entry to live.

---

## 2. `@cache_delete`

**Purpose**: Invalidates (deletes) cache entries after the decorated function executes successfully. This is crucial for maintaining data consistency after updates or deletions.

### Capabilities

1.  **Single Key Invalidation**: Delete a specific cache entry.
2.  **Bulk Invalidation**: Delete multiple specific cache entries at once.
3.  **Pattern Matching (Wildcards)**: Invalidate a group of keys that match a specific pattern (e.g., all data for a specific user).

### Usage

#### 1. Deleting Specific Keys
The `key_builder` can return a single string or a list of strings. These exact keys will be deleted.

```python
from app.core.cache.decorators import cache_delete

# Use lambda to return list of keys to delete
@cache_delete(key_builder=lambda user_id, **_: [f"user:{user_id}", f"user_profile:{user_id}"])
async def update_user(user_id: str, data: dict):
    # ... update logic ...
    pass
```

#### 2. Pattern Matching (Wildcards)
The decorator supports Redis glob-style patterns. If a key contains `*`, it is treated as a pattern.

**Safe & Efficient Deletion**:
When a pattern is detected, the decorator uses the Redis **`SCAN`** command (not `KEYS`) to safely iterate through the database and delete matches. This prevents blocking the Redis server, making it safe for production use even with large datasets.

**Common Patterns**:
- `prefix:*` (e.g., `contest:123:*`): Deletes all keys starting with the prefix.
- `*:suffix` (e.g., `*:settings`): Deletes all keys ending with the suffix.

```python
# Use lambda with wildcards to invalidate patterns
@cache_delete(key_builder=lambda contest_id: [f"contest:{contest_id}:*"])
async def delete_contest(contest_id: str):
    # ... delete logic ...
    pass
```

### Parameters
- `key_builder` (`Callable[..., str | list[str]]`): A function that takes the same arguments as the decorated function and returns:
    - A `str` for a single key.
    - A `list[str]` for multiple keys.
    - Any string containing `*` will trigger pattern matching logic.

---

## 3. `@cache_set`

**Purpose**: Explicitly updates or sets a cache entry after the function executes. This is useful for "write-through" caching where you want to keep the cache fresh immediately after a write operation.

### Key Features
- **Result-Based Keys**: Can generate the cache key based on the *result* of the function rather than its arguments (using `from_result=True`).
- **Serialization**: Similar to `@cache_get`, it respects Pydantic models for serialization if type hints are present.

### Usage

```python
from app.core.cache.decorators import cache_set

@cache_set(
    key_builder=lambda user: f"user:{user.id}", 
    ttl=600, 
    from_result=True
)
async def create_user(data: CreateUserRequest) -> UserResponse:
    # ... create user in db ...
    return new_user
```

### Parameters
- `key_builder` (`Callable[..., str]`): Function to generate the cache key.
- `ttl` (`int`, default=300): Expiration time for the new cache entry.
- `from_result` (`bool`, default=False): 
  - If `True`, `key_builder` is called with the *return value* of the function.
  - If `False`, `key_builder` is called with the *arguments* of the function.

---

## Implementation Details

### Serialization Logic
The decorators check `func.__annotations__.get("return")`.
1. **Pydantic Models**: If the return type is a valid Pydantic type, `TypeAdapter(return_type)` is created. 
   - Uses `adapter.validate_json(cached_data)` for deserialization.
   - Uses `adapter.dump_json(result)` for serialization.
2. **Fallback**: If no type is found or `TypeAdapter` fails, it uses `app.core.cache.serialize`.
   - `json.dumps(data, default=str)` for serialization.
   - `json.loads(data)` for deserialization.

### Error Handling
All Redis operations are wrapped in `try/except` blocks to ensure that cache failures do not crash the application. Errors are logged to the application logger.

### Configuration
Caching is efficiently gated by `config.CACHE_ENABLED`. If disabled, decorators simply execute the underlying function without any Redis overhead.

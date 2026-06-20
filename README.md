# Amrita ICPC Coding Platform - Backend

Backend service for the Amrita ICPC Coding Platform, built with FastAPI and SQLAlchemy.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) (for Python package and environment management)
- [Docker](https://www.docker.com/) & Docker Compose (for Database and Redis)

## Setup & Installation

1.  **Clone the repository**

    ```bash
    git clone <repository_url>
    cd Amrita-ICPC-backend
    ```

2.  **Environment Setup**

    Create the virtual environment and install dependencies using `uv`:

    ```bash
    uv sync
    ```

3.  **Configuration**

    Copy the example environment file and configure it:

    ```bash
    cp .env.example .env
    ```

    Update `.env` with your specific configurations if needed. By default, it is configured to work with the provided Docker Compose setup.

## Running the Application

1.  **Start Infrastructure Services**

    Start PostgreSQL and Redis using Docker Compose:

    ```bash
    docker-compose up -d
    ```

2.  **Run the Backend Server**

    Start the FastAPI application:

    ```bash
    uv run -m app.main
    ```

    The API will be available at `http://localhost:8000`.
    API Documentation (Swagger UI) is available at `http://localhost:8000/docs`.

3.  **Run the Evaluation Worker**

    Submission evaluation is split into stages (SUBMIT, POLL, PERSIST — see
    `worker/`), each on its own Celery queue. **Celery Beat must be running** or
    results are never collected: SUBMIT only pushes Judge0 tokens into Redis,
    and only the Beat-scheduled poller (`worker.poller.poll_pending_evaluations`)
    triggers PERSIST, which is the only place `SubmissionTestCase` rows get
    written. A plain `celery worker` with no `-Q` only consumes the default
    `student_submit` queue and no Beat — submissions will appear to do nothing.

    For local development, run one worker that consumes every queue with an
    embedded Beat scheduler (`-B`):

    ```bash
    uv run celery -A app.core.clients.celery:celery_app worker \
      --loglevel=info \
      -Q student_submit,bulk_contest_evaluation,poller,persist \
      -B \
      --concurrency=4
    ```

    In production, run the 4 roles as separate processes instead (see
    `docker-compose.yml`: `celery_worker_student`, `celery_worker_bulk`,
    `celery_worker_poller`, `celery_beat`) so bulk re-evaluation never starves
    live student submissions, and `-B` is never embedded in more than one
    process (a duplicated Beat schedules everything twice).

## Database Migrations

This project uses Alembic for database migrations.

-   **Generate a new migration** (after modifying models):
    ```bash
    uv run alembic revision --autogenerate -m "Description of changes"
    ```

-   **Apply migrations**:
    ```bash
    uv run alembic upgrade head
    ```

## Testing

To run the unit tests, use the following command:

```bash
uv run pytest
```

## Development

-   **Development Mode**: In development environment (default), the application automatically checks and creates tables on startup if they don't exist.
-   **Code Structure**:
    -   `app/main.py`: Application entry point.
    -   `app/core/`: Configuration and core utilities.
    -   `app/models/`: SQLAlchemy database models.
    -   `app/api/`: API route handlers (to be implemented).

## Code Storage

Code-like payloads should be stored in MinIO via `CodeStorageService`.

-   Usage guide: `docs/code-storage-service.md`
-   Service implementation: `app/core/storage/code_storage.py`

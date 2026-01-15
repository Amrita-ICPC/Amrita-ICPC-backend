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

## Development

-   **Development Mode**: In development environment (default), the application automatically checks and creates tables on startup if they don't exist.
-   **Code Structure**:
    -   `app/main.py`: Application entry point.
    -   `app/core/`: Configuration and core utilities.
    -   `app/models/`: SQLAlchemy database models.
    -   `app/api/`: API route handlers (to be implemented).

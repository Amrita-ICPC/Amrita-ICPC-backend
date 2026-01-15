import logging
import sys
from typing import Optional
from rich.logging import RichHandler
from .config import config

class Logger:
    _instance: Optional['Logger'] = None
    _initialized: bool = False

    def __new__(cls, name: Optional[str] = None, log_level: str = "INFO",
                log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s') -> 'Logger':
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
        return cls._instance

    def __init__(self, name: Optional[str] = None, log_level: str = "INFO",
                 log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s') -> None:
        if not self._initialized:
            self.name = name or __name__
            self.log_level = getattr(logging, log_level.upper(), logging.INFO)
            self.log_format = log_format
            self._setup_logger()
            Logger._initialized = True

    def _setup_logger(self) -> None:
        """Set up the logger with proper handlers and formatters."""
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(self.log_level)

        # Remove existing handlers to avoid duplicates
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        if config.USE_RICH_LOGGING:
            # Create Rich console handler
            rich_handler = RichHandler(
                rich_tracebacks=True,
                markup=True,
                show_time=True,
                show_level=True,
                show_path=True,
            )
            rich_handler.setLevel(self.log_level)

            # Add handler to logger
            self.logger.addHandler(rich_handler)
        else:
            # Create console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)

            # Create formatter and add it to handler
            formatter = logging.Formatter(self.log_format)
            console_handler.setFormatter(formatter)

            # Add handler to logger
            self.logger.addHandler(console_handler)

        # Prevent propagation to avoid duplicate messages
        self.logger.propagate = False

    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """Get a logger instance with the specified name or return the default logger."""
        if name:
            # Create a new logger with the specified name
            logger_instance = logging.getLogger(name)
            logger_instance.setLevel(self.log_level)

            # Remove existing handlers to avoid duplicates
            for handler in logger_instance.handlers[:]:
                logger_instance.removeHandler(handler)

            if config.USE_RICH_LOGGING:
                # Create Rich console handler
                rich_handler = RichHandler(
                    rich_tracebacks=True,
                    markup=True,
                    show_time=True,
                    show_level=True,
                    show_path=True,
                )
                rich_handler.setLevel(self.log_level)

                # Add handler to logger
                logger_instance.addHandler(rich_handler)
            else:
                # Create console handler
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(self.log_level)

                # Create formatter and add it to handler
                formatter = logging.Formatter(self.log_format)
                console_handler.setFormatter(formatter)

                # Add handler to logger
                logger_instance.addHandler(console_handler)

            # Prevent propagation to avoid duplicate messages
            logger_instance.propagate = False

            return logger_instance

        return self.logger

    @classmethod
    def get_instance(cls, name: Optional[str] = None) -> 'Logger':
        """Get the singleton logger instance."""
        if cls._instance is None:
            cls._instance = cls(name=name)
        return cls._instance

if config.USE_RICH_LOGGING:
    # Logging Configuration
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format=config.LOG_FORMAT,
        datefmt="[%X]",
        style="{",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                markup=True,
                show_time=True,
                show_level=True,
                show_path=True,
            ),
        ],
    )

def setup_sqlalchemy_logging():
    """Configure SQLAlchemy logging with RichHandler."""
    if config.USE_RICH_LOGGING:
        sqlalchemy_logger = logging.getLogger("sqlalchemy.engine")
        sqlalchemy_logger.setLevel(logging.INFO if config.ENVIRONMENT == "development" else logging.WARN)
        # Remove existing handlers
        for handler in sqlalchemy_logger.handlers[:]:
            sqlalchemy_logger.removeHandler(handler)
        
        sqlalchemy_logger.addHandler(RichHandler(
            rich_tracebacks=True,
            markup=True,
            show_time=True,
            show_level=True,
            show_path=True,
        ))
        sqlalchemy_logger.propagate = False

def setup_uvicorn_logging():
    """Configure Uvicorn logging with RichHandler."""
    if config.USE_RICH_LOGGING:
        loggers = ["uvicorn", "uvicorn.access", "uvicorn.error"]
        for logger_name in loggers:
            logger_instance = logging.getLogger(logger_name)
            logger_instance.setLevel(config.LOG_LEVEL)
            
            # Remove existing handlers
            for handler in logger_instance.handlers[:]:
                logger_instance.removeHandler(handler)
            
            # Add RichHandler
            logger_instance.addHandler(RichHandler(
                rich_tracebacks=True,
                markup=True,
                show_time=True,
                show_level=True,
                show_path=True,
            ))
            logger_instance.propagate = False

# Global logger instance
logger = Logger(name='api', log_level=config.LOG_LEVEL, log_format=config.LOG_FORMAT).get_logger()
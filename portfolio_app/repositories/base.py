"""Base repository for database operations."""

from typing import TypeVar, Generic, List, Optional, Type
from flask_sqlalchemy import SQLAlchemy

T = TypeVar('T')


class BaseRepository(Generic[T]):
    """Base repository providing common database operations."""

    def __init__(self, model: Type[T], db: SQLAlchemy):
        """Initialize repository with model and database session.

        Args:
            model: The SQLAlchemy model class
            db: The SQLAlchemy database instance
        """
        self.model = model
        self.db = db

    def get_by_id(self, id: int) -> Optional[T]:
        """Get a single entity by ID.

        Args:
            id: The entity ID

        Returns:
            The entity if found, None otherwise
        """
        return self.db.session.get(self.model, id)

    def get_all(self) -> List[T]:
        """Get all entities.

        Returns:
            List of all entities
        """
        return self.model.query.all()

    def add(self, entity: T) -> None:
        """Add an entity to the session.

        Args:
            entity: The entity to add
        """
        self.db.session.add(entity)

    def delete(self, entity: T) -> None:
        """Delete an entity from the session.

        Args:
            entity: The entity to delete
        """
        self.db.session.delete(entity)

    def commit(self) -> None:
        """Commit the current transaction."""
        self.db.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.db.session.rollback()

    def flush(self) -> None:
        """Flush the current session."""
        self.db.session.flush()

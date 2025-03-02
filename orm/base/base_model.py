from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import (
    as_declarative,
    declared_attr,
    declarative_base,
    sessionmaker,
    Session,
)
import contextlib
from typing import AsyncIterator, Optional, Type, Any, Iterator

from sqlalchemy.sql.functions import count

from sqlalchemy import create_engine


DATABASE_URL_ASYNC = "postgresql+asyncpg://SG_USER:SG_PASS@localhost:5432/SG_DB"
DATABASE_URL_SYNC = "postgresql+psycopg://SG_USER:SG_PASS@localhost:5432/SG_DB"
DECLARATIVE_BASE = declarative_base()


class ORM:
    def __init__(self, model: Type["BaseORM"]):
        self.model = model

    async def create(self, **kwargs):
        """Create a new record."""
        async for db_session in self.model._async_session():
            instance = self.model(**kwargs)
            db_session.add(instance)
            await db_session.commit()
            await db_session.refresh(instance)
            return instance

    async def get(self, pk: int):
        """Retrieve a record by ID."""
        for db_session in self.model._sync_session():
            result = db_session.execute(select(self.model).filter(self.model.id == pk))
            return result.scalars().first()

    async def update(self, pk, **kwargs):
        """Update a record by ID."""
        async for db_session in self.model._async_session():
            instance = await db_session.get(self.model, pk)
            if not instance:
                return None
            for key, value in kwargs.items():
                setattr(instance, key, value)
            await db_session.commit()
            await db_session.refresh(instance)
            return instance

    async def delete(self, pk):
        """Delete a record by ID."""
        async for db_session in self.model._async_session():
            instance = await db_session.get(self.model, pk)
            if not instance:
                return False
            await db_session.delete(instance)
            await db_session.commit()
            return True

    async def all(self):
        """Retrieve all records."""
        async for db_session in self.model._async_session():
            query = select(self.model)
            result = await db_session.execute(query)
            return result.scalars().all()

    async def filter(self, **filters):
        """Filter records by criteria."""
        async for db_session in self.model._async_session():
            query = select(self.model).where(*self._filter_conditions(filters))
            result = await db_session.execute(query)
            return result.scalars().all()

    async def first(self, **filters):
        """Retrieve the first record matching the criteria."""
        async for db_session in self.model._async_session():
            query = select(self.model).where(*self._filter_conditions(filters))
            result = await db_session.execute(query)
            return result.scalars().first()

    async def count(self):
        """Count all records."""
        async for db_session in self.model._async_session():
            result = await db_session.execute(select(count()).select_from(self.model))
            return result.scalar()

    async def exists(self, **filters):
        """Check if any record matches the criteria."""
        return await self.first(**filters) is not None

    async def execute_query(self, query):
        async for db_session in self.model._async_session():
            result = await db_session.execute(query)
            return result

    def _filter_conditions(self, filtered_fields: dict[str, Any] = None):
        filter_conditions = []
        fields = filtered_fields or {}
        for attr, value in fields.items():
            if hasattr(self.model, attr):
                filter_conditions.append(getattr(self.model, attr) == value)
            else:
                raise AttributeError(
                    f"Model {self.model.__name__} does not have '{attr}' attribute"
                )
        return filter_conditions

    async def select_related(self, attrs: list[str] = None, **kwargs):
        attrs = attrs or []
        for attr in attrs:
            if not hasattr(self.model, attr):
                raise AttributeError(
                    f"Model {self.__name__} does not have '{attr}' attribute"
                )
        async for db_session in self.model._async_session():
            result = await db_session.execute(
                select(self.model).filter(*self._filter_conditions(kwargs))
            )
            instance = result.scalars().first()
            if not instance:
                return None
            await db_session.refresh(instance, attrs)
            return instance


@as_declarative()
class BaseORM:
    id: int
    __name__: str

    _db_manager: Optional["DataBaseSessionManager"] = None
    _orm_instance: Optional[ORM] = None

    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    @classmethod
    def column_objects(cls):
        """Returns a dictionary of column objects for the model."""
        if hasattr(cls, "__table__"):
            for col in cls.__table__.c:
                column_name = col.name
                column_type = col.type
                is_primary = col.primary_key
                has_relation = bool(col.foreign_keys)

                print(
                    f"Column: {column_name}, Type: {column_type}, Primary: {is_primary}"
                )

                if has_relation:
                    foreign_keys = [fk.target_fullname for fk in col.foreign_keys]
                    print(f"   🔗 Foreign Key Relation to: {foreign_keys}")

                yield col
        return None

    @classmethod
    def initialize(cls, db_manager: "DataBaseSessionManager"):
        """Initialize the Base class with a session manager."""
        cls._db_manager = db_manager

    @classmethod
    async def _async_session(cls) -> AsyncIterator[AsyncSession]:
        """Get an async session."""
        if cls._db_manager is None:
            raise Exception("DataBaseSessionManager is not initialized for Base.")
        async with cls._db_manager.async_session() as session:
            yield session

    @classmethod
    def _sync_session(cls) -> Iterator[Session]:
        """Get an async session."""
        if cls._db_manager is None:
            raise Exception("DataBaseSessionManager is not initialized for Base.")
        with cls._db_manager.sync_session() as session:
            yield session

    @classmethod
    @property
    def objects(cls) -> ORM:
        """Return an ORM instance for the class."""
        return ORM(model=cls)

    async def save(self):
        async for db_session in self._async_session():
            merged_instance = await db_session.merge(
                self
            )  # Ensures no duplicate sessions
            await db_session.commit()
            await db_session.refresh(merged_instance)
            return merged_instance  # Return the updated instance


class DataBaseSessionManager:
    def __init__(self, async_database_url: str, sync_database_url: str):
        """Initialize both async and sync database engines and sessionmakers."""
        # Async Engine & Session
        self._async_engine = create_async_engine(
            url=async_database_url,
            pool_size=5,
            max_overflow=2,
            pool_timeout=10,
            pool_recycle=600,
        )
        self._async_sessionmaker = async_sessionmaker(
            bind=self._async_engine, expire_on_commit=False, class_=AsyncSession
        )

        # Sync Engine & Session
        self._sync_engine = create_engine(
            url=sync_database_url,
            pool_size=5,
            max_overflow=2,
            pool_timeout=10,
            pool_recycle=600,
        )
        self._sync_sessionmaker = sessionmaker(
            bind=self._sync_engine, expire_on_commit=False, class_=Session
        )

    async def close(self):
        """Dispose of the async engine."""
        if self._async_engine:
            await self._async_engine.dispose()
            self._async_engine = None
            self._async_sessionmaker = None
        if self._sync_engine:
            self._sync_engine.dispose()
            self._sync_engine = None
            self._sync_sessionmaker = None

    async def create_all_tables(self, base):
        """Create all tables asynchronously."""
        if self._async_engine is None:
            raise Exception("DataBaseSessionManager is not initialized")
        async with self._async_engine.begin() as conn:
            await conn.run_sync(base.metadata.create_all)

    def create_all_tables_sync(self, base):
        """Create all tables synchronously."""
        if self._sync_engine is None:
            raise Exception("DataBaseSessionManager is not initialized")
        base.metadata.create_all(self._sync_engine)

    @contextlib.asynccontextmanager
    async def async_session(self) -> AsyncIterator[AsyncSession]:
        """Provide an async session."""
        if self._async_sessionmaker is None:
            raise Exception("DataBaseSessionManager is not initialized")
        async with self._async_sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e

    @contextlib.contextmanager
    def sync_session(self) -> Iterator[Session]:
        """Provide a sync session."""
        if self._sync_sessionmaker is None:
            raise Exception("DataBaseSessionManager is not initialized")
        session = self._sync_sessionmaker()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()


# Create tables (if not already created)
db_manager = DataBaseSessionManager(DATABASE_URL_ASYNC, DATABASE_URL_SYNC)
BaseORM.initialize(db_manager)

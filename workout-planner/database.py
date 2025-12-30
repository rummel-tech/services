"""Compatibility shim for tests referencing legacy `database` module.

This module proxies all attribute access and assignment to ``core.database`` so
test fixtures can override ``DATABASE_URL`` and have the change respected by
the running application.
"""
from types import ModuleType
import core.database as _core_db


def __getattr__(name: str):
	return getattr(_core_db, name)


def __setattr__(name: str, value):
	# Forward assignments so tests changing DATABASE_URL affect core.database too
	if name == "DATABASE_URL":
		setattr(_core_db, "DATABASE_URL", value)
		setattr(_core_db, "USE_SQLITE", value.startswith("sqlite"))
	else:
		setattr(_core_db, name, value)


# Eagerly initialize SQLite when available so legacy imports still work
try:
	_core_db.init_sqlite()
except Exception:
	# Allow tests to configure DB paths later without failing import
	pass


# Expose a module-level reference for tools that expect a module object
core: ModuleType = _core_db

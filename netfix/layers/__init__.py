"""Layered network diagnostics for netfix.

Importing this package registers all layered diagnostics in
:mod:`netfix.diagnose` so they can be invoked by name.
"""
from netfix.layers import egress, local, path, proxy

__all__ = ["local", "proxy", "egress", "path"]

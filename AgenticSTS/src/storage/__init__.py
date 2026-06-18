"""Dynamic-data path resolution.

All code that reads or writes dynamic data (memory, skills, evolution
artifacts, run history) must route through :mod:`src.storage.paths` rather
than hard-coding ``"data/..."`` literals.

This makes the future sibling-repo split (``AgenticSTS-Data``) a config flip
instead of a codebase-wide edit.
"""

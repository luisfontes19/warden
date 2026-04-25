"""PyInstaller hook for the jq package.

The jq package is a single C extension (.so/.dylib/.pyd) with libjq statically
linked. Because it is not a proper Python package (no __init__.py),
PyInstaller may not detect it automatically.
"""

hiddenimports = ["jq"]

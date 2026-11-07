"""Make lightgbm and xgboost importable on macOS without a system libomp (G03/A5).

The macOS arm64 wheels of lightgbm 4.7.0 and xgboost 3.4.1 link ``@rpath/libomp.dylib``
and search only Homebrew and MacPorts paths. scikit-learn's wheel bundles a libomp in
``sklearn/.dylibs``. Pointing ``DYLD_FALLBACK_LIBRARY_PATH`` at it works, but the variable
has to be set before the interpreter starts, and ``uv run`` does not pass ``DYLD_*``
through. So this helper re-executes the current interpreter once with the variable set.

``brew install libomp`` is the usual developer fix and makes this a no-op. G23 decides
what end users get.
"""

from __future__ import annotations

import importlib.util
import os
import sys

_MARK = "_TRUELIFT_SPIKE_OMP_REEXEC"


def ensure_openmp() -> str:
    """Return how the learners loaded: ``"system"`` or ``"sklearn-libomp"``."""
    try:
        import lightgbm  # noqa: F401
        import xgboost  # noqa: F401
    except OSError:
        if os.environ.get(_MARK) or sys.platform != "darwin":
            raise
        spec = importlib.util.find_spec("sklearn")
        if spec is None or spec.origin is None:
            raise
        dylibs = os.path.join(os.path.dirname(spec.origin), ".dylibs")
        env = dict(os.environ, DYLD_FALLBACK_LIBRARY_PATH=dylibs, **{_MARK: "1"})
        os.execve(sys.executable, [sys.executable, *sys.argv], env)
    return "sklearn-libomp" if os.environ.get(_MARK) else "system"

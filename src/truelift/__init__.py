"""truelift: a local causal-inference assistant for discount ROI."""

import os

__version__ = "0.0.1"

# The provider is the only network destination at run time (C8, G11/A9). LiteLLM downloads its
# model cost map on import unless this is set, so set it before anything can import LiteLLM.
# Forced, not defaulted: a user's own "False" must not reopen the fetch.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

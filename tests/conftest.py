"""Force RAG off for the default suite so .env cannot reach Neon during pytest."""

import os

os.environ["RAG_ENABLED"] = "false"

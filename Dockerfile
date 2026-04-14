FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .

# App dependencies (no torch, no sentence-transformers, no dev deps)
RUN uv pip install --system --no-cache \
    "openai>=1.0" "chromadb>=0.5" \
    "tiktoken>=0.7" "pydantic>=2.0" "pydantic-settings>=2.0" \
    "structlog>=24.0" "python-dotenv>=1.0" "textual>=0.80" \
    "rich>=13.0" "pyyaml>=6.0" "sqlalchemy>=2.0" "tqdm" "numpy"

# Code (no deps, fast)
COPY . .
RUN uv pip install --system --no-deps --no-cache -e .

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m"]
CMD ["party_of_one"]

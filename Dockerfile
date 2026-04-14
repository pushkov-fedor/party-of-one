FROM python:3.11-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system -e ".[dev]"

COPY . .

# Pre-download embedding model at build time
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('deepvk/USER-bge-m3')" 2>/dev/null || true

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m"]
CMD ["party_of_one.play", "--help"]

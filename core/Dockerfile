FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
# Kept in sync by hand with pyproject.toml's [project.dependencies] — alembic/pyjwt/boto3/
# python-multipart were added there across SP-1a/b/c but had drifted out of this list,
# crash-looping the container on `import jwt` etc. the moment CORE_AUTH_MODE=oidc is used.
# mcp was added in SP-2a for the same reason — kept it in sync here too.
RUN uv pip install --system --no-cache \
    "fastapi>=0.111" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" \
    "pydantic>=2.7" "httpx>=0.27" "psycopg[binary]>=3.1" \
    "alembic>=1.13" "pyjwt[crypto]>=2.8" "boto3>=1.34" "python-multipart>=0.0.9" \
    "mcp>=1.12" "shapely>=2.0" "procrastinate>=2.0" "pyogrio>=0.9" "pyproj>=3.6" \
    "pgvector>=0.3"

COPY app ./app

EXPOSE 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]

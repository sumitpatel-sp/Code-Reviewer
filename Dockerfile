# Use Python 3.12, matching the project's declared Python version.
FROM python:3.12-slim

# Store application files in one predictable location inside the container.
WORKDIR /code

# Copy dependencies first so Docker can reuse this layer when only source code changes.
COPY requirements.txt ./
# Installs all Python dependencies including semgrep (cross-language static analysis).
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the remaining project files after dependencies are installed.
COPY . .

# FastAPI listens on this port inside the container.
EXPOSE 8000

# Start the API. --host exposes it to the computer running Docker.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

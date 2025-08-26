# Dockerfile
FROM python:3.11-slim

# Avoid writing .pyc files and force unbuffered stdout/stderr (logs show up immediately)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the project source code
COPY . .

# Expose the application port
EXPOSE 8000

# Default command for local/dev. In docker-compose you can override this if needed.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


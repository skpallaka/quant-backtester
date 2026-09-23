FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY migrations ./migrations
COPY scripts ./scripts

ENV FLASK_APP=quant_backtester.api.app:app

EXPOSE 5000

# Default to the API; the worker Deployment overrides this command.
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]

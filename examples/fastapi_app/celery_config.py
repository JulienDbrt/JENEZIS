"""
Celery app configuration for the example application.
This file allows the celery worker to be started from the `examples/fastapi_app` directory.
"""
from jenezis.core.connections import celery_app

# The celery_app is imported from the core connections module where it is defined.
# To run the worker, use the following command from the project root:
# celery -A examples.fastapi_app.celery_config worker --loglevel=info

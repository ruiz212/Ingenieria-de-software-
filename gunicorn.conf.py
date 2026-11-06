"""Gunicorn production configuration optimized for Azure App Service B1 tier.
Default: 1 worker and 2 threads. Validate capacity with production metrics.
App Service Basic B1 must not be confused with burstable B-series VMs.
"""
import os

# Port: Listen on Azure's assigned PORT or WEBSITES_PORT (default to 8000)
port = os.environ.get('PORT', os.environ.get('WEBSITES_PORT', '8000'))
bind = f"0.0.0.0:{port}"

# Keep memory use conservative; allow at most two explicitly requested workers.
workers = int(os.environ.get('GUNICORN_WORKERS', os.environ.get('WEB_CONCURRENCY', 1)))
workers = min(workers, 2)

# Worker threads: gthread handles concurrent I/O (SQL queries, static files)
# without spawning multiple memory-heavy Python processes.
threads = int(os.environ.get('GUNICORN_THREADS', 2))
worker_class = 'gthread'

# HTTP Keep-Alive and timeouts (600s matches Azure Oryx standard)
keepalive = 5
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 600))

# Periodic worker recycling to eliminate memory fragmentation
max_requests = 1000
max_requests_jitter = 50

preload_app = False

# Logging configuration
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

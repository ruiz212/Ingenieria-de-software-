"""Gunicorn production configuration for Azure App Service.
Leverages multiple CPU cores and multithreaded worker model (gthread)
to maximize throughput and minimize latency on upgraded servers.
"""
import multiprocessing
import os

# Server socket
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:8000')

# Worker processes:
# Scales dynamically with server CPU cores allocated in Azure App Service.
cpu_cores = multiprocessing.cpu_count()
default_workers = max(2, min(cpu_cores * 2, 8))
workers = int(os.environ.get('GUNICORN_WORKERS', os.environ.get('WEB_CONCURRENCY', default_workers)))

# Worker threads:
# gthread worker class handles concurrent I/O (SQL, static assets) without blocking.
threads = int(os.environ.get('GUNICORN_THREADS', 4))
worker_class = 'gthread'

# HTTP Connection pooling and Keep-Alive (reuses TCP/TLS connections)
keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', 5))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))

# Periodic worker recycling to eliminate memory fragmentation
max_requests = 1000
max_requests_jitter = 50

# Preloading application code for fast worker startup and copy-on-write memory sharing
preload_app = False

# Logging configuration
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY kubertree ./kubertree
RUN pip install --no-cache-dir .

# OpenShift runs containers with an arbitrary non-root UID in group 0.
# Make the app tree group-owned and group-writable so any such UID can run it.
RUN chgrp -R 0 /app && chmod -R g=u /app

USER 1001
ENV KUBERTREE_BIND_HOST=0.0.0.0 KUBERTREE_BIND_PORT=8000
EXPOSE 8000

CMD ["python", "-m", "kubertree"]

# Optional offline demo only. Build from projects/coursepilot.
FROM python:3.11-slim
WORKDIR /app
COPY core.py agents.py api.py app.py ./
USER 65534:65534
ENTRYPOINT ["python", "app.py", "--db", ":memory:"]
CMD ["demo"]

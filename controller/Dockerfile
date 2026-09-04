FROM python:3.12-slim

WORKDIR /app
COPY Projects/AurumFarmer /aurum-farmer
COPY controller/pyproject.toml controller/README.md ./
COPY controller/src ./src
RUN python -m pip install --no-cache-dir /aurum-farmer .

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "boxbrain_controller.main:app", "--host", "0.0.0.0", "--port", "8000"]


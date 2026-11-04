FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
WORKDIR /app
COPY service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-deps 'torch==2.8.0+cpu' --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r /tmp/requirements.txt
COPY service/ service/
COPY student/ student/
COPY worker/ worker/
COPY training/__init__.py training/common.py training/data.py training/artifacts.py training/
COPY data/schema.json data/schema.json
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2 AWS_EC2_METADATA_DISABLED=true
USER 65532:65532
EXPOSE 8000
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "25"]

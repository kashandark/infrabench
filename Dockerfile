FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home bench
USER bench
WORKDIR /data
ENTRYPOINT ["infrabench"]
CMD ["list"]

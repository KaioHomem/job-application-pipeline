FROM python:3.12-slim
WORKDIR /app
COPY mcp_server/requirements.txt mcp_server/requirements.txt
RUN pip install --no-cache-dir -r mcp_server/requirements.txt
COPY src src
COPY config config
COPY web/data web/data
COPY mcp_server mcp_server
ENV PORT=8000
EXPOSE 8000
CMD ["python", "mcp_server/server.py", "--http", "--host", "0.0.0.0"]

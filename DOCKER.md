# Docker

Build and run the WebDAV server using Docker:

```bash
# Using docker-compose (recommended)
docker-compose up -d

# Or build and run manually
docker build -t py-webdav .
docker run -d -p 8080:8080 -v $(pwd)/webdav-data:/data py-webdav
```

Configuration via environment variables:
- `WEBDAV_HOST`: Host to bind to (default: 0.0.0.0)
- `WEBDAV_PORT`: Port to listen on (default: 8080)
- `WEBDAV_DIR`: Directory to serve (default: /data)

Example with custom settings:

```bash
# Create .env file from example
cp .env.example .env

# Edit .env to customize port and data directory
# Then start the server
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the server
docker-compose down
```

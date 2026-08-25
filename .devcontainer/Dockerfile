FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip jq make ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the AWS SAM CLI from the official Linux release archive.
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) sam_arch="x86_64" ;; \
      arm64) sam_arch="arm64" ;; \
      *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-${sam_arch}.zip" -o /tmp/aws-sam-cli.zip; \
    mkdir -p /tmp/sam-installation; \
    unzip -q /tmp/aws-sam-cli.zip -d /tmp/sam-installation; \
    /tmp/sam-installation/install; \
    rm -rf /tmp/aws-sam-cli.zip /tmp/sam-installation

USER vscode

FROM node:22-bookworm AS node
FROM rust:1.99.1-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git pkg-config protobuf-compiler libprotobuf-dev \
    libasound2-dev libudev-dev libwayland-dev libxkbcommon-dev \
    && rustup component add clippy rustfmt \
    && rm -rf /var/lib/apt/lists/*

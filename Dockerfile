# Use the dev image to build and install dependencies.
FROM python:3.12-trixie AS builder

WORKDIR /app

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# Leverage a bind mount to requirements.txt to avoid having to copy them into
# this layer.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    pip install -r requirements.txt

# Use the minimal runtime image. It runs as nonroot by default.
FROM python:3.12-trixie

WORKDIR /app

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy the source code into the container.
COPY . .

# Build libacars only when explicitly requested:
# docker build --build-arg INSTALL_LIBACARS=true -t airframes-socket .
ARG INSTALL_LIBACARS=false
RUN if [ "$INSTALL_LIBACARS" = "true" ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
        libjansson-dev \
        libxml2-dev \
        zlib1g-dev \
      && git clone --depth 1 https://github.com/szpajder/libacars.git /tmp/libacars \
      && cmake -S /tmp/libacars -B /tmp/libacars/build -DCMAKE_BUILD_TYPE=Release \
      && cmake --build /tmp/libacars/build --parallel \
      && cmake --install /tmp/libacars/build \
      && ldconfig \
      && apt-get purge -y --auto-remove \
        build-essential \
        cmake \
        git \
        libjansson-dev \
        libxml2-dev \
        zlib1g-dev \
      && apt-get install -y --no-install-recommends \
        libjansson4 \
        libxml2 \
        zlib1g \
      && rm -rf /var/lib/apt/lists/* /tmp/libacars; \
    fi


# Use a shell entrypoint to translate environment variables into CLI flags.
RUN chmod +x /app/docker-entrypoint.sh
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD []

# Build the official LibreSpeed Rust engine for the build host architecture.
# For MikroTik CHR x86_64, build natively as linux/amd64.
ARG LIBRESPEED_RS_REF=9390a0226b86afe8e78177492ba1614711fddedb

FROM rust:1-bookworm AS librespeed-builder
ARG LIBRESPEED_RS_REF
RUN apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 update && apt-get -o Acquire::Retries=5 install -y --no-install-recommends ca-certificates git pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone https://github.com/librespeed/speedtest-rust.git . \
    && git checkout --detach "${LIBRESPEED_RS_REF}"
RUN cargo build --locked --release

FROM debian:bookworm-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SUNLINEBF_HOST=0.0.0.0 \
    SUNLINEBF_PORT=8081 \
    SUNLINEBF_DB=/data/results.sqlite3
RUN apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 update && apt-get -o Acquire::Retries=5 install -y --no-install-recommends ca-certificates python3 bash \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/sunlinebf /opt/librespeed /data
WORKDIR /opt/sunlinebf
COPY index.html style.css app.js server.py speedtest.js speedtest_worker.js LICENSE /opt/sunlinebf/
COPY --from=librespeed-builder /src/target/release/librespeed-rs /usr/local/bin/librespeed-rs
COPY --from=librespeed-builder /src/LICENSE.txt /opt/librespeed/LICENSE.txt
COPY --from=librespeed-builder /src/country_asn.mmdb /opt/librespeed/country_asn.mmdb
COPY rust-config.toml /opt/librespeed/configs.toml
COPY entrypoint.sh /usr/local/bin/sunlinebf-entrypoint
RUN chmod 0755 /usr/local/bin/sunlinebf-entrypoint \
    && chmod -R a+rX /opt/sunlinebf /opt/librespeed \
    && chmod 0777 /data
WORKDIR /opt/librespeed
VOLUME ["/data"]
EXPOSE 8080 8081
ENTRYPOINT ["/usr/local/bin/sunlinebf-entrypoint"]

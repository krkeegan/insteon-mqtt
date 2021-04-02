ARG BUILD_FROM
#FROM $BUILD_FROM
FROM homeassistant/aarch64-base

ENV LANG C.UTF-8

COPY . /opt/insteon-mqtt

RUN ls /

RUN apk update && \
    apk --no-cache add python3-dev && \
    apk add --no-cache py3-pip && \
    pip3 install /opt/insteon-mqtt && \
    chmod +x /opt/insteon-mqtt/hassio/entrypoint.sh

CMD ["/opt/insteon-mqtt/hassio/entrypoint.sh"]

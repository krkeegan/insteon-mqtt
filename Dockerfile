ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

COPY . /opt/insteon-mqtt

RUN apk update

RUN apk add --no-cache py3-pip && \
    pip3 install /opt/insteon-mqtt && \
    chmod +x /opt/insteon-mqtt/hassio/entrypoint.sh

CMD ["/opt/insteon-mqtt/hassio/entrypoint.sh"]

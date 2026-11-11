FROM python:3.12-alpine
# Home Assistant passes the add-on version as a build arg; shown in the display footer
ARG BUILD_VERSION=dev
ENV ADDON_VERSION=$BUILD_VERSION
RUN pip install --no-cache-dir pillow==12.* astral==3.* tzdata
# Inter font (SIL OFL 1.1), fetched from the official release and checksum-verified
ARG INTER_URL=https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip
ARG INTER_SHA256=9883fdd4a49d4fb66bd8177ba6625ef9a64aa45899767dde3d36aa425756b11e
RUN mkdir -p /app/fonts && cd /tmp \
 && wget -q -O inter.zip "$INTER_URL" \
 && echo "$INTER_SHA256  inter.zip" | sha256sum -c - \
 && unzip -q -j inter.zip LICENSE.txt \
      extras/otf/Inter-Regular.otf extras/otf/Inter-Medium.otf extras/otf/Inter-SemiBold.otf \
      extras/otf/Inter-Bold.otf extras/otf/InterDisplay-Light.otf extras/otf/InterDisplay-SemiBold.otf \
      -d /app/fonts \
 && rm inter.zip
COPY app /app
WORKDIR /app
CMD ["python3", "-u", "server.py"]

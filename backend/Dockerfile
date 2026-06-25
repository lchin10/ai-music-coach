# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build Audiveris (the Java OMR CLI) from source.
# Building from a pinned tag is the most version-robust way to get a Linux
# launcher; prebuilt Linux binaries are not reliably published per release.
# Audiveris 5.x requires Java 17, so we need a full JDK here (not just a JRE).
# ---------------------------------------------------------------------------
FROM eclipse-temurin:17-jdk-jammy AS audiveris-build

ARG AUDIVERIS_VERSION=5.3.1
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN git clone --depth 1 --branch ${AUDIVERIS_VERSION} \
        https://github.com/Audiveris/audiveris.git
WORKDIR /build/audiveris
# `installDist` (from the Gradle application plugin) produces a self-contained
# distribution at build/install/Audiveris with a bin/Audiveris launcher.
RUN ./gradlew --no-daemon -x test installDist

# ---------------------------------------------------------------------------
# Stage 2: runtime image — Python app + a JRE + Audiveris + Tesseract.
# Pin to bookworm: newer Debian (trixie) drops the openjdk-17-jre-headless
# package that Audiveris 5.x requires.
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm

# JRE to run Audiveris, Tesseract (Audiveris OCR dependency), and the fonts/
# native libs the OMR pipeline needs. opencv-python-headless needs no GUI libs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless \
        tesseract-ocr \
        tesseract-ocr-eng \
        libfreetype6 \
        fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Copy the built Audiveris distribution from the build stage.
COPY --from=audiveris-build /build/audiveris/build/install/Audiveris /opt/audiveris

# Audiveris must run headless; AUDIVERIS_PATH is read by the processor service.
ENV JAVA_TOOL_OPTIONS="-Djava.awt.headless=true" \
    AUDIVERIS_PATH="/opt/audiveris/bin/Audiveris" \
    TESSDATA_PREFIX="/usr/share/tesseract-ocr/5/tessdata" \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Install Python deps first (separate layer for better build caching).
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e .

# Render injects $PORT; default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

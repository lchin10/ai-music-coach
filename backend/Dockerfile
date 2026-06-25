# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Single-stage image: Ubuntu 22.04 (matches the prebuilt Audiveris .deb) +
# Python app + Audiveris + Tesseract.
#
# We install Audiveris from its official prebuilt Ubuntu .deb rather than
# building from source: the source Gradle build pulls javax.media.jai from
# repository.springsource.com, which was permanently shut down (Jan 2025), so
# `gradlew build` no longer resolves dependencies. The .deb is built with
# jpackage and bundles its own Java runtime, so no separate JRE is needed.
# ---------------------------------------------------------------------------
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Pin the Audiveris release; the ubuntu22.04 .deb matches this base image.
ARG AUDIVERIS_VERSION=5.10.2
ARG AUDIVERIS_DEB=Audiveris-${AUDIVERIS_VERSION}-ubuntu22.04-x86_64.deb

# System deps: Python, Tesseract (OCR for Audiveris), and the Audiveris .deb
# itself (apt resolves its dependencies, including the bundled-runtime libs).
# opencv-python-headless needs no GUI libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
        python3 python3-venv python3-pip \
        tesseract-ocr tesseract-ocr-eng \
        libfreetype6 fontconfig \
    # The .deb's post-install registers a desktop menu entry via
    # xdg-desktop-menu, which fails in a headless container ("No writable
    # system menu directory"). Stub those tools so the postinst succeeds; the
    # app files themselves are unpacked regardless.
    && printf '#!/bin/sh\nexit 0\n' > /usr/local/bin/xdg-desktop-menu \
    && printf '#!/bin/sh\nexit 0\n' > /usr/local/bin/xdg-desktop-icon \
    && chmod +x /usr/local/bin/xdg-desktop-menu /usr/local/bin/xdg-desktop-icon \
    && curl -fsSL -o /tmp/audiveris.deb \
        "https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/${AUDIVERIS_DEB}" \
    && (apt-get install -y --no-install-recommends /tmp/audiveris.deb || true) \
    && rm /tmp/audiveris.deb \
    # jpackage installs the launcher under /opt/<app>/bin; symlink it onto PATH
    # as `audiveris` so the processor's shutil.which("audiveris") finds it.
    # Fail loudly if the launcher did not land.
    && launcher="$(find /opt -type f -name 'Audiveris' 2>/dev/null | head -1)" \
    && test -n "$launcher" \
    && ln -s "$launcher" /usr/local/bin/audiveris \
    && rm -rf /var/lib/apt/lists/*

# Audiveris must run headless. AUDIVERIS_PATH is read by the processor service;
# point it at the symlink created above.
ENV JAVA_TOOL_OPTIONS="-Djava.awt.headless=true" \
    AUDIVERIS_PATH="/usr/local/bin/audiveris" \
    PYTHONUNBUFFERED=1

# Install the Python app into an isolated venv (avoids PEP-668 conflicts with
# the system Python).
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e .

# Render injects $PORT; default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

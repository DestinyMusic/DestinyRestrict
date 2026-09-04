# 1. Base Image
FROM python:3.10-slim

# 2. Setup Non-Root User (CRITICAL FOR HUGGING FACE SPACES)
RUN useradd -m -u 1000 user

# 3. Environment Variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# 4. Set Working Directory
WORKDIR /app

# 5. Install system dependencies (ADDED FFMPEG & SOX)
RUN apt-get update -qq && \
    apt-get install -yqq --no-install-recommends \
    p7zip-full \
    coreutils \
    build-essential \
    python3-dev \
    mediainfo \
    ffmpeg \
    sox \
    fonts-freefont-ttf && \
    rm -rf /var/lib/apt/lists/*

# 6. Change ownership of the app directory to the new Hugging Face user
RUN chown -R user:user /app

# 7. Switch to the non-root user
USER user

# 8. Virtual Environment Setup
ENV VENV_PATH="/app/venv"
RUN python3 -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

# 9. Install Python Requirements (Using ultra-fast 'uv')
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -q uv && \
    uv pip install -q --no-cache-dir -r requirements.txt

# 10. Copy Bot Files
COPY --chown=user:user . .

# 11. Run the bot
CMD ["python3", "restrict_bot.py"]

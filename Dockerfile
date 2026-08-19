FROM python:3.10-slim

WORKDIR /app

# Forces Python to print logs immediately
ENV PYTHONUNBUFFERED=1

# 1. Quietly install system dependencies (ADDED mediainfo)
RUN apt-get update -qq && \
    apt-get install -yqq --no-install-recommends \
    7zip \
    coreutils \
    build-essential \
    python3-dev \
    mediainfo > /dev/null 2>&1 && \
    rm -rf /var/lib/apt/lists/*

# 2. Create a Virtual Environment and add it to the system PATH
# (This fixes the pip error and means you don't have to type out the full venv)
ENV VENV_PATH="/opt/venv"
RUN python3 -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

# 3. Install 'uv' for hyper-fast installs, then install requirements silently
COPY requirements.txt .
RUN pip3 install --no-cache-dir -q uv && \
    uv pip install -q --no-cache-dir -r requirements.txt

# 4. Copy the rest of the bot files
COPY . .

# 5. Start the bot
CMD ["python3", "restrict_bot.py"]

FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    git \
    ansible \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка Trivy
RUN curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# Установка Hadolint
RUN curl -sfL https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 -o /usr/local/bin/hadolint \
    && chmod +x /usr/local/bin/hadolint

# Установка Ansible collection для Docker
RUN ansible-galaxy collection install community.docker

WORKDIR /app

# Копирование requirements и установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Создание директории для загрузок
RUN mkdir -p /tmp/sdp_uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

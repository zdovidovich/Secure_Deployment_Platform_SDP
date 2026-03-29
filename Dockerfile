FROM python:3.13.12-alpine

WORKDIR /SDP

COPY . /SDP/

RUN pip install -r ./app/requirements.txt
RUN apk update && apk upgrade
RUN apk add ansible
RUN ansible-galaxy collection install community.docker

RUN wget https://github.com/aquasecurity/trivy/releases/download/v0.69.3/trivy_0.69.3_Linux-64bit.tar.gz -O /tmp/trivy.tar.gz && tar -xzf /tmp/trivy.tar.gz && chmod +x /tmp/trivy

RUN wget https://github.com/hadolint/hadolint/releases/download/v2.14.0/hadolint-linux-x86_64 -O /tmp/hadolint && chmod +x /tmp/hadolint



EXPOSE 8080

CMD ["python", "./app/app.py"]

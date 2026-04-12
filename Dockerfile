FROM python:3.13.13-alpine

WORKDIR /SDP

RUN apk update && apk upgrade
RUN apk add --no-cache ansible=13.0.0-r0
RUN apk add openssh-client=10.2_p1-r0

COPY ./app/requirements.txt /SDP/app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip==26.0.1 && \
    pip install --no-cache-dir -r /SDP/app/requirements.txt
        
RUN ansible-galaxy collection install --no-cache community.docker

RUN wget -q https://github.com/aquasecurity/trivy/releases/download/v0.69.3/trivy_0.69.3_Linux-64bit.tar.gz -O /tmp/trivy.tar.gz && \
    tar -xzf /tmp/trivy.tar.gz -C /tmp && \
    mv /tmp/trivy /usr/local/bin/trivy && \
    chmod +x /usr/local/bin/trivy && \
    rm /tmp/trivy.tar.gz && \
    trivy image --download-db-only

RUN wget -q https://github.com/hadolint/hadolint/releases/download/v2.14.0/hadolint-linux-x86_64 -O /tmp/hadolint && \
    mv /tmp/hadolint /usr/local/bin/hadolint && \
    chmod +x /usr/local/bin/hadolint

COPY . /SDP/

EXPOSE 8080

CMD ["python", "./app/app.py"]

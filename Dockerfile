FROM python:3.13.12-alpine

WORKDIR /SDP

COPY . /SDP/

RUN pip install -r ./app/requirements.txt
RUN apk add ansible
RUN ansible-galaxy collection install community.docker

EXPOSE 8080

CMD ["python", "./app/app.py"]

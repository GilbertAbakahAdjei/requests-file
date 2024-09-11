FROM ubuntu:latest
RUN apt-get update && apt-get install -y git unzip zip curl tar wget python3 python3-pip
COPY . /app
WORKDIR /app
RUN /usr/bin/python3 -m pip install --break-system-packages -r requirements.txt
RUN /usr/bin/python3 -m unittest ./tests/test_requests_file.py -v
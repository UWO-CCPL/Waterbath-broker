FROM python:3.8.6-slim-buster
WORKDIR /root
ADD . .
RUN pip install -r requirements.txt
CMD python main.py
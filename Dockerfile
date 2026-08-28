FROM python:3.10

WORKDIR /app

COPY requirements.txt requirements.txt

COPY snitch ./snitch
COPY static ./static

RUN mkdir -p /data

EXPOSE 3000

RUN pip install -r requirements.txt

CMD ["python", "-m", "snitch.main"]
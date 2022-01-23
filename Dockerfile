FROM python:3.10-alpine
WORKDIR /server
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "server.py"]

FROM python:3.8

COPY requirements.txt /requirements.txt
RUN pip3 install -r /requirements.txt

WORKDIR /app
COPY . /app
ENV PYTHONPATH=/app
ENV FLASK_APP=main.py

EXPOSE 4500

CMD ["python","main.py"]


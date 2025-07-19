FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y xfsprogs
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD [ "python","/app/lsdisk.py" ]
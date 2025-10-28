FROM python:3.13-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y xfsprogs e2fsprogs util-linux
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD [ "python","/app/lsdisk.py" ]
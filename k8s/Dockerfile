FROM python:3.12-slim
WORKDIR /app
COPY ../requirements.txt .
RUN pip install -r requirements.txt
COPY ../csi_utils.py .
COPY ../utils.py .
COPY . .
ENV PYTHONUNBUFFERED=1
CMD [ "python","/app/check_disk_agent.py" ]
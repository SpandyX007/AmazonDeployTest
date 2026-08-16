# install python base image
FROM python:3.11-slim

#change working directory to code
WORKDIR /code

# copy the requirement file to the docker
COPY requirements.txt /code/requirements.txt

# install python libraries
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# append project and data directories to PYTHONPATH

# add the whole python code to the docker
COPY . /code/backend

EXPOSE 80

# specify default command
CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","80"]
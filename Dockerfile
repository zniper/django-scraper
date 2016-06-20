FROM python:2.7
ENV PYTHONUNBUFFERED 1
RUN mkdir /scraper
ADD . /scraper
WORKDIR /scraper
RUN pip install Django django-nose coverage coveralls flake8
RUN pip install .
RUN flake8 scraper  --exclude=*/migrations/*,*test*
RUN coverage run --source='./' --omit=*/migrations/*,*test* run_tests.py

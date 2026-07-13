FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git gcc-12 g++-12 \
    && rm -rf /var/lib/apt/lists/*

ENV CC=gcc-12
ENV CXX=g++-12

RUN pip install --no-cache-dir "setuptools<66" wheel pytest hypothesis numpy Cython extension_helpers
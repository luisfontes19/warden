FROM python:3.14-trixie

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt update
RUN apt install -y git curl

RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.local/bin:${PATH}"

RUN curl -1sLf 'https://dl.cloudsmith.io/public/task/task/setup.deb.sh' | bash && apt install -y task

ENV PYTHONDONTWRITEBYTECODE=1

#ENTRYPOINT ["uv", "run", "--watch", "--"]

ENTRYPOINT ["sh", "-c", "while true; do sleep 1; done"]

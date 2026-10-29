import os
import time

from flask import Flask, Response

app = Flask(__name__)
started_at = time.monotonic()
live_failed = False
ready_failed = False
APP_VERSION = os.environ.get("APP_VERSION", "v1")


def is_started():
    return time.monotonic() - started_at >= 10


@app.get("/")
def index():
    message = os.environ.get("APP_MESSAGE", "Hello from Python")
    pod_name = os.environ.get("POD_NAME", os.environ.get("HOSTNAME", "unknown"))
    token_status = "set" if os.environ.get("APP_TOKEN") else "not set"
    return Response(
        f"{message} | pod={pod_name} | version={APP_VERSION}\nAPP_TOKEN is {token_status}\n",
        mimetype="text/plain",
    )


@app.get("/ready")
def ready():
    if not is_started() or ready_failed:
        return Response("Not ready\n", status=503, mimetype="text/plain")
    return Response("Ready\n", mimetype="text/plain")


@app.get("/live")
def live():
    if not is_started() or live_failed:
        return Response("Not alive\n", status=503, mimetype="text/plain")
    return Response("Alive\n", mimetype="text/plain")


@app.get("/you-are-death")
def make_unlive():
    global live_failed
    live_failed = True
    return Response("Liveness disabled until restart\n", mimetype="text/plain")


@app.get("/not-ready")
def make_not_ready():
    global ready_failed
    ready_failed = True
    return Response("Readiness disabled\n", mimetype="text/plain")


@app.get("/ready-again")
def make_ready_again():
    global ready_failed
    ready_failed = False
    return Response("Readiness restored\n", mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

import ssl
import sys
import threading
import time
import json
import urllib.error
import urllib.request
import queue


class NodeRedPipe:
    """A thread-safe, non-blocking pipe to send JSON payloads to a Node-RED HTTP endpoint with retries and error handling."""

    def __init__(
        self,
        url,
        timeout=10.0,
        queue_size=1000,
        retries=2,
        retry_delay=1.0,
        insecure_tls=False,
        ca_file=None,
    ):
        self.url = url
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.ssl_context = self._build_ssl_context(insecure_tls, ca_file)
        self.queue = queue.Queue(maxsize=queue_size)
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.last_error_at = 0

    def _build_ssl_context(self, insecure_tls, ca_file):
        if insecure_tls:
            return ssl._create_unverified_context()
        if ca_file:
            return ssl.create_default_context(cafile=ca_file)
        return None

    def start(self):
        self.thread.start()

    def send(self, payload):
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            self._log_error("Node-RED queue is full; dropping message")

    def _worker(self):
        while True:
            payload = self.queue.get()
            try:
                self._post_with_retries(payload)
            except Exception as exc:
                self._log_error(f"Node-RED POST failed: {exc}")
            finally:
                self.queue.task_done()

    def _post_with_retries(self, payload):
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                self._post(payload)
                return
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.retry_delay)

        raise last_error  # pyright: ignore[reportGeneralTypeIssues]

    def _post(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "airframes-socket-client",
            },
            method="POST",
        )

        with urllib.request.urlopen(
            request,
            timeout=self.timeout,
            context=self.ssl_context,
        ) as response:
            if response.status >= 400:
                raise urllib.error.HTTPError(
                    self.url,
                    response.status,
                    response.reason,
                    response.headers,
                    response,
                )

    def _log_error(self, message):
        now = time.monotonic()
        if now - self.last_error_at < 10:
            return
        self.last_error_at = now
        print(message, file=sys.stderr)

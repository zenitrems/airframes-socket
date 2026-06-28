import asyncio
import contextlib
import json
import sys
import ssl
import time

import aiohttp


class NodeRedPipe:
    """An async pipe to send JSON payloads to a Node-RED HTTP endpoint with retries and error handling."""

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
        self.queue = asyncio.Queue(maxsize=queue_size)
        self.session = None
        self.worker_task = None
        self.last_error_at = 0
        self.closed = False

    def _build_ssl_context(self, insecure_tls, ca_file):
        if insecure_tls:
            return ssl._create_unverified_context()
        if ca_file:
            return ssl.create_default_context(cafile=ca_file)
        return None

    async def start(self):
        if self.worker_task is not None:
            return
        self.session = aiohttp.ClientSession()
        self.worker_task = asyncio.create_task(self._worker())

    async def send(self, payload):
        if self.closed:
            self._log_error("Node-RED pipe is closed; dropping message")
            return

        try:
            self.queue.put_nowait(payload)
        except asyncio.QueueFull:
            self._log_error("Node-RED queue is full; dropping message")

    async def close(self):
        self.closed = True
        if self.worker_task is not None:
            await self.queue.join()
            self.worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.worker_task
        if self.session is not None:
            await self.session.close()

    async def _worker(self):
        while True:
            payload = await self.queue.get()
            try:
                await self._post_with_retries(payload)
            except Exception as exc:
                self._log_error(f"Node-RED POST failed: {exc}")
            finally:
                self.queue.task_done()

    async def _post_with_retries(self, payload):
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                await self._post(payload)
                return
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    await asyncio.sleep(self.retry_delay)

        raise last_error

    async def _post(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "airframes-socket-client",
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with self.session.post(
            self.url,
            data=body,
            headers=headers,
            timeout=timeout,
            ssl=self.ssl_context,
        ) as response:
            if response.status >= 400:
                content = await response.text()
                raise aiohttp.ClientResponseError(
                    history=(),
                    request_info=response.request_info,
                    status=response.status,
                    message=content,
                    headers=response.headers,
                )

    def _log_error(self, message):
        now = time.monotonic()
        if now - self.last_error_at < 10:
            return
        self.last_error_at = now
        print(message, file=sys.stderr)

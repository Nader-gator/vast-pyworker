import os
import logging
import dataclasses
import base64
from typing import Union, Type

from aiohttp import web, ClientResponse
from anyio import open_file

from lib.backend import Backend, LogAction
from lib.data_types import EndpointHandler, JsonDataException
from lib.server import start_server
from .data_types import DefaultComfyWorkflowData, CustomComfyWorkflowData


MODEL_SERVER_URL = "http://0.0.0.0:8188"

# This is the last log line that gets emitted once comfyui+extensions have been fully loaded
MODEL_SERVER_START_LOG_MSG = "To see the GUI go to: http://127.0.0.1:18188"
MODEL_SERVER_ERROR_LOG_MSGS = [
    "MetadataIncompleteBuffer",  # This error is emitted when the downloaded model is corrupted
    "Value not in list: unet_name",  # This error is emitted when the model file is not there at all
]


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s[%(levelname)-5s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__file__)


async def generate_response(
    request: web.Request, response: ClientResponse
) -> Union[web.Response, web.StreamResponse]:
    _ = request
    match response.status:
        case 200:
            log.debug("SUCCESS")
            res = await response.json()
            if "output" not in res:
                return web.json_response(
                    data=dict(error="there was an error in the workflow"),
                    status=422,
                )
            image_paths = [path["local_path"] for path in res["output"]["images"]]
            if not image_paths:
                return web.json_response(
                    data=dict(error="workflow did not produce any images"),
                    status=422,
                )
            images = []
            for image_path in image_paths:
                async with await open_file(image_path, mode="rb") as f:
                    contents = await f.read()
                    images.append(
                        f"data:image/png;base64,{base64.b64encode(contents).decode('utf-8')}"
                    )
            return web.json_response(data=dict(images=images))
        case code:
            log.debug("SENDING RESPONSE: ERROR: unknown code")
            return web.Response(status=code)


async def handle_workflow(self: EndpointHandler, request: web.Request):
    data = await request.json()
    try:
        auth_data, payload = self.get_data_from_request(data)
    except JsonDataException as e:
        return web.json_response(data=e.message, status=422)
    log.debug(f"got request, {auth_data.reqnum}")
    try:
        return await backend.handle_request(
            handler=self, auth_data=auth_data, payload=payload, request=request
        )
    except Exception as e:
        log.debug(f"Exception in main handler loop {e}")
        return web.Response(status=500)


@dataclasses.dataclass
class DefaultComfyWorkflowHandler(EndpointHandler[DefaultComfyWorkflowData]):

    @property
    def endpoint(self) -> str:
        return "/rp-api/runsync"

    @classmethod
    def payload_cls(cls) -> Type[DefaultComfyWorkflowData]:
        return DefaultComfyWorkflowData

    def make_benchmark_payload(self) -> DefaultComfyWorkflowData:
        return DefaultComfyWorkflowData.for_test()

    async def generate_response(
        self, request: web.Request, response: ClientResponse
    ) -> Union[web.Response, web.StreamResponse]:
        return await generate_response(request, response)

    async def handle_request(
        self, request: web.Request
    ) -> Union[web.Response, web.StreamResponse]:
        return await handle_workflow(self, request=request)


@dataclasses.dataclass
class CustomComfyWorkflowHandler(EndpointHandler[CustomComfyWorkflowData]):

    @property
    def endpoint(self) -> str:
        return "/rp-api/runsync"

    @classmethod
    def payload_cls(cls) -> Type[CustomComfyWorkflowData]:
        return CustomComfyWorkflowData

    def make_benchmark_payload(self) -> CustomComfyWorkflowData:
        return CustomComfyWorkflowData.for_test()

    async def generate_response(
        self, request: web.Request, response: ClientResponse
    ) -> Union[web.Response, web.StreamResponse]:
        return await generate_response(request, response)

    async def handle_request(
        self, request: web.Request
    ) -> Union[web.Response, web.StreamResponse]:
        return await handle_workflow(self, request=request)


backend = Backend(
    model_server_url=MODEL_SERVER_URL,
    model_log_file=os.environ["MODEL_LOG"],
    allow_parallel_requests=False,
    benchmark_handler=DefaultComfyWorkflowHandler(
        benchmark_runs=3, benchmark_words=100
    ),
    log_actions=[
        (LogAction.ModelLoaded, MODEL_SERVER_START_LOG_MSG),
        (LogAction.Info, "Downloading:"),
        *[
            (LogAction.ModelError, error_msg)
            for error_msg in MODEL_SERVER_ERROR_LOG_MSGS
        ],
    ],
)


async def handle_ping(_):
    return web.Response(body="pong")


routes = [
    web.post("/prompt", DefaultComfyWorkflowHandler().handle_request),
    web.post("/custom-workflow", CustomComfyWorkflowHandler().handle_request),
    web.get("/ping", handle_ping),
]

if __name__ == "__main__":
    start_server(backend, routes)

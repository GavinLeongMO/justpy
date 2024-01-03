"""
Created on 2022-09-02

@author: wf
"""
import asyncio
import fnmatch
import inspect
import json
import logging
import os
import pathlib
import socket
from enum import Enum

import psutil
import sys
import traceback
import typing
import uuid
from sys import platform
from multiprocessing import Process
from threading import Thread
from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route
from starlette.endpoints import HTTPEndpoint
from starlette.responses import HTMLResponse, JSONResponse,PlainTextResponse, Response
from starlette.templating import Jinja2Templates

from jpcore.component import Component
import jpcore.jpconfig as jpconfig
from jpcore.justpy_config import  JpConfig
from jpcore.template import Context
from jpcore.webpage import WebPage
from itsdangerous import Signer

# typing shorthand notations
WebPage_or_Response = typing.Union[typing.Union[WebPage, Response], typing.Awaitable[typing.Union[WebPage, Response]]]
Jp_Route_Callback = typing.Union[
    typing.Callable[[typing.Optional[Request]], WebPage_or_Response],
    typing.Callable[[], WebPage_or_Response]
]
# TODO refactor to object oriented version where this is a property of some instance of some class
cookie_signer = Signer(str(jpconfig.SECRET_KEY))

def create_component_file_list():
    """
    create the component file list
    """
    file_list = []
    component_dir = os.path.join(jpconfig.STATIC_DIRECTORY, "components")
    if os.path.isdir(component_dir):
        for file in os.listdir(component_dir):
            # [TODO]
            # if fnmatch.fnmatch(file, "*.js"):
            if fnmatch.fnmatch(file, "component_generator.js") or fnmatch.fnmatch(file, "html_component.js") or fnmatch.fnmatch(file, "quasar_component.js"):
                file_list.append(f"/components/{file}")
    return file_list


component_file_list = create_component_file_list()
grand_parent = pathlib.Path(__file__).parent.parent.resolve()
template_dir=f"{grand_parent}/justpy/templates"

lib_dir = os.path.join(template_dir, "js", jpconfig.FRONTEND_ENGINE_TYPE)
# remove .js extension
# [TODO]
# jpconfig.FRONTEND_ENGINE_LIBS = [fn[:-3]
#                         for fn in os.listdir(lib_dir)
#                         if fnmatch.fnmatch(fn, "*.js")
#                         ]
jpconfig.FRONTEND_ENGINE_LIBS = [fn[:-3]
                        for fn in os.listdir(lib_dir)
                        if fnmatch.fnmatch(fn, "component_generator.js") or fnmatch.fnmatch(fn, "html_component.js") or fnmatch.fnmatch(fn, "quasar_component.js")
                        ]

TEMPLATES_DIRECTORY = JpConfig.config(
    "TEMPLATES_DIRECTORY", cast=str, default=template_dir
)

templates = Jinja2Templates(directory=TEMPLATES_DIRECTORY)

template_options = {
    "tailwind": jpconfig.TAILWIND,
    "quasar": jpconfig.QUASAR,
    "quasar_version": jpconfig.QUASAR_VERSION,
    "highcharts": jpconfig.HIGHCHARTS,
    "aggrid": jpconfig.AGGRID,
    "aggrid_enterprise": jpconfig.AGGRID_ENTERPRISE,
    "static_name": jpconfig.STATIC_NAME,
    "component_file_list": component_file_list,
    "no_internet": jpconfig.NO_INTERNET,
    "katex": jpconfig.KATEX,
    "plotly": jpconfig.PLOTLY,
    "bokeh": jpconfig.BOKEH,
    "deckgl": jpconfig.DECKGL,
    "vega": jpconfig.VEGA,
}


class CommunicationType(Enum):
    """
    communication types supported by justpy
    """
    WEBSOCKET = 0
    AJAX = 1


async def handle_event(
        data_dict: dict,
        com_type: CommunicationType = CommunicationType.WEBSOCKET,
        page_event: bool = False
) -> typing.Optional[dict]:
    """
    handle the given event
    
    Args:
        data_dict(dict): the dict with the data
        com_type(CommunicationType):  the communication type - default: WEBSOCKET
        page_event(bool): if True handle as a page event
    """
    logging.info(
        "%s %s %s", "In event handler:", com_type.WEBSOCKET.name, str(data_dict)
    )
    event_data = data_dict["event_data"]
    page_id = event_data["page_id"]
    try:
        p = WebPage.instances[page_id]
    except:
        logging.warning("No page to load")
        return
    event_data["page"] = p
    if com_type is CommunicationType.WEBSOCKET:
        websocket_id = event_data["websocket_id"]
        event_data["websocket"] = WebPage.sockets[page_id][websocket_id]
    # The page_update event is generated by the reload_interval Ajax call
    if event_data["event_type"] == "page_update":
        build_list = p.build_list()
        return {"type": "page_update", "data": build_list}

    if page_event:
        c = p
    else:
        component_id = event_data["id"]
        c = Component.instances.get(component_id, None)
        if c is not None:
            event_data["target"] = c
        else:
            logging.warning(
                f"component with id {component_id} doesn't exist (anymore ...) it might have been deleted before the event handling was triggered"
            )

    try:
        if c is not None:
            before_result = await c.run_event_function("before", event_data, True)
    except:
        pass
    try:
        if c is not None:
            if hasattr(c, "on_" + event_data["event_type"]):
                event_result = await c.run_event_function(
                    event_data["event_type"], event_data, True
                )
            else:
                event_result = None
                logging.debug(f"{c} has no {event_data['event_type']} event handler")
        else:
            event_result = None
        logging.debug(f"Event result:{event_result}")
    except Exception as e:
        # raise Exception(e)
        if jpconfig.CRASH:
            print(traceback.format_exc())
            sys.exit(1)
        event_result = None
        # logging.info('%s %s', 'Event result:', '\u001b[47;1m\033[93mAttempting to run event handler:' + str(e) + '\033[0m')
        logging.info(
            "%s %s",
            "Event result:",
            "\u001b[47;1m\033[93mError in event handler:\033[0m",
        )
        logging.info("%s", traceback.format_exc())

    # If page is not to be updated, the event_function should return anything but None
    if event_result is None:
        if com_type is CommunicationType.WEBSOCKET:  # WebSockets communication
            if jpconfig.LATENCY:
                await asyncio.sleep(jpconfig.LATENCY / 1000)
            await p.update()
        elif com_type is CommunicationType.AJAX:  # Ajax communication
            build_list = p.build_list()
    try:
        if c is not None:
            after_result = await c.run_event_function("after", event_data, True)
    except:
        pass
    if com_type is CommunicationType.AJAX and event_result is None:
        dict_to_send = {
            "type": "page_update",
            "data": build_list,
            "page_options": {
                "display_url": p.display_url,
                "title": p.title,
                "redirect": p.redirect,
                "open": p.open,
                "favicon": p.favicon,
            },
        }
        return dict_to_send

# https://stackoverflow.com/questions/57412825/how-to-start-a-uvicorn-fastapi-in-background-when-testing-with-pytest
# https://github.com/encode/uvicorn/discussions/1103
# https://stackoverflow.com/questions/68603658/how-to-terminate-a-uvicorn-fastapi-application-cleanly-with-workers-2-when
class JustpyApp(FastAPI):
    """
    a justpy application is a special Starlette application
    
      uses starlette Routing

    see
       https://www.starlette.io/routing/

       https://github.com/encode/starlette/blob/master/starlette/routing.py
    """
    # @Todo - legacy for SetRoute 
    app=None

    def __init__(self,**kwargs):
        # https://www.starlette.io/applications/
        FastAPI.__init__(self,**kwargs)
        # @Todo - legacy for SetRoute 
        JustpyApp.app=self
    
    def route_as_text(self,route):
        """
        get a string representation of the given route
        """
        text= f"{route.__class__.__name__}(name: {route.name}, path: {route.path}, format: {route.path_format},  regex: {route.path_regex})"
        if isinstance(route,Route):
            text+=f"func: {route.endpoint.__name__}"
        return text
    
    def add_jproute(
            self,
            path: str,
            wpfunc: Jp_Route_Callback,
            name: typing.Optional[str] = None,
            methods: typing.Optional[typing.List[str]] = None
    ) -> typing.Callable:
        """
        add a route for the given Webpage returning func
        
        Args:
            path(str): the path to use as route
            wpfunc(typing.Callable): a Webpage returning func
            name(str): the name of the route
            methods:
        """
        endpoint=self.response(wpfunc)
        if name is None:
            name=wpfunc.__name__
        self.router.add_route(path, endpoint, methods=methods, name=name, include_in_schema=False)
        return endpoint
    
    def jproute(
            self,
            path: str,
            name: typing.Optional[str] = None,
            methods: typing.Optional[typing.List[str]] = None
    ) -> typing.Callable:  # pragma: nocover
        """ 
        justpy route decorator
        
        function will we "wrapped" as a response and a route added
        
        Args:
            path: the path to use as route
            name: the name of the route
            methods:
        """
        
        def routeResponse(func: typing.Callable) -> typing.Callable:
            """
            decorator for the given func
            
            Args:
                func(typing.Callable): the function to convert to a reponse
                
            Returns:
                Callable: an endpoint that has been routed
            
            """
            endpoint = self.add_jproute(path=path, name=name, wpfunc=func, methods=methods)
            self.route(path)
            return endpoint
        
        return routeResponse
    
    def response(self, func: Jp_Route_Callback) -> typing.Callable:
        """
        response decorator converts a function to a response
        
        see also https://github.com/justpy-org/justpy/issues/532
        castAsEndPoint
        
        Args:
            func(typing.Callable): the function (returning a WebPage) to convert to a response

        Returns:

        """
        async def funcResponse(request: Request) -> Response:
            """
            decorator function to apply the function to the request and
            return it as a response
            
            Args:
                request(Request): the request to apply the function to
                
            Returns:
                Response: a Response applying the justpy infrastructure
            
            """
            new_cookie = self.handle_session_cookie(request)
            wp_or_response = await self.get_page_for_func(request, func)
            if isinstance(wp_or_response, WebPage):
                wp = wp_or_response
                response = self.get_response_for_load_page(request, wp)
                response = self.set_cookie(request, response, wp, new_cookie)
            else:
                response = wp_or_response
            if jpconfig.LATENCY:
                await asyncio.sleep(jpconfig.LATENCY / 1000)
            return response
    
        # return the decorated function, thus allowing access to the func
        # parameter in the funcResponse later when applied 
        return funcResponse

    async def get_page_for_func(
            self,
            request: Request,
            func: Jp_Route_Callback
    ) -> typing.Union[WebPage, Response]:
        """
        get the Webpage for the given func

        Args:
            request: the request to pass to the given function
            func: the function
            
        Returns:
            WebPage: the Webpage returned by the given function
        """
        # @TODO - get rid of the global func_to_run concept that isn't
        # in scope here (anymore) anyways
        func_to_run = func
        func_parameters = len(inspect.signature(func_to_run).parameters)
        assert (func_parameters < 2), f"Function {func_to_run.__name__} cannot have more than one parameter"
        if inspect.iscoroutinefunction(func_to_run):
            if func_parameters == 1:
                load_page = await func_to_run(request)
            else:
                load_page = await func_to_run()
        else:
            if func_parameters == 1:
                load_page = func_to_run(request)
            else:
                load_page = func_to_run()
        return load_page

    def get_response_for_load_page(self, request: Request, load_page: WebPage) -> Response:
        """
        get the response for the given webpage
        
        Args:
            request(Request): the request to handle
            load_page(WebPage): the webpage to wrap with justpy and  
            return as a full HtmlResponse
        
        Returns:
            Response: the response for the given load_page
        """
        page_type = type(load_page)
        assert issubclass(
            page_type, WebPage
        ), f"Function did not return a web page but a {page_type.__name__}"
        if len(load_page) == 0 and not load_page.html:
            error_html="""<span style="color:red">Web page is empty - you might want to add components</span>"""
            return HTMLResponse(error_html, 500)
        page_options = {
            "reload_interval": load_page.reload_interval,
            "body_style": load_page.body_style,
            "body_classes": load_page.body_classes,
            "css": load_page.css,
            "head_html": load_page.head_html,
            "body_html": load_page.body_html,
            "display_url": load_page.display_url,
            "dark": load_page.dark,
            "title": load_page.title,
            "redirect": load_page.redirect,
            "highcharts_theme": load_page.highcharts_theme,
            "debug": load_page.debug,
            "events": load_page.events,
            "favicon": load_page.favicon if load_page.favicon else jpconfig.FAVICON,
        }
        if load_page.use_cache:
            page_dict = load_page.cache
        else:
            page_dict = load_page.build_list()
        template_options["tailwind"] = load_page.tailwind
        context = {
            "request": request,
            "page_id": load_page.page_id,
            "justpy_dict": json.dumps(page_dict, default=str),
            "use_websockets": json.dumps(WebPage.use_websockets),
            "options": template_options,
            "page_options": page_options,
            "html": load_page.html,
            "frontend_engine_type": jpconfig.FRONTEND_ENGINE_TYPE,
            "frontend_engine_libs": jpconfig.FRONTEND_ENGINE_LIBS
        }
        # wrap the context in a context object to make it available
        context_obj = Context(context)
        context["context_obj"] = context_obj
        response = templates.TemplateResponse(load_page.template_file, context)
        return response
    
    def handle_session_cookie(self, request) -> typing.Union[bool, Response]:
        """
        handle the session cookie for this request
        
        Returns:
            True if a new cookie and session has been created
        """
        # Handle web requests
        session_cookie = request.cookies.get(jpconfig.SESSION_COOKIE_NAME)
        new_cookie=None
        if jpconfig.SESSIONS:
            new_cookie = False
            if session_cookie:
                try:
                    session_id = cookie_signer.unsign(session_cookie).decode("utf-8")
                except:
                    return PlainTextResponse("Bad Session")
                request.state.session_id = session_id
                request.session_id = session_id
            else:
                # Create new session_id
                request.state.session_id = str(uuid.uuid4().hex)
                request.session_id = request.state.session_id
                new_cookie = True
                logging.debug(f"New session_id created: {request.session_id}")
        return new_cookie
    
    def set_cookie(
            self,
            request: Request,
            response: Response,
            load_page: WebPage,
            new_cookie: typing.Union[bool, Response]
    ) -> Response:
        """
        set the cookie_value
        
        Args:
            request: the request 
            response: the response to be sent
            load_page(WebPage): the WebPage to handle
            new_cookie(bool|Response): True if there is a new cookie. Or Response if cookie was invalid
        """
        if isinstance(new_cookie, Response):
            return new_cookie
        if jpconfig.SESSIONS and new_cookie:
            cookie_value = cookie_signer.sign(request.state.session_id)
            cookie_value = cookie_value.decode("utf-8")
            response.set_cookie(
                jpconfig.SESSION_COOKIE_NAME, cookie_value, max_age=jpconfig.COOKIE_MAX_AGE, httponly=True
            )
            for k, v in load_page.cookies.items():
                response.set_cookie(k, v, max_age=jpconfig.COOKIE_MAX_AGE, httponly=True)
        return response


class JustpyAjaxEndpoint(HTTPEndpoint):
    """
    Justpy specific HTTPEndpoint/app (ASGI application)
    """
    
    def __init__(self,scope,receive,send):
        """ 
        constructor
        """
        HTTPEndpoint.__init__(self,scope, receive, send)

    async def post(self, request):
        """
        Handles post method. Used in Ajax mode for events when websockets disabled
        
        Args:
            request(Request): the request to handle
        """
        data_dict = await request.json()
        # {'type': 'event', 'event_data': {'event_type': 'beforeunload', 'page_id': 0}}
        if data_dict["event_data"]["event_type"] == "beforeunload":
            return await self.on_disconnect(data_dict["event_data"]["page_id"])

        session_cookie = request.cookies.get(jpconfig.SESSION_COOKIE_NAME)
        if jpconfig.SESSIONS and session_cookie:
            session_id = cookie_signer.unsign(session_cookie).decode("utf-8")
            data_dict["event_data"]["session_id"] = session_id

        # data_dict['event_data']['session'] = request.session
        msg_type = data_dict["type"]
        data_dict["event_data"]["msg_type"] = msg_type
        page_event = True if msg_type == "page_event" else False
        result = await handle_event(data_dict, com_type=CommunicationType.AJAX, page_event=page_event)
        if result:
            if jpconfig.LATENCY:
                await asyncio.sleep(jpconfig.LATENCY / 1000)
            return JSONResponse(result)
        else:
            return JSONResponse(False)

    async def on_disconnect(self, page_id):
        logging.debug(f"In disconnect Homepage")
        await WebPage.instances[
            page_id
        ].on_disconnect()  # Run the specific page disconnect function
        return JSONResponse(False)


class JustpyServer:
    """
    a justpy Server


    """

    def __init__(
        self,
        host: str = None,
        port: int = 10000,
        sleep_time: float = 0.5,
        mode: str = None,
        debug: bool = False,
    ):
        """
        constructor

        Args:
            port(int): the port
            host(str): the host
            sleep_time(float): the time to sleep after server process was started
            mode(str): None, direct or process. If None direct is used on MacOs and process on other platforms.
                process mode will run the task as a process and kill it with psutils, direct will use threading and
                trying shutdown with uvicorns built in shutdown method (as of 2022-09 this leads to error messages since
                the starlette router is not shutdown properly)
            debug(bool): if True switch debugging on
        """
        if host is None:
            host=JustpyServer.getDefaultHost()
        self.host = host
        self.port = port
        self.sleep_time = sleep_time
        self.server = None
        self.proc = None
        self.thread = None
        if mode is None:
            if platform == "darwin":
                mode = "direct"
            else:
                mode = "process"
        self.mode = mode
        self.debug = debug
        self.running = False
        
    @classmethod
    def getDefaultHost(cls) -> str:
        """
        get the default host as the fully qualifying hostname
        of the computer the server runs on
        
        Returns:
            str: the hostname
        """
        host = socket.getfqdn() 
        # work around https://github.com/python/cpython/issues/79345
        if host=="1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.ip6.arpa":
            host="localhost"
            # host="127.0.0.1"
        return host

    async def start(self, wpfunc, websockets: bool = True, **kwargs):
        """
        start a justpy server for the given webpage function wpfunc

        Args:
            wpfunc: the (async) function for the webpage
            websockets: If True use websockets for server/client communication
            kwargs:
        """
        # this import is actually calling code ...
        import justpy as jp

        if self.mode == "direct":
            jp.justpy(
                wpfunc,
                host=self.host,
                port=self.port,
                start_server=False,
                websockets=websockets,
                kwargs=kwargs,
            )
            await asyncio.sleep(self.sleep_time)  # time for the server to start
            self.server = jp.get_server()
            self.thread = Thread(target=self.server.run)
            self.thread.start()
        elif self.mode == "process":
            needed_kwargs = {
                "host": self.host,
                "port": self.port,
                "start_server": True,
            }
            kwargs = {**needed_kwargs, **kwargs}
            self.proc = Process(
                target=jp.justpy,
                args=(wpfunc,),
                kwargs=kwargs,
            )
            self.proc.daemon = True
            self.proc.start()
        await asyncio.sleep(self.sleep_time)  # time for the server to start

    async def stop(self):
        """
        stop the server
        """
        # self.cancel()
        # https://stackoverflow.com/a/59089890/1497139
        # tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        # [task.cancel() for task in tasks]
        # await asyncio.gather(*tasks)
        # https://stackoverflow.com/questions/58133694/graceful-shutdown-of-uvicorn-starlette-app-with-websockets
        if self.server:
            # await asyncio.wait([jp.app.router.shutdown()],timeout=self.sleep_time)
            self.server.should_exit = True
            self.server.force_exit = True
            await asyncio.sleep(self.sleep_time)
            await self.server.shutdown()
        if self.thread:
            self.thread.join(timeout=self.sleep_time)
        if self.proc:
            pid = self.proc.pid
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                child.terminate()
            self.proc.terminate()

    def next_server(self) -> 'JustpyServer':
        """
        get another similar server with the port number incremented by one
        """
        next_server = JustpyServer(
            port=self.port + 1,
            host=self.host,
            sleep_time=self.sleep_time,
            mode=self.mode,
            debug=self.debug,
        )
        return next_server

    def get_url(self, path: str) -> str:
        """
        get the url for the given path

        Args:
            path(str): the path
        Returns:
            str: the url for the path

        """
        url = f"http://{self.host}:{self.port}{path}"
        return url
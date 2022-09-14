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
import re
import psutil
import sys
import traceback
import typing
import uuid
from sys import platform
from multiprocessing import Process
from threading import Thread
from starlette.applications import Starlette
from starlette.routing import Route,Match
from starlette.endpoints import HTTPEndpoint
from starlette.responses import HTMLResponse, JSONResponse,PlainTextResponse, Response
from starlette.templating import Jinja2Templates

from jpcore.component import Component
from jpcore.justpy_config import config, AGGRID, AGGRID_ENTERPRISE,BOKEH,COOKIE_MAX_AGE, CRASH
from jpcore.justpy_config import DECKGL, FAVICON, HIGHCHARTS,HTML_404_PAGE,KATEX, LATENCY
from jpcore.justpy_config import NO_INTERNET, PLOTLY, SECRET_KEY, SESSION_COOKIE_NAME, SESSIONS
from jpcore.justpy_config import STATIC_DIRECTORY,STATIC_NAME
from jpcore.justpy_config import QUASAR, QUASAR_VERSION,TAILWIND, VEGA
from jpcore.template import Context
from jpcore.webpage import WebPage
from itsdangerous import Signer

# TODO refacto to object oriented version where this is a property of some instance of some class
cookie_signer = Signer(str(SECRET_KEY))

def create_component_file_list():
    file_list = []
    component_dir = os.path.join(STATIC_DIRECTORY, "components")
    if os.path.isdir(component_dir):
        for file in os.listdir(component_dir):
            if fnmatch.fnmatch(file, "*.js"):
                file_list.append(f"/components/{file}")
    return file_list


component_file_list = create_component_file_list()
grand_parent = pathlib.Path(__file__).parent.parent.resolve()
template_dir=f"{grand_parent}/justpy/templates"

TEMPLATES_DIRECTORY = config(
    "TEMPLATES_DIRECTORY", cast=str, default=template_dir
)

templates = Jinja2Templates(directory=TEMPLATES_DIRECTORY)

template_options = {
    "tailwind": TAILWIND,
    "quasar": QUASAR,
    "quasar_version": QUASAR_VERSION,
    "highcharts": HIGHCHARTS,
    "aggrid": AGGRID,
    "aggrid_enterprise": AGGRID_ENTERPRISE,
    "static_name": STATIC_NAME,
    "component_file_list": component_file_list,
    "no_internet": NO_INTERNET,
    "katex": KATEX,
    "plotly": PLOTLY,
    "bokeh": BOKEH,
    "deckgl": DECKGL,
    "vega": VEGA,
}

async def handle_event(data_dict, com_type=0, page_event=False):
    # com_type 0: websocket, con_type 1: ajax
    connection_type = {0: "websocket", 1: "ajax"}
    logging.info(
        "%s %s %s", "In event handler:", connection_type[com_type], str(data_dict)
    )
    event_data = data_dict["event_data"]
    try:
        p = WebPage.instances[event_data["page_id"]]
    except:
        logging.warning("No page to load")
        return
    event_data["page"] = p
    if com_type == 0:
        event_data["websocket"] = WebPage.sockets[event_data["page_id"]][
            event_data["websocket_id"]
        ]
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
        if CRASH:
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
        if com_type == 0:  # WebSockets communication
            if LATENCY:
                await asyncio.sleep(LATENCY / 1000)
            await p.update()
        elif com_type == 1:  # Ajax communication
            build_list = p.build_list()
    try:
        if c is not None:
            after_result = await c.run_event_function("after", event_data, True)
    except:
        pass
    if com_type == 1 and event_result is None:
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
class JustpyApp(Starlette):
    """
    a justpy application is a special Starlette application
    
      uses starlette Routing

    see
       https://www.starlette.io/routing/

       https://github.com/encode/starlette/blob/master/starlette/routing.py
    """
    app=None

    def __init__(self,**kwargs):
        # https://www.starlette.io/applications/
        Starlette.__init__(self,**kwargs)
        JustpyApp.app=self
        
    def get_func_for_request(self, request):
        """
        Get the function for the given request

        Args:
            request: the starlette request

        Returns:
            Callable: the function that is bound to the path of the given request
        """
        scope = request.scope
        return self.get_func_for_scope(scope)
    
    def get_func_for_scope(self, scope):
        """
        Get the function (endpoint in starlette jargon) for the given scope

        Args:
            path: the path to check
        Returns:
            Callable: the function that is bound to the given path
        """
        for route in self.getRoutesByPriority():
            if isinstance(route,Route):
                match, _matchScope = route.matches(scope)
                if match is not Match.NONE:
                    func_to_run = route.endpoint
                    return func_to_run
        return None
    
    def prioritize_routes(self):
        """
        modify the routes priority
        """
        self.router.routes=self.getRoutesByPriority()
    
    def getRoutesByPriority(self):
        """
        get the routes by priority
        """
        routes=self.router.routes
        routes_by_priority=[]
        homepage_names=["default","Homepage"]
        homepages=[]
        for route in routes:
            if isinstance(route,Route) and route.name and route.name in homepage_names:
                homepages.append(route)
            else:
                routes_by_priority.append(route)
        for homepage in homepages:
            routes_by_priority.append(homepage)
        return routes_by_priority
    
    def route_as_text(self,route):
        """
        get a string representation of the given route
        """
        text= f"{route.__class__.__name__}(name: {route.name}, path: {route.path}, format: {route.path_format},  regex: {route.path_regex})"
        if isinstance(route,Route):
            text+=f"func: {route.endpoint.__name__}"
        return text
    
    def jproute(self,
        path: str,
        name: typing.Optional[str] = None)-> typing.Callable:  # pragma: nocover
        """ 
        justpy route decorator
        
        function will we "wrapped" as a response and a route added
        
        Args:
            func(typing.Callable): the function to convert to a reponse
        """
        
        def routeResponse(func:typing.Callable)-> typing.Callable:
            """
            decorator for the given func
            
            Args:
                func(typing.Callable)
                
            Returns:
                Callable: an endpoint that has been routed
            
            """
            endpoint=self.response(func)
            self.router.add_route(
                path,
                endpoint,
                name=name if name is not None else func.__name__,
                include_in_schema=False,
            )
            self.route(path)
            return endpoint
        
        return routeResponse
    
    def response(self,func:typing.Callable):
        """
        response decorator converts a function to a response
        
        Args:
            func(typing.Callable): the function to convert to a reponse
        """
        def funcResponse(request)->HTMLResponse:
            """
            decorator function to apply the function to the request and
            return it as a response
            
            Args:
                request(Request): the request to apply the function to
                
            Returns:
                Response: a HTMLResponse applying the justpy infrastructure
            
            """
            new_cookie=self.handle_session_cookie(request)
            wp=func(request)
            response=self.get_response_for_load_page(request, wp)
            self.set_cookie(request, response, wp, new_cookie)
            return response
    
        # return the decorated function, thus allowing access to the func
        # parameter in the funcResponse later when applied 
        return funcResponse
    
    def get_response_for_load_page(self,request,load_page):
        """
        get the response for the given webpage
        
        Args:
            request(Request): the request to handle
            load_page(WebPage): the webpage to wrap with justpy and  
            return as a full HtmlResponse
        
        Returns:
            Reponse: the response for the given load_page
        """
        page_type = type(load_page)
        assert issubclass(
            page_type, WebPage
        ), f"Function did not return a web page but a {page_type.__name__}"
        assert (
            len(load_page) > 0 or load_page.html
        ), "\u001b[47;1m\033[93mWeb page is empty, add components\033[0m"
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
            "favicon": load_page.favicon if load_page.favicon else FAVICON,
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
        }
        # wrap the context in a context object to make it available
        context_obj = Context(context)
        context["context_obj"] = context_obj
        response = templates.TemplateResponse(load_page.template_file, context)
        return response
    
    def handle_session_cookie(self,request)->bool:
        """
        handle the session cookie for this request
        
        Returns:
            True if a new cookie and session has been created
        """
        # Handle web requests
        session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
        new_cookie=None
        if SESSIONS:
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
    
    def set_cookie(self,request,response,load_page,new_cookie:bool):
        """
        set the cookie_value
        
        Args:
            request: the request 
            response: the response to be sent
            load_page(WebPage): the WebPage to handle
            new_cookie(bool): True if there is a new cookie
        """
        if SESSIONS and new_cookie:
            cookie_value = cookie_signer.sign(request.state.session_id)
            cookie_value = cookie_value.decode("utf-8")
            response.set_cookie(
                SESSION_COOKIE_NAME, cookie_value, max_age=COOKIE_MAX_AGE, httponly=True
            )
            for k, v in load_page.cookies.items():
                response.set_cookie(k, v, max_age=COOKIE_MAX_AGE, httponly=True)

class JustpyEndpoint(HTTPEndpoint):
    """
    Justpy specific HTTPEndpoint/app (ASGI application)
    """
    
    def __init__(self,scope,receive,send):
        """ 
        constructor
        """
        HTTPEndpoint.__init__(self,scope, receive, send)
        
    async def get(self, request):
        """
        main justpy request handler 
        """
        app=request.app
        new_cookie=app.handle_session_cookie(request)
        response=await self.get_response_for_request(request,new_cookie)
        if LATENCY:
            await asyncio.sleep(LATENCY / 1000)
        return response
    
    async def get_response_for_request(self,request,new_cookie:bool):
        """
        get the page for the given request
        
        Args:
            request: the request to handle
            new_cookie(bool): True if a new cookie needs to be set
            
        Returns:
            Response: a Response for the request
        """
        from justpy.routing import JpRoute
        func = JpRoute.get_func_for_request(request)
        #func = request.get_func_for_request(request)
        if not func:
            return HTMLResponse(content=HTML_404_PAGE, status_code=404)
        load_page=await self.get_page_for_func(request,func)
        # @TODO does this really still make sense after refactoring the routing?
        if isinstance(load_page, Response):
            logging.debug("Returning raw starlette.responses.Response.")
            return load_page
        # @TODO - shouldn't we return proper error response pages instead
        # of relying on the exception handling via assertions here?
        app=request.app
        response=app.get_response_for_load_page(request,load_page) 
        app.set_cookie(request,response,load_page,new_cookie)
        return response
    
    async def get_page_for_func(self,request,func):
        """
        get the Webpage for the given func
        
        Args:
            request: the request to pass to the given function
            func: the function
        """
        # @TODO - get rid of the global func_to_run concept that isn't
        # in scope here (anymore) anyways
        func_to_run = func
        func_parameters = len(inspect.signature(func_to_run).parameters)
        assert (
            func_parameters < 2
        ), f"Function {func_to_run.__name__} cannot have more than one parameter"
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
    
        
    async def post(self, request):
        # Handles post method. Used in Ajax mode for events when websockets disabled
        if request["path"] == "/zzz_justpy_ajax":
            data_dict = await request.json()
            # {'type': 'event', 'event_data': {'event_type': 'beforeunload', 'page_id': 0}}
            if data_dict["event_data"]["event_type"] == "beforeunload":
                return await self.on_disconnect(data_dict["event_data"]["page_id"])

            session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
            if SESSIONS and session_cookie:
                session_id = cookie_signer.unsign(session_cookie).decode("utf-8")
                data_dict["event_data"]["session_id"] = session_id

            # data_dict['event_data']['session'] = request.session
            msg_type = data_dict["type"]
            data_dict["event_data"]["msg_type"] = msg_type
            page_event = True if msg_type == "page_event" else False
            result = await handle_event(data_dict, com_type=1, page_event=page_event)
            if result:
                if LATENCY:
                    await asyncio.sleep(LATENCY / 1000)
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
            host = socket.getfqdn()
            # host="127.0.0.1"
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

    async def start(self, wpfunc, **kwargs):
        """
        start a justpy server for the given webpage function wpfunc

        Args:
            wpfunc: the (async) function for the webpage


        """
        # this import is actually calling code ...
        import justpy as jp

        if self.mode == "direct":
            jp.justpy(
                wpfunc,
                host=self.host,
                port=self.port,
                start_server=False,
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

    def next_server(self):
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

    def get_url(self, path):
        """
        get the url for the given path

        Args:
            path(str): the path
        Returns:
            str: the url for the path

        """
        url = f"http://{self.host}:{self.port}{path}"
        return url


class JustpyDemoApp:
    """
    a justpy application
    """

    def __init__(self, pymodule_file, wp: typing.Callable = None, **kwargs):
        """
        Args:
            pymodule_file(str): the python module path where the app resides
            wp(Callable): the webpage function to call
            **kwargs: further keyword arguments to pass to the webpage function
        """
        self.pymodule_file = pymodule_file
        with open(self.pymodule_file, "r") as sourcefile:
            self.source = sourcefile.read()
            self.check_demo()
        self.wp = wp
        self.kwargs = kwargs

    def check_demo(self):
        """
        Check whether this is a demo
        """
        self.is_demo = False
        if "Demo(" or "Demo (" in self.source:
            endpoint_match = re.search(
                """Demo[ ]?[(]["'](.*)["'],\s*(.*?)(,.*)*[)]""", self.source
            )
            if endpoint_match:
                self.description = endpoint_match.group(1)
                self.endpoint = endpoint_match.group(2)
                # jenkins could have /var/lib/jenkins/jobs/justpy/workspace/examples/charts_tutorial/pandas/women_majors2.py is not a demo
                module_match = re.search(
                    "justpy/(workspace/)?(examples/.*)[.]py", self.pymodule_file
                )
                if module_match:
                    self.pymodule = module_match.group(2)
                    self.pymodule = self.pymodule.replace("/", ".")
                    self.is_demo = not "lambda" in self.endpoint
                return

    async def start(self, server: JustpyServer):
        """
        Start me on the given server

        Args:
            server(JustpyServer): the server to start
        """
        if self.wp is None:
            raise Exception(f"can't start {self.pymodule_file} -wp/endoint is None")
        return await server.start(self.wp)

    def __str__(self):
        text = f"{self.pymodule}:{self.endpoint}:{self.description}"
        return text

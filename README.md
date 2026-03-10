<p align="center">
  <img src="https://raw.githubusercontent.com/MarkoSterk/PyJolt/refs/heads/main/src/pyjolt/graphics/pyjolt_logo.png" alt="PyJolt Logo" width="200">
</p>

# PyJolt - async first python web framework

This framework is in its alpha stage and will probably see some major changes/improvements until it reaches
the beta stage for testing. Any eager tinkerers are invited to test the framework in its alpha stage and provide feedback.

## Getting started

### From PyPi with uv or pip

In your project folder
```
uv init
uv add pyjolt
```
or with pip
```
pip install pyjolt
```
We strongly recommend using uv for dependency management.

The above command will install pyjolt with basic dependencies. For some subpackages you will need additional dependencies. Options are:

**Caching**
```
uv add "pyjolt[cache]"
```

**Scheduler**
```
uv add "pyjolt[scheduler]"
```

**AI interface** (experimental)
```
uv add "pyjolt[ai_interface]"
```

**Full install**
```
uv add "pyjolt[full]"
```

##Getting started with project template

```
uv run pyjolt new-project
```

or with pip (don't forget to activate the virtual environment)
```
pipx pyjolt new-project
```

This will create a template project structure which you can use to get started.

## Blank start

If you wish to start without the template you can do that ofcourse. However, we recommend you have a look at the template structure to see how to organize your project. There is also an example project in the "examples/dev" folder of this GitHub repo where you can see the app structure and recommended patterns.

A minimum app example would be:

```
#app/__init__.py <-- in the app folder

from app.configs import Config
from pyjolt import PyJolt, app, on_shutdown, on_startup

@app(__name__, configs = Config)
class Application(PyJolt):
    pass
```

and the configuration object is:

```
#app/configs.py <-- in the app folder

import os
from pyjolt import BaseConfig

class Config(BaseConfig): #must inherit from BaseConfig
    """Config class"""
    APP_NAME: str = "Test app"
    VERSION: str = "1.0"
    SECRET_KEY: str = "some-super-secret-key" #change for a secure random string
    BASE_PATH: str = os.path.dirname(__file__)
    DEBUG: bool = True
```

Available configuration options of the application are:

```
APP_NAME: str = Field(description="Human-readable name of the app")
VERSION: str = Field(description="Application version")
BASE_PATH: str #base path of app. os.path.dirname(__file__) in the configs.py file is the usual value

REQUEST_CLASS: Type[Request] = Field(Request, description="Request class used for handling application requests. Must be a subclass of pyjolt.request.Request")
RESPONSE_CLASS: Type[Response] = Field(Response, description="Response class used for returning application responses. Must be a subclass of pyjolt.response.Response")

# required for Authentication extension
SECRET_KEY: Optional[str]

# optionals with sensible defaults
DEBUG: Optional[bool] = True
HOST: Optional[str] = "localhost"
TEMPLATES_DIR: Optional[str] = "/templates"
STATIC_DIR: Optional[str] = "/static"
STATIC_URL: Optional[str] = "/static"
TEMPLATES_STRICT: Optional[bool] = True
STRICT_SLASHES: Optional[bool] = False
OPEN_API: Optional[bool] = True
OPEN_API_URL: Optional[str] = "/openapi"
OPEN_API_DESCRIPTION: Optional[str] = "Simple API"

#global CORS policy - optional with defaults
CORS_ENABLED: Optional[bool] = True #use cors
CORS_ALLOW_ORIGINS: Optional[list[str]] = ["*"] #List of allowed origins
CORS_ALLOW_METHODS: Optional[list[str]] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"] #allowed methods
CORS_ALLOW_HEADERS: Optional[list[str]] = ["Authorization", "Content-Type"] #List of allowed headers
CORS_EXPOSE_HEADERS: Optional[list[str]] = [] # List of headers to expose
CORS_ALLOW_CREDENTIALS: Optional[bool] = True #Allow credentials
CORS_MAX_AGE: Optional[int] = None #Max age in seconds. None to disable

# controllers, extensions, models
CONTROLLERS: Optional[List[str]] #import strings
CLI_CONTROLLERS: Optional[List[str]] #import strings
EXTENSIONS: Optional[List[str]] #import strings
MODELS: Optional[List[str]] #import strings
EXCEPTION_HANDLERS: Optional[List[str]] #import strings
MIDDLEWARE: Optional[List[str]] #import strings
LOGGERS: Optional[List[str]] #import strings

DEFAULT_LOGGER: dict[str, Any] = {
    LEVEL: Optional[LogLevel] = LogLevel.TRACE
    FORMAT: Optional[str] = "<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {extra[logger_name]} | <level>{message}<level>"
    BACKTRACE: Optional[bool] = True
    DIAGNOSE: Optional[bool] = True
    COLORIZE: Optional[bool] = True
}
```

You can then run the app with a run script:

```
#run.py <-- in the root folder

if __name__ == "__main__":
    import uvicorn
    from app.configs import Config
    configs = Config() #to load default values of user does not provide them
    uvicorn.run("app:Application", host=configs.HOST, port=configs.PORT, lifespan=configs.LIFESPAN, reload=configs.DEBUG, factory=True)
```

```sh
uv run --env-file .env.dev run.py
```

or directly from the terminal with:

```sh
uv run --env-file .env.dev uvicorn app:Application --reload --port 8080 --factory --host localhost
```

This will start the application on localhost on port 8080 with reload enabled (debug mode). The **lifespan** argument is important when you wish to use a database connection or other on_startup/on_shutdown methods. If lifespan="on", uvicorn will give startup/shutdown signals which the app can use to run certain methods. Other lifespan options are: "auto" and "off".

The ***--env-file .env.dev*** can be omitted if environmental variables are not used.

### Startup and shutdown methods

Sometimes we wish to add startup and shutdown methods to our application. One of the most common reasons is connecting to a database at startup and disconnecting at shutdown. In fact, this is what the SqlDatabase extension does automatically (see Extensions section below).
To add such methods, we can add them to the application class implementation like this:

```
from app.configs import Config
from pyjolt import PyJolt, app, on_shutdown, on_startup


@app(__name__, configs = Config)
class Application(PyJolt):

    @on_startup
    async def first_startup_method(self):
        print("Starting up...")

    @on_shutdown
    async def first_shutdown_method(self):
        print("Shuting down...")
```

All methods decorated with the @on_startup or @on_shutdown decorators will be executed when the application starts. In theory, any number of methods can be defined and decorated, however, they will be executed in alphabetical order which can cause issues if not careful. Therefore we suggest you use a single method per-decorator and use it to delegate work to other methods in the correct order.


### Application methods and properties

```
def get_conf(self, config_name: str, default: Any = None) -> Any:
    """
    Returns app configuration with provided config_name.
    Raises error if configuration is not found.
    """

def url_for(self, endpoint: str, **values) -> str:
    """
    Returns url for endpoint method/handler
    :param endpoint: the name of the endpoint handler method namespaced with the controller name
    :param values: dynamic route parameters
    :return: url (string) for endpoint
    """

def run_cli(self):
    """
    Runs the app and executes a CLI command (does not start the actual server).
    """
@property
def configs(self) -> dict[str, Any]:
    """
    Returns the entire application configuration dictionary
    """

@property
def root_path(self) -> str:
    """
    Returns root path of application
    """

@property
def app(self):
    """
    Returns self
    For compatibility with the Controller class
    which contains the app object on the app property
    """

@property
def static_files_path(self) -> str:
    """Static files paths"""

@property
def version(self) -> str:
    """Returns app version"""

@property
def app_name(self) -> str:
    """Returns app name"""

@property
def logger(self):
    """Returns the logger object (from Loguru)"""
```

## Logging

PyJolt uses Loguru for logging. It is available through the application object (***app.logger: Logger***) in every controller endpoint through the ***self*** keyword in endpoint methods. A default logger is configured for the application. You can modify its behaviour through application configurations. Configurations with defaults are:

```
LEVEL: Optional[LogLevel] = LogLevel.TRACE
FORMAT: Optional[str] = "<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {extra[logger_name]} | <level>{message}<level>"
BACKTRACE: Optional[bool] = True
DIAGNOSE: Optional[bool] = True
COLORIZE: Optional[bool] = True
```

To change the configurations you have to create a new dictionary with the name **DEFAULT_LOGGER** in the app configurations and provide the above configuration options. Example:

```
#from pyjolt import LogLevel

DEFAULT_LOGGER: dict[str, Any] = {
    "LEVEL": LogLevel.DEBUG,
    "FORMAT": "<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {extra[logger_name]} | <level>{message}<level>"
    "BACKTRACE": True
    "DIAGNOSE": True
    "COLORIZE": True
    "SERIALIZE": False
    "ENCODING": "utf-8"
}
```

### Adding custom logger sinks

PyJolt uses the same global Logger instance everywhere. However, you can configure different sinks and configure filters, output formats etc.
To add a custom logger you have to create a class which inherits from the LoggerBase class

```
#app/loggers/file_logger.py
from pyjolt.logging import LoggerBase

class FileLogger(LoggerBase):
    """File logger example"""
```

and then simply add the logger to the application configs:

```
#configs.py

LOGGERS: Optional[List[str]] = ['app.logging.file_logger:FileLogger']
```

To configure the file logger you have to add an app config field (dictonary) with the name of the logger as
upper-snake-case (FileLogger -> FILE_LOGGER):

```
#configs.py
import os
from pyjolt import LogLevel

FILE_LOGGER: dict[str, Any] = {
    SINK: Optional[str|Path] = os.path.join(BASE_PATH, "logging", "file.log"),
    LEVEL: Optional[LogLevel] = LogLevel.TRACE,
    FORMAT: Optional[str] = "<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {extra[logger_name]} | <level>{message}</level>",
    ENQUEUE: Optional[bool] = False,
    BACKTRACE: Optional[bool] = True,
    DIAGNOSE: Optional[bool] = True,
    COLORIZE: Optional[bool] = True,
    DELAY: Optional[bool] = True,
    ROTATION: Optional[RotationType] = "5 MB", #accepts: str, int, timedelta
    RETENTION: Optional[RetentionType] = "5 files", #accepts: str, int or timedelta
    COMPRESSION: CompressionType = "zip",
    SERIALIZE: Optional[bool] = False
    ENCODING: Optional[str] = "utf-8",
    MODE: Optional[str] = "a",
}
```
This will add a file sink which will write a "file.log" file until it reaches the 5 MB threshold size. When this size is reached, the file is renamed "file.log.<TIME_STAMP>" and a new "file.log" is started. The setup will rotate 5 files.

If you wish to implement log filtering or more complex formating you can simply override the default methods of the LoggerBase class:

**WARNING**
When using ENQUEUE=True, you MUST use server lifespan events to trigger appropriate removal of added sinks at application shutdown. Otherwise, a warning (resource tracker) for leaked semaphore objects will be triggered.

```
class FileLogger(LoggerBase):
    """Example file logger"""

    def get_format(self) -> str:
        """Should return a valid format string for the logger output"""
        return self.get_conf_value(
            "FORMAT",
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | {extra[logger_name]} | "
            "{name}:{function}:{line} - <cyan>{message}</cyan>",
        )

    def get_filter(self) -> FilterType:
        """Should return a filter method which returns a boolean"""
        return None
```

For example, the ***get_format*** method could return a valid JSON format string for the logger (to create a .jsonl file) and the filter method could filter log messages for specific phrases to destinguish between different log messages. Example filter method:

```
def get_filter(self):
    def _filter(record: dict[str, any]) -> bool:
        # Only log messages where the message includes the string "PERFORMANCE"
        # Message from a performance logger for bottleneck detection.
        return "PERFORMANCE" in record["message"]

    return _filter
```

Every logger accepts all of the above configurations, however, some are only applied to file loggers (retention, rotation, queueu, etc) because they don't make sense for simple console loggers. **DEFAULT** sink is ***STDERR***, but ***STDOUT*** is also accepted.


## Adding controllers for request handling

Controllers are created as classes with **async** methods that handle specific requests. An example controller is:

```
#app/api/users/user_api.py

from pyjolt import Request, Response, HttpStatus, MediaType
from pyjolt.controller import Controller, path, get, produces, post, consumes
from pydantic import BaseModel

class UserData(BaseModel):
    email: str
    fullname: str

@path("/api/v1/users")
class UsersApi(Controller):

    @get("/<int:user_id>")
    @produces(MediaType.APPLICATION_JSON)
    async def get_user(self, req: Request, user_id: int) -> Response:
        """Returns a user by user_id"""
        #some logic to load the user

        return req.response.json({
            "id": user_id,
            "fullname": "John Doe",
            "email": "johndoe@email.com"
        }).status(HttpStatus.OK)

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    async def create_user(self, req: Request, user_data: UserData) -> Response[UserData]:
        """Creates new user"""
        #logic for creating and storing user
        return req.response.json(user_data).status(HttpStatus.CREATED)

```
Each endpoint method has access to the application object and its configurations and methods via the self argument (self.app: PyJolt).
The controller must be registered with the application in the configurations:

```
CONTROLLERS: List[str] = [
    'app.api.users.user_api:UserApi' #path:Controller
]
```

In the above example controller the **post** route accepts incomming json data (@consumes) and automatically
injects it into the **user_data** variable with a Pydantic BaseModel type object. The incomming data is also automatically validated
and raises a validation error (422 - Unprocessible entity) if data is incorrect/missing. For more details about data validation and options we suggest you take a look at the Pydantic library. The @produces decorator automatically sets the correct content-type on the
response object and the return type hint (-> Response[UserData]:) indicates as what type of object the response body should be serialized.

### Available decorators for controllers

```
@path(url_path: str, open_api_spec: bool = True, tags: list[str]|None = None)
```

This is the main decorator for a controller. It assignes the controller a url path and controlls if the controller should be included in the OpenApi specifications.
It also assignes tag(s) for grouping of controller endpoints in the OpenApi specs.

```
@get(url_path: str, open_api_spec: bool = True, tags: list[str]|None = None)
@post(url_path: str, open_api_spec: bool = True, tags: list[str]|None = None)
@put(url_path: str, open_api_spec: bool = True, tags: list[str]|None = None)
@patch(url_path: str, open_api_spec: bool = True, tags: list[str]|None = None)
@delete(url_path: str, open_api_spec: bool = True, tags: list[str]|None = None)
@socket(url_path: str) #for webwocket connections
```

Main decorator assigned to controller endpoint methods. Determines the type of http request an endpoint handles (GET, POST, PUT, PATCH or DELETE), the endpoint url path (conbines with the controller path), if it should be added to the OpenApi specifications and fine grain endpoint grouping in the OpenApi specs via the **tags** argument.

```
@consumes(media_type: MediaType)
```

Indicates the kind of http request body this endpoint consumes (example: MediaType.APPLICATION_JSON, indicates it needs a json request body.). Available options are:

```
APPLICATION_X_WWW_FORM_URLENCODED = "application/x-www-form-urlencoded"
MULTIPART_FORM_DATA = "multipart/form-data"
APPLICATION_JSON = "application/json"
APPLICATION_PROBLEM_JSON = "application/problem+json"
APPLICATION_XML = "application/xml"
TEXT_XML = "text/xml"
TEXT_PLAIN = "text/plain"
TEXT_HTML = "text/html"
APPLICATION_OCTET_STREAM = "application/octet-stream"
IMAGE_PNG = "image/png"
IMAGE_JPEG = "image/jpeg"
IMAGE_GIF = "image/gif"
APPLICATION_PDF = "application/pdf"
APPLICATION_X_NDJSON = "application/x-ndjson"
APPLICATION_CSV = "application/csv"
TEXT_CSV = "text/csv"
APPLICATION_YAML = "application/yaml"
TEXT_YAML = "text/yaml"
APPLICATION_GRAPHQL = "application/graphql"
NO_CONTENT = "empty"
```

If this decorator is used it must be used in conjuction with a Pydantic data class provided as a parameter in the endpoint method:

```
@post("/")
@consumes(MediaType.APPLICATION_JSON)
@produces(MediaType.APPLICATION_JSON)
async def create_user(self, req: Request, data: TestModel) -> Response[ResponseModel]:
    """Consumes and produces json"""
```

TestModel is a Pydantic class.

```
@produces(media_type: MediaType)
```

The produces decorator indicates and sets the media type of the response body. Although the media type is set automatically it still shows a warning if the actual media type which was set in the endpoint by the developer does not match the intended value.

```
@open_api_docs(*args: Descriptor)
```

This decorator sets the possible return types of the decorated endpoint if the request was not successful (example: 404, 400, 401, 403 response codes). It accepts any number of Descriptor objects:

```
Descriptor(status: HttpStatus = HttpStatus.BAD_REQUEST, description: str|None = None, media_type: MediaType = MediaType.APPLICATION_JSON, body: Type[BaseModel]|None = None)
```

like this:

```
@get("/<int:user_id>")
@produces(MediaType.APPLICATION_JSON)
@open_api_docs(Descriptor(status=HttpStatus.NOT_FOUND, description="User not found", body=ErrorResponse),
                Descriptor(status=HttpStatus.BAD_REQUEST, description="Bad request", body=ErrorResponse))
async def get_user(self, req: Request, user_id: int) -> Response[ResponseModel]:
    """Endpoint logic """
```

The above example adds two possible endpoint responses (NOT_FOUND and BAD_REQUEST) with descriptions and what type of object is returned as json (default).

```
@development
```

This decorator can be applied to the controller class or individual endpoints. Controllers/endpoints with this decorator will be
disabled (unreachable) when the application is not in ***DEBUG*** mode (when ***DEBUG=False***). The decorator is for easy disabling
of features which are not yet ready for production.

### Request and Response objects

Each request gets its own Request object which is passed to the controller endpoint method. The Request object contains all
request parameters:

```
req: Request
req.route_parameters -> dict[str, int|str] #route parameters as a dictionary
req.method -> str #http method (uppercase string: GET, POST, PUT, PATCH, DELETE)
req.path -> str #request path (url: str)
req.query_string -> str #(the entire query string - what comes after "?" in the url)
req.headers -> dict[str, str] #all request headers
req.query_params -> dict[str, str] #query parameters as a dictionary
req.user -> Any #loaded user (if present). See the authentication implementation below.
req.res -> Response #the Response object
req.state -> Any #for setting any state which must be passed down in the request chain (i.e. middleware etc)
```

The response object provided on the Request object has methods:

```
req.res: Response
req.res.status(self, status_code: int|HttpStatus) -> Self #sets http status code
req.res.redirect(self, location: str, status_code: int|HttpStatus = HttpStatus.SEE_OTHER) -> instructs client to redirect to location
req.res.json(self, data: Any) -> Self #sets a json object as the response body
req.res.no_content(self) -> Self #no content response
req.res.text(self, text: str) -> Self #sets text as the response body
req.res.html_from_string(self, text: str, context: Optional[dict[str, Any]] = None) -> Self #creates a rendered template from the provided string
req.res.html(self, template_path: str, context: Optional[dict[str, Any]] = None) -> Self #creates a rendered template from the template file
req.res.send_file(self, body, headers) -> Self #sends a file as the response
req.res.set_header(self, key: str, value: str) -> Self #sets response header
req.res.set_cookie(self, cookie_name: str, value: str,
                   max_age: int|None = None, path: str = "/",
                   domain: str|None = None, secure: bool = False,
                   http_only: bool = True) -> Self #sets a cookie in the response
delete_cookie(self, cookie_name: str,
                      path: str = "/", domain: Optional[str] = None) -> Self #deletes a cookie
```


### Before and after request handling in Controllers

Sometimes we need to process a request before it ever hits the endpoint. For this, middleware or additional decorators is often used. If only a specific endpoint needs
this pre- or postprocessing, decorators are the way to go, however, if all controller endpoints need it we can add methods to the controller which will run for each request.
We can to this by adding and decorating controller methods:

```
#at the top of the controller file:
from pyjolt.controller import (Controller, path, get, produces, before_request, after_request)
####
@path("/api/v1/users", tags=["Users"])
class UsersApi(Controller):

    @before_request
    async def before_request_method(self, req: Request):
        """Some before request logic"""

    @after_request
    async def after_request_method(self, res: Response):
        """Some after request logic"""

    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    async def get_users(self, req: Request) -> Response[ResponseModel]:
        """Endpoint for returning all app users"""
        #await asyncio.sleep(10)
        session = db.create_session()
        users = await User.query(session).all()
        response: ResponseModel = ResponseModel(message="All users fetched.",
                                                status="success", data=None)
        await session.close() #must close the session
        return req.response.json(response).status(HttpStatus.OK)
```

The before and after request methods don't have to return anything. The request/response objects can be manipulated in-place. In theory, any number of methods
can be decorated with the before- and after_request decorators and all will run before the request is passed to the endpoint method, however, they are executed in
alphabetical order which can be combersome. This is why we suggest you use a single method which calls/delegates work to other methods.

### Websockets

You can add a websocket handler to any controller by using the ***@socket(url_path: str)*** decorator on the handler method.

```
@path("/api/v1/users", tags=["Users"])
class UsersApi(Controller):

    @socket("/ws")
    #@auth.login_required
    #@role_required
    async def socket_handler(self, req: Request) -> None:
        """
        Example socket handler
        This method doesn't return anything. It is receiving/sending messages directly via the Request and Response objects.
        """
        #accept the connection
        await req.accept()
        while True:
            data = await req.receive()
            if data["type"] == "websocket.disconnect":
                break #breaks the loop if the user disconnects
            if data["type"] == "websocket.receive":
                ##some logic to perform when user sends a message
                await req.res.send({
                    "type": "websocket.send",
                    "text": "Hello from server. Echo: " + data.get("text", "")
                })
```

This is a minimal websocker handler implementation. It first accepts the connection and then listens to receiving/incomming messages and sends responses.
The handler method can be protected with ***@login_required*** and ***@role_required*** decorators from the authentication extension. See implementation details in the
extension section.

## CORS

PyJolt has built-in CORS support. There are several configurations which you can set to in the Config class to configure CORS.
Configuration options with default values are:

```
CORS_ENABLED: Optional[bool] = True #use cors
CORS_ALLOW_ORIGINS: Optional[list[str]] = ["*"] #List of allowed origins
CORS_ALLOW_METHODS: Optional[list[str]] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"] #allowed methods
CORS_ALLOW_HEADERS: Optional[list[str]] = ["Authorization", "Content-Type"] #List of allowed headers
CORS_EXPOSE_HEADERS: Optional[list[str]] = [] # List of headers to expose
CORS_ALLOW_CREDENTIALS: Optional[bool] = True #Allow credentials
CORS_MAX_AGE: Optional[int] = None #Max age in seconds. None to disable
```

The above configurations will set CORS policy on the application scope. If you wish to fine-tune the policy on specific
endpoints you can use two decoratos.

To disable cors on an endpoint:

```
#imports
from pyjolt.controller import no_cors

#inside a controller

@GET("/")
@no_cors
async def my_endpoint(self, req: Request) -> Response:
    """some endpoint logic"""
```

this will disable CORS for this specific endpoint no matter the global settings.

If you wish you can set a different set of CORS rules for an endpoint using the ***@cors*** decorator:

```
#imports
from pyjolt.controller import cors

#inside a controller

@GET("/")
@cors(*,
    allow_origins: Optional[list[str]] = None,
    allow_methods: Optional[list[str]] = None,
    allow_headers: Optional[list[str]] = None,
    expose_headers: Optional[list[str]] = None,
    allow_credentials: Optional[bool] = None,
    max_age: Optional[int] = None,)
async def my_endpoint(self, req: Request) -> Response:
    """some endpoint logic"""
```

This will override the global CORS settings with endpoint-specific settings.

### CORS responses

If the request does not comply with CORS policy error responses are automatically returned:

**403 - Forbiden** - if the request origin is not allowed
**405 - Method not allowed** - if the request method is not allowed

## Routing

PyJolt uses the same router as Flask under the hood (Werkzeug). This means that all the same patterns apply.

Examples:
```
@get("/api/v1/users/<int:user_id>)
@get("/api/v1/users/<string:user_name>)
@get("/api/v1/users/<path:path>) #handles: "/api/v1/users/account/dashboard/main"
```

Route parameters marked with "<int:>" will be injected into the handler as integers, "<string:>" as a string and "<path:>" injects the entire path as a string.

### Route not found

If a route is not found (wrong url or http method) a NotFound (from pyjolt.exception import NotFound) error is raised. You can handle the exception in the ExceptionHandler class. If not handled, a generic JSON response is returned.

## Exception handling

Exception handling can be achived by creating an exception handler class (or more then one) and registering it with the application.

```
# app/api/exceptions/exception_handler.py

from typing import Any
from pydantic import BaseModel, ValidationError
from pyjolt.exceptions import ExceptionHandler, handles
from pyjolt import Request, Response, HttpStatus

from .custom_exceptions import EntityNotFound

class ErrorResponse(BaseModel):
    message: str
    details: Any|None = None

class CustomExceptionHandler(ExceptionHandler):

    @handles(ValidationError)
    async def validation_error(self, req: "Request", exc: ValidationError) -> "Response[ErrorResponse]":
        """Handles validation errors"""
        details = {}
        if hasattr(exc, "errors"):
            for error in exc.errors():
                details[error["loc"][0]] = error["msg"]

        return req.response.json({
            "message": "Validation failed.",
            "details": details
        }).status(HttpStatus.UNPROCESSABLE_ENTITY)
```

The above CustomExceptionHandler class can also be registered with the application in configs.py file.

```
EXCEPTION_HANDLERS: List[str] = [
    'app.api.exceptions.exception_handler:CustomExceptionHandler'
]
```

You can define any number of methods and decorate them with the @handles decorator to indicate which exception
should be handled by the method. The @handles decorator excepts any number of exceptions as arguments.

Any exceptions that are raised throughout the app can be handled in one or more ExceptionHandler classes. If an unhandled exception occurs
and the application is in DEBUG mode, the exception will raise an error, however, if the application is NOT in DEBUG mode, the exception is
suppressed and a JSON response with content

```
{
    "status": "error",
    "message": "Internal server error",
}
```

with status code 500 (Internal server error) is returned and the request is logged as critical.
To avoid this generic response you can implement a handler in your ExceptionHandler class which handles raw exceptions (pythons Exception class).

```
@handles(ValidationError, SomeOtherException, AThirdException)
async def handler_method(self, req: "Request", exc: ValidationError|SomeOtherException|AThirdException) -> "Response[ErrorResponse]":
    ###handler logic and response return
```

Each handler method accepts exactly three arguments. The "self" keyword pointing at the exception handler instance (has acces to the application object -> self.app),
the current request object and the raised exception.

### Custom exceptions

Custom exceptions can be made by defining a class which inherits from the pyjolt.exceptions.BaseHttpException, from the pyjolt.Exceptions.CustomException or simply by inheriting from pythons Exception class.

```
from pyjolt.exception import BaseHttpException, CustomException

class MyCustomException(Exception):
    """implementation"""

class MyCustomHttpException(BaseHttpException):
    """implementation"""

class CustomExceptionFromCustomException(CustomException):
    """implementation"""
```

The exceptions can then be registered with your exception handler to provide required responses to users.

### Quick aborts

Sometimes, you just wish to quickly abort a request (when data is not found, something else goes wrong.). Since PyJolt advocates for the
fail-fast pattern, it provides two convinience methods for quickly aborting requests. These methods are:

```
from pyjolt import abort, html_abort
abort(msg: str, status_code: HttpStatus = HttpStatus.BAD_REQUEST, status: str = "error", data: Any = None)
html_abort(template: str, status_code: HttpStatus = HttpStatus.BAD_REQUEST, data: Any = None)
```

These methods raise a AborterException and HtmlAborterException, respectively. An example of the abort method use;

```
from pyjolt import abort, html_abort

@get("/api/v1/users/<int:user_id>)
async def get_user(self, req: Request, user_id: int) -> Response:
    """Handler logic"""
    #Entity not found
    abort(msg=f"User with id {user_id} not found",
        status_code=HttpStatus.NOT_FOUND,
        status="error", data=None)
```

To handle AborterExceptions you have to implement a handler in your ExceptionHandler class, however, HtmlAborterExceptions are automatically
rendered and returned.

### Redirecting
Sometimes we wish to redirect the user to a different resource. In this case we can use a redirect response of the Response object.

```
@get("/api/v1/auth/login)
async def get_user(self, req: Request, data: UserLoginData) -> Response:
    """Handler logic"""
    #Redirect after login
    return req.response.redirect("url-for-location")
```

The above example instructs the client to redirect to "url-for-location" with default status code 303 (SEE OTHER).

### Redirecting to other endpoint

We can provide a hard-coded string to the ***redirect*** method, however, this can be cumbersome. The url might change and the redirect would break.
To avoid this, we can use the url_for method provided by the application object:

```
#Redirect after login
return req.response.redirect(self.app.url_for("<ControllerName>.<endpointMethodName>"), **kwargs)
```

This will construct the correct url with any route parameters (provided as key-value pairs <-> kwargs) and return it as a string.
In this way, we do not have to hard-code and remember all urls in our app. We can also change the non-dynamic parts of the endpoint
without breaking redirects.


## Static assets/files

The application serves files in the "/static" folder on the path "/static/<path:filename>".
If you have an image named "my_image.png" in the static folder you can access it on the url: http://localhost:8080/static/my_image.png
The path ("/static") and folder name ("/static") can be configured via the application configurations. The folder should be inside the "app" folder.

To construct the above example url for ***my_image.png*** we can use the ***url_for*** method like this:

```
self.app.url_for("Static.get", filename="my_image.png")
```

This will return the correct url for the image. If the image was located in subfolders we would simply have to change the ***filename** argument
in the method call.

In this example, the url_for method returns the url for the ***get*** method of the ***Static*** controller (automatically registered by the application)
with required ***filename*** argument.

## Template (HTML) responses

Controller endpoints can also return rendered HTML or plain text content.

```
#inside a controller class

@get("/<int:user_id>")
@produces(MediaType.TEXT_HTML)
async def get_user(self, req: Request, user_id: int) -> Response:
    """Returns a user by user_id"""
    #some logic to load the user
    context: dict[str, Any] = {#any key-value pairs you wish to include in the template}

    return await (req.response.html("my_template.html", context)).status(HttpStatus.OK)
```

The template name/path must be relative to the templates folder of the application. Because the html response accesses/loads the template
from the templates folder, the .html method of the response object is async and must thus be awaited.

The name/location of the templates folder can be configured via application configurations.

PyJolt uses Jinja2 as the templating engine, the synatx is thus the same as in any framework which uses the same engine.

## OpenAPI specifications

OpenAPI specifications are automatically generated and exposed on "/openapi/docs" (Swagger UI) and "/openapi/specs.json" endpoints (in Debug mode only).
To make sure the endpoint descriptions, return types and request specification are accurate, we suggest you use all required endpoint decorators available for
endpoints.

## Extensions
PyJolt has a few built-in extensions that can be used ad configured for database connection/management, task scheduling, authentication and
interfacing with LLMs.

### Database connectivity and management

#### SQL

To add SQL database connectivity to your PyJolt app you can use the database.sql module.

```
#extensions.py
from pyjolt.database.sql import SqlDatabase
from pyjolt.database.sql.migrate import Migrate

db: SqlDatabase = SqlDatabase(db_name="db", configs_name="SQL_DATABASE") #"db" and "SQL_DATABASE" is the default so they can be omitted
migrate: Migrate = Migrate(db, command_prefix: str = "")
```

you can then indicate the extensions in the app configurations:

```
EXTENSIONS: List[str] = [
    'app.extensions:db',
    'app.extensions:migrate'
]
```

This will initilize and configure the extensions with the application at startup. To configure the extensions simply add
neccessary configurations to the config class or dictionary. Available configurations are:

```
SQL_DATADATE = {
    "DATABASE_URI": "sqlite+aiosqlite:///./test.db",#for a simple SQLite database
    "SESSION_NAME": "session",
    "SHOW_SQL": False
}
```

To use a Postgresql db the **DATABASE_URI** string should be like this:
```
"DATABASE_URI": "postgresql+asyncpg://user:pass@localhost/dbname"
```

Session name variable (for use with @managed_session and @readonly_session):
```
"SESSION_NAME": "session"
```
This is the name of the AsyncSession variable that is injected when using the managed_session decorator of the extension. The default is "session". This is useful when you wish to use
managed sessions for multiple databases in the same controller endpoint.

```
"SHOW_SQL": False
```

This configuration directs the extension to log every executed SQL statement to the console. This is a good way to
debug and optimize code during development but should not be used in production.

**Migrate**
```
ALEMBIC_MIGRATION_DIR: str = "migrations" #default folder name for migrations
ALEMBIC_DATABASE_URI_SYNC: str = "sqlite:///./test.db" #a connection string with a sync driver
```

The SqlDatabase extension accepts a configs_name: str argument which is passed to its Migrate instance. This argument determines the configurations dictionary in the configs.py file which
should be used for the extension. By default all extensions use upper-pascal-case format of the extension name (SqlDatabase -> "SQL_DATABASE"). The Migrate instance can be passed a
command_prefix: str which can be used to differentiate different migration instances if uses multiple (for multiple databases).
```
#extensions.py
.
.
.
db: SqlDatabase = SqlDatabase(configs_name="MY_DATABASE") #default configs_name="SQL_DATABASE"
migrate: Migrate = Migrate(db: SqlDatabase, command_prefix: str = "")
```

In this case the configuration variables should be:
```
MY_DATABASE = {
    "DATABASE_URI": "<connection_str>",
    "ALEMBIC_MIGRATION_DIR": "<migrations_directory>"
    "ALEMBIC_DATABASE_URI_SYNC": "<connection_str_with_sync_driver>"
}

```
This is useful in cases where you need more then one database.

The migrate extension exposes some function which facilitate database management.
They can be envoked via the cli.py script in the project root

```
#cli.py <- next to the run.py script
"""CLI utility script"""

if __name__ == "__main__":
    from app import Application
    app = Application()
    app.run_cli()
```

You can run the script with command like this:
```sh
uv run cli.py db-init
uv run cli.py db-migrate --message "Your migration message"
uv run cli.py db-upgrade
```
The above commands initialize the migrations tracking of the DB, prepares the migration script and finally upgrades the DB.

Other available cli commands for DB management are:

```
db-downgrade --revision "rev. number"
db-history --verbose --indicate-current
db-current --verbose
db-heads --verbose
db-show --revision "rev. number"
db-stamp --revision "rev. number"
```

Arguments to the above commands are optional.

**If using command_prefix**
If using a command prefix for the Migrate instance the commands can be executed like this:

```
uv run cli.py <command_prefix>db-init
uv run cli.py <command_prefix>db-migrate --message "Your migration message"
uv run cli.py <command_prefix>db-upgrade
```

The same applies to other commands of the Migrate extension.

**The use of the Migrate extension is completely optional when using a database.**

##### Database Models
To store/fetch data from the database you can use model classes. An example class is:

```
#app/api/models/user_model.py

from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped, relationship

from pyjolt.database import create_declerative_base

Base = create_declerative_base("db") #passed argument must be the same as the database name you wish to
                                    #use the model with. Default is "db" so it can be omitted.

class User(Base):
    """
    User model
    """
    __tablename__: str = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    fullname: Mapped[str] = mapped_column(String(30))
    email: Mapped[str] = mapped_column(String(50), unique=True)
```

The Base class created with create_declerative_base should be used with all db models for the same database.

##### Querying
To perform queries in the database you can use the associated models. A simple query for getting a user by its ID is:

```
user: User = await User.query(session).filter_by(id=user_id).first()
```

This returns the first user that matches the filter_by criteria. To get all users in the table you can do:

```
users:  list[User] = await User.query(session).all()
```

The ***session*** object is an active AsyncSession instance which can be injected via the ***@managed_session*** or ***@readonly_session*** decorators on controller endpoint handlers.

**Manual session handling is highly discouraged and should be used only for very specific use cases and with utmost care. Unclosed sessions can cause memory leaks and other problem, especially in long running apps.**

The ***Model.query(session)*** method returns an AsyncQuery object which exposes many methods for querying and filtering:

```
def where(self, *conditions) -> "AsyncQuery": #Adds WHERE conditions (same as `filter()`).
def filter(self, *conditions) -> "AsyncQuery": #Adds WHERE conditions to the query (supports multiple conditions).
def filter_by(self, **kwargs) -> "AsyncQuery": #Adds WHERE conditions using keyword arguments (simpler syntax).
def join(self, other_model: Model) -> "AsyncQuery": #Performs a SQL JOIN with another model.
def limit(self, num: int) -> "AsyncQuery": #"Limits the number of results returned.
def offset(self, num: int) -> "AsyncQuery": #Skips a certain number of results (used for pagination).
def order_by(self, *columns) -> "AsyncQuery": Sorts results based on one or more columns.
def like(self, column, pattern, escape=None) -> "AsyncQuery": #Filters results using a SQL LIKE condition.
def ilike(self, column, pattern, escape=None) -> "AsyncQuery": #Filters results using a SQL ILIKE condition.
```

The above methods always return the AsyncQuery object and thus serve as query builders. This means that the methods can be chained to construct the desired query.
Actual results are returned once we execute the query with one of the following methods (must be awaited):

```
async def count(self) -> int: #returns number of results
async def paginate(self, page: int = 1, per_page: int = 10) -> Dict[str, Any]: #returnes a dictionary with paginated results (see below)
async def all(self) -> list: #returns all results
async def first(self) -> Any: #returns first result
async def one(self) -> Any: #returns only one result
```

##### Paginated results

The paginate method returns a pagination object (dictionary) with the following structure:

```
result = dict: {
    "items": list[Model], #List of results
    "total": int, #Total records
    "page": int, #Current page
    "pages": int, #Total pages
    "per_page": int, #Results per page
    "has_next": bool, #Whether there's a next page
    "has_prev": bool #Whether there's a previous page
}
```

**For model detection (for correct Migration extension working) all models should be added in the app configurations**

```
MODELS: List[str] = [
    'app.api.models.user_model:User'
]
```

**SqlDatabase and Migrate extension uses Sqlalchemy and Alembic under the hood.**

##### Automatic session handling

Manual session handling is highly discouraged because it is easy to forget to close/commit an active session. Therefore two convenience decorators can be used:

```
@post("/")
@consumes(MediaType.APPLICATION_JSON)
@produces(MediaType.APPLICATION_JSON)
@db.managed_session
async def create_user(self, req: Request, user_data: UserData, session: AsyncSession) -> Response[UserData]:
    """Creates new user"""
    user: User = User(fullname=user_data.fullname, email=user_data.email)
    session.add(user)
    await session.flush() #to get the new users id.
    return req.response.json(UserData(id=user_id, fullname=user.fullname)).status(HttpStatus.OK)

@get("/<int:user_id>")
@consumes(MediaType.APPLICATION_JSON)
@produces(MediaType.APPLICATION_JSON)
@db.readonly_session
async def get_user(self, req: Request, user_id: int, session: AsyncSession) -> Response[UserData]:
    """Creates new user"""
    user: User = await User.query(session).filter_by(id=user_id).first()
    return req.response.json(UserData(id=user_id, fullname=user.fullname)).status(HttpStatus.OK)
```

The ***@managed_session*** decorator automatically injects the active session into the endpoint handler and runs the endpoint inside a session context, which handles
session closure/commit and possible rollbacks in case of errors. The ***@readonly_session*** decorator injects the active session which can be used for read-only operations.
No rollbacks or commits neccessary. The readonly session decorator prevents accidental writes (nothing is commited), has slightly lower overhead, fewer lock surprises and
communicates a clear intent (reading data).

**session.flush()** will cause the session to perform the insert and fetch the objects id(s).

#### NoSQL

Besides SQL databases another popular solution are NoSQL databases like MongoDB. PyJolt supports them out of the box. To setup a NoSQL database you must provide the following configurations:

```
#configs.py

NOSQL_DATABASE = {
    "BACKEND": type #class of the selected NoSQL backend implementation. Example for MongoDB: from pyjolt.database.nosql.backends import MongoBackend
    "DATABASE_URI": str #connection string. Example: mongodb+srv://<db_username>:<db_password>@cluster0.273gshd.mongodb.net
    "DATABASE": Optional[str]
    "DB_INJECT_NAME": str = "db" #name of the injected variable for managed sessions
    "SESSION_NAME": str = "session" #name of the injected session variable for managed sessions
}
```

To use the NoSQL extension simply add it to the extension like this:

```
#extensions.py
#other extensions
from pyjolt.database.nosql import NoSqlDatabase

nosqldb: NoSqlDatabase = NoSqlDatabase()
```

and then add the extension to the app configs

```
#configs.py

EXTENSIONS: list[str] = [
    #other extensions
    'app.extensions:nosqldb',
]
```

This will initilize the extension and configure it. As usual, a config variable prefix can be supplied at instantiation: nosqldb: NoSqlDatabase = NoSqlDatabase(variable_prefix="MY_PREFIX_").

##### Managed database transactions

To use a managed database transaction (scoped session) you can use the ***@managed_database*** decorator on controller endpoint handler methods.

```
#inside a controller

@post("/")
@consumes(MediaType.APPLICATION_JSON)
@produces(MediaType.APPLICATION_JSON)
@nosqldb.managed_database
async def create_user(self, req: Request, data: TestModel, db: Any, session: Any = None) -> Response[TestModelOut]:
    """Consumes and produces json"""
    #inserts a new document into collection
    await db.insert_one("<collection_name>", {"email": data.email, "fullname": data.fullname, "age": data.age}, session=session)
    return req.response.json({
        "message": "User added successfully",
        "status": "success"
    }).status(200)
```

The above usage of the ***managed_database*** decorator injects a db client handle and the corresponding session into the endpoint handler. You can pass the session object
to all queries/inserts to scope them to the same session. This ensures that the entire transaction is rolled back in case of exceptions in one of the queries/inserts.

**session** objects are not available in all databases and therefore the injected session object is ***None*** in those cases. Please check if your database supports managed/scoped sessions. If managed/scoped sessions are not available everything still works, however, each query/insert is treated as an isolated call.

##### Simple queries/inserts

If you wish to perform only one query, insert or delete (i.e. get/delete user by id or insert one user) you can simply use the instantiated NoSqlDatabase extension object (***nosqldb***) to call the desired query/insert/delete method.

##### Methods and properties
The extension exposes the following methods/properties:

```
@property
def variable_prefix(self) -> str:
    return self._variable_prefix

@property
def db_name(self) -> str:
    return self.__db_name__

@property
def backend(self) -> AsyncNoSqlBackendBase:
    if not self._backend:
        raise RuntimeError("Backend not connected. Was init_app/connect called?")
    return self._backend

def database_handle(self) -> Any:
    return self.backend.database_handle()

def get_collection(self, name: str) -> Any:
    return self.backend.get_collection(name)

async def find_one(self, collection: str, filter: Mapping[str, Any], **kwargs) -> Any:
    return await self.backend.find_one(collection, filter, **kwargs)

async def find_many(self, collection: str, filter: Mapping[str, Any] | None = None, **kwargs) -> list[Any]:
    return await self.backend.find_many(collection, filter, **kwargs)

async def insert_one(self, collection: str, doc: Mapping[str, Any], **kwargs) -> Any:
    return await self.backend.insert_one(collection, doc, **kwargs)

async def insert_many(self, collection: str, docs: Iterable[Mapping[str, Any]], **kwargs) -> Any:
    return await self.backend.insert_many(collection, docs, **kwargs)

async def update_one(self, collection: str, filter: Mapping[str, Any], update: Mapping[str, Any], **kwargs) -> Any:
    return await self.backend.update_one(collection, filter, update, **kwargs)

async def delete_one(self, collection: str, filter: Mapping[str, Any], **kwargs) -> Any:
    return await self.backend.delete_one(collection, filter, **kwargs)

async def aggregate(self, collection: str, pipeline: Iterable[Mapping[str, Any]], **kwargs) -> list[Any]:
    return await self.backend.aggregate(collection, pipeline, **kwargs)

async def execute_raw(self, *args, **kwargs) -> Any:
    """
    Escape hatch for backend-specific commands. See MongoBackend.execute_raw docstring.
    """
    return await self.backend.execute_raw(*args, **kwargs)
```

Keep in mind that some aspects, like the ***execute_raw*** method are backend specific. They therefore depend on the selected backend (MongoDB etc).

##### Custom backend implementations

To create a custom backend implementation create a class which extends and implements the ***AsyncNoSqlBackendBase*** abstract class. The abstract class can be imported as ***from pyjolt.database.nosql.backends import AsyncNoSqlBackendBase***. After that, simply implement all required methods. The required methods are:

```
class AsyncNoSqlBackendBase(ABC):
    """
    Minimal async adapter interface a backend must implement.
    """

    @classmethod
    @abstractmethod
    def configure_from_app(cls, app: "PyJolt", variable_prefix: str) -> "AsyncNoSqlBackendBase":
        """
        Classmethod to configure backend from app config.
        Called during NoSqlDatabase.init_app().
        """
        ...

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    def database_handle(self) -> Any:
        """
        Returns an object representing the 'database' to use inside handlers.
        For backends without a database concept, return a client/root handle.
        """
        ...

    @abstractmethod
    def supports_transactions(self) -> bool:
        ...

    @abstractmethod
    async def start_session(self) -> Any:
        """
        Return a session/context object usable in transactions (or None if unsupported).
        """
        ...

    @abstractmethod
    async def with_transaction(self, fn: Callable[..., Any], *args, session: Any = None, **kwargs) -> Any:
        """
        Execute fn inside a transaction if supported; otherwise call fn directly.
        """
        ...

    @abstractmethod
    def get_collection(self, name: str) -> Any:
        ...

    @abstractmethod
    async def find_one(self, collection: str, filter: Mapping[str, Any], *, session: Any = None, **kwargs) -> Any:
        ...

    @abstractmethod
    async def find_many(self, collection: str, filter: Mapping[str, Any] | None = None, *, session: Any = None,
                        limit: Optional[int] = None, skip: Optional[int] = None, sort: Optional[Iterable[tuple[str, int]]] = None,
                        **kwargs) -> list[Any]:
        ...

    @abstractmethod
    async def insert_one(self, collection: str, doc: Mapping[str, Any], *, session: Any = None, **kwargs) -> Any:
        ...

    @abstractmethod
    async def insert_many(self, collection: str, docs: Iterable[Mapping[str, Any]], *, session: Any = None, **kwargs) -> Any:
        ...

    @abstractmethod
    async def update_one(self, collection: str, filter: Mapping[str, Any], update: Mapping[str, Any], *,
                         upsert: bool = False, session: Any = None, **kwargs) -> Any:
        ...

    @abstractmethod
    async def delete_one(self, collection: str, filter: Mapping[str, Any], *, session: Any = None, **kwargs) -> Any:
        ...

    @abstractmethod
    async def aggregate(self, collection: str, pipeline: Iterable[Mapping[str, Any]], *,
                        session: Any = None, **kwargs) -> list[Any]:
        ...

    @abstractmethod
    async def execute_raw(self, *args, **kwargs) -> Any:
        """
        Backend escape hatch for commands that don't fit the generic surface.
        For MongoDB, this could be db.command(...), collection.bulk_write(...), etc.
        """
        ...
```

The specific implementation for each database backend type will differ. Have a look at the ***pyjolt.database.nosql.backend.mongo_backend*** for MongoDB.

##### MongoDB
To use MongoDB as the backend you will have to install the following dependencies:

```
uv add motor
uv add "mongodb[srv]"
```

## User Authentication

To setup user authentication and protection of controller endpoints use the authentication extension.

```
#authentication.py <- next to extensions.py

from enum import StrEnum
from typing import Optional
from pyjolt import Request
from pyjolt.auth import Authentication

from app.extensions import db
from app.api.models import User

class UserRoles(StrEnum):
    ADMIN = "admin"
    SUPERUSER = "superuser"
    USER = "user"

class Auth(Authentication):

    async def user_loader(self, req: Request) -> Optional[User]:
        """Loads user from the provided cookie"""
        cookie_header = req.headers.get("cookie", "")
        if cookie_header:
            # Split the cookie string on semicolons and equals signs to extract individual cookies
            cookies = dict(cookie.strip().split('=', 1) for cookie in cookie_header.split(';'))
            auth_cookie = cookies.get("auth_cookie")
            if auth_cookie:
                user_id = self.decode_signed_cookie(auth_cookie)
                if user_id:
                    session = db.create_session()
                    user = await User.query(session).filter_by(id=user_id).first()
                    await session.close()
                    return user
        return None

    async def role_check(self, user: User, roles: list[UserRoles]) -> bool:
        """Checks intersection of user roles and required roles"""
        user_roles = set([role.role for role in user.roles])
        return len(user_roles.intersection(set(roles))) > 0

auth: Auth = Auth()
```

The Auth class inherits from the PyJolt Authentication class. The user must implement the user_loader and role_check (optional) methods.
These methods provide logic for loading a user when a protected endpoint is requested and checking if the user has permissions.
Above is an example which loads the user from a cookie. If the user is not found an AuthenticationException is raised which can be handled
in the CustomExceptionHandler. If the user doesn't have required roles (role_check -> False) an UnauthorizedException exception is raised
which can be also handled in the CustomExceptionHandler.

The instantiated Auth class must be added to the application configs.

```
EXTENSIONS: List[str] = [
    'app.extensions:db',
    'app.extensions:migrate',
    'app.authentication:auth'
]
```

Controller endpoints can be protected with two decorators like this:

```
@get("/<int:user_id>")
@produces(MediaType.APPLICATION_JSON)
@auth.login_required
@auth.role_required(UserRoles.ADMIN, UserRoles.SUPERUSER)
async def get_user(self, req: Request, user_id: int) -> Response[UserData]:
    """Returns a user by user_id"""
    session = db.create_session()
    user: User = await User.query(session).filter_by(id=user_id).first()
    await session.close()

    return req.response.json(UserData(id=user_id, fullname=user.fullname, email=user.email)).status(HttpStatus.OK)
```

If using the @auth.role_required decorator you MUST also use the @auth.login_required decorator. The login_required
decorator calls the user_loader method and attaches the loaded user object to the Request object: **req.user**.
The above role_check implementation assumes that there is a one-to-many relationship on the User and Role (not shown) models.

The Authentication extension can be configured with the following options:

```
AUTHENTICATION = {
    "AUTHENTICATION_ERROR_MESSAGE": str = "Login required" #message of the raised exception
    "UNAUTHORIZED_ERROR_MESSAGE": str = "Missing user role(s)" #message of the raised exception
}
```

The auth instance exposes other useful methods for easy user authentication:

```
auth.create_signed_cookie_value(self, value: str|int) -> str #creates a signed cookie
auth.decode_signed_cookie(self, cookie_value: str) -> str #decodes signed cookie
auth.create_password_hash(self, password: str) -> str #creates a password hash
auth.check_password_hash(self, password: str, hashed_password: str) -> bool #check password hash against provided password
auth.create_jwt_token(self, payload: Dict, expires_in: int = 3600) -> str #creates a JWT string
auth.validate_jwt_token(self, token: str) -> Dict|None #validates JWT string (from request)
```

The decode_signed_cookie method is used in the above user_loader example.

### Update - @login_required and @role_required with Controller classes

Both authentication related decorators can now be used on controller classes to protect all endpoints simultaneusly instead of each individual endpoint.
This is useful for classes serving resources for which the user always has to be authenticated and for classes related to administrator tasks where the user always has to
be authenticated and also have specific authorizations/roles (i.e. Admin). Usage:

```

@path("/api/v1/users", tags=["Users"])
@login_required
@role_required(*roles)
class UsersApi(Controller):
    """All endpoints are protected"""
    ...
```

The decorators are added to the classes methods list which is executed upon each request even before the @before_request methods. The execution order of the methods is
top-bottom so make sure the @login_required decorator is above the @role_required decorator to load the user before checking roles.

## Task scheduling

The task_manager extensions allows for easy management of tasks that should run periodically or running of one-time fire&forget methods.
To use the extension you have to install the neccessary dependencies with:

```
uv add "pyjolt[scheduler]"
```

The extension can be setup like this:

```
#scheduler.py <- next to __init__.py

from pyjolt.task_manager import TaskManager, schedule_job

class Scheduler(TaskManager):

    @schedule_job("interval", minutes=1, id="my_job")
    async def some_task(self):
        print("Performing task")

scheduler: Scheduler = Scheduler()
```

It can then be added to application configs like the Authentication extension.

```
EXTENSIONS: List[str] = [
    'app.extensions:db',
    'app.extensions:migrate',
    'app.authentication:auth',
    'app.scheduler:scheduler'
]
```

All methods defined in the Scheduler class and decorated with the @schedule_job decorator will be run with provided parameters. The extension uses the APScheduler
module we therefore recommend you take a look at their documentation for more details about job scheduling. In the above example, the "some_task" method will run
as an interval method every minute. To use the extension to run fire&forget methods (like sending emails) where we don't neccessary have to wait for the method to finish
we can use the run_background_task method:

```
from app.scheduler import scheduler


@post("/")
@consumes(MediaType.APPLICATION_JSON)
@produces(MediaType.APPLICATION_JSON)
async def get_user(self, req: Request, user_data: UserData) -> Response[UserData]:
    """Creates new user"""
    user: User = User(fullname=user_data.fullname, email=user_data.email)
    session = db.create_session()
    session.add(user)
    await session.commit()

    scheduler.run_background_task(send_email, *args, **kwargs) #args and kwargs are any number or arguments and keyword arguments that the send_mail method might need
    return req.response.json(UserData(id=user_id, fullname=user.fullname)).status(HttpStatus.OK)
```

This kicks off the send_email method without waiting for it to finish.

The extension accepts the following configuration options via the application (indicated are defaults):

```
TASK_MANAGER = {
    "JOB_STORES": {
        "default": MemoryJobStore()
    },
    "EXECUTORS": {
        "default": AsyncIOExecutor()
    },
    "JOB_DEFAULTS": {
        "coalesce": False,
        "max_instances": 3
    },
    "DAEMON": True,
    "SCHEDULER": AsyncIOScheduler
}
```

The scheduler object exposes a number of methods which can be used to manipulate ongoing scheduled tasks:

```
scheduler.add_job(self, func: Callable, *args, **kwargs) -> Job #adds a Job to the scheduler
scheduler.remove_job(self, job: str|Job, job_store: Optional[str] = None) #removes job from scheduler by its id:str or the Job object
scheduler.pause_job(self, job: str|Job) #pauses a running job by job id:str or the Job object
scheduler.resume_job(self, job: str|Job) #resumes a job by job id:str or the Job object
scheduler.get_job(self, job_id: str) -> Job|None #returns the job if it exists
```

## Caching

Caching is a simple method to increase the throughput of applications. It stores responses of frequently requested resources whos data
doesn't change often. An example would be fetching all users of an app, where new users are not added often. Why do database queries for each request if the query result is always going to be the same. To prevent unneccessary database queries the controller endpoint response can be cached with the caching extensions.

After this, you can add the extension to your app with:

```
#extensions.py <-next to __init__.py

from pyjolt.caching import Cache

#other extensions
cache: Cache = Cache() #can also add a variable prefix to specify a configs namespace for using multiple caching instances.
# cache: Cache = Cache(variable_prefix = "MY_CACHE_")
```

and then you can add the instantiated extension to application configs:

```
EXTENSIONS: List[str] = [
    'app.extensions:db',
    'app.extensions:migrate',
    'app.authentication:auth',
    'app.scheduler:scheduler',
    'app.extensions:cache'
]
```

The cache can use in-memory caching (default), SQLite database or Redis. To use the in-memory cache no configurations are strictly neccessary.
Available configurations:

```
CACHE = {
    BACKEND: Type[BaseCacheBackend] = MemoryCacheBackend
    REDIS_URL: str
    DURATION: int = 300 #cache duration in seconds - with default 300 s
    REDIS_PASSWORD: str
    KEY_PREFIX: Optional[str] #for using a namespace in a Redis/SQLite db (if multiple applications use the db)
    SQLITE_PATH: Optional[str] = "./pyjolt_cache.db" - SQLite cache only
    SQLITE_TABLE: Optional[str] = "cache_entries" #name of cache table in SQLite - SQLite cache only
    SQLITE_WAL_CHECKPOINT_MODE: Optional[str] = "PASSIVE" #Mode for WAL checkpointing: PASSIVE|FULL|RESTART|TRUNCATE - SQLite cache only
    SQLITE_WAL_CHECKPOINT_EVERY: Optional[int] = 100 #Insert WAL checkpoint every N write operations - SQLite cache only
}
```

Only the default cache duration can be set if using in-memory/SQLite caching. The default value is 300 seconds.
When using a variable prefix, the configs look like: "MY_PREFIX_CACHE_BACKEND", if "MY_PREFIX_" is passed as the prefix variable.

Once configured the caching extension can be used like this in controller endpoints:

```
@get("/<int:user_id>")
@produces(MediaType.APPLICATION_JSON)
@cache.cache(duration=300)#default is 300 so this is not needed
async def get_user(self, req: Request, user_id: int) -> Response[UserData]:
    """Returns a user by user_id"""
    user: User = await User.query().filter_by(id=user_id).first()

    return req.response.json(UserData(id=user_id, fullname=user.fullname, email=user.email)).status(HttpStatus.OK)
```

**The @cache.cache decorator MUST be applied as the bottom-most decorator** to make sure it caches the result of the actual
endpoint function and NOT results of other decorators. This is especially crucial if using authentication.

The caching extension stores the result of the endpoint by creating a key-value pair, where the key is a combination
of the endpoint function name and route parameters. This makes sure that the endpoint stores the response for user_id=1 and user_id=2
seperately.

The extension exposes several methods on the cache object which allows for manual manipulation of the cache:

```
cache.set(key: str, value: Response, duration: Optional[int]) -> None #sets a cached key-value pair
cache.get(key: str) -> Dict #gets the cache value for the provided key
cache.delete(key: str) -> None #removes cache entry for the provided key
cache.clear() -> None #clears entire cache
```

### Custom caching backends

To create a custom caching backend you have to create a class which inherits and satisfies the ***BaseCacheBackend*** abstract class.
Simply inherit from this class and implement the following methods:

```
#pyjolt.caching

class BaseCacheBackend(ABC):
    """
    Abstract cache backend blueprint.

    Subclasses should implement:
    - configure_from_app(cls, app) -> BaseCacheBackend
    - connect / disconnect
    - get / set / delete / clear
    """

    @classmethod
    @abstractmethod
    def configure_from_app(cls, app: "PyJolt", variable_prefix: str) -> "BaseCacheBackend":
        """Create a configured backend instance using app config."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish any required connections (no-op for memory)."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down connections (no-op for memory)."""

    @abstractmethod
    async def get(self, key: str) -> Optional[dict]:
        """Return cached payload dict or None."""

    @abstractmethod
    async def set(self, key: str, value: dict, duration: Optional[int] = None) -> None:
        """Store payload dict under key with optional TTL in seconds."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a cached entry if present."""

    @abstractmethod
    async def clear(self) -> None:
        """Clear the entire cache namespace."""
```

Once you implement the class according to specifications (from pyjolt.caching import BaseCacheBackend), simply pass it as the config parameter ("CACHE_BACKEND") and use it.

## AI Interface (Experimental!)

The AI Interface extension helps the user integrate a chat interface to popular vendors with ChatGPT compatible api's seemlesly. You must first install the needed dependencies with:

```
uv add "pyjolt[ai_interface]"
```

This will install OpenAi, Torch, Numpy, Sentence-transformers and pgvector libraries. These are neccessary for all required funcionality. With this, you will be able to connect to any ChatGPT compatible api like Groq, xAI, Perplexity (Sonar), Google Gemini and locally hosten Ollama, LM Studio or VLLM.

The extension accepts several configurations which are listed below (with defaults):

```
AI_INTERFACE = {
    API_KEY: str #required
    API_BASE_URL: Optional[str] = "https://api.openai.com/v1" #points to the OpenAi compatible api of the service
    ORGANIZATION_ID: Optional[str] = None
    PROJECT_ID: Optional[str] = None
    TIMEOUT: Optional[int] = 30
    MODEL: Optional[str] = "gpt-3.5-turbo" #model that is used
    TEMPERATURE: Optional[float] = 1.0 #temperature (randomness) of the used model. For higher "creativity"
    RESPONSE_FORMAT: Optional[dict[str, str]] = {"type": "json_object"} #format of the return object
    TOOL_CHOICE: Optional[bool] = False #if AI tools can be used
    MAX_RETRIES: Optional[int] = 0 #number of retries in case of failure
    CHAT_CONTEXT_NAME: Optional[str] = "chat_context" #name of the injected chat context varible
}
```

To implement the interface:

```
#ai_interface.py #next to __init__.py

from typing import Optional

from app.api.models.chat_session import ChatSession
from app.extensions import db

from pyjolt.database import AsyncSession
from pyjolt.ai_interface import AiInterface
from pyjolt.request import Request


class Interface(AiInterface):

    @db.managed_session
    async def chat_context_loader(self, req: Request,
                                  session: AsyncSession) -> Optional[ChatSession]:
        chat_session_id: Optional[int] = req.route_parameters.get("chat_session_id",
                                                                  None)
        if chat_session_id is None:
            return None
        return await ChatSession.query(session).filter_by(id = chat_session_id).first()

ai_interface: Interface = Interface()
```

Then simply include the ai_interface in the application configs like before to load and register it with the app:

```
#configs.py

EXTENSIONS: list[str] = [
    'app.extensions:db',
    'app.extensions:migrate',
    'app.authentication:auth',
    'app.ai_interface:ai_interface'
]
```

When implementing the interface you have to provide the ***chat_context_loader*** method which at minimum accepts the ***self*** argument pointing at the extension (has access to the application via ***self.app***) and the current request. The above example
also adds the ***@db.managed_session*** decorator for automatic injection and handling of database sessions. The implemented method must return None (when the chat context was not found) or the chat context object (database model). If the method returns None, the extension raises a ChatContextNotFound exception (from pyjolt.ai_interface import ChatContextNotFound). This error can simply be handled in the ExceptionHandler implementation (see above).

If the method returns a valid object (not None), the object is injected into the endpoint handler method with the configured chat context name (default: "chat_context"). This helps with loading existing chat contexts and keeps the endpoint handlers lean.

### AI Tools

You can also expose certain functions to the AI interface which can be called directly by the AI. This is useful to run methods like getting the current weather in a location. The exposed methods must be declared inside the interface class (next to the chat_context_loader) and decorated with the ***@tool*** decorator. Example:

```
from pyjolt.ai_interface import tool

class Interface(AiInterface):

    #chat_context_loader implementation

    @tool(name = "method_name", description: "method_description")
    async def some_tool(self, arg1: str, arg2: str) -> Any:
        """some tool logic"
```

The above example exposes the method ***some_method*** to the AI interface. The decorator ***@tool*** accepts to optional arguments (name and description). If none are provided the actual method name is used and the doc string for the description. The description helps the AI interface (the called LLM) determine which method should be called. Therefore it is recommended to provide concise and accurate descriptions. The exposed method is not just exposed but also analyzed and a method metadata object is constructed which also provides details about the implemented method (arguments, arguments types etc.). With this added metadata the AI (called LLM) can determine which arguments it must pass to the method or if any arguments are missing.

If execution of the tool method failes for whatever reason, a "FailedToRunAiToolMethod" exception is raised which can be handled in the ExceptionHandler implementation.

The number of method tools is not limited, however, we recommend to seperate them into subclasses which the main interface class can inherit from (in addition to the AiInterface class). In this way, you can keep the tools logically grouped.

## Email client

The email client extension can be used for sending emails using the ***aiosmtplib*** package. You can simply initilize the extension:

```
#app/extensions.py
from pyjolt.email import EmailClient

email_client: EmailClient = EmailClient(configs_name = "EMAIL_CLIENT") #configs_name="EMAIL_CLIENT" is the default and can be omitted
```

You then register the extension in the application configs:
```
#app/configs.py

EXTENSIONS: list[str] = [
    .
    .
    .
    "app.extension:email_client"
]
```

You have to provide certain configurations for the client:

```
#app/configs.py

EMAIL_CLIENT: dict[str, str|int|bool] = {
    "SENDER_NAME_OR_ADDRESS": str #the name or email that is used for the sender
    "SMTP_SERVER": str #url of the smtp server
    "SMTP_PORT" int #port of the smtp server
    "USERNAME": str #username for the used email account
    "PASSWORD": str #password of the used email account
    "USE_TLS": bool = True #if tls encryption should be used. Default = True
}

```

Once registered and configured the client can be used in any endpoint/method like this:

```
#inside endpoint method:

await email_client.send_email(to_address: str|list[str], subject: str, body: str, attachments: Optional[dict[str, bytes]] = None) -> None
await email_client.send_email_with_template(to_address: str|list[str], subject: str, template_path: str, attachments: Optional[dict[str, bytes]] = None, context: Optional[dict[str, Any]] = None) -> None
```

The first method sends the string body and the second method uses the template at the provided path (same as in template html responses)

## Command line interface

If you wish you can create command line interface utility methods to help with application maintanence. To do so you have to use the CLIController class:

```
#app/cli/cli_controller.py

from pyjolt.cli import CLIController, command, argument

class UtilityCLIController(CLIController):
    """A simple CLI utility controller."""

    @command("greet", help="Greet a user with a message.")
    @argument("name", arg_type=str, description="The name of the user to greet.")
    async def greet(self, name: str):
        """Greet by name."""
        print(f"Hello, {name}! Welcome to the CLI utility.")

    @command("add", help="Add two numbers.")
    @argument("a", arg_type=int, description="The first number.")
    @argument("b", arg_type=int, description="The second number.")
    async def add(self, a: int, b: int):
        """Add two numbers and print the result."""
        result = a + b
        print(f"The sum of {a} and {b} is {result}.")
```

In this controller you can add as many cli method as you wish with the use of the @command and @argument decorators. The ***self*** keyword points at the controller instance which has access to the application instance (***self.app: PyJolt***).
Each command method requires the @command decorator, but the @argument decorator(s) are optional depending on if the method needs input from the user or not.

### @command
The @command decorator requires a coommand_name: str argument under which the command will be accessible. You can also provide a ***help*** argument detailing the purpose of the method and options.

### @argument
You can add as many @argument decorators as you wish to a method. This decorator tells the parser what arguments (name) to except and in what data type these arguments are going to be. PyJolt automatically casts arguments
into the provided type. Allowed types are ***int***, ***float*** and ***str***.

After you have created the CLI controller you have to register it with the application. To do so you have to add it in the application configurations

```
CLI_CONTROLLERS: List[str] = [
    'app.cli.cli_controller:UtilityCLIController' #path:CLIController
]
```

## Middleware

Middleware can be useful for anything from logging to measuring performance or modifying requests/responses. To use middleware in your PyJolt app you have to create a middleware class

```
#app/middleware/timing_mw.py

import time
from pyjolt.middleware import MiddlewareBase
from pyjolt.request import Request
from pyjolt.response import Response

class TimingMW(MiddlewareBase):
    async def middleware(self, req: Request) -> Response:
        t0 = time.perf_counter()
        res = await self.next(req)           # pass down
        res.headers["x-process-time-ms"] = str(int((time.perf_counter() - t0)*1000))
        return res
```

This class must inherit from MiddlewareBase and define an ***async def middleware(self, req: Request) -> Response*** method. The example measures how long it takes to process the request and adds an "x-process-time-ms" header to the response. Each middleware must return a Response (either by returning one directly - short-circuit, or by awaiting self.next(req) and returning that result).

To add the middleware to the application you simply register it by adding it to the configurations of the app:

```
#configs.py

MIDDLEWARE: list[str] = [
    'app.middleware.timing_mw:TimingMW'
]
```

**Middleware order note**
Middleware wraps the base application in reverse order of the provided list, so the **first element** is the **outermost** wrapper.

#### Exception handling in middleware
Middleware runs in the same call chain as endpoint handlers. If your middleware raises, the framework catches it and dispatches to any registered exception handlers. If you handle the error inside the middleware and return a Response, exception handlers will not run. To attach data (e.g., timing) even on errors, store it on req.state: Any in a finally block and read it in your exception handler.

**Note**
Middleware is useful when you wish to run some functionality for every request. For more fine-grained functionality we recommend using before/after request handlers in controllers or decorators on endpoint handlers.

## Testing

PyJolt uses Pytest for running tests. For creating tests use the PyJoltTestClient object from ***pyjolt.testing***.
We recommend creating a ***tests*** folder inside your ***app*** directory (next to templates and static folders). You may organize tests differently as long as you follow Pytest’s discovery rules.

### Configuring test client

Inside the ***tests*** folder create a **conftest.py** file with the following content:

```
# tests/conftest.py

import pytest
from pyjolt.testing import PyJoltTestClient
from app import Application

@pytest.fixture
async def application():
    yield Application()

@pytest.fixture
async def client(application):
    async with PyJoltTestClient(application) as c:
        yield c
```

this creates and yields the test client for use in all test methods. The test client manages lifespan events using asgi_lifespan, so any startup/shutdown hooks will work just like when running the app with Uvicorn.
Inside the ***tests*** folder you can create as many test files as you wish. To can also organize them into subfolders as long as you follow **Pytest naming conventions**. An example test file is:

```
#tests/test_user_api.py

async def test_get_users(client):
    res = await client.get("/api/v1/users")
    assert res.status_code == 200

```

In this file there is a single method (test_get_users) which gets the PyJoltTestClient automatically injected. It makes a GET request to the "/api/v1/users" endpoint and asserts that the response
status code is 200 (OK). If the assertion fails the test fails.

### Running tests

If you use uv for dependency management you can run all specified tests with the following command:

```
uv run --env-file path/to/.env pytest
```

this will load environmental variables and run pytest. Pytest automatically detects the ***tests** folder and all specified tests (if proper naming conventions are followed). If you don't use .env files
you can ommit "--env-file path/to/.env".

#### Pytest configs

If using ***uv*** for dependency management you can add configurations for Pytest to the pyproject.toml file. Otherwise, look up configuration handling. uv example:

```
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

## Benchmarks

A simple test using Apache Bench, hitting the endpoint (example app) ***/api/v1/users*** shows the following results:

```
(PyJolt) marko@Markos-MacBook-Air PyJolt % ab -k -c 200 -n 2000 http://localhost:8080/api/v1/users
This is ApacheBench, Version 2.3 <$Revision: 1923142 $>
Copyright 1996 Adam Twiss, Zeus Technology Ltd, http://www.zeustech.net/
Licensed to The Apache Software Foundation, http://www.apache.org/

Benchmarking localhost (be patient)
Completed 200 requests
Completed 400 requests
Completed 600 requests
Completed 800 requests
Completed 1000 requests
Completed 1200 requests
Completed 1400 requests
Completed 1600 requests
Completed 1800 requests
Completed 2000 requests
Finished 2000 requests


Server Software:        uvicorn
Server Hostname:        localhost
Server Port:            8080

Document Path:          /api/v1/users
Document Length:        139 bytes

Concurrency Level:      200
Time taken for tests:   1.845 seconds
Complete requests:      2000
Failed requests:        0
Keep-Alive requests:    0
Total transferred:      573561 bytes
HTML transferred:       278000 bytes
Requests per second:    1083.84 [#/sec] (mean)
Time per request:       184.529 [ms] (mean)
Time per request:       0.923 [ms] (mean, across all concurrent requests)
Transfer rate:          303.54 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    0   0.7      0       3
Processing:     6  178 114.2    177    1065
Waiting:        2  178 114.2    177    1064
Total:          6  179 114.3    177    1067

Percentage of the requests served within a certain time (ms)
  50%    177
  66%    194
  75%    202
  80%    214
  90%    341
  95%    377
  98%    512
  99%    534
 100%   1067 (longest request)
```

The test was performed on ***localhost*** with 200 concurrent requests and 2000 total requests. The endpoint performs a simple query (SQLite database) to fetch all users.

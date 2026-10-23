"""PyScript adapter. Imported only when Application.start() is called."""

import asyncio
import json
import re
from urllib.parse import urlsplit, parse_qs, urlencode

from js import document, window  # type: ignore[import-not-found]
from pyodide.http import pyfetch  # type: ignore[import-not-found]
from pyscript.ffi import create_proxy, is_none  # type: ignore[import-not-found]

from .exceptions import APIError, NetworkError, JsonResponseError
from .view import ComponentView
from .lifecycle import invoke


class APIClient:
    def __init__(self, prefix, token):
        self.prefix = prefix.rstrip("/")
        self.token = token

    def scoped(self, scope):
        client = self

        class ScopedClient:
            async def request(self, *args, **kwargs):
                return await scope.wait(client.request(*args, **kwargs))

            async def get_json(self, path, **options):
                return await self.request("GET", path, **options)

            async def post_json(self, path, data=None, **options):
                return await self.request("POST", path, data=data, **options)

            async def put_json(self, path, data=None, **options):
                return await self.request("PUT", path, data=data, **options)

            async def patch_json(self, path, data=None, **options):
                return await self.request("PATCH", path, data=data, **options)

            async def delete(self, path, **options):
                return await self.request("DELETE", path, **options)

        return ScopedClient()

    async def request(
        self, method, path, *, data=None, headers=None, response_type="json"
    ):
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or not path.startswith("/") or "\\" in path:
            raise ValueError("API paths must be local absolute paths")
        headers = {**(headers or {}), "X-Patera-UI-Token": self.token}
        options = {
            "method": method,
            "credentials": "same-origin",
            "headers": headers,
            "redirect": "error",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
            options["body"] = json.dumps(data)
        abort = window.AbortController.new()
        options["signal"] = abort.signal
        try:
            try:
                response = await pyfetch(self.prefix + path, **options)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                raise NetworkError(f"{method} {path}") from error
            if not response.ok:
                raise APIError(response.status, await response.text())
            text = await response.text()
            if response_type == "text":
                return text
            if response_type != "json":
                raise ValueError("response_type must be json or text")
            if not text.strip():
                return None
            try:
                return json.loads(text)
            except ValueError as error:
                raise JsonResponseError(f"Invalid JSON from {path}") from error
        except asyncio.CancelledError:
            abort.abort()
            raise

    async def get_json(self, path, **options):
        return await self.request("GET", path, **options)

    async def post_json(self, path, data=None, **options):
        return await self.request("POST", path, data=data, **options)

    async def put_json(self, path, data=None, **options):
        return await self.request("PUT", path, data=data, **options)

    async def patch_json(self, path, data=None, **options):
        return await self.request("PATCH", path, data=data, **options)

    async def delete(self, path, **options):
        return await self.request("DELETE", path, **options)


class Browser:
    def __init__(self, app, target, config):
        self.app = app
        self.root = document.querySelector(target)
        if is_none(self.root):
            raise RuntimeError(f"Missing UI root: {target}")
        self.mount = config.get("mount", "").rstrip("/")
        self.api = APIClient(config.get("api_prefix", ""), config.get("token", ""))
        self.listeners = []
        self.components = {}
        self.component_types = {}
        self.tasks = set()
        self.proxies = []
        self.next_id = 0
        self.closed = False
        self.scroll_restoration = str(window.history.scrollRestoration)
        window.history.scrollRestoration = "manual"
        self.active_layouts = []
        self.pending_context = None
        self.rendered_context = None
        self.reload_url = config.get("reload_url")
        self.build_id = config.get("build_id")

    def spawn(self, awaitable):
        task = asyncio.create_task(awaitable)
        self.tasks.add(task)

        def completed(done):
            self.tasks.discard(done)
            if not done.cancelled() and (error := done.exception()) is not None:
                self.app.report_error(error)

        task.add_done_callback(completed)
        return task

    def listen(self, element, name, callback, collection=None):
        proxy = create_proxy(callback)
        element.addEventListener(name, proxy)
        (self.listeners if collection is None else collection).append(
            (element, name, proxy)
        )

    @staticmethod
    def unlisten(collection):
        for element, name, proxy in collection:
            element.removeEventListener(name, proxy)
            proxy.destroy()
        collection.clear()

    def relative(self, pathname):
        if pathname == self.mount:
            return "/"
        if pathname.startswith(self.mount + "/"):
            return pathname[len(self.mount) :]
        return None

    async def start(self):
        for component in self.app.components:
            self.register_component(component)
        connected = create_proxy(self.connect)
        disconnected = create_proxy(self.disconnect)
        self.proxies.extend([connected, disconnected])
        window.pateraUI.attach(self.root, connected, disconnected)
        for tag in self.component_types:
            window.pateraUI.define(tag)
        self.listen(document, "click", self.click)
        self.listen(window, "popstate", self.popstate)
        path = self.relative(str(window.location.pathname))
        if path is None:
            raise ValueError("Initial URL is outside the UI mount")
        await self.app.navigate(
            path + str(window.location.search) + str(window.location.hash),
            history="replace",
        )
        if self.reload_url:
            self.spawn(self.watch_build())

    async def watch_build(self):
        while not self.closed:
            await asyncio.sleep(1)
            try:
                response = await pyfetch(self.reload_url, cache="no-store")
                if response.ok and (await response.json())["id"] != self.build_id:
                    window.location.reload()
                    return
            except Exception:
                # Backend reloads can briefly make the server unavailable.
                continue

    def click(self, event):
        if (
            event.defaultPrevented
            or event.button != 0
            or any((event.metaKey, event.ctrlKey, event.shiftKey, event.altKey))
        ):
            return
        target = event.target
        if not hasattr(target, "closest"):
            return
        link = target.closest("a[href]")
        if (
            is_none(link)
            or link.hasAttribute("download")
            or link.hasAttribute("data-ui-ignore")
            or link.hasAttribute("router-ignore")
        ):
            return
        if str(link.target) not in {"", "_self"}:
            return
        if str(link.origin) != str(window.location.origin):
            return
        path = self.relative(str(link.pathname))
        if path is None:
            return
        if (
            str(link.pathname) == str(window.location.pathname)
            and str(link.search) == str(window.location.search)
            and link.hash
        ):
            return
        event.preventDefault()
        self.spawn(self.app.navigate(path + str(link.search) + str(link.hash)))

    def save_scroll(self):
        window.pateraUI.saveScroll()

    def popstate(self, event):
        path = self.relative(str(window.location.pathname))
        if path is not None:
            scroll = list(window.pateraUI.scrollState())
            url = path + str(window.location.search) + str(window.location.hash)

            async def navigate():
                generation = self.app._generation + 1
                success = await self.app.navigate(url, history="none")
                if success and self.app._generation == generation:
                    window.scrollTo(*scroll)

            self.spawn(navigate())

    def history(self, url, mode):
        if mode != "none":
            method = (
                window.history.pushState
                if mode == "push"
                else window.history.replaceState
            )
            method(None, "", self.mount + url)
        fragment = urlsplit(url).fragment
        if fragment:
            element = document.getElementById(fragment)
            if not is_none(element):
                element.scrollIntoView()

    def release_navigation_task(self, task):
        # A handler may navigate away from its own component. The navigation
        # scope now owns this work; disconnection must not cancel the redirect.
        for record in self.components.values():
            record["instance"].scope.tasks.discard(task)

    def register_component(self, component):
        tag = component.tag
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+", tag):
            raise ValueError(f"Invalid custom element name: {tag!r}")
        existing = self.component_types.get(tag)
        if existing is not None and existing is not component:
            raise ValueError(f"Duplicate component: {tag}")
        self.component_types[tag] = component
        window.pateraUI.define(tag)

    async def present(self, view, context):
        self.pending_context = context
        generation = self.app._generation
        created = []

        def check():
            if self.closed or context.closed or generation != self.app._generation:
                raise asyncio.CancelledError()

        try:
            check()
            if not isinstance(view, ComponentView):
                markup = view.render(self.app.template_engine)
                await self.clear_components()
                check()
                self.active_layouts = []
                self.root.innerHTML = str(markup)
                await self.wait_root(self.root)
                title = view.title
            else:
                metadata = view.metadata
                layout = metadata.layout or self.app.base_layout
                chain = ([(layout, None)] if layout else []) + [
                    (item.layout, item.target) for item in metadata.sublayouts
                ]
                common = 0
                while common < min(len(chain), len(self.active_layouts)):
                    old_type, old_target, instance = self.active_layouts[common]
                    if chain[common] != (old_type, old_target) or instance.scope.closed:
                        break
                    instance.context = context
                    if instance._renderer:
                        for name, values in (
                            ("params", context.params),
                            ("query", self.query_parameters()),
                        ):
                            captured = instance._renderer.context.get(name)
                            if isinstance(captured, dict):
                                previous = dict(captured)
                                captured.clear()
                                captured.update(values)
                                for key in previous.keys() | values.keys():
                                    if previous.get(key) != values.get(key):
                                        self.invalidate(instance, name + "." + key)
                    common += 1
                for _, _, instance in reversed(self.active_layouts[common:]):
                    instance.element.remove()
                self.active_layouts = self.active_layouts[:common]
                parent = self.active_layouts[-1][2].element if common else self.root
                for component, selector in chain[common:]:
                    check()
                    target = (
                        parent
                        if selector is None
                        else self.find_target(parent, selector)
                    )
                    target.innerHTML = ""
                    instance = self.create(component, target, context, {})
                    created.append(instance)
                    await instance.scope.wait(instance.init_complete, shared=True)
                    check()
                    self.active_layouts.append((component, selector, instance))
                    parent = instance.element
                    await self.app.emit("layout-change", instance)
                target = (
                    self.find_target(parent, metadata.target or self.app.default_target)
                    if chain
                    else self.root
                )
                check()
                target.innerHTML = ""
                if view.component is None:
                    target.innerHTML = str(
                        view.content.render(self.app.template_engine)
                    )
                    await self.wait_root(target)
                    title = view.content.title or metadata.title
                else:
                    instance = self.create(view.component, target, context, view.args)
                    created.append(instance)
                    await instance.scope.wait(instance.init_complete, shared=True)
                    check()
                    title = (
                        await invoke(metadata.title, instance)
                        if callable(metadata.title)
                        else metadata.title
                    )
            check()
            if title is not None:
                document.title = str(title)
            self.rendered_context = context
            panel = document.getElementById("patera-ui-error")
            if not is_none(panel):
                panel.remove()
        except BaseException:
            for instance in reversed(created):
                instance.element.remove()
            self.active_layouts = [
                entry for entry in self.active_layouts if entry[2] not in created
            ]
            raise
        finally:
            if self.pending_context is context:
                self.pending_context = None

    def find_target(self, parent, selector):
        target = parent.querySelector(selector)
        if is_none(target) or (
            parent.hasAttribute("data-ui-instance")
            and target.closest("[data-ui-instance]") != parent
        ):
            raise LookupError(f"Missing owned layout target: {selector}")
        return target

    def create(self, component, target, context, args):
        self.register_component(component)
        element = document.createElement(component.tag)
        element.setAttribute("data-ui-args", json.dumps(args))
        target.appendChild(element)
        record = self.components.get(str(element.getAttribute("data-ui-instance")))
        if record is None:
            raise RuntimeError(f"Unable to connect {component.tag}")
        record["instance"].context = context
        return record["instance"]

    def error(self, error):
        window.console.error(str(error))
        panel = document.getElementById("patera-ui-error")
        if is_none(panel):
            panel = document.createElement("div")
            panel.id = "patera-ui-error"
            panel.setAttribute("role", "alert")
            self.root.before(panel)
        panel.textContent = f"UI error: {error}"

    def connect(self, element):
        if self.closed or element.hasAttribute("data-ui-instance"):
            return
        self.next_id += 1
        key = str(self.next_id)
        element.setAttribute("data-ui-instance", key)
        try:
            instance = self.component_types[str(element.localName)](self.app, element)
            instance.context = self.pending_context or self.app.context
            instance.args = self.arguments(element)
            parent = (
                element.parentElement.closest("[data-ui-instance]")
                if not is_none(element.parentElement)
                else None
            )
            if not is_none(parent):
                instance.parent = self.components[
                    str(parent.getAttribute("data-ui-instance"))
                ]["instance"]
        except Exception as error:
            element.removeAttribute("data-ui-instance")
            self.app.report_error(error)
            return
        record = {
            "instance": instance,
            "listeners": [],
            "unsubscribe": None,
            "task": None,
        }
        self.components[key] = record
        record["unsubscribe"] = instance.state.subscribe(
            lambda name, value: self.state_changed(instance, name, value)
        )
        if element.hasAttribute("defer"):
            return

        async def initialize():
            try:
                await instance.init_element()
            except asyncio.CancelledError:
                pass
            except Exception as error:
                if (
                    not self.pending_context
                    or instance.initialization_state == "fulfilled"
                ):
                    self.app.report_error(error, instance.context)

        record["task"] = self.spawn(initialize())

    def record(self, instance):
        return self.components.get(
            str(instance.element.getAttribute("data-ui-instance"))
        )

    def owned(self, instance, node):
        if node == instance.element:
            return True
        owner = (
            node.parentElement.closest("[data-ui-instance]")
            if node.hasAttribute("data-ui-instance")
            else node.closest("[data-ui-instance]")
        )
        return not is_none(owner) and owner == instance.element

    def arguments(self, element):
        value = element.getAttribute("data-ui-args")
        args = json.loads(str(value)) if not is_none(value) else {}
        for attr in list(element.attributes):
            name = str(attr.name)
            prefix = next(
                (p for p in (":", "data-jolt-", "data-ui-arg-") if name.startswith(p)),
                None,
            )
            if prefix:
                raw = str(attr.value)
                try:
                    args[name[len(prefix) :]] = json.loads(raw)
                except ValueError:
                    args[name[len(prefix) :]] = raw
        return args

    async def render_component(self, instance, markup, renderer):
        instance.scope.check()
        record = self.record(instance)
        if record is None:
            raise asyncio.CancelledError()
        if markup is not None:
            self.unlisten(record["listeners"])
            instance.element.innerHTML = str(markup)
        instance._renderer = renderer
        self.hydrate(instance)
        for name, value in instance.state._values.items():
            self.state_changed(instance, name, value)

    def hydrate(self, instance):
        record = self.record(instance)
        if record is None or instance.scope.closed:
            return
        self.unlisten(record["listeners"])
        for node in instance.element.querySelectorAll("*"):
            if not self.owned(instance, node):
                continue
            for attribute in list(node.attributes):
                name, method_name = str(attribute.name), str(attribute.value)
                prefix = next(
                    (p for p in ("@", "data-ui-on-", "jolt-") if name.startswith(p)),
                    None,
                )
                if not prefix:
                    continue
                event_name = name[len(prefix) :]
                if event_name == "show-if":
                    continue
                method = (
                    getattr(instance, method_name, None)
                    if not method_name.startswith("_")
                    else None
                )
                if not callable(method):
                    raise ValueError(f"Missing event handler: {method_name}")
                if (
                    prefix == "data-ui-on-"
                    and getattr(method, "__ui_event__", None) != event_name
                ):
                    raise ValueError(
                        f"Missing @event({event_name!r}) handler: {method_name}"
                    )

                def callback(e, method=method, node=node):
                    if str(e.type) == "submit":
                        e.preventDefault()
                    args = self.arguments(node)
                    # Explicit modifiers run during DOM dispatch, before Python awaits.
                    if node.hasAttribute("data-ui-prevent-default"):
                        e.preventDefault()
                    if node.hasAttribute("data-ui-stop-propagation"):
                        e.stopPropagation()

                    async def call():
                        if args:
                            await invoke(method, e, args)
                        else:
                            await invoke(method, e)

                    instance.spawn(call())

                self.listen(node, event_name, callback, record["listeners"])

    def state_changed(self, instance, name, value):
        if instance.scope.closed:
            return
        for node in [
            instance.element,
            *instance.element.querySelectorAll("[data-ui-text], [data-ui-value]"),
        ]:
            if not self.owned(instance, node):
                continue
            if str(node.getAttribute("data-ui-text")) == name:
                node.textContent = str(value)
            if str(node.getAttribute("data-ui-value")) == name and str(
                node.value
            ) != str(value):
                node.value = str(value)
        self.invalidate(instance, name)

    def invalidate(self, instance, binding):
        if instance.scope.closed or instance._renderer is None:
            return
        try:
            for identifier, markup in instance._renderer.refresh(binding):
                window.pateraUI.replaceBinding(instance.element, identifier, markup)
            self.hydrate(instance)
        except Exception as error:
            self.app.report_error(error, instance.context)

    def data_changed(self, name, value):
        for record in list(self.components.values()):
            instance = record["instance"]
            if instance.metadata.get("data_field") == name:
                instance.spawn(instance.rerender())
            else:
                self.invalidate(instance, "app." + name)

    def query_parameters(self):
        if self.pending_context:
            return {
                key: values[-1] for key, values in self.pending_context.query.items()
            }
        return {
            key: values[-1]
            for key, values in parse_qs(
                str(window.location.search).lstrip("?"), keep_blank_values=True
            ).items()
        }

    def update_query(self, values, *, replace_all=False, history="push"):
        if history not in {"push", "replace"}:
            raise ValueError("Query history must be push or replace")
        previous = self.query_parameters()
        updated = {} if replace_all else dict(previous)
        for key, value in values.items():
            if value is None:
                updated.pop(key, None)
            else:
                updated[key] = str(value)
        if previous == updated:
            return
        active_url = urlsplit(
            self.app.context.url if self.app.context else str(window.location.href)
        )
        path = (
            active_url.path
            if self.app.context
            else self.relative(active_url.path) or "/"
        )
        url = (
            path
            + ("?" + urlencode(updated) if updated else "")
            + ("#" + active_url.fragment if active_url.fragment else "")
        )
        if not self.pending_context:
            self.history(url, history)
        if self.app.context:
            self.app.context.url = url
        for record in list(self.components.values()):
            instance = record["instance"]
            if instance._renderer:
                query = instance._renderer.context.get("query")
                if isinstance(query, dict):
                    query.clear()
                    query.update(updated)
            for key in previous.keys() | updated.keys():
                if previous.get(key) != updated.get(key):
                    self.invalidate(instance, "query." + key)

    def select(self, instance, selector, *, many=False):
        # Escape shorthand attribute names in selector syntax, outside literals.
        chars, quote, index = [], None, 0
        while index < len(selector):
            char = selector[index]
            if char == "\\" and index + 1 < len(selector):
                chars.extend(selector[index : index + 2])
                index += 2
                continue
            if quote:
                if char == quote:
                    quote = None
            elif char in ("'", '"'):
                quote = char
            elif char == "[":
                match = re.match(r"\[\s*:", selector[index:])
                if match:
                    chars.append(match[0][:-1] + "\\:")
                    index += len(match[0])
                    continue
            chars.append(char)
            index += 1
        selector = "".join(chars)
        nodes = [
            node
            for node in instance.element.querySelectorAll(selector)
            if self.owned(instance, node)
        ]
        return nodes if many else (nodes[0] if nodes else None)

    async def insert_html(self, instance, markup, *, target=None, position="beforeend"):
        target = target or instance.element
        if target != instance.element and not self.owned(instance, target):
            raise ValueError("Insertion target belongs to another component")
        if position not in {"afterbegin", "beforeend"}:
            raise ValueError(
                "Insert inside the owned target with afterbegin or beforeend"
            )
        target.insertAdjacentHTML(position, str(markup))
        self.hydrate(instance)
        await self.wait_children(instance)

    async def wait_children(self, instance):
        await self.wait_root(instance.element)

    async def wait_root(self, element):
        futures = []
        for node in element.querySelectorAll("[data-ui-instance]"):
            record = self.components.get(str(node.getAttribute("data-ui-instance")))
            if record and not node.hasAttribute("defer"):
                futures.append(record["instance"].init_complete)
        if futures:
            await asyncio.gather(*(asyncio.shield(future) for future in futures))

    def disconnect(self, element):
        key = str(element.getAttribute("data-ui-instance"))
        element.removeAttribute("data-ui-instance")
        record = self.components.pop(key, None)
        if record is not None:
            instance = record["instance"]
            instance.scope.cancel()
            self.unlisten(record["listeners"])
            if record["unsubscribe"]:
                record["unsubscribe"]()
            self.spawn(instance.dispose())

    async def dispose(self, record):
        self.unlisten(record["listeners"])
        if record["unsubscribe"]:
            record["unsubscribe"]()
        await record["instance"].dispose()

    async def clear_components(self):
        records = list(self.components.values())
        self.components.clear()
        for record in reversed(records):
            record["instance"].element.removeAttribute("data-ui-instance")
            try:
                await self.dispose(record)
            except Exception as error:
                self.error(error)

    async def close(self):
        self.closed = True
        window.history.scrollRestoration = self.scroll_restoration
        self.unlisten(self.listeners)
        await self.clear_components()
        window.pateraUI.detach(self.root)
        for task in tuple(self.tasks):
            task.cancel()
        for proxy in self.proxies:
            proxy.destroy()
        self.proxies.clear()

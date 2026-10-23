# Python desktop notes

A separate example of the optional UI extension. Existing `desktop_notes` is
unchanged. Requires the workspace installation or `patera-desktop-ui`.

From this directory, put a complete PyScript offline distribution in `ui-runtime`
and lock its actual paths/versions with `patera cli ui:lock-runtime`. See the
[extension README](../../packages/patera-desktop-ui/README.md) for runtime setup.
Then run:

```sh
patera cli ui:build
patera cli desktop:run
```

Or use `patera dev` and open `http://127.0.0.1:3000/app/` (use the configured
server port). Notes persist in `user_data_dir("Patera Python Notes")/notes.sqlite`.
Use `patera cli desktop:package` to prepare and bundle the offline UI.

The browser only receives frontend sources and view templates. SQLite and API
handlers stay in the native backend. Jinja2 and MarkupSafe are bundled by the
extension. The runtime files and generated output are build inputs/artifacts,
not part of this example's source.

The frontend uses `Application(__name__)` to discover component pages in
`frontend/frontend/pages/`, persistent layouts in `layouts/`, `@tag` components
in `components/`, and error handlers in `exceptions/`. The counter remains
mounted while navigating. Detail and edit pages share a nested layout. The
search field updates a query parameter and a Jinja fragment without replacing
the input. Notes can be created, viewed and edited; failures render an error page.
Event handlers use `SubmitEvent` and `InputEvent` from `patera.desktop.ui.types`
under `TYPE_CHECKING`. Framework classes come from `patera.desktop.ui`.

See the [runtime guide](../../packages/patera-desktop-ui/docs/runtime.md) for
the component, lifecycle, binding and routing APIs.

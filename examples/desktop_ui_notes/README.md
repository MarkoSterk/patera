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

## Explore the workspace

1. Open **Overview** and choose **Add example notes** to insert six real notes.
   This is optional and never replaces existing notes.
2. Browse **Library**, search titles and content, and change the sort order.
   Search and sort are reflected in the URL and restored by Back/Forward.
3. Open a note. The note browser remains mounted when switching notes or moving
   between reading and editing; its filter and scroll position are retained.
4. Choose **New note**, type a draft, and visit another page. Resume it from
   Overview or New note. Editing existing notes also preserves unsaved drafts.
5. Star notes in the reading view and find them under **Favorites**.
6. Change the theme and collection density under **Preferences**. They apply
   immediately across the workspace, without replacing the outer layout.
7. Save or delete a note and watch the sidebar counts and library update.
   Deletion requires a second, explicit confirmation in the reading view.

Notes persist in SQLite. Drafts, favorites, and appearance preferences are
**window-session state**: they survive navigation, but reset on reload or close.
The interface makes that distinction explicit. Drafts are not saved to disk.

## What demonstrates SPA behavior

`NotesApplication` owns a shared notes store. The persistent main layout fetches
the library once; internal navigation uses that store. Successful writes update
it immediately, notifying mounted Jinja fragments. **Refresh library** explicitly
reloads changes made outside the window. No data polling is used by the example
(the extension's DEBUG build-version polling still applies).

Discovery registers component pages in `frontend/frontend/pages/`, persistent
layouts in `layouts/`, components in `components/`, and error handlers in
`exceptions/`. The main sidebar and status bar remain mounted across routes;
the nested note layout preserves the note browser between detail/edit pages.
Only the route outlet and explicitly bound fragments are replaced. The reusable
`note-form` component handles both creation and editing, with per-note drafts.
All templates use Jinja2, and the responsive stylesheet is bundled locally.

Event handlers use types from `patera.desktop.ui.types` under `TYPE_CHECKING`.
Framework classes come from `patera.desktop.ui`. The native SQLite API supports
listing, reading, creating, updating, and deleting notes.

`tests/browser/desktop_ui.cjs` checks the complete flow with external requests
blocked, including one initial document load and one library read across
internal navigation. Set `UI_TEST_SCREENSHOT` to a `.png` path to capture the
light overview and dark library during the test.

See the [runtime guide](../../packages/patera-desktop-ui/docs/runtime.md) for
the component, lifecycle, binding and routing APIs.

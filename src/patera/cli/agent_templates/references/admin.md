# Administrative interfaces

Install `patera-admin`. Subclass `AdminInterface` from `patera.admin` and set an
explicit `MANAGED_MODELS` list. Register that class in `app_extensions`; configure
the matching upper-snake key with `AdminConfig`.

Key fields include `ADMIN_BASE_URL`, `DEFAULT_LANGUAGE`, `URL_FOR_FOR_LOGIN` and
`URL_FOR_FOR_LOGOUT` (the repeated FOR is intentional). Login/logout values are
route names implemented by the application. Admin does not create accounts or
provide your authentication policy. URLs include a language segment, e.g.
`/admin/en/dashboard`, plus the application URL prefix when configured.

Map roles returned by the auth loader to `Permissions` values from `patera.admin`:
`ADMIN_CAN_ENTER`, `ADMIN_CAN_VIEW`, `ADMIN_CAN_CREATE`, `ADMIN_CAN_EDIT`,
`ADMIN_CAN_DELETE`. A role named `admin` does not automatically grant these.
Each action needs entry permission and its own permission. Protect operational
panels and changing requests, not merely the dashboard navigation.

Model form metadata derives from
`patera.database.sql.declarative_base.ModelMeta`. Exclude sensitive/uneditable
fields and provide create/update schemas. `admin_create`, `admin_update`, and
`admin_delete` hooks implement application rules; raise `AdminFormError` from
`patera.admin.form_values` for field errors. Generic CRUD does not know password
hashing, ownership, or publication rules. Test direct requests with forged fields
and insufficient permissions, not just the displayed form.

Sources: tutorial chapters 11 and 19; architecture chapter 17.

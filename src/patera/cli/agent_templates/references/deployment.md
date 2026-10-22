# Runtime and deployment

`patera dev` requires `patera[dev]` and runs Uvicorn with reload and DEBUG on.
`patera prod` requires `patera[prod]` and runs Granian with DEBUG off. App discovery
looks in the conventional `app` package; select another with `--app module:Class`
or `PATERA_IMPORT`. Keep `@app` on the implementation class.

Dev/application CLI load an explicit `--env-file` or search `.env`, `.env.dev`,
`.env.local` in order. Production loads only an explicitly named environment file.
Existing process environment values win. Tests use `.env.test` when present.

Address precedence is `PATERA_HOST`/`PATERA_PORT`, defaults on the Config class,
then launcher defaults: localhost:3000 for dev, 0.0.0.0:80 for prod. Production
maps localhost to 0.0.0.0. Configure the deployment address explicitly as needed.

Keep ASGI lifespan enabled for database, cache, scheduler and cleanup hooks.
Apply reviewed migrations as an explicit deployment step. Persist databases,
uploads and necessary logs outside replaceable images; never place private
uploads under the public static directory. Match proxy path handling to
`URL_PREFIX` and static URLs. Use a health endpoint that checks required readiness.

Multiple workers each have their own singletons, memory caches and schedulers.
Choose a scheduler owner or distributed coordination; do not assume job IDs
prevent execution in several processes. Pin dependencies and test the production
configuration. Docker Compose is optional; honor the project's deployment system.

Sources: tutorial chapters 20–21; architecture chapters 9 and 13.

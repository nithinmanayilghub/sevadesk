# Glossary

Plain-word meanings. Newest terms at the bottom.

- **Reverse proxy** - A server that sits in front of your apps. It receives every request and passes each one to the right app. Caddy is ours.
- **Origin** - The triple of scheme, host and port, like `http://localhost:80`. Browsers treat different origins as separate places.
- **CORS** - A browser rule that blocks a page from calling a different origin unless that origin allows it. One origin means no CORS trouble.
- **Migration** - A small script that changes the database structure (add a table, add a column). Migrations run in order, so every database ends up the same.
- **ORM** - Object-Relational Mapper. A tool that lets you use Python classes instead of writing raw SQL. SQLAlchemy is ours.
- **OpenAPI** - A standard file that describes an API: its paths, inputs and outputs. Tools can read it to build docs and client code.
- **Transaction** - A group of database changes that succeed together or fail together. If one fails, a rollback undoes them all.
- **Env var** - A setting kept outside the code, in the environment. We use it for things like the database URL, so secrets stay out of code.
- **Testcontainers** - A test tool that starts a real Docker container (here, Postgres 18) for a test, then removes it. Tests run against the real thing.

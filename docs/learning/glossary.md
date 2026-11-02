# Glossary

Plain-word meanings. Newest terms at the bottom.

- **Reverse proxy** - A server that sits in front of your apps. It receives every request and passes each one to the right app. Caddy is ours.
- **Origin** - The triple of scheme, host and port, like `http://localhost:80`. Browsers treat different origins as separate places.
- **CORS** - A browser rule that blocks a page from calling a different origin unless that origin allows it. One origin means no CORS trouble.
- **Migration** - A small script that changes the database structure (add a table, add a column). Migrations run in order, so every database ends up the same.
- **ORM** - Object-Relational Mapper. A tool that lets you use Python classes instead of writing raw SQL. SQLAlchemy is ours.
- **OpenAPI** - A standard file that describes an API: its paths, inputs and outputs. Tools can read it to build docs and client code.
- **Transaction** - A group of database changes that succeed together or fail together. If one fails, a rollback undoes them all. In SevaDesk, the `get_session` dependency owns the transaction; services never commit.
- **Env var** - A setting kept outside the code, in the environment. We use it for things like the database URL, so secrets stay out of code.
- **Testcontainers** - A test tool that starts a real Docker container (here, Postgres 18) for a test, then removes it. Tests run against the real thing.
- **Caddy** - Our reverse proxy and web server. It is the front door: every browser request hits Caddy first.
- **FastAPI** - A Python framework for building web APIs. It also writes the OpenAPI description for us.
- **Postgres** - Our database. It stores data in tables and keeps it safe, even if the app restarts.
- **Docker** - A tool that runs programs in sealed boxes called containers. Each box has everything the program needs, so it runs the same on every computer.

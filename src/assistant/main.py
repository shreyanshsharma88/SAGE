from assistant.db.migrations import run_migrations
from assistant.db.repository import Repository
from assistant.tui.app import SageApp


def main() -> None:
    run_migrations()
    repository: Repository = Repository()
    app: SageApp = SageApp(repository)
    try:
        app.run()
    finally:
        repository.close()


if __name__ == "__main__":
    main()

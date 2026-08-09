import asyncio

from assistant.db.migrations import run_migrations
from assistant.db.repository import Repository
from assistant.reminders import REMINDER_POLL_SECONDS, check_and_fire_reminders


async def run_forever() -> None:
    run_migrations()
    repository: Repository = Repository()
    try:
        while True:
            check_and_fire_reminders(repository)
            await asyncio.sleep(REMINDER_POLL_SECONDS)
    finally:
        repository.close()


def main() -> None:
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()

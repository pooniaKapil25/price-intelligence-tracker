"""Explicit, operator-run Rewalto connection check; never runs during pytest collection."""

from backend.services.rewalto_client import check_connection


def main() -> None:
    try:
        check_connection()
        print("Rewalto connection succeeded.")
    except Exception as error:
        print(f"Rewalto connection failed ({type(error).__name__}).")


if __name__ == "__main__":
    main()

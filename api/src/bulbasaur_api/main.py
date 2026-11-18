"""Entry point for the optional Bulbasaur HTTP server."""


def main() -> None:
    import uvicorn

    uvicorn.run("bulbasaur_api.app:app", host="127.0.0.1", port=8088)


if __name__ == "__main__":
    main()

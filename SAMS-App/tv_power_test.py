
import asyncio
from androidtvremote2 import AndroidTVRemote

HOST = "192.168.1.10"


async def main():
    remote = AndroidTVRemote(
        "SAMS",
        "sams_tv_cert.pem",
        "sams_tv_key.pem",
        HOST,
    )

    try:
        print(f"Connecting to XStream Smart Box at {HOST}...")
        await remote.async_connect()

        state = remote.is_on
        print(f"Reported power state: {state!r}")

        if state is True:
            print("The box reports that it is ON.")
            print("No power command sent, to avoid turning it off.")
            return

        if state is None:
            print("Power state is unknown. No command sent.")
            return

        confirm = input(
            "Attempt to wake the box with POWER? Type YES: "
        ).strip()

        if confirm != "YES":
            print("Cancelled.")
            return

        remote.send_key_command("POWER")
        print("Wake attempt sent. Check the TV screen.")

    except Exception as error:
        print(f"{type(error).__name__}: {error}")

    finally:
        remote.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

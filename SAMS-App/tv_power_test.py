import sys
import asyncio
from androidtvremote2 import AndroidTVRemote

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.12"


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
            confirm = input(
                "Send POWER to attempt to turn it OFF? Type YES: "
            ).strip()

            if confirm != "YES":
                print("Cancelled.")
                return

            remote.send_key_command("POWER")
            print("POWER command sent. Check the TV screen.")

        elif state is False:
            print("The box reports that it is OFF.")
            confirm = input(
                "Send POWER to attempt to wake it? Type YES: "
            ).strip()

            if confirm != "YES":
                print("Cancelled.")
                return

            remote.send_key_command("POWER")
            print("POWER command sent. Check the TV screen.")

        else:
            print("Power state is unknown.")
            print("No command sent for safety.")

    except Exception as error:
        print(f"{type(error).__name__}: {error}")

    finally:
        remote.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
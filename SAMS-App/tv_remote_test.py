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
        print(f"Connecting to the streaming box at {HOST}...")
        await remote.async_connect()

        print("Connected successfully!")
        print(f"Box reports on: {remote.is_on}")
        print(f"Current app: {remote.current_app}")

        consent = input(
            "\nSend one harmless DPAD_UP navigation command? Type YES: "
        ).strip()

        if consent == "YES":
            remote.send_key_command("KEYCODE_DPAD_UP")
            print("Navigation command sent.")
            await asyncio.sleep(1)
        else:
            print("Command cancelled.")

    except Exception as error:
        print(f"Connection or command failed: "
              f"{type(error).__name__}: {error}")

    finally:
        remote.disconnect()
        print("Disconnected.")

if __name__ == "__main__":
    asyncio.run(main())
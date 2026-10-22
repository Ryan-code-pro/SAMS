
import asyncio
import getpass

from androidtvremote2 import AndroidTVRemote, CannotConnect, InvalidAuth

HOST = "192.168.1.10"
CLIENT_NAME = "SAMS"

async def main():
    remote = AndroidTVRemote(
        CLIENT_NAME,
        "sams_tv_cert.pem",
        "sams_tv_key.pem",
        HOST,
    )

    if await remote.async_generate_cert_if_missing():
        print("Created local pairing certificate.")

    print(f"\nTarget: Living Room TV / XStream Smart Box ({HOST})")
    print("Pairing may wake the streaming box.")
    consent = input("Is it okay to begin pairing? Type YES: ").strip()

    if consent != "YES":
        print("Cancelled. No pairing attempted.")
        return

    try:
        await remote.async_start_pairing()
        print("\nCheck the TV screen for its pairing code.")
        code = getpass.getpass("Enter the pairing code shown on TV: ").strip()

        await remote.async_finish_pairing(code)
        print("Pairing succeeded!")

    except InvalidAuth:
        print("Pairing code rejected. No remote command was sent.")
    except CannotConnect as error:
        print(f"Could not connect: {error}")
    except Exception as error:
        print(f"Pairing did not complete: {type(error).__name__}: {error}")
    finally:
        remote.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

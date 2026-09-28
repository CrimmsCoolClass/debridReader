import os
import sys

from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMessageBox,
)

from realdebrid import RealDebrid
from ui.library_window import LibraryWindow


API_KEY_FILE = os.path.expanduser(
    "~/.config/debrid-reader/api-key"
)


def load_api_key():

    # --------------------------------------------------------
    # First check the environment variable.
    #
    # This keeps the old method working too.
    # --------------------------------------------------------

    environment_key = os.environ.get(
        "REAL_DEBRID_TOKEN"
    )

    if environment_key:
        return environment_key.strip()

    # --------------------------------------------------------
    # Otherwise check our saved API key.
    # --------------------------------------------------------

    try:

        with open(
            API_KEY_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            api_key = file.read().strip()

            if api_key:
                return api_key

    except FileNotFoundError:

        pass

    except OSError as error:

        QMessageBox.warning(
            None,
            "API Key",
            f"Could not read saved API key:\n{error}",
        )

    return None


def save_api_key(
    api_key,
):

    directory = os.path.dirname(
        API_KEY_FILE
    )

    os.makedirs(
        directory,
        mode=0o700,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Write the key.
    # --------------------------------------------------------

    with open(
        API_KEY_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            api_key
        )

    # --------------------------------------------------------
    # Make sure the file itself is only readable/writable
    # by the current user.
    # --------------------------------------------------------

    os.chmod(
        API_KEY_FILE,
        0o600,
    )


def ask_for_api_key():

    while True:

        api_key, accepted = QInputDialog.getText(
            None,
            "Real-Debrid API Key",
            "Enter your Real-Debrid API key:",
        )

        if not accepted:
            return None

        api_key = api_key.strip()

        if not api_key:

            QMessageBox.warning(
                None,
                "API Key",
                "Please enter an API key.",
            )

            continue

        try:

            save_api_key(
                api_key
            )

        except OSError as error:

            QMessageBox.critical(
                None,
                "API Key",
                f"Could not save the API key:\n{error}",
            )

            return None

        return api_key


def main():

    app = QApplication(
        sys.argv
    )

    # --------------------------------------------------------
    # Try to get the API key.
    # --------------------------------------------------------

    token = load_api_key()

    # --------------------------------------------------------
    # If there isn't one, ask the user.
    # --------------------------------------------------------

    if not token:

        token = ask_for_api_key()

        if not token:

            return 0

    # --------------------------------------------------------
    # Start Real-Debrid.
    # --------------------------------------------------------

    try:

        realdebrid = RealDebrid(
            token
        )

        window = LibraryWindow(
            realdebrid
        )

        window.show()

        return app.exec()

    except Exception as error:

        QMessageBox.critical(
            None,
            "Debrid Reader",
            str(error),
        )

        return 1


if __name__ == "__main__":

    sys.exit(
        main()
    )

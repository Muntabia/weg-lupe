"""Zugangspasswort entfernen oder neu setzen, z. B. wenn man sich ausgesperrt hat.

Im Container:
  weglupe-reset-password             Passwort entfernen
  weglupe-reset-password NEUES_PW    Passwort neu setzen (Benutzer: weg)
"""
import sys

from . import db, settings


def main():
    db.conn()
    if len(sys.argv) > 1 and sys.argv[1]:
        pw = sys.argv[1]
        if len(pw) < 8:
            sys.exit("Das Passwort muss mindestens 8 Zeichen haben.")
        db.ex("INSERT INTO settings (key, value) VALUES ('auth_user', 'weg') "
              "ON CONFLICT(key) DO UPDATE SET value = excluded.value")
        settings.set_password(pw)
        print("Passwort gesetzt. Benutzername: weg")
    else:
        settings.set_password(None)
        print("Passwort entfernt. WEG-Lupe ist jetzt ohne Anmeldung erreichbar.")
        print("Bitte in der App unter Einstellungen ein neues Passwort setzen.")


if __name__ == "__main__":
    main()

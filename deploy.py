#!/usr/bin/env python
import argparse
import os

import requests

my_domain = "mastodonproportional.pythonanywhere.com"
username = "mastodonproportional"

parser = argparse.ArgumentParser()
parser.add_argument(
    "token",
    metavar="PYTHON_ANYWHERE_TOKEN",
    help="A Python Anywhere API token for your account",
)

args = parser.parse_args()

print("Rsync files....")
os.system(
    "rsync -rv --exclude '*.pyc' *"
    " mastodonproportional@ssh.pythonanywhere.com:mastodonproportional.pythonanywhere.com"
)

print("Reinstall dependencies....")
os.system(
    "ssh mastodonproportional@ssh.pythonanywhere.com"
    " '~/proporti.onl.venv/bin/pip install -U -r "
    "~/mastodonproportional.pythonanywhere.com/requirements.txt'"
)

print("Restarting....")
uri = "https://www.pythonanywhere.com/api/v0/user/{uname}/webapps/{dom}/reload/"
response = requests.post(
    uri.format(uname=username, dom=my_domain),
    headers={"Authorization": "Token {token}".format(token=args.token)},
)

if response.status_code == 200:
    print("All OK")
else:
    print(
        "Got unexpected status code {}: {!r}".format(
            response.status_code, response.content
        )
    )

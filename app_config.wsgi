# This file contains an example WSGI configuration required to serve up the
# web application on https://yourproject.pythonanywhere.com/
# It works by setting the variable 'application' to a WSGI handler of some
# description.

import os
import sys

# add your project directory to the sys.path
# project_home needs to match the working directory configured on pythonanywhere
project_home = '/home/yourproject/mastodon-gender-distribution'
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

os.environ['COOKIE_SECRET'] = 'SECRET_GOES_HERE'
os.environ['DEPLOY_URL'] = 'https://yourproject.pythonanywhere.com/'

# import flask app but need to call it "application" for WSGI to work
from server import app as application  # noqa
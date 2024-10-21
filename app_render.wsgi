# This file contains the WSGI configuration required to serve up your
# web application on Render
import os
import sys

# add your project directory to the sys.path
project_home = '/opt/render/project/src'
if project_home not in sys.path:
    sys.path = [project_home] + sys.path


# import flask app but need to call it "application" for WSGI to work
from server import app as application
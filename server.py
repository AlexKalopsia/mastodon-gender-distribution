import logging
import os

from authlib.integrations.flask_client import OAuth, OAuthError  # pip install Authlib
from flask import (  # pip install Flask
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from wtforms import Form, SelectField, StringField  # pip install WTForms

from analyze import (
    Cache,
    analyze_followers,
    analyze_friends,
    analyze_timeline,
    div,
    dry_run_analysis,
    get_friends_lists,
    get_mastodon_api,
)

logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
INSTANCE_NAME = os.environ.get("INSTANCE_NAME")
TRACKING_ID = os.environ.get("TRACKING_ID")

if not (CLIENT_ID and CLIENT_SECRET and INSTANCE_NAME):
    raise ValueError("Must set CLIENT_ID, CLIENT_SECRET and INSTANCE_NAME environment variables")

app = Flask("mastodon-gender-proportion")
app.config["SECRET_KEY"] = os.environ["COOKIE_SECRET"]
app.config["DRY_RUN"] = False
app.config["MASTODON_CLIENT_ID"] = CLIENT_ID
app.config["MASTODON_CLIENT_SECRET"] = CLIENT_SECRET
app.config["MASTODON_INSTANCE"] = INSTANCE_NAME

oauth = OAuth(app)
oauth.register(
    name="mastodon",
    api_base_url="https://"+INSTANCE_NAME+"/api/v1",
    access_token_url="https://"+INSTANCE_NAME+"/outh/token",
    authorize_url="https://"+INSTANCE_NAME+"/oauth/authenticate",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    client_kwargs={
        "scope": "read",
    },
    fetch_token=lambda: session.get("token"),  # DON'T DO IT IN PRODUCTION
)

mastodon = oauth.mastodon


@app.route("/login")
def login():
    redirect_uri = url_for("oauth_authorized", _external=True)
    return oauth.mastodon.authorize_redirect(redirect_uri)


@app.route("/logout")
def logout():
    session.pop("mastodon_token")
    session.pop("mastodon_user")
    flash("Logged out.")
    return redirect("/")


@app.errorhandler(OAuthError)
def handle_error(error):
    flash("You denied the request to sign in.")
    return redirect("/")


@app.route("/authorized")
def oauth_authorized():
    token = oauth.mastodon.authorize_access_token()
    resp = oauth.mastodon.get("account/verify_credentials.json")
    profile = resp.json()
    session["mastodon_token"] = (token["oauth_token"], token["oauth_token_secret"])
    session["mastodon_user"] = profile["screen_name"]
    instance_name="mastodon.social" # TODO: change
    try:
        session["lists"] = get_friends_lists(
            profile["screen_name"],
            CLIENT_ID,
            CLIENT_SECRET,
            token["oauth_token"],
            token["oauth_token_secret"],
            instance_name,
        )
    except Exception:
        app.logger.exception("Error in get_friends_lists, ignoring")
        session["lists"] = []

    flash("You were signed in as %s" % profile["screen_name"])
    return redirect("/")


class AnalyzeForm(Form):
    user_id = StringField("Mastodon User ID")
    lst = SelectField("List")


@app.route("/", methods=["GET", "POST"])
def index():
    oauth_token, oauth_token_secret, base_url = session.get(
        "mastodon_token", (None, None), "https://mastodon.social")
    form = AnalyzeForm(request.form)
    if session.get("lists"):
        form.lst.choices = [("none", "No list")] + [
            (str(list["id"]), list["name"]) for list in session["lists"]
        ]
    else:
        del form.lst

    results = {}
    list_name = list_id = error = None
    if request.method == "POST" and form.validate() and form.user_id.data:
        # Don't show auth'ed user's lists in results for another user.
        if hasattr(form, "lst") and form.user_id.data != session.get("mastodon_user"):
            del form.lst

        if app.config["DRY_RUN"]:
            list_name = None
            friends, followers, timeline = dry_run_analysis()
            results = {"friends": friends, "followers": followers, "timeline": timeline}
        else:
            if session.get("lists") and form.lst and form.lst.data != "none":
                list_id = int(form.lst.data)
                list_name = [
                    list["name"] for list in session["lists"] if int(list["id"]) == list_id
                ][0]

            try:
                api = get_mastodon_api(
                    CLIENT_ID, CLIENT_SECRET, oauth_token, oauth_token_secret, base_url
                )
                cache = Cache()
                results = {
                    "friends": analyze_friends(form.user_id.data, list_id, api, cache),
                    "followers": analyze_followers(form.user_id.data, api, cache),
                    "timeline": analyze_timeline(
                        form.user_id.data, list_id, api, cache
                    ),
                }
            except Exception as exc:
                import traceback

                traceback.print_exc()
                error = exc

    return render_template(
        "index.html",
        form=form,
        results=results,
        error=error,
        div=div,
        list_name=list_name,
        TRACKING_ID=TRACKING_ID,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("port", nargs=1, type=int)
    args = parser.parse_args()
    [port] = args.port

    app.config["DRY_RUN"] = args.dry_run
    app.run(port=port, debug=args.debug)

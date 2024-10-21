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
    analyze_following,
    analyze_timeline,
    div,
    dry_run_analysis,
    get_following_lists,
    get_mastodon_api,
    get_user_id_from_handle,
)

logging.basicConfig(filename='debug.log', level=logging.DEBUG)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logging.debug("Current Working Directory:", os.getcwd())

CLIENT_KEY = os.environ.get("CLIENT_KEY")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
INSTANCE = os.environ.get("INSTANCE")
TRACKING_ID = os.environ.get("TRACKING_ID")

if not (CLIENT_KEY and CLIENT_SECRET and INSTANCE):
    raise ValueError(
        "Must set CLIENT_KEY, CLIENT_SECRET and INSTANCE environment variables")

app = Flask("mastodon-gender-proportion")
app.config["SECRET_KEY"] = os.environ["COOKIE_SECRET"]
app.config["DRY_RUN"] = False
app.config["MASTODON_CLIENT_ID"] = CLIENT_KEY
app.config["MASTODON_CLIENT_SECRET"] = CLIENT_SECRET
app.config["MASTODON_INSTANCE"] = INSTANCE

oauth = OAuth(app)
oauth.register(
    name="mastodon",
    api_base_url="https://"+INSTANCE+"/api/v1",
    access_token_url="https://"+INSTANCE+"/oauth/token",
    authorize_url="https://"+INSTANCE+"/oauth/authorize",
    client_id=CLIENT_KEY,
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
    resp = oauth.mastodon.get(f"https://{INSTANCE}/api/v1/accounts/verify_credentials")
    print("Response status:", resp.status_code)
    print("Response text:", resp.text)

    try:
        profile = resp.json()
        print(profile)
    except ValueError as e:
        print("JSON decode error:", e)
        return "Failed to decode JSON response"
        
    print(token)
    session["mastodon_token"] = token["access_token"]
    session["mastodon_user"] = profile["acct"]
    instance="mastodon.social" # TODO: change
    try:
        session["lists"] = get_following_lists(
            profile["display_name"],
            CLIENT_KEY,
            CLIENT_SECRET,
            token["access_token"],
            instance,
        )
    except Exception:
        app.logger.exception("Error in get_friends_lists, ignoring")
        session["lists"] = []

    flash("You were signed in as %s" % profile["display_name"])
    return redirect("/")


class AnalyzeForm(Form):
    acct = StringField("Mastodon User")
    lst = SelectField("List")


@app.route("/", methods=["GET", "POST"])
def index():
    tok = session.get(
        "mastodon_token")
    form = AnalyzeForm(request.form)
    if session.get("lists"):
        form.lst.choices = [("none", "No list")] + [
            (str(list["id"]), list["name"]) for list in session["lists"]
        ]
    else:
        del form.lst

    results = {}
    list_name = list_id = error = None
    if request.method == "POST" and form.validate() and form.acct.data:
        # Don't show auth'ed user's lists in results for another user.
        if hasattr(form, "lst") and form.acct.data != session.get("mastodon_user"):
            del form.lst

        if app.config["DRY_RUN"]:
            list_name = None
            friends, followers, timeline = dry_run_analysis()
            results = {"friends": friends, "followers": followers, "timeline": timeline}
        else:
            if session.get("lists") and form.lst and form.lst.data != "none":
                list_id = int(form.lst.data)
                list_name = [
                    list["name"] 
                    for list in session["lists"] 
                    if int(list["id"]) == list_id
                ][0]

            try:
                api = get_mastodon_api(
                    tok, INSTANCE
                )
                cache = Cache()

                user_id = get_user_id_from_handle(api, form.acct.data)
                results = {
                    "friends": analyze_following(user_id, list_id, api, cache),
                    "followers": analyze_followers(user_id, api, cache),
                    "timeline": analyze_timeline(
                        user_id, list_id, api, cache
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

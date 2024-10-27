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
from mastodon import MastodonNotFoundError
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
    get_user_from_handle,
    parse_mastodon_handle,
)

logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

CLIENT_KEY = os.environ.get("CLIENT_KEY")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
INSTANCE = os.environ.get("INSTANCE")
TRACKING_ID = os.environ.get("TRACKING_ID")

if not (CLIENT_KEY and CLIENT_SECRET and INSTANCE):
    raise ValueError(
        "Must set CLIENT_KEY, CLIENT_SECRET and INSTANCE environment variables")

app = Flask("mastodon-gender-distribution")
app.config["SECRET_KEY"] = os.environ["COOKIE_SECRET"]
app.config["DRY_RUN"] = False
app.config["MASTODON_CLIENT_ID"] = CLIENT_KEY
app.config["MASTODON_CLIENT_SECRET"] = CLIENT_SECRET
app.config["MASTODON_INSTANCE"] = INSTANCE

oauth = OAuth(app)

@app.route("/login")
def login():
    instance = request.args.get('instance')
    oauth.register(
        name="mastodon",
        api_base_url="https://"+instance+"/api/v1",
        access_token_url="https://"+instance+"/oauth/token",
        authorize_url="https://"+instance+"/oauth/authorize",
        client_id=CLIENT_KEY,
        client_secret=CLIENT_SECRET,
        client_kwargs={
            "scope": "read",
        },
        fetch_token=lambda: session.get("token"),  # DON'T DO IT IN PRODUCTION
    )

    redirect_uri = url_for("oauth_authorized", instance=instance, _external=True)
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
    instance = request.args.get('instance')
    token = oauth.mastodon.authorize_access_token()
    resp = oauth.mastodon.get(f"https://{instance}/api/v1/accounts/verify_credentials")
    print("Response status:", resp.status_code)
    print("Response text:", resp.text)

    try:
        profile = resp.json()
        print(profile)
    except ValueError as e:
        print("JSON decode error:", e)
        return "Failed to decode JSON response"
        
    session["mastodon_token"] = token["access_token"]
    session["mastodon_user"] = profile["acct"]

    try:
        session["lists"] = get_following_lists(
            profile["id"],
            token["access_token"],
            instance,
        )
    except Exception:
        app.logger.exception("Error in get_following_lists, ignoring")
        session["lists"] = []

    flash("You were signed in as %s" % profile["display_name"])
    return redirect("/")

class LoginForm(Form):
    login_acct = StringField("Mastodon user handle")

class AnalyzeForm(Form):
    analyze_acct = StringField("Mastodon user handle")
    lst = SelectField("List")


@app.route("/", methods=["GET", "POST"])
def index():
    tok = session.get(
        "mastodon_token")

    form = LoginForm(request.form)
    
    if request.method == "POST":
        form_type = request.form.get("form_type")
        if form_type == "login":
            form = LoginForm(request.form)
            handle = form.login_acct.data
            username, instance = parse_mastodon_handle(handle)
            
            return render_template(
                "index.html",
                form=form,
                div=div,
                TRACKING_ID=TRACKING_ID,
            )
        elif form_type == "analyze":
            form = AnalyzeForm(request.form)

            if session.get("lists"):
                form.lst.choices = [("none", "No list")] + [
                    (str(list["id"]), list["name"]) for list in session["lists"]
                ]
            else:
                del form.lst

            different_user = form.analyze_acct.data != session.get("mastodon_user")

            results = {}
            list_name = list_id = error = None
    
            if form.validate() and form.analyze_acct.data:
            # Don't show auth'ed user's lists in results for another user.
                if hasattr(form, "lst") and different_user:
                    del form.lst

                if app.config["DRY_RUN"]:
                    list_name = None
                    following, followers, timeline = dry_run_analysis()
                    results = {"following": following, "followers": followers, "timeline": timeline}
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

                        user = get_user_from_handle(form.analyze_acct.data, api)

                        if different_user and user.indexable is False:
                            raise Exception(
                                f"User {form.analyze_acct.data} is not indexable.\n"
                                f"If the account is yours, you can change the setting on: "
                                f"Settings > Public profile > Privacy and reach > "
                                f"Include public posts in search results"
                            )

                        results = {
                            "following": analyze_following(user.id, list_id, api, cache),
                            "followers": analyze_followers(user.id, api, cache),
                            "timeline": analyze_timeline(
                                user.id, list_id, api, cache
                            ),
                        }
                        for key, value in results.items():
                            if not value:
                                raise Exception(
                                    f"Failed to fetch results "
                                    f"for user {form.analyze_acct.data}."
                                )
                    except Exception as exc:
                        import traceback

                        traceback.print_exc()
                        if isinstance(exc, MastodonNotFoundError):
                            error = f"Could not find user {form.analyze_acct.data}."
                        else:
                            error = exc

                    if error is not None:
                        error = str(error).replace("\n", "<br>")

            return render_template(
                "index.html",
                form=form,
                results=results,
                error=error,
                div=div,
                list_name=list_name,
                TRACKING_ID=TRACKING_ID,
            )
    return render_template(
        "index.html",
        form=form,
        div=div,
        TRACKING_ID=TRACKING_ID,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("port", nargs="?", type=int)
    args = parser.parse_args()

    if args.port is None:
        port = int(os.environ.get("PORT", 8000))
    else:
        port = args.port

    app.config["DRY_RUN"] = args.dry_run
    app.run(port=port, debug=args.debug)
